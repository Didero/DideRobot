# -*- coding: utf-8 -*-

import gc, json, os, random, re, time, zipfile
import traceback

import requests
from bs4 import BeautifulSoup
import gevent

from commands.CommandTemplate import CommandTemplate
import Constants
import GlobalStore
from util import IrcFormattingUtil
from util import FileUtil
from util import StringUtil
from util import WebUtil
from IrcMessage import IrcMessage
from CustomExceptions import CommandException, CommandInputException, WebRequestException
from StringWithSuffix import StringWithSuffix


class Command(CommandTemplate):
	triggers = ['mtg', 'mtgf', 'mtgb', 'magic', 'mtglink']
	helptext = "Looks up info on Magic: The Gathering cards. Provide a card name or regex to search for, or 'random' for a surprise. "
	helptext += "Use 'search' with key-value attribute pairs for more control, see https://mtgjson.com/structures/card/ for available attributes. "
	helptext += "'{commandPrefix}mtgf' adds the flavor text and sets to the output. '{commandPrefix}mtgb [setname]' opens a boosterpack. "
	helptext += "'{commandPrefix}mtglink' returns links to the card on Gatherer and ScryFall.com"
	scheduledFunctionTime = 172800.0  #Every other day, since it doesn't update too often
	callInThread = True  #If a call causes a card update, make sure that doesn't block the whole bot

	areCardfilesInUse = False
	dataFormatVersion = '4.5.1'
	FORCE_UPDATE_AFTER_SECONDS = 7776000 # 90 days in seconds

	def onLoad(self):
		GlobalStore.commandhandler.addCommandFunction(__file__, 'searchMagicTheGatheringCards', self.getFormattedResultFromSearchString)

	def executeScheduledFunction(self):
		if not self.areCardfilesInUse and self.shouldUpdate():
			try:
				self.updateCardFile()
			except Exception as e:
				self.logError("[MTG] A {} error occurred during scheduled update: {}".format(type(e), e))
			finally:
				self.areCardfilesInUse = False

	def execute(self, message):
		"""
		:type message: IrcMessage
		"""
		#Immediately check if there's any parameters, to prevent useless work
		if message.messagePartsLength == 0:
			return message.reply(self.getHelp(message))

		#If the card set is currently being updated, we probably shouldn't try loading it
		if self.areCardfilesInUse:
			message.reply("I'm currently updating my card datastore, sorry! If you try again in, oh, 10 seconds, I should be done. You'll be the first to look through the new cards!")
			return

		#Check if we have all the files we need
		if not self.doNeededFilesExist():
			message.reply("Whoops, I don't seem to have all the files I need. I'll update now, try again in like 25 seconds. Sorry!")
			self.resetScheduledFunctionGreenlet()
			self.updateCardFile(True)
			return

		searchType = message.messageParts[0].lower()

		#Check for update command before file existence, to prevent message that card file is missing after update, which doesn't make much sense
		if searchType == 'update' or searchType == 'forceupdate':
			if not message.bot.isUserAdmin(message.user, message.userNickname, message.userAddress):
				replytext = "Sorry, only admins can use my update function"
			elif not searchType == 'forceupdate' and not self.shouldUpdate():
				replytext = "I've already got all the latest card data, no update is needed"
			else:
				#Since we're checking now, set the automatic check to start counting from now on
				self.resetScheduledFunctionGreenlet()
				#Actually update
				replytext = self.updateCardFile()
			message.reply(replytext)
			return

		#Allow checking of card database version
		elif searchType == 'version':
			with open(os.path.join(GlobalStore.scriptfolder, 'data', 'MTGversion.json'), 'r', encoding='utf-8') as versionfile:
				versions = json.load(versionfile)
			message.reply("My card database is based on version {} from http://www.mtgjson.com".format(versions['dataVersion']))
			return

		#We can also search for definitions
		elif searchType == 'define':
			return message.replyWithLengthLimit(self.getDefinition(" ".join(message.messageParts[1:])))

		elif searchType == 'booster' or message.trigger == 'mtgb':
			if (searchType == 'booster' and message.messagePartsLength == 1) or (message.trigger == 'mtgb' and message.messagePartsLength == 0):
				message.reply("Please provide a set name, so I can open a boosterpack from that set. Or use 'random' to have me pick one")
				return
			setname = ' '.join(message.messageParts[1:]).lower() if searchType == 'booster' else message.message.lower()
			message.reply(self.openBoosterpack(setname))
			return

		#Default search
		else:
			#Check if a proper search type was provided
			if searchType in ('search', 'random', 'randomcommander'):
				searchString = " ".join(message.messageParts[1:])
			else:
				#Unknown searchtype, just assume the entire entered text is a name search
				searchType = 'search'
				searchString = message.message
			#Do the search
			searchDict, matchingCards = self.getMatchingCardsFromSearchString(searchType, searchString)
			#Show the results
			if len(matchingCards) == 0:
				#No matches
				replytext = "Sorry, I couldn't find any cards that match your search query"
			else:
				numberOfCardsToList = 20 if message.isPrivateMessage else 10
				shouldPickRandomCard = searchType.startswith('random')
				if message.trigger == 'mtglink':
					replytext = self.getLinksFromSearchString(searchDict, matchingCards, shouldPickRandomCard, numberOfCardsToList)
				else:
					#Normal search, format it
					replytext = self.formatSearchResult(matchingCards, message.trigger.endswith('f'), shouldPickRandomCard, numberOfCardsToList, searchDict.get('name', None), True)
			message.reply(replytext)

	def getFormattedResultFromSearchString(self, searchType, searchString, extendedInfo=False, resultListLength=10):
		if self.areCardfilesInUse:
			return "[Updating cardfiles]"
		searchDict, matchingCards = self.getMatchingCardsFromSearchString(searchType, searchString)
		#Search was successful, second parameter is the parsed search dictionary, third is the matching cards. Return a formatted result
		return self.formatSearchResult(matchingCards, extendedInfo, searchType.startswith('random'), resultListLength, searchDict.get('name', None), True)

	def getMatchingCardsFromSearchString(self, searchType, searchString):
		#Special case to prevent it having to load in all the cards before picking one
		if searchType == 'random' and not searchString:
			#Just pick a random card from all available ones
			with open(os.path.join(GlobalStore.scriptfolder, 'data', 'MTGversion.json'), 'r', encoding='utf-8') as versionfile:
				linecount = json.load(versionfile)['cardCount']
			if linecount <= 0:
				raise CommandException("I don't seem to know how many cards I have, that's weird... Tell my owner(s), they should help me with updating")
			randomLineNumber = random.randint(1, linecount) - 1 # minus 1 because getLineFromFile() starts at 0
			card = json.loads(FileUtil.getLineFromFile(os.path.join(GlobalStore.scriptfolder, 'data', 'MTGcards.json'), randomLineNumber))
			cardname, carddata = card.popitem()
			return ({}, {cardname: (randomLineNumber, None)})

		#Make sure the search string is an actual string, and not None or something
		if searchString is None:
			searchString = ""

		#Check if the user passed valid search terms
		searchDict = self.parseSearchParameters(searchType, searchString)
		#Check if the entered search terms can be converted to the regex we need
		regexDict = self.searchDictToRegexDict(searchDict)
		#Search for cards matching the regex dict
		matchingCards = self.searchCardStore(regexDict)
		#Clear the stored regexes, since we don't need them anymore
		del regexDict
		re.purge()
		#Done, return the search dictionary (possibly needed for further parsing), and the matching cards
		return (searchDict, matchingCards)

	@staticmethod
	def parseSearchParameters(searchType, searchString):
		searchDict = {}
		if searchType == 'search' and not searchString:
			raise CommandInputException("Error: 'search' parameter requires a search query too")
		#Check if there is an actual search (with colon as key-value separator)
		elif ':' in searchString:
			#Advanced search! Turn the search string into a usable dictionary
			searchDict = StringUtil.stringToDict(searchString.lower(), True)
			if len(searchDict) == 0:
				raise CommandInputException("That is not a valid search query. It should be entered like JSON, so 'name: ooze, type: creature,...'. "
							  "For a list of valid keys, see https://mtgjson.com/data-models/card/ (though not all keys may be available)")
		#Not a special search, just set the whole message as a 'name' search, since that's the most common search
		elif searchString:
			searchDict['name'] = searchString.lower()

		#Commander search. Regardless of everything else, it has to be a legendary creature
		if searchType == 'randomcommander':
			#Don't just search for 'legendary creature.*', because there are legendary artifact creatures too
			searchDict['type'] = 'legendary.+creature.*' + searchDict.get('type', '')

		#Correct some values, to make searching easier (so a search for 'set' or 'sets' both work)
		searchTermsToCorrect = {'set': ('sets', 'setname'), 'colors': ('color', 'colour', 'colours'), 'type': ('types', 'supertypes', 'subtypes'), 'flavor': ('flavour', 'flavortext', 'flavourtext'), 'cmc': ('convertedmanacost', 'manacost', 'manavalue')}
		for correctTerm, listOfWrongterms in searchTermsToCorrect.items():
			for wrongTerm in listOfWrongterms:
				if wrongTerm in searchDict:
					if correctTerm not in searchDict:
						searchDict[correctTerm] = searchDict[wrongTerm]
					searchDict.pop(wrongTerm)
		return searchDict

	def searchDictToRegexDict(self, searchDict):
		#Turn the search strings into actual regexes
		regexDict = {}
		errors = []
		for attrib, query in searchDict.items():
			try:
				regex = re.compile(query, re.IGNORECASE)
			except (re.error, SyntaxError):
				#Try parsing the string again as an escaped string, so mismatched brackets for instance aren't a problem
				try:
					regex = re.compile(re.escape(query), re.IGNORECASE)
				except re.error as e:
					self.logDebug("[MTG] Regex error when trying to parse '{}': {}".format(query, e))
					errors.append(attrib)
				else:
					regexDict[attrib] = regex
			else:
				regexDict[attrib] = regex
		#If there were errors parsing the regular expressions, don't continue, to prevent errors further down
		if len(errors) > 0:
			#If there was only one search element to begin with, there's no need to specify
			if len(searchDict) == 1:
				replytext = "An error occurred when trying to parse your search query. Please check if it is a valid regular expression, and that there are no non-UTF8 characters"
			#If there were more elements but only one error, specify
			elif len(errors) == 1:
				replytext = "An error occurred while trying to parse the query for the '{}' field. Please check if it is a valid regular expression without non-UTF8 characters".format(errors[0])
			#Multiple errors, list them all
			else:
				replytext = "Errors occurred while parsing attributes: {}. Please check your search query for errors".format(", ".join(errors))
			raise CommandInputException(replytext)
		return regexDict

	@staticmethod
	def searchCardStore(regexDict):
		#Get the 'setname' search separately, so we can iterate over the rest later
		setRegex = regexDict.pop('set', None)
		setKeys = ('artist', 'flavor', 'multiverseid', 'number', 'rarity', 'watermark')

		# A dict with cardname as key, and a list as value
		#  First item in the list is line number of the card in the cardfile, last item is the matching setname (if any)
		matchingCards = {}
		with open(os.path.join(GlobalStore.scriptfolder, 'data', 'MTGcards.json'), 'r', encoding='utf-8') as jsonfile:
			for cardlineNumber, cardline in enumerate(jsonfile):
				# Don't hog the CPU
				if cardlineNumber % 500 == 0:
					gevent.idle()

				cardname, carddata = json.loads(cardline).popitem()

				#Store how much sets we started with, so we know at the end if any sets got removed
				setCountAtStart = len(carddata[1])

				#First check if we need to see if the set name matches
				if setRegex:
					for setname in list(carddata[1].keys()):
						#If the setname didn't match, remove it from the set list
						if not setRegex.search(setname):
							del carddata[1][setname]
					if len(carddata[1]) == 0:
						#No set name matched, skip this card
						continue

				#Then check if the rest of the attributes match
				for attrib in regexDict:
					#Some data is stored in the card data, some in the set data, because it differs per set (rarity etc)
					if attrib in setKeys:
						for setname in list(carddata[1].keys()):
							#If this attribute doesn't fit the search criteria, remove this set
							if attrib not in carddata[1] or not regexDict[attrib].search(carddata[1][setname][attrib]):
								del carddata[1][setname]
						#No matching sets left, skip this card
						if len(carddata[1]) == 0:
							break
					#Most data is stored as general card data
					else:
						if attrib not in carddata[0] or not regexDict[attrib].search(carddata[0][attrib]):
							#If the wanted attribute is either not in the card, or it doesn't match, move on to the next card
							break
				else:
					#If we didn't break from the loop, then the card matched all search criteria. Store it
					# If all sets matched, don't store that. Otherwise, store a list of the sets that did match
					setNameMatches = None if len(carddata[1]) == setCountAtStart else list(carddata[1].keys())
					# Use the formatted name so displaying them is easier later
					matchingCards[carddata[0]['name']] = (cardlineNumber, setNameMatches)
		return matchingCards

	def formatSearchResult(self, cardstore, addExtendedCardInfo, pickRandomCard, maxCardsToList=10, nameToMatch=None, addResultCount=True):
		numberOfCardsFound = len(cardstore)

		if numberOfCardsFound == 0:
			return "Sorry, no card matching your query was found"

		if pickRandomCard:
			cardname = random.choice(list(cardstore.keys()))
			cardstore = {cardname: cardstore[cardname]}
		#If the name we have to match is in there literally, lift it out
		# (For instance, a search for 'Mirror Entity' returns 'Mirror Entity' and 'Mirror Entity Avatar'.
		# Show the full info on 'Mirror Entity' but also report we found more matches)
		elif nameToMatch:
			nameToMatch = nameToMatch.lower()
			for cardname, cardtuple in cardstore.items():
				if cardname.lower() == nameToMatch:
					cardstore = {cardname: cardtuple}
					break

		#If there's only one card found, just display it
		# Use 'len()' instead of 'numberOfCardsFound' because 'pickRandomCard' or 'nameToMatch' could've changed it,
		# and we need the cardcount var to show how many cards we found at the end
		if len(cardstore) == 1:
			#Retrieve the full info on the card we found
			linenumber, setname = next(iter(cardstore.values()))
			cardname, carddata = json.loads(FileUtil.getLineFromFile(os.path.join("data", "MTGcards.json"), linenumber)).popitem()
			replytext = self.getFormattedCardInfo(carddata, addExtendedCardInfo, setname)
			#We may have culled the cardstore list, so there may have been more matches initially. List a count of those
			if addResultCount and numberOfCardsFound > 1:
				replytext += " ({:,} more found)".format(numberOfCardsFound - 1)
			return replytext

		#Check if we didn't find more matches than we're allowed to show
		cardnames = list(cardstore.keys())
		if numberOfCardsFound > maxCardsToList:
			cardnames = random.sample(cardnames, maxCardsToList)
		#Show them alphabetically
		cardnames = sorted(cardnames)

		replytext = "Your search returned {:,} cards: {}".format(numberOfCardsFound, "; ".join(cardnames))
		if numberOfCardsFound > maxCardsToList:
			replytext += " and {:,} more".format(numberOfCardsFound - maxCardsToList)
		return replytext

	@staticmethod
	def getFormattedCardInfo(carddata, addExtendedInfo=False, setname=None, startingLength=0):
		card = carddata[0]
		sets = carddata[1]
		cardInfoList = [IrcFormattingUtil.makeTextBold(card['name'])]
		if 'type' in card and len(card['type']) > 0:
			cardInfoList.append(card['type'])
		if 'manacost' in card:
			manacost = card['manacost']
			#Only add the cumulative mana cost if it's different from the total cost (No need to say '3 mana, 3 total')
			if 'cmc' in card and card['cmc'] != card['manacost']:
				manacost += ", CMC " + card['cmc']
			#If no cmc is shown, specify the number is the manacost
			else:
				manacost += " mana"
			cardInfoList.append(manacost)
		if 'power' in card and 'toughness' in card:
			cardInfoList.append(card['power'] + "/" + card['toughness'] + " P/T")
		if 'loyalty' in card:
			cardInfoList.append(card['loyalty'] + " loyalty")
		if 'hand' in card or 'life' in card:
			handLife = ""
			if 'hand' in card:
				handLife = card['hand'] + " handmod"
			if 'hand' in card and 'life' in card:
				handLife += ", "
			if 'life' in card:
				handLife += card['life'] + " lifemod"
			cardInfoList.append(handLife)
		if 'layout' in card:
			cardInfoList.append(card['layout'])
			if 'otherfaces' in card:
				cardInfoList[-1] += ", with " + card['otherfaces']
		#All cards have a 'text' key set (for search reasons), it's just empty on ones that didn't have one
		if len(card['text']) > 0:
			cardInfoList.append(card['text'])
		if addExtendedInfo:
			#'setname' can either be a string of the setname, or a list of matching setnames
			# Since we need it as a string later, make sure it is one
			if setname and isinstance(setname, (list, tuple)):
				setname = random.choice(setname)
			#If it's an invalid setname, pick a random one that is valid
			if not setname or setname not in sets:
				setname = random.choice(list(sets.keys()))
			if 'flavor' in sets[setname]:
				#Make the flavor text gray to indicate it's not too important.
				#  '\x03' is colour code character, '14' is gray, '\x0f' is decoration end character
				cardInfoList.append('\x0314' + sets[setname]['flavor'] + '\x0f')
			maxSetsToDisplay = 4
			setcount = len(sets)
			setlist = list(sets.keys())
			if setcount > maxSetsToDisplay:
				setlist = random.sample(setlist, maxSetsToDisplay)
			setlistString = "in "
			for setname in setlist:
				#Make the display 'setname (first letter of rarity)', so 'Magic 2015 (R)'
				rarity = sets[setname]['rarity']
				if rarity == "Basic Land":
					rarity = 'L'
				else:
					rarity = rarity[0].upper()
				setlistString += "{} ({}); ".format(setname, rarity)
			setlistString = setlistString[:-2]  #Remove the last '; '
			if setcount > maxSetsToDisplay:
				setlistString += "; {:,} more".format(setcount - maxSetsToDisplay)
			cardInfoList.append(setlistString)
		#No extra set info, but still add a warning if it's in a non-legal set
		else:
			for illegalSet in ('Happy Holidays', 'Unglued', 'Unhinged', 'Unstable'):
				if illegalSet in sets:
					cardInfoList.append("in illegal set \x0304{illegalSet}\x0f!".format(illegalSet=illegalSet))  #color-code the setname red
					break

		#FILL THAT SHIT IN (encoded properly)
		separatorLength = len(Constants.GREY_SEPARATOR)
		#Keep adding parts to the output until an entire block wouldn't fit on one line, then start a new message
		replytext = ''
		messageLength = startingLength

		while len(cardInfoList) > 0:
			cardInfoPart = cardInfoList.pop(0)
			partLength = len(cardInfoPart)
			if messageLength + partLength < Constants.MAX_MESSAGE_LENGTH:
				replytext += cardInfoPart
				messageLength += partLength
				#Separator!
				if messageLength + separatorLength > Constants.MAX_MESSAGE_LENGTH:
					#If the separator wouldn't fit anymore, start a new message
					replytext += '\n'
					messageLength = 0
				#Add a separator
				replytext += Constants.GREY_SEPARATOR
				messageLength += separatorLength
			else:
				#If we would exceed max message length, cut off at the highest space and continue in a new message
				#  If the message started with a special character (bold for name, grey for flavour), copy those
				prefix = ''
				#bold
				if cardInfoPart.startswith(IrcFormattingUtil.BOLD):
					prefix = IrcFormattingUtil.BOLD
				#color
				elif cardInfoPart.startswith(IrcFormattingUtil.COLOUR):
					#Also copy colour code
					prefix = cardInfoPart[:3]
				#Get the spot in the text where the cut-off would be (How much of the part text fits in the open space)
				splitIndex = Constants.MAX_MESSAGE_LENGTH - messageLength
				#Then get the last space before that index, so we don't split mid-word (if possible)
				if ' ' in cardInfoPart[:splitIndex]:
					splitIndex = cardInfoPart.rindex(' ', 0, splitIndex)
				#If we can't find a space, add a dash to indicate the word continues in the new message
				elif splitIndex > 0:
					cardInfoPart = cardInfoPart[:splitIndex-1] + '-' + cardInfoPart[splitIndex-1:]
				#Add the second section back to the list, so it can be properly added, even if it would still be too long
				cardInfoList.insert(0, prefix + cardInfoPart[splitIndex:])
				#Then add the first part to the message
				replytext += cardInfoPart[:splitIndex] + '\n'
				messageLength = 0

		#Remove the separator at the end, if there is one
		if replytext.endswith(Constants.GREY_SEPARATOR):
			replytext = replytext[:-separatorLength].rstrip()
		return replytext

	def getLinksFromSearchString(self, searchDict, matchingCards, pickRandomCard, numberOfCardsToListOnLargeResult):
			# Reply with links to further information about the found card
			matchingCardname = None
			if pickRandomCard:
				matchingCardname = random.choice(list(matchingCards.keys()))
			elif len(matchingCards) == 1:
				matchingCardname = next(iter(matchingCards.keys()))
			#Check if the searched name is a literal match with one of found cards. If so, pick that one
			elif 'name' in searchDict:
				if searchDict['name'] in matchingCards:
					matchingCardname = searchDict['name']
				else:
					#Compare each name
					cardNameToMatch = searchDict['name'].lower()
					for cardname, carddata in matchingCards.items():
						if cardname.lower() == cardNameToMatch:
							matchingCardname = cardname
							break
			if not matchingCardname:
				# No results or too many, reuse the normal way of listing cards
				return self.formatSearchResult(matchingCards, False, False, numberOfCardsToListOnLargeResult, None, True)
			#Retrieve card data
			lineNumber, listOfSetNamesToMatch = matchingCards[matchingCardname]
			matchingCardname, carddata = json.loads(FileUtil.getLineFromFile(os.path.join("data", "MTGcards.json"), lineNumber)).popitem()
			#We need to pick a set to link to. Pick the first set that has both a multiverse id and a number, so we can show as many links as possible. If that's not possible, pick a random one
			setNamesToCheck = listOfSetNamesToMatch if listOfSetNamesToMatch else list(carddata[1].keys())
			for setName in setNamesToCheck:
				if 'multiverseid' in carddata[1][setName] and 'number' in carddata[1][setName]:
					setNameToMatch = setName
					break
			else:
				# No set has a number and multiverseid, pick a random set
				setNameToMatch = random.choice(setNamesToCheck)
			setSpecificCardData = carddata[1][setNameToMatch]
			#Retrieve set info, since we need the setcode
			with open(os.path.join(GlobalStore.scriptfolder, "data", "MTGsets.json"), 'r', encoding='utf-8') as setfile:
				setcode = json.load(setfile)[setNameToMatch.lower()]['code']
			#Not all cards have a multiverse id (mostly special editions of cards) or a card number (mostly old cards)
			# Check if the required fields exist
			linkString = ""
			if 'multiverseid' in setSpecificCardData:
				linkString += "http://gatherer.wizards.com/Pages/Card/Details.aspx?multiverseid=" + setSpecificCardData['multiverseid']
			if 'multiverseid' in setSpecificCardData and 'number' in setSpecificCardData:
				linkString += Constants.GREY_SEPARATOR
			if 'number' in setSpecificCardData:
				linkString += "https://scryfall.com/card/{}/{}" .format(setcode.lower(), setSpecificCardData['number'])
			displayCardname = IrcFormattingUtil.makeTextBold(carddata[0]['name'])
			if not linkString:
				return "I'm sorry, I don't have enough data on {} to construct links. Must be a pretty rare card!".format(displayCardname)
			return "{}: {}".format(displayCardname, linkString)

	@staticmethod
	def getDefinition(searchterm):
		"""
		Searches for the definition of the provided MtG-related term. Supports regular expressions as the search term
		:param searchterm The term to find the definition of. Can be a partial match or a regular expression
		:return The matching term followed by the definition of that term
		"""
		definitionsFilename = os.path.join(GlobalStore.scriptfolder, 'data', 'MTGdefinitions.json')
		possibleDefinitions = {}  #Keys are the matching terms found, values are the line they're found at for easy lookup

		if searchterm == 'random':
			randomLineNumber = random.randrange(0, FileUtil.getLineCount(definitionsFilename))
			term = json.loads(FileUtil.getLineFromFile(definitionsFilename, randomLineNumber)).popitem()[0]
			possibleDefinitions = {term: randomLineNumber}
		else:
			try:
				searchRegex = re.compile(searchterm)
			except re.error:
				return "That is not valid regex. Please check for typos, and try again"

			with open(definitionsFilename, 'r', encoding='utf-8') as definitionsFile:
				for linecount, line in enumerate(definitionsFile):
					term, definition = json.loads(line).popitem()
					if re.search(searchRegex, term):
						possibleDefinitions[term] = linecount
				if len(possibleDefinitions) == 0:
					#If nothing was found, search again, but this time check the definitions themselves
					definitionsFile.seek(0)
					for linecount, line in enumerate(definitionsFile):
						term, definition = json.loads(line).popitem()
						if re.search(searchRegex, definition):
							possibleDefinitions[term] = linecount

		replytext = None
		suffix = None
		possibleDefinitionsCount = len(possibleDefinitions)
		if possibleDefinitionsCount == 0:
			replytext = "Sorry, I don't have any info on that term. If you think it's important, poke my owner(s), maybe they'll add it!"
		elif possibleDefinitionsCount == 1:
			#Found one definition, return that
			term, linenumber = possibleDefinitions.popitem()
			definition = json.loads(FileUtil.getLineFromFile(definitionsFilename, linenumber)).popitem()[1]
			replytext = "{}: {}".format(IrcFormattingUtil.makeTextBold(term), definition)
		#Multiple matching definitions found
		else:
			if searchterm in possibleDefinitions:
				#Multiple matches, but one of them is the literal search term. Return that, and how many other matches we found
				definition = json.loads(FileUtil.getLineFromFile(definitionsFilename, possibleDefinitions[searchterm])).popitem()[1]
				replytext = "{}: {}".format(IrcFormattingUtil.makeTextBold(searchterm), definition)
				suffix = " ({:,} more matches)".format(possibleDefinitionsCount-1)
			else:
				replytext = "Your search returned {:,} results, please be more specific".format(possibleDefinitionsCount)
				if possibleDefinitionsCount < 10:
					replytext += ": {}".format("; ".join(sorted(possibleDefinitions.keys())))
		return StringWithSuffix(replytext, suffix)


	@staticmethod
	def openBoosterpack(askedSetname):
		askedSetname = askedSetname.lower()
		properSetname = ''
		#First check if the message is a valid setname
		with open(os.path.join(GlobalStore.scriptfolder, 'data', 'MTGsets.json'), 'r', encoding='utf-8') as setsfile:
			setdata = json.load(setsfile)
		if not setdata:
			raise CommandException("That's weird, I should have set data, but this file is just... empty. Tell my owner(s), something's probably broken, maybe they can fix it")

		if askedSetname == 'random':
			properSetname = random.choice(setdata['_setsWithBoosterpacks'])
		elif askedSetname in setdata:
			properSetname = askedSetname
		#If we haven't found a name match, check if we can find a set code match
		elif len(askedSetname) == 3:
			askedSetcode = askedSetname.upper()  #Setcodes are all upper case, adjust for that
			for setname in setdata:
				#Skip the list with the sets that have boosterpacks
				if setname == '_setsWithBoosterpacks':
					continue
				if askedSetcode == setdata[setname].get('code') or askedSetcode == setdata[setname].get('mtgocode'):
					properSetname = setname
					#Since setcodes are unique, no need to keep looking
					break

		if properSetname == '':
			#Setname not found literally. Try and find the closest match
			try:
				askedSetnameRegex = re.compile(askedSetname, re.IGNORECASE)
			except re.error:
				askedSetnameRegex = re.compile(re.escape(askedSetname), re.IGNORECASE)
			for setname in setdata:
				#Skip the list of the sets that have boosterpacks
				if setname == '_setsWithBoosterpacks':
					continue
				if askedSetnameRegex.search(setname):
					#Match found! If we hadn't found a match previously, store this name
					if properSetname == '':
						properSetname = setname
					#If we previously found a set and the current set doesn't have a booster, don't claim we found two sets
					elif 'booster' not in setdata[setname]:
						continue
					#If the previously found set doesn't have a booster but this one does, store the current set as the found one
					elif 'booster' not in setdata[properSetname]:
						properSetname = setname
					#Both matching sets we found contain boosters. Inform the user of the conflict
					else:
						#A match has been found previously. We can't make a boosterpack from two sets, so show an error
						raise CommandInputException("That setname matches at least two sets, '{}' and '{}'. I can't make a boosterpack from more than one set. "
									   "Please be a bit more specific".format(setname, properSetname))

		#If we still haven't found anything, give up
		if properSetname == '':
			raise CommandInputException("I'm sorry, I don't know the set '{}'. Did you make a typo?".format(askedSetname))
		#Some sets don't have booster packs, check for that too
		if 'booster' not in setdata[properSetname]:
			raise CommandInputException("The set '{}' doesn't have booster packs, according to my data. Sorry".format(properSetname))
		boosterData = setdata[properSetname]['booster']

		#Name exists, get the proper spelling, since in other places setnames aren't lower-case
		properSetname = setdata[properSetname]['name']

		#First pick which sheet division we should use
		totalBoosterWeight = boosterData['boostersTotalWeight']
		pickedWeight = random.randint(1, totalBoosterWeight)
		for sheetContents in boosterData['boosters']:
			if sheetContents['weight'] < pickedWeight:
				#Skip this sheet
				pickedWeight -= sheetContents['weight']
			else:
				#Use this sheet
				break

		#Pick cards according to the sheet
		boosterResult = {}
		for sheetName, cardCount in sheetContents['contents'].items():
			#The sheet's card selection is either a list, or a dict with cardnames as keys and their weight as values
			sheet = boosterData['sheets'][sheetName]
			if isinstance(sheet, list):
				boosterResult[sheetName] = random.sample(sheet, cardCount)
			else:
				#Weighted dict, use the same approach as in picking the sheet:
				# Picking a random number from total weight, iterating through entries, and lowering picked weight unti it matches the current card weight
				boosterResult[sheetName] = []
				for i in range(cardCount):
					pickedWeight = random.randint(1, sheet['totalWeight'])
					for cardName, cardWeight in sheet['cards'].items():
						if cardWeight < pickedWeight:
							#Card doesn't match the wanted weight. Skip this card and lower the weight we want to find
							pickedWeight -= cardWeight
						else:
							#This is the card we randomly weighted-picked, store it
							boosterResult[sheetName].append(cardName)
							#Remove this card from the list so it can't get picked twice
							del sheet['cards'][cardName]
							#Also lower the total weight so it still matches
							sheet['totalWeight'] -= cardWeight
							break

		#Format the result
		replytext = properSetname + Constants.GREY_SEPARATOR
		for category, cardlist in boosterResult.items():
			replytext += "{}: {}. ".format(IrcFormattingUtil.makeTextBold(category.capitalize()), "; ".join(cardlist))
		return replytext

	def downloadCardDataset(self):
		url = "https://mtgjson.com/api/v5/AllSetFiles.zip"
		cardzipFilename = os.path.join(GlobalStore.scriptfolder, 'data', 'AllSetFiles.zip')
		try:
			filepath = WebUtil.downloadFile(url, cardzipFilename)
		except WebRequestException as wre:
			self.logError("[MTG] An error occurred while trying to download the card file: " + wre)
			raise CommandException("Error while downloading the MtG card data")
		return filepath

	def getLatestVersionNumber(self):
		versionRequest = None
		try:
			versionRequest = requests.get("https://mtgjson.com/api/v5/Meta.json", timeout=10.0)
			latestVersionData = versionRequest.json()['data']
		except requests.exceptions.Timeout:
			self.logError("[MTG] Fetching card version timed out")
			raise CommandException("Fetching online card version took too long")
		except ValueError:
			self.logError("[MTG] Unable to parse downloaded version file, returned text is: " + versionRequest.text if versionRequest else "[not a request]")
			raise CommandException("Unable to parse downloaded version file")
		if 'version' not in latestVersionData:
			self.logError("'version' field does not exist in downloaded version file, data is" + json.dumps(latestVersionData))
			raise CommandException("Missing 'version' field in version file")
		versionNumber = latestVersionData['version']
		# The version string is constructed like 'major.minor.patch+priceUpdateDate'. We don't need the last part, so strip it off
		if '+' in versionNumber:
			versionNumber = versionNumber.split('+', 1)[0]
		return versionNumber

	@staticmethod
	def doNeededFilesExist():
		for fn in ('cards', 'definitions', 'sets', 'version'):
			filename = os.path.join(GlobalStore.scriptfolder, 'data', 'MTG{}.json'.format(fn))
			if not os.path.isfile(filename):
				return False
			#Check if it isn't an empty file
			if os.path.getsize(filename) == 0:
				return False
		return True

	def shouldUpdate(self):
		basepath = os.path.join(GlobalStore.scriptfolder, 'data')
		#If one of the required files doesn't exist, we should update
		if not self.doNeededFilesExist():
			return True
		with open(os.path.join(basepath, 'MTGversion.json'), 'r', encoding='utf-8') as versionfile:
			versiondata = json.load(versionfile)
		#We should fix the files if the version file is missing keys we need
		for requiredKey in ('formatVersion', 'dataVersion', 'lastUpdateTime'):
			if requiredKey not in versiondata:
				return True
		#We should update if the latest formatting version differs from the stored one
		if versiondata['formatVersion'] != self.dataFormatVersion:
			return True
		secondsSinceLastUpdate = time.time() - versiondata['lastUpdateTime']
		#If the last update check has been recent, don't update (with some leniency to prevent edge cases)
		if secondsSinceLastUpdate < self.scheduledFunctionTime - 5.0:
			return False
		# Since the MtGJSON dataset also sometimes updates without increasing the version number, force an update if none has been downloaded for a while
		elif secondsSinceLastUpdate > self.FORCE_UPDATE_AFTER_SECONDS:
			return True
		#Get the latest online version to see if we're behind
		return self.getLatestVersionNumber() != versiondata['dataVersion']

	def updateCardFile(self, shouldUpdateDefinitions=True):
		starttime = time.time()
		cardStoreFilename = os.path.join(GlobalStore.scriptfolder, 'data', 'MTGcards.json')
		cardStoreTempFilename = cardStoreFilename + ".tmp"
		gamewideCardStoreFilename = os.path.join(GlobalStore.scriptfolder, 'data', 'MTGcards_gamewide.json')
		setStoreFilename = os.path.join(GlobalStore.scriptfolder, 'data', 'MTGsets.json')
		definitionsFilename = os.path.join(GlobalStore.scriptfolder, 'data', 'MTGdefinitions.json')
		definitionsTempFilename = definitionsFilename + ".tmp"

		#Download the wrongly-formatted (for our purposes) card data
		cardDatasetFilename = self.downloadCardDataset()

		#Inform everything that we're going to be changing the card files
		self.areCardfilesInUse = True
		self.logInfo("[MtG] Updating card database!")

		#Set up the dicts we're going to store our data in
		newcardstore = {}
		setstore = {'_setsWithBoosterpacks': []}
		#Since definitions from cards get written to file immediately, just keep a list of which keywords we already stored
		definitions = []
		#Lists of what to do with certain set keys
		setKeysToKeep = ('block', 'booster', 'cards', 'code', 'mtgoCode', 'name', 'releaseDate', 'type')
		raritiesToRemove = ('checklist', 'double faced', 'draft-matters', 'foil', 'full art print', 'marketing', 'power nine', 'timeshifted purple', 'token', 'Steamflogger Boss')
		raritiesToRename = {'land': 'basic land', 'urza land': 'land — urza’s', 'mythic rare': 'mythic'}  #Non-standard rarities are interpreted as regexes for type
		rarityPrefixesToRemove = {'double faced ': 13, 'foil ': 5, 'timeshifted ': 12}  #The numbers are the string length, saves a lot of 'len()' calls. Removing 'double faced' makes the result less accurate but it's far easier this way
		#Lists of what to do with certain card keys
		setSpecificCardKeys = ('artist', 'flavor', 'multiverseid', 'number', 'rarity', 'watermark')
		cardKeysToKeep = ('colors', 'layout', 'loyalty', 'manaCost', 'manaValue', 'name', 'names', 'othercards', 'power', 'text', 'toughness', 'type')
		setSpecificCardKeysToRename = {'flavorText': 'flavor', 'multiverseId': 'multiverseid'}
		cardKeysToRename = {'manaCost': 'manacost', 'manaValue': 'cmc'}
		keysToFormatNicer = ('manacost', 'text')  #'flavor' also needs to be formatted nicer, but that's done separately since it's a set-specific key, in contrast with the others listed here
		#Some number fields can be 'null' if they're 'X' on the card, so their value depends on some card text or mana spent. Change that to 'X' in our dataset
		nullFieldsToX = ('loyalty',)
		layoutTypesToRemove = ('normal', 'phenomenon', 'plane', 'scheme', 'vanguard')
		listKeysToMakeString = ('colors', 'names')
		#Some values are stored inside a sub-dict. Move them out of there. In the following dict, the key is the sub-dict key, and the values are the sub-dict values to move up a layer
		nestedValuesToKeep = {'identifiers': 'multiverseId'}

		# This function will be called on the 'keysToFormatNicer' keys
		#  Made into a function, because it's used in two places
		def formatNicer(text):
			#Remove brackets around mana cost
			if '{' in text:
				text = text.replace('}{', ' ').replace('{', '').replace('}', '')
			#Replace newlines with spaces. If the sentence ends in a letter, add a period
			text = re.sub(r'(?<=\w)\n+', '. ', text)
			text = StringUtil.removeNewlines(text)
			#Prevent double spaces
			text = re.sub(r' {2,}', ' ', text).strip()
			return text

		#Write each keyword we find to the definitions file so we don't have to keep it in memory
		definitionsFile = None
		if shouldUpdateDefinitions:
			definitionsFile = open(definitionsTempFilename, 'w', encoding='utf-8')

		#Go through each file in the sets zip (Saves memory compared to downloading the single file with all the sets)
		# Write gamewide (so not set-specific) data to a temporary file (Like card text, CMC). This way we don't have to keep that in memory during the entire loop
		# Keys will be lower()'ed cardnames, values will be a dict of the card's fields that are not variable between the sets the card is in
		with zipfile.ZipFile(cardDatasetFilename, 'r') as setfilesZip, open(gamewideCardStoreFilename, 'w', encoding='utf-8') as gamewideCardStoreFile:
			#First check if the zip file contains enough info
			if not setfilesZip.namelist():
				self.logError("[MTG] Downloaded card data file is empty")
			#Go through each file in the sets zip
			for setfilename in setfilesZip.namelist():
				# Set JSON has a 'meta' key with version and date, and a 'data' key with the actual data
				# Keep numbers as strings, saves on converting them back later
				setData = json.loads(setfilesZip.read(setfilename), parse_int=lambda x: x, parse_float=lambda x: x)['data']
				#Clean up the set data a bit
				for setKey in list(setData.keys()):
					if setKey not in setKeysToKeep:
						del setData[setKey]
				if 'mtgoCode' in setData:
					if setData['mtgoCode'] is None:
						del setData['mtgoCode']
					else:
						setData['mtgocode'] = setData.pop('mtgoCode')
				setstore[setData['name'].lower()] = setData

				#Pop off cards when we need them, to save on memory
				cardlist = setData.pop('cards')
				uuidToCardName = {}
				for cardcount in range(0, len(cardlist)):
					card = cardlist.pop()

					# Handle split or double-faced cards. The 'name is the current side, then ' // ' and then the other card name
					# Turn that into the name being just this card and a 'names' array with the other card(s)
					# We need to do this before anything else because it can change the card name, which we use as the unique key
					if 'faceName' in card or ' // ' in card['name']:
						card['othercards'] = card['name'].split(' // ')
						card['name'] = card.get('faceName', card['othercards'][0])
						card['othercards'].remove(card['name'])
						#Turn it into a string for easy display later
						card['othercards'] = "; ".join(card['othercards'])

					cardname = card['name'].lower()  #lowering the keys makes searching easier later, especially when comparing against the literal searchstring

					#For the set booster, we need to be able to match uuids to card names
					uuidToCardName[card['uuid']] = card['name']

					#Move wanted values out of sub-dictionaries
					for nameOfSubDict, subDictKeyToKeep in nestedValuesToKeep.items():
						if nameOfSubDict in card:
							subDict = card.pop(nameOfSubDict)
							if subDictKeyToKeep in subDict:
								card[subDictKeyToKeep] = subDict[subDictKeyToKeep]

					for setSpecificCardKeyToRename, newKeyName in setSpecificCardKeysToRename.items():
						if setSpecificCardKeyToRename in card:
							card[newKeyName] = card.pop(setSpecificCardKeyToRename)
					#Make flavor text read better
					if 'flavor' in card:
						card['flavor'] = formatNicer(card['flavor'])
					#New and already listed cards need their set info stored
					#TODO: Some sets have multiple cards with the same name but a different artist (f.i. land cards). Handle that
					setSpecificCardData = {}
					for setSpecificKey in setSpecificCardKeys:
						if setSpecificKey in card:
							setSpecificCardData[setSpecificKey] = card.pop(setSpecificKey)

					#If the card isn't in the store yet, parse its data
					if cardname not in newcardstore:
						#Remove data we don't use, to save some space, memory and time
						for key in list(card.keys()):
							if key not in cardKeysToKeep:
								del card[key]

						#No need to store there's nothing special about the card's layout or if the special-ness is already evident from the text
						if card['layout'] in layoutTypesToRemove:
							del card['layout']
						#For display purposes, capitalise the first letter of the layout
						else:
							card['layout'] = card['layout'].capitalize()

						#The 'Colors' field benefits from some ordering, for readability.
						if 'colors' in card:
							card['colors'] = sorted(card['colors'])

						#Make sure all stored values are strings, that makes searching later much easier
						for attrib in listKeysToMakeString:
							if attrib in card:
								card[attrib] = "; ".join(card[attrib])

						for field in nullFieldsToX:
							if field in card and card[field] is None:
								card[field] = 'X'

						#Make some card keys lowercase, more readable, and/or shorter
						for keyToRename, newName in cardKeysToRename.items():
							if keyToRename in card:
								card[newName] = card.pop(keyToRename)

						#Converted mana cost is stored as a float, but in most cases its decimal is zero. If so, remove that decimal
						if 'cmc' in card and card['cmc'].endswith('.0'):
							card['cmc'] = card['cmc'][:-2]

						#Get possible term definitions from this card's text, if needed
						if shouldUpdateDefinitions and 'text' in card:
							definitionsFromCard = self.parseKeywordDefinitionsFromCardText(card['text'], card['name'], definitions)
							#Write the found definitions to file immediately, and store that we found them
							for term, definition in definitionsFromCard.items():
								definitionsFile.write(json.dumps({term: definition}))
								definitionsFile.write('\n')
								definitions.append(term)

						#Clean text up a bit to make it display better
						for keyToFormat in keysToFormatNicer:
							if keyToFormat in card:
								card[keyToFormat] = formatNicer(card[keyToFormat])

						#To make searching easier later, without all sorts of key checking, make sure the 'text' key always exists
						if 'text' not in card:
							card['text'] = ""

						#Save the data to file for now, we'll add all the set-specific data later
						gamewideCardStoreFile.write(json.dumps({cardname: card}))
						gamewideCardStoreFile.write('\n')

						#Store that we already parsed the gamewide card data, and make a dict for the set-specific data
						newcardstore[cardname] = {}

					#NOW store the set-specific info in the cardstore, so we can be sure the dict exists
					newcardstore[cardname][setData['name']] = setSpecificCardData

				#The 'booster' set field is a bit verbose, make that shorter and easier to use
				if 'booster' in setData:
					boosterData = setData.pop('booster')
					if 'default' in boosterData:
						boosterData = boosterData['default']
					else:
						boosterData = boosterData.popitem()[1]

					#Convert all sheet layout values from string to int
					# (Needed because automatic conversion in 'json.load' is disabled, because we want card power etc as string)
					boosterData['boostersTotalWeight'] = int(boosterData['boostersTotalWeight'], 10)
					for boosterLayout in boosterData['boosters']:
						boosterLayout['weight'] = int(boosterLayout['weight'], 10)
						for sheetName in boosterLayout['contents']:
							boosterLayout['contents'][sheetName] = int(boosterLayout['contents'][sheetName], 10)

					#Boosters are based on 'sheets': the list and weights of cards in each booster category. We need to rewrite them a bit
					for sheetName, sheetData in boosterData['sheets'].items():
						#We don't care about the 'foil' field
						if 'foil' in sheetData:
							del sheetData['foil']

						#The booster card weighted dict uses card uuids, replace those with card names
						sheetCardNamesAndWeights = {}
						for sheetCardCount in range(len(sheetData['cards'])):
							sheetCardUuid, sheetCardWeight = sheetData['cards'].popitem()
							if sheetCardUuid in uuidToCardName:
								sheetCardName = uuidToCardName[sheetCardUuid]
								if sheetCardName not in sheetCardNamesAndWeights:
									sheetCardNamesAndWeights[sheetCardName] = int(sheetCardWeight, 10)
								else:
									sheetCardNamesAndWeights[sheetCardName] += int(sheetCardWeight, 10)
						sheetData['cards'] = sheetCardNamesAndWeights
						sheetData['totalWeight'] = int(sheetData['totalWeight'], 10)

						#If the whole card list has weight 1, simplify it from a weight dict to a list
						if len(sheetData['cards']) == sheetData['totalWeight']:
							#Every card has a weight of 1, simplify cards to a list
							boosterData['sheets'][sheetName] = list(sheetData['cards'].keys())
						#The list could also be the same weight, in which case we could simplify it too. Check for that
						elif len(sheetData['cards']) > 0:
							weightToCheckAgainst = next(iter(sheetData['cards'].values()))
							for weightToCheck in sheetData['cards'].values():
								if weightToCheck != weightToCheckAgainst:
									#Not all weights are the same, so we can stop checking
									break
							else:
								#If we reach here, all the weights were the same, so we can turn the dict into a list
								boosterData['sheets'][sheetName] = list(sheetData['cards'].keys())

					setData['booster'] = boosterData
					# Keep a list of sets that have booster packs
					setstore['_setsWithBoosterpacks'].append(setData['name'].lower())

				#Don't hog the execution thread for too long, give it up after each set
				gevent.idle()

		#Since we don't need the downloaded cardfile anymore now, delete it
		os.remove(cardDatasetFilename)

		#Check if we have data to save
		if not newcardstore or not setstore:
			self.logError("[MTG] No card or set data was retrieved, not updating the data files")
			os.remove(gamewideCardStoreFilename)
			if definitionsFile:
				definitionsFile.close()
				os.remove(definitionsTempFilename)
			self.areCardfilesInUse = False
			raise CommandException(displayMessage="I couldn't download or read the card data from MTGJSON, sorry. I'll just keep my old data for now")

		#Save the new databases to disk
		with open(setStoreFilename, 'w', encoding='utf-8') as setsfile:
			setsfile.write(json.dumps(setstore))
		#We don't need the card info in memory anymore, hopefully this way the memory used get freed
		del setstore

		#Write the combined card data to file
		# (Use a temporary intermediate file so we still have the data if something would go wrong)
		numberOfCards = 0
		with open(gamewideCardStoreFilename, 'r', encoding='utf-8') as gamewideCardStoreFile, open(cardStoreTempFilename, 'w', encoding='utf-8') as cardfile:
			#Go through each card's game-wide data and append the set-specific data to it
			for line in gamewideCardStoreFile:
				numberOfCards += 1
				cardname, gamewideCardData = json.loads(line).popitem()
				#Write each card's as a separate JSON file so we can go through it line by line instead of having to load it all at once
				cardfile.write(json.dumps({cardname: [gamewideCardData, newcardstore.pop(cardname)]}))
				cardfile.write('\n')
		FileUtil.deleteIfExists(cardStoreFilename)  #Delete the file because Windows can't rename to an existing filename
		os.rename(cardStoreTempFilename, cardStoreFilename)

		#We don't need the temporary gamewide card data file anymore
		os.remove(gamewideCardStoreFilename)

		#Store the new version data
		latestVersionNumber = self.getLatestVersionNumber()
		with open(os.path.join(GlobalStore.scriptfolder, 'data', 'MTGversion.json'), 'w', encoding='utf-8') as versionFile:
			versionFile.write(json.dumps({'formatVersion': self.dataFormatVersion, 'dataVersion': latestVersionNumber, 'lastUpdateTime': time.time(), 'cardCount': numberOfCards}))

		replytext = "MtG card database successfully updated (Changelog: https://mtgjson.com/changelogs/mtgjson-v5/ )"
		if shouldUpdateDefinitions and definitionsFile:
			#Download the definitions too, and add them to the definitions we found in the card texts
			try:
				downloadedDefinitions = self.downloadDefinitions(definitions)
				for term, definition in downloadedDefinitions.items():
					definitionsFile.write(json.dumps({term: definition}))
					definitionsFile.write('\n')
				replytext += ", definitions also updated"
			except CommandException:
				replytext += ", but an error occurred when trying to download the definitions, check the logs for the error"
			#Save the definitions to file
			definitionsFile.close()
			FileUtil.deleteIfExists(definitionsFilename)
			os.rename(definitionsTempFilename, definitionsFilename)
			#And (try to) clean up the memory used
			del definitions
			del downloadedDefinitions

		#Updating apparently uses up RAM that Python doesn't clear up soon or properly. Force it to
		re.purge()
		gc.collect()

		self.areCardfilesInUse = False
		self.logInfo("[MtG] updating database took {} seconds".format(time.time() - starttime))
		return replytext

	@staticmethod
	def parseKeywordDefinitionsFromCardText(cardtext, cardname, existingDefinitions=None):
		newDefinitions = {}
		#Go through all the lines of the card text, since each line could have a definition
		lines = cardtext.splitlines()
		for line in lines:
			if '(' not in line:
				continue
			term, definition = line.split('(', 1)
			if term.count(' ') > 2:  # Make sure there aren't any sentences in there
				continue
			if ',' in term or ';' in term:  # Some cards list multiple keywords, ignore those since they're listed individually on other cards
				continue
			if '{' in term:
				#Get the term without any mana costs
				term = term.split('{', 1)[0]
			if '\u2014' in term:  # This is the special dash, which is sometimes used in costs too
				term = term.split('\u2014', 1)[0]
			term = term.rstrip().lower()
			if len(term) == 0:
				continue
			# Check to see if the term ends with mana costs. If it does, strip that off
			if ' ' in term:
				end = term.split(' ')[-1]
				#Remove any periods from the end
				if end.endswith('.'):
					end = end[:-1]
				if end.isdigit() or end == 'x':
					term = term.rsplit(" ", 1)[0]
			#For some keywords, the card description just doesn't work that well. Ignore those, and get those from Wikipedia later on
			if term in ('bolster', 'kicker', 'multikicker'):
				continue
			#If the term is already stored, skip it
			if existingDefinitions and term in existingDefinitions:
				continue
			#This is a new definition, add it, after cleaning it up a bit
			definition = definition.rstrip(')')
			#Some definitions start with a cost, remove that
			if definition.startswith('{'):
				definition = definition[definition.find(':') + 1:]
			definition = definition.strip()
			#Some explanations mention the current card name. Generalize the definition
			definition = definition.replace(cardname, 'this card')
			#Finally, store the term and definition!
			newDefinitions[term] = definition
		return newDefinitions

	def downloadDefinitions(self, existingDefinitions=None):
		newDefinitions = {}

		#Get keyword definitions and slang term meanings from other sites
		definitionSources = [("http://en.m.wikipedia.org/wiki/List_of_Magic:_The_Gathering_keywords", "content"),
			("http://mtgsalvation.gamepedia.com/List_of_Magic_slang", "mw-parser-output")]
		try:
			for url, section in definitionSources:
				defHeaders = BeautifulSoup(StringUtil.removeNewlines(requests.get(url, timeout=10.0).text), 'html.parser').find(class_=section).find_all(['h3', 'h4'])
				for defHeader in defHeaders:
					keyword = defHeader.find(class_='mw-headline').text.lower()
					#On MTGSalvation, sections are sorted into alphabetized subsections. Ignore the letter headers
					if len(keyword) <= 1:
						continue
					#Don't store any definitions that are already stored
					if existingDefinitions and keyword in existingDefinitions:
						continue
					#Cycle through all the paragraphs following the header
					currentParagraph = defHeader.next_sibling
					# Warnings are shown in a table after the header, ignore those
					if currentParagraph.name == 'table':
						currentParagraph = currentParagraph.next_sibling
					paragraphText = ""
					#If there's no next_sibling, 'currentParagraph' is set to None. Check for that
					while currentParagraph and currentParagraph.name in ('p', 'ul', 'dl', 'ol'):
						paragraphText += " " + currentParagraph.text
						currentParagraph = currentParagraph.next_sibling
					paragraphText = re.sub(r" ?\[\d+?]", "", paragraphText).lstrip().rstrip(' .')  #Remove the reference links ('[1]')
					if len(paragraphText) == 0:
						self.logWarning("[MTG] Definition for '{}' is empty, skipping".format(keyword))
						continue
					newDefinitions[keyword] = paragraphText
		except Exception as e:
			self.logError("[MTG] [DefinitionsUpdate] An error ({}) occurred: {}".format(type(e), e))
			traceback.print_exc()
			try:
				self.logError("[MTG] request url:", e.request.url)
				self.logError("[MTG] request headers:", e.request.headers)
			except AttributeError:
				self.logError(" no request attribute found")
			raise CommandException("An exception occurred while downloading or parsing MTG definitions")
		return newDefinitions
