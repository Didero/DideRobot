# -*- coding: utf-8 -*-

import gc, json, os, random, re, time, zipfile
import traceback

import requests
from bs4 import BeautifulSoup
import gevent

from CommandTemplate import CommandTemplate
import Constants
import GlobalStore
import SharedFunctions
from IrcMessage import IrcMessage


class Command(CommandTemplate):
	triggers = ['mtg', 'mtgf', 'mtgb', 'magic']
	helptext = "Looks up info on Magic: The Gathering cards. Provide a card name or regex to search for, or 'random' for a surprise. "
	helptext += "Use 'search' with key-value attribute pairs for more control, see http://mtgjson.com/documentation.html#cards for available attributes. "
	helptext += "{commandPrefix}mtgf adds the flavor text and sets to the output. '{commandPrefix}mtgb [setname]' opens a boosterpack"
	scheduledFunctionTime = 172800.0  #Every other day, since it doesn't update too often
	callInThread = True  #If a call causes a card update, make sure that doesn't block the whole bot

	areCardfilesInUse = False
	dataFormatVersion = '4.3.1'

	def onLoad(self):
		GlobalStore.commandhandler.addCommandFunction(__file__, 'searchMagicTheGatheringCards', self.searchCards)

	def executeScheduledFunction(self):
		if not self.areCardfilesInUse and self.shouldUpdate():
			self.updateCardFile()

	def execute(self, message):
		"""
		:type message: IrcMessage
		"""
		#Immediately check if there's any parameters, to prevent useless work
		if message.messagePartsLength == 0:
			return message.reply(self.getHelp(message), "say")

		#If the card set is currently being updated, we probably shouldn't try loading it
		if self.areCardfilesInUse:
			message.reply("I'm currently updating my card datastore, sorry! If you try again in, oh, 10 seconds, I should be done. You'll be the first to look through the new cards!")
			return

		#Check if we have all the files we need
		if not self.doNeededFilesExist():
			message.reply("Whoops, I don't seem to have all the files I need. I'll update now, try again in like 15 seconds. Sorry!", "say")
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
				success, replytext = self.updateCardFile()
			message.reply(replytext)
			return

		#Allow checking of card database version
		elif searchType == 'version':
			with open(os.path.join(GlobalStore.scriptfolder, 'data', 'MTGversion.json'), 'r') as versionfile:
				versions = json.load(versionfile)
			message.reply("My card database is based on version {} from http://www.mtgjson.com".format(versions['dataVersion']))
			return

		#We can also search for definitions
		elif searchType == 'define':
			#Get only the first part of the definition if the 'full info' trigger wasn't used, otherwise get the whole definition, which can be really long
			definitionText = self.getDefinition(" ".join(message.messageParts[1:]), None if message.trigger == 'mtgf' else Constants.MAX_MESSAGE_LENGTH)
			#Now split the definition up into message-sized chunks and send each of them, if necessary
			# This is not needed in a private message, since huge blocks of text are less of a problem there
			if not message.isPrivateMessage and message.trigger == 'mtgf' and len(definitionText) > Constants.MAX_MESSAGE_LENGTH:
				#Cut it up at a word boundary
				splitIndex = definitionText[:Constants.MAX_MESSAGE_LENGTH].rfind(' ')
				textRemainder = definitionText[splitIndex + 1:]
				definitionText = definitionText[:splitIndex]
				#Since we'll be sending the rest of the definition in notices, add an indication that it's not the whole message
				definitionText += u' [...]'
				#Don't send messages too quickly
				secondsBetweenMessages = message.bot.secondsBetweenLineSends
				if not secondsBetweenMessages:
					secondsBetweenMessages = 0.2
				counter = 1
				while len(textRemainder) > 0:
					gevent.spawn_later(secondsBetweenMessages * counter, message.bot.sendMessage, message.userNickname,
									   u"({}) {}".format(counter + 1, textRemainder[:Constants.MAX_MESSAGE_LENGTH]), 'notice')
					textRemainder = textRemainder[Constants.MAX_MESSAGE_LENGTH:]
					counter += 1
			#Present the result!
			return message.reply(definitionText, "say")

		elif searchType == 'booster' or message.trigger == 'mtgb':
			if (searchType == 'booster' and message.messagePartsLength == 1) or (message.trigger == 'mtgb' and message.messagePartsLength == 0):
				message.reply("Please provide a set name, so I can open a boosterpack from that set. Or use 'random' to have me pick one")
				return
			setname = ' '.join(message.messageParts[1:]).lower() if searchType == 'booster' else message.message.lower()
			message.reply(self.openBoosterpack(setname)[1])
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
			message.reply(self.searchCards(searchType, searchString, message.trigger.endswith('f'), 20 if message.isPrivateMessage else 10), "say")

	def searchCards(self, searchType, searchString, extendedInfo=False, resultListLength=10):
		#Special case to prevent it having to load in all the cards before picking one
		if searchType == 'random' and not searchString:
			#Just pick a random card from all available ones
			card = json.loads(SharedFunctions.getRandomLineFromFile(os.path.join(GlobalStore.scriptfolder, 'data', 'MTGcards.json')))
			cardname, carddata = card.popitem()
			return self.getFormattedCardInfo(carddata, extendedInfo)

		#Make sure the search string is an actual string, and not None or something
		if searchString is None:
			searchString = ""

		#Check if the user passed valid search terms
		parseSuccess, searchDict = self.parseSearchParameters(searchType, searchString)
		if not parseSuccess:
			#If an error occurred, the second returned parameter isn't the searchdict but an error message
			return searchDict
		#Check if the entered search terms can be converted to the regex we need
		parseSuccess, regexDict = self.searchDictToRegexDict(searchDict)
		if not parseSuccess:
			#Again, 'regexDict' is the error string if an error occurred
			return regexDict
		matchingCards = self.searchCardStore(regexDict)
		#Clear the stored regexes, since we don't need them anymore
		del regexDict
		re.purge()
		#Done, show the formatted result
		return self.formatSearchResult(matchingCards, extendedInfo, searchType.startswith('random'), resultListLength, searchDict.get('name', None), len(searchDict) > 0)

	@staticmethod
	def parseSearchParameters(searchType, searchString):
		searchDict = {}
		if searchType == 'search' and not searchString:
			return (False, "Error: 'search' parameter requires a search query too")
		#Check if there is an actual search (with colon as key-value separator)
		elif ':' in searchString:
			#Advanced search! Turn the search string into a usable dictionary
			searchDict = SharedFunctions.stringToDict(searchString.lower(), True)
			if len(searchDict) == 0:
				return (False, "That is not a valid search query. It should be entered like JSON, so 'name: ooze, type: creature,...'. "
							  "For a list of valid keys, see http://mtgjson.com/documentation.html#cards (though not all keys may be available)")
		#Not a special search, just set the whole message as a 'name' search, since that's the most common search
		elif searchString:
			searchDict['name'] = searchString.lower()

		#Commander search. Regardless of everything else, it has to be a legendary creature
		if searchType == 'randomcommander':
			if 'type' not in searchDict:
				searchDict['type'] = ""
			#Don't just search for 'legendary creature.*', because there are legendary artifact creatures too
			searchDict['type'] = 'legendary.+creature.*' + searchDict['type']

		#Correct some values, to make searching easier (so a search for 'set' or 'sets' both work)
		searchTermsToCorrect = {'set': ('sets', 'setname'), 'colors': ('color', 'colour', 'colours'), 'type': ('types', 'supertypes', 'subtypes'), 'flavor': ('flavour',)}
		for correctTerm, listOfWrongterms in searchTermsToCorrect.iteritems():
			for wrongTerm in listOfWrongterms:
				if wrongTerm in searchDict:
					if correctTerm not in searchDict:
						searchDict[correctTerm] = searchDict[wrongTerm]
					searchDict.pop(wrongTerm)
		return (True, searchDict)

	def searchDictToRegexDict(self, searchDict):
		#Turn the search strings into actual regexes
		regexDict = {}
		errors = []
		for attrib, query in searchDict.iteritems():
			# Since the query is probably a string, and the card data is unicode, convert the query to unicode before turning it into a regex
			# This fixes the module not finding a literal search for 'Ætherling', for instance
			if not isinstance(query, unicode):
				query = unicode(query, encoding='utf8', errors='replace')
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
			except UnicodeDecodeError as e:
				self.logDebug("[MTG] Unicode error in key '{}': {}".format(attrib, e))
				errors.append(attrib)
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
			return (False, replytext)
		return (True, regexDict)

	@staticmethod
	def searchCardStore(regexDict):
		#Get the 'setname' search separately, so we can iterate over the rest later
		setRegex = regexDict.pop('set', None)
		setKeys = ('artist', 'flavor', 'multiverseid', 'number', 'rarity', 'watermark')

		# A dict with cardname as key, and a list as value
		#  First item in the list is line number of the card in the cardfile, last item is the matching setname (if any)
		matchingCards = {}
		with open(os.path.join(GlobalStore.scriptfolder, 'data', 'MTGcards.json')) as jsonfile:
			for cardlineNumber, cardline in enumerate(jsonfile):
				cardname, carddata = json.loads(cardline).popitem()

				#Store how much sets we started with, so we know at the end if any sets got removed
				setCountAtStart = len(carddata[1])

				#First check if we need to see if the set name matches
				if setRegex:
					for setname in carddata[1].keys():
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
						for setname in carddata[1].keys():
							#If this attribute doesn't fit the search criteria, remove this set
							if not regexDict[attrib].search(carddata[1][setname][attrib]):
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
					setNameMatches = None if len(carddata[1]) == setCountAtStart else carddata[1].keys()
					# Use the formatted name so displaying them is easier later
					matchingCards[carddata[0]['name']] = (cardlineNumber, setNameMatches)
		return matchingCards

	def formatSearchResult(self, cardstore, addExtendedCardInfo, pickRandomCard, maxCardsToList=10, nameToMatch=None, addResultCount=True):
		numberOfCardsFound = len(cardstore)

		if numberOfCardsFound == 0:
			return "Sorry, no card matching your query was found"

		if pickRandomCard:
			cardname = random.choice(cardstore.keys())
			cardstore = {cardname: cardstore[cardname]}
		#If the name we have to match is in there literally, lift it out
		# (For instance, a search for 'Mirror Entity' returns 'Mirror Entity' and 'Mirror Entity Avatar'.
		# Show the full info on 'Mirror Entity' but also report we found more matches)
		elif nameToMatch:
			nameToMatch = nameToMatch.lower()
			for cardname, cardtuple in cardstore.iteritems():
				if cardname.lower() == nameToMatch:
					cardstore = {cardname: cardtuple}
					break

		#If there's only one card found, just display it
		# Use 'len()' instead of 'numberOfCardsFound' because 'pickRandomCard' or 'nameToMatch' could've changed it,
		# and we need the cardcount var to show how many cards we found at the end
		if len(cardstore) == 1:
			#Retrieve the full info on the card we found
			linenumber, setname = cardstore.values()[0]
			cardname, carddata = json.loads(SharedFunctions.getLineFromFile(os.path.join("data", "MTGcards.json"), linenumber)).popitem()
			replytext = self.getFormattedCardInfo(carddata, addExtendedCardInfo, setname)
			#We may have culled the cardstore list, so there may have been more matches initially. List a count of those
			if addResultCount and numberOfCardsFound > 1:
				replytext += " ({:,} more match{} found)".format(numberOfCardsFound - 1, 'es' if numberOfCardsFound > 2 else '')  #>2 because we subtract 1
			return replytext

		#Check if we didn't find more matches than we're allowed to show
		cardnames = cardstore.keys()
		if numberOfCardsFound > maxCardsToList:
			cardnames = random.sample(cardnames, maxCardsToList)
		#Show them alphabetically
		cardnames = sorted(cardnames)

		replytext = u"Your search returned {:,} cards: {}".format(numberOfCardsFound, u"; ".join(cardnames))
		if numberOfCardsFound > maxCardsToList:
			replytext += u" and {:,} more".format(numberOfCardsFound - maxCardsToList)
		return replytext

	@staticmethod
	def getFormattedCardInfo(carddata, addExtendedInfo=False, setname=None, startingLength=0):
		card = carddata[0]
		sets = carddata[1]
		cardInfoList = [SharedFunctions.makeTextBold(card['name'])]
		if 'type' in card and len(card['type']) > 0:
			cardInfoList.append(card['type'])
		if 'manacost' in card:
			manacost = card['manacost']
			#Only add the cumulative mana cost if it's different from the total cost (No need to say '3 mana, 3 total')
			if 'cmc' in card and card['cmc'] != card['manacost']:
				manacost += u", CMC " + card['cmc']
			#If no cmc is shown, specify the number is the manacost
			else:
				manacost += u" mana"
			cardInfoList.append(manacost)
		if 'power' in card and 'toughness' in card:
			cardInfoList.append(card['power'] + u"/" + card['toughness'] + u" P/T")
		if 'loyalty' in card:
			cardInfoList.append(card['loyalty'] + u" loyalty")
		if 'hand' in card or 'life' in card:
			handLife = u""
			if 'hand' in card:
				handLife = card['hand'] + u" handmod"
			if 'hand' in card and 'life' in card:
				handLife += u", "
			if 'life' in card:
				handLife += card['life'] + u" lifemod"
			cardInfoList.append(handLife)
		if 'layout' in card and card['layout'] != u'normal':
			cardInfoList.append(u"Layout is '" + card['layout'] + u"'")
			if 'names' in card:
				cardInfoList[-1] += u", also contains " + card['names']
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
				setname = random.choice(sets.keys())
			if 'flavor' in sets[setname]:
				#Make the flavor text gray to indicate it's not too important.
				#  '\x03' is colour code character, '14' is gray, '\x0f' is decoration end character
				cardInfoList.append(u'\x0314' + sets[setname]['flavor'] + u'\x0f')
			maxSetsToDisplay = 4
			setcount = len(sets)
			setlist = sets.keys()
			if setcount > maxSetsToDisplay:
				setlist = random.sample(setlist, maxSetsToDisplay)
			setlistString = u"in "
			for setname in setlist:
				#Make the display 'setname (first letter of rarity)', so 'Magic 2015 (R)'
				rarity = sets[setname]['rarity']
				if rarity == u"Basic Land":
					rarity = u'L'
				else:
					rarity = rarity[0]
				setlistString += u"{} ({}); ".format(setname, rarity)
			setlistString = setlistString[:-2]  #Remove the last '; '
			if setcount > maxSetsToDisplay:
				setlistString += u" and {:,} more".format(setcount - maxSetsToDisplay)
			cardInfoList.append(setlistString)
		#No extra set info, but still add a warning if it's in a non-legal set
		else:
			for illegalSet in (u'Happy Holidays', u'Unglued', u'Unhinged', u'Unstable'):
				if illegalSet in sets:
					cardInfoList.append(u"in illegal set \x0304{illegalSet}\x0f!".format(illegalSet=illegalSet))  #color-code the setname red
					break

		#FILL THAT SHIT IN (encoded properly)
		separatorLength = len(Constants.GREY_SEPARATOR)
		#Keep adding parts to the output until an entire block wouldn't fit on one line, then start a new message
		replytext = u''
		messageLength = startingLength
		MAX_MESSAGE_LENGTH = 325

		while len(cardInfoList) > 0:
			cardInfoPart = cardInfoList.pop(0)
			partLength = len(cardInfoPart)
			if messageLength + partLength < MAX_MESSAGE_LENGTH:
				replytext += cardInfoPart
				messageLength += partLength
				#Separator!
				if messageLength + separatorLength > MAX_MESSAGE_LENGTH:
					#If the separator wouldn't fit anymore, start a new message
					replytext += '\n'
					messageLength = 0
				#Add a separator
				replytext += Constants.GREY_SEPARATOR
				messageLength += separatorLength
			else:
				#If we would exceed max message length, cut off at the highest space and continue in a new message
				#  If the message started with a special character (bold for name, grey for flavour), copy those
				prefix = u''
				#bold
				if cardInfoPart.startswith(u'\x02'):
					prefix = u'\x02'
				#color
				elif cardInfoPart.startswith(u'\x03'):
					#Also copy colour code
					prefix = cardInfoPart[:3]
				#Get the spot in the text where the cut-off would be (How much of the part text fits in the open space)
				splitIndex = MAX_MESSAGE_LENGTH - messageLength
				#Then get the last space before that index, so we don't split mid-word (if possible)
				if u' ' in cardInfoPart[:splitIndex]:
					splitIndex = cardInfoPart.rindex(u' ', 0, splitIndex)
				#If we can't find a space, add a dash to indicate the word continues in the new message
				elif splitIndex > 0:
					cardInfoPart = cardInfoPart[:splitIndex-1] + u'-' + cardInfoPart[splitIndex-1:]
				#Add the second section back to the list, so it can be properly added, even if it would still be too long
				cardInfoList.insert(0, prefix + cardInfoPart[splitIndex:])
				#Then add the first part to the message
				replytext += cardInfoPart[:splitIndex] + u'\n'
				messageLength = 0

		#Remove the separator at the end, if there is one
		if replytext.endswith(Constants.GREY_SEPARATOR):
			replytext = replytext[:-separatorLength].rstrip()
		#Make sure we return a string and not unicode
		replytext = replytext.encode('utf-8')
		return replytext

	@staticmethod
	def getDefinition(searchterm, maxMessageLength=None):
		"""
		Searches for the definition of the provided MtG-related term. Supports regular expressions as the search term
		:param searchterm The term to find the definition of. Can be a partial match or a regular expression
		:param maxMessageLength The maximum length of the returned definition. If set to None or to zero or smaller, the full definition will be returned
		:return The matching term followed by the definition of that term
		"""
		definitionsFilename = os.path.join(GlobalStore.scriptfolder, 'data', 'MTGdefinitions.json')

		#Make sure maxMessageLength is a valid value
		if maxMessageLength and maxMessageLength <= 0:
			maxMessageLength = None

		possibleDefinitions = {}  #Keys are the matching terms found, values are the line they're found at for easy lookup

		if searchterm == 'random':
			randomLineNumber = random.randrange(0, SharedFunctions.getLineCount(definitionsFilename))
			term = json.loads(SharedFunctions.getLineFromFile(definitionsFilename, randomLineNumber)).keys()[0]
			possibleDefinitions = {term: randomLineNumber}
		else:
			try:
				searchRegex = re.compile(searchterm)
			except re.error:
				return u"That is not valid regex. Please check for typos, and try again"

			with open(definitionsFilename, 'r') as definitionsFile:
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

		possibleDefinitionsCount = len(possibleDefinitions)
		if possibleDefinitionsCount == 0:
			replytext = u"Sorry, I don't have any info on that term. If you think it's important, poke my owner(s), maybe they'll add it!"
		elif possibleDefinitionsCount == 1:
			#Found one definition, return that
			term, linenumber = possibleDefinitions.popitem()
			definition = json.loads(SharedFunctions.getLineFromFile(definitionsFilename, linenumber)).values()[0]
			replytext = u"{}: {}".format(SharedFunctions.makeTextBold(term), definition)
			#Limit the message length
			if maxMessageLength and len(replytext) > maxMessageLength:
				splitIndex = replytext[:maxMessageLength].rfind(' ')
				replytext = replytext[:splitIndex] + u' [...]'
		#Multiple matching definitions found
		else:
			if searchterm in possibleDefinitions:
				#Multiple matches, but one of them is the literal search term. Return that, and how many other matches we found
				definition = json.loads(SharedFunctions.getLineFromFile(definitionsFilename, possibleDefinitions[searchterm])).values()[0]
				replytext = u"{}: {}".format(SharedFunctions.makeTextBold(searchterm), definition)
				if maxMessageLength and len(replytext) > maxMessageLength - 18:  #-18 to account for the ' XX more matches' text later
					replytext = replytext[:maxMessageLength-24] + ' [...]'  #18 + len(' [...]')
				replytext += u" ({:,} more matches)".format(possibleDefinitionsCount-1)
			else:
				replytext = u"Your search returned {:,} results, please be more specific".format(possibleDefinitionsCount)
				if possibleDefinitionsCount < 10:
					replytext += u": {}".format(u"; ".join(sorted(possibleDefinitions.keys())))
		return replytext


	@staticmethod
	def openBoosterpack(askedSetname):
		askedSetname = askedSetname.lower()
		properSetname = u''
		#First check if the message is a valid setname
		with open(os.path.join(GlobalStore.scriptfolder, 'data', 'MTGsets.json'), 'r') as setsfile:
			setdata = json.load(setsfile)
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
				if askedSetcode == setdata[setname]['code']:
					properSetname = setname
					#Since setcodes are unique, no need to keep looking
					break
		if properSetname == u'':
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
					if properSetname == u'':
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
						return (False, u"That setname matches at least two sets, '{}' and '{}'. I can't make a boosterpack from more than one set. "
									   u"Please be a bit more specific".format(setname, properSetname))
		#If we still haven't found anything, give up
		if properSetname == u'':
			return (False, "I'm sorry, I don't know the set '{}'. Did you make a typo?".format(askedSetname))
		#Some sets don't have booster packs, check for that too
		if 'booster' not in setdata[properSetname]:
			return (False, "The set '{}' doesn't have booster packs, according to my data. Sorry".format(properSetname))
		boosterRarities = setdata[properSetname]['booster']

		#Resolve any random choices (in the '_choice' field). It's a list of lists, since there can be multiple cards with choices
		if '_choice' in boosterRarities:
			for rarityOptions in boosterRarities['_choice']:
				#Make it a weighted choice ('mythic rare' should happen far less often than 'rare', for instance)
				if 'mythic rare' in rarityOptions:
					if random.randint(0, 1000) <= 125:  #Chance of 1 in 8, which is supposedly the real-world chance
						rarityPick = 'mythic rare'
					else:
						rarityOptions.remove('mythic rare')
						rarityPick = random.choice(rarityOptions)
				else:
					rarityPick = random.choice(rarityOptions)
				#Add the rarity we picked to the list of rarities we already have
				if rarityPick not in boosterRarities:
					boosterRarities[rarityPick] = 1
				else:
					boosterRarities[rarityPick] += 1
			del boosterRarities['_choice']

		#Name exists, get the proper spelling, since in other places setnames aren't lower-case
		properSetname = setdata[properSetname]['name']

		#Check if we need to collect some special-case types too instead of just rarities
		typesToCollect = []  #This will become a tuple with the first entry being the type in text and the second entry the compiled regex
		defaultRarities = ('common', 'uncommon', 'rare', 'mythic rare', '_choice')
		for rarity in boosterRarities:
			if rarity not in defaultRarities:
				typesToCollect.append((rarity, re.compile(rarity, re.IGNORECASE)))
		collectTypes = True if len(typesToCollect) > 0 else False

		#A dictionary with the found cards, sorted by rarity
		possibleCards = {}
		#First fill in the required rarities
		for rarity in boosterRarities:
			possibleCards[rarity.lower()] = []

		#Get all cards from that set
		with open(os.path.join(GlobalStore.scriptfolder, 'data', 'MTGcards.json'), 'r') as jsonfile:
			for cardline in jsonfile:
				cardname, carddata = json.loads(cardline).popitem()
				if properSetname not in carddata[1]:
					continue
				#Skip cards whose number ends with 'b', since they're the backside of doublefaced cards or the upside-down part of split cards
				if 'number' in carddata[0] and carddata[0]['number'].endswith('b'):
					continue
				if collectTypes:
					for typeName, typeRegex in typesToCollect:
						if typeRegex.search(carddata[0]['type']):
							possibleCards[typeName].append(carddata[0]['name'])
							continue
				rarity = carddata[1][properSetname]['rarity'].lower()
				if rarity in boosterRarities:
					possibleCards[rarity].append(carddata[0]['name'])

		#Some sets don't have basic lands, but need them in their boosterpacks (Gatecrash f.i.) Fix that
		#TODO: Handle rarities properly, a 'land' shouldn't be a 'basic land' but a land from that set
		if 'basic land' in boosterRarities and len(possibleCards['basic land']) == 0:
			CommandTemplate.logWarning(u"[MTG] Booster for set '{}' needs {:,} basic lands, but set doesn't have any! Adding manually".format(properSetname, boosterRarities['basic land']))
			possibleCards['basic land'] = ['Forest', 'Island', 'Mountain', 'Plains', 'Swamp']

		#Check if we found enough cards
		for rarity, count in boosterRarities.iteritems():
			if rarity == '_choice':
				continue
			if rarity not in possibleCards:
				return (False, u"No cards with rarity '{}' found in set '{}', and I can't make a booster pack without it!".format(rarity, properSetname))
			elif len(possibleCards[rarity]) < count:
				return (False, u"The set '{}' doesn't seem to contain enough '{}'-rarity cards for a boosterpack. "
							   u"I need {:,}, but I only found {:,}".format(properSetname, rarity, boosterRarities[rarity], len(possibleCards[rarity])))

		#Draw the cards!
		replytext = "{}{}".format(properSetname.encode('utf-8'), Constants.GREY_SEPARATOR)
		for rarity, count in boosterRarities.iteritems():
			cardlist = "; ".join(random.sample(possibleCards[rarity], count)).encode('utf-8')
			replytext += "{}: {}. ".format(SharedFunctions.makeTextBold(rarity.encode('utf-8').capitalize()), cardlist)
		return (True, replytext)

	def downloadCardDataset(self):
		url = "http://mtgjson.com/json/AllSetFilesWindows.zip"  # Use the Windows version to keep it multi-platform (Windows can't handle files named 'CON')
		cardzipFilename = os.path.join(GlobalStore.scriptfolder, 'data', url.split('/')[-1])
		success, extraInfo = SharedFunctions.downloadFile(url, cardzipFilename)
		if not success:
			self.logError("[MTG] An error occurred while trying to download the card file: " + extraInfo.message)
			return (False, "Something went wrong while trying to download the card file.")
		return (True, extraInfo)

	def getLatestVersionNumber(self):
		try:
			latestVersion = requests.get("http://mtgjson.com/json/version.json", timeout=10.0).text
		except requests.exceptions.Timeout:
			self.logError("[MTG] Fetching card version timed out")
			return (False, "Fetching online card version took too long")
		latestVersion = latestVersion.replace('"', '')  #Version is a quoted string, remove the quotes
		return (True, latestVersion)

	@staticmethod
	def doNeededFilesExist():
		for fn in ('cards', 'definitions', 'sets', 'version'):
			if not os.path.isfile(os.path.join(GlobalStore.scriptfolder, 'data', 'MTG{}.json'.format(fn))):
				return False
		return True

	def shouldUpdate(self):
		basepath = os.path.join(GlobalStore.scriptfolder, 'data')
		#If one of the required files doesn't exist, we should update
		if not self.doNeededFilesExist():
			return True
		with open(os.path.join(basepath, 'MTGversion.json'), 'r') as versionfile:
			versiondata = json.load(versionfile)
		#We should fix the files if the version file is missing keys we need
		for requiredKey in ('formatVersion', 'dataVersion', 'lastUpdateTime'):
			if requiredKey not in versiondata:
				return True
		#We should update if the latest formatting version differs from the stored one
		if versiondata['formatVersion'] != self.dataFormatVersion:
			return True
		#If the last update check has been recent, don't update (with some leniency to prevent edge cases)
		if time.time() - versiondata['lastUpdateTime'] < self.scheduledFunctionTime - 5.0:
			return False
		#Get the latest online version to see if we're behind
		success, result = self.getLatestVersionNumber()
		if success and result != versiondata['dataVersion']:
			return True
		return False

	def updateCardFile(self, shouldUpdateDefinitions=True):
		starttime = time.time()
		cardStoreFilename = os.path.join(GlobalStore.scriptfolder, 'data', 'MTGcards.json')
		gamewideCardStoreFilename = os.path.join(GlobalStore.scriptfolder, 'data', 'MTGcards_gamewide.json')
		setStoreFilename = os.path.join(GlobalStore.scriptfolder, 'data', 'MTGsets.json')
		definitionsFilename = os.path.join(GlobalStore.scriptfolder, 'data', 'MTGdefinitions.json')

		#Inform everything that we're going to be changing the card files
		self.areCardfilesInUse = True
		self.logInfo("[MtG] Updating card database!")

		#Download the wrongly-formatted (for our purposes) card data
		success, result = self.downloadCardDataset()
		if not success:
			return (False, result)
		else:
			cardDatasetFilename = result

		#Set up the dicts we're going to store our data in
		newcardstore = {}
		setstore = {'_setsWithBoosterpacks': []}
		#Since definitions from cards get written to file immediately, just keep a list of which keywords we already stored
		definitions = []
		#Lists of what to do with certain set keys
		setKeysToRemove = ('border', 'magicRaritiesCodes', 'mkm_id', 'mkm_name', 'oldCode', 'onlineOnly', 'translations')
		raritiesToRemove = ('checklist', 'double faced', 'draft-matters', 'foil', 'marketing', 'power nine', 'timeshifted purple', 'token')
		raritiesToRename = {'land': 'basic land', 'urza land': 'land — urza’s'}  #Non-standard rarities are interpreted as regexes for type
		rarityPrefixesToRemove = {'foil ': 5, 'timeshifted ': 12}  #The numbers are the string length, saves a lot of 'len()' calls
		#Lists of what to do with certain card keys
		keysToRemove = ('border', 'colorIdentity', 'id', 'imageName', 'mciNumber', 'releaseDate', 'reserved', 'starter', 'subtypes', 'supertypes', 'timeshifted', 'types', 'variations')
		keysToFormatNicer = ('flavor', 'manacost', 'text')
		layoutTypesToRemove = ('normal', 'phenomenon', 'plane', 'scheme', 'vanguard')
		listKeysToMakeString = ('colors', 'names')
		setSpecificCardKeys = ('artist', 'flavor', 'multiverseid', 'number', 'rarity', 'watermark')

		# This function will be called on the 'keysToFormatNicer' keys
		#  Made into a function, because it's used in two places
		def formatNicer(text):
			#Remove brackets around mana cost
			if '{' in text:
				text = text.replace('}{', ' ').replace('{', '').replace('}', '')
			#Replace newlines with spaces. If the sentence ends in a letter, add a period
			text = re.sub('(?<=\w)\n', '. ', text).replace('\n', ' ')
			#Prevent double spaces
			text = re.sub(' {2,}', ' ', text).strip()
			return text

		#Reference to a temporary file where we will store gamewide JSON-parsed card info (Like card text, CMC)
		# This way we don't have to keep that in memory during the entire loop
		# Keys will be lower()'ed cardnames, values will be a dict of the card's fields that are true regardless of the set the card is in
		gamewideCardStoreFile = open(gamewideCardStoreFilename, 'w')

		#Write each keyword we find to the definitions file so we don't have to keep it in memory
		if shouldUpdateDefinitions:
			definitionsFile = open(definitionsFilename, 'w')

		#Go through each file in the sets zip (Saves memory compared to downloading the single file with all the sets)
		with zipfile.ZipFile(cardDatasetFilename, 'r') as setfilesZip:
			#Go through each file in the sets zip
			for setfilename in setfilesZip.namelist():
				# Keep numbers as strings, saves on converting them back later
				setData = json.loads(setfilesZip.read(setfilename), parse_int=lambda x: x, parse_float=lambda x: x)
				#Put the cardlist in a separate variable, so we can store all the set information easily
				cardlist = setData.pop('cards')
				#Clean up the set data a bit
				for setKeyToRemove in setKeysToRemove:
					if setKeyToRemove in setData:
						del setData[setKeyToRemove]
				#The 'booster' set field is a bit verbose, make that shorter and easier to use
				if 'booster' in setData:
					originalBoosterList = setData.pop('booster')
					countedBoosterData = {}
					try:
						for rarity in originalBoosterList:
							#If the entry is a list, it's a list of possible choices for that card
							#  ('['rare', 'mythic rare']' means a booster pack contains a rare OR a mythic rare)
							if isinstance(rarity, list):
								#Remove useless options here too
								for rarityToRemove in raritiesToRemove:
									if rarityToRemove in rarity:
										rarity.remove(rarityToRemove)
								#Rename 'wrongly' named rarites
								for r in raritiesToRename:
									if r in rarity:
										rarity.remove(r)
										rarity.append(raritiesToRename[r])
								#Check if any of the choices have a prefix that needs to be removed (use a copy so we can delete elements in the loop)
								for choice in rarity[:]:
									for rp in rarityPrefixesToRemove:
										if choice.startswith(rp):
											#Remove the original choice...
											rarity.remove(choice)
											newRarity = choice[rarityPrefixesToRemove[rp]:]
											#...and put in the choice without the prefix, if it's not there already
											if newRarity not in rarity:
												rarity.append(newRarity)
								#If we removed all options and just have an empty list now, replace it with a rare
								if len(rarity) == 0:
									rarity = 'rare'
								#If we've removed all but one option, it's not a choice anymore, so treat it like a 'normal' rarity
								elif len(rarity) == 1:
									rarity = rarity[0]
								else:
									#If it's still a list, keep it like that
									if '_choice' not in countedBoosterData:
										countedBoosterData['_choice'] = [rarity]
									else:
										countedBoosterData['_choice'].append(rarity)
									#...but don't do any of the other stuff
									continue
							#Some keys are dumb and useless ('marketing'). Ignore those
							if rarity in raritiesToRemove:
								continue
							#Here the rarity for a basic land is called 'land', while in the cards themselves it's 'basic land'. Correct that
							for rarityToRename in raritiesToRename:
								if rarity == rarityToRename:
									rarity = raritiesToRename[rarity]
							#Remove any useless prefixes like 'foil'
							for rp in rarityPrefixesToRemove:
								if rarity.startswith(rp):
									rarity = rarity[rarityPrefixesToRemove[rp]:]
							#Finally, count the rarity
							if rarity not in countedBoosterData:
								countedBoosterData[rarity] = 1
							else:
								countedBoosterData[rarity] += 1
					except Exception as e:
						self.logError("Error while parsing booster field of set '{}' ({}): {!r}".format(setData['name'], setfilename, e))
					else:
						#If no parsing error occurred, add the parsed booster data
						setData['booster'] = countedBoosterData
						# Keep a list of sets that have booster packs
						setstore['_setsWithBoosterpacks'].append(setData['name'].lower())
				setstore[setData['name'].lower()] = setData

				#Pop off cards when we need them, to save on memory
				for cardcount in xrange(0, len(cardlist)):
					card = cardlist.pop()
					cardname = card['name'].lower()  #lowering the keys makes searching easier later, especially when comparing against the literal searchstring

					#Make flavor text read better
					if 'flavor' in card:
						card['flavor'] = formatNicer(card['flavor'])
					#New and already listed cards need their set info stored
					#TODO: Some sets have multiple cards with the same name but a different artist (f.i. land cards). Handle that
					setSpecificCardData = {}
					for setSpecificKey in setSpecificCardKeys:
						if setSpecificKey in card:
							setSpecificCardData[setSpecificKey] = card.pop(setSpecificKey)
					#Don't add it to newcardstore yet, so we can check if it's in there already or not
					# But do the loop now so the set-specific keys are removed from the card dict

					#If the card isn't in the store yet, parse its data
					if cardname not in newcardstore:
						#Remove some useless data to save some space, memory and time
						for keyToRemove in keysToRemove:
							if keyToRemove in card:
								del card[keyToRemove]

						#No need to store there's nothing special about the card's layout or if the special-ness is already evident from the text
						if card['layout'] in layoutTypesToRemove:
							del card['layout']

						#The 'Colors' field benefits from some ordering, for readability.
						if 'colors' in card:
							card['colors'] = sorted(card['colors'])

						#Remove the current card from the list of names this card also contains (for flip cards)
						# (Saves on having to remove it later, and the presence of this field shows it's in there too)
						if 'names' in card:
							card['names'].remove(card['name'])

						#Make sure all stored values are strings, that makes searching later much easier
						for attrib in listKeysToMakeString:
							if attrib in card:
								card[attrib] = u"; ".join(card[attrib])

						#Make 'manaCost' lowercase, since we make the searchstring lowercase too, and we don't want to miss this
						if 'manaCost' in card:
							card['manacost'] = card['manaCost']
							del card['manaCost']

						#Get possible term definitions from this card's text, if needed
						if shouldUpdateDefinitions and 'text' in card:
							definitionsFromCard = self.parseKeywordDefinitionsFromCardText(card['text'], card['name'], definitions)
							#Write the found definitions to file immediately, and store that we found them
							for term, definition in definitionsFromCard.iteritems():
								definitionsFile.write(json.dumps({term: definition}))
								definitionsFile.write('\n')
								definitions.append(term)

						#Clean text up a bit to make it display better
						for keyToFormat in keysToFormatNicer:
							if keyToFormat in card:
								card[keyToFormat] = formatNicer(card[keyToFormat])

						#To make searching easier later, without all sorts of key checking, make sure the 'text' key always exists
						if 'text' not in card:
							card['text'] = u""

						#Save the data to file for now, we'll add all the set-specific data later
						gamewideCardStoreFile.write(json.dumps({cardname: card}))
						gamewideCardStoreFile.write('\n')

						#Store that we already parsed the gamewide card data, and make a dict for the set-specific data
						newcardstore[cardname] = {}

					#NOW store the set-specific info in the cardstore, so we can be sure the dict exists
					newcardstore[cardname][setData['name']] = setSpecificCardData

				#Don't hog the execution thread for too long, give it up after each set
				gevent.idle()

		#Make sure all the data is flushed to disk
		gamewideCardStoreFile.close()

		#First delete the original files
		if os.path.exists(cardStoreFilename):
			os.remove(cardStoreFilename)
		if os.path.exists(setStoreFilename):
			os.remove(setStoreFilename)
		#Save the new databases to disk
		with open(cardStoreFilename, 'w') as cardfile:
			gamewideCardStoreFile = open(gamewideCardStoreFilename, 'r')
			#Go through each card's game-wide data and append the set-specific data to it
			for line in gamewideCardStoreFile:
				cardname, gamewideCardData = json.loads(line).popitem()
				#Write each card's as a separate JSON file so we can go through it line by line instead of having to load it all at once
				cardfile.write(json.dumps({cardname: [gamewideCardData, newcardstore.pop(cardname)]}))
				cardfile.write('\n')
			gamewideCardStoreFile.close()
		with open(setStoreFilename, 'w') as setsfile:
			setsfile.write(json.dumps(setstore))

		#We don't need the temporary gamewide card data file anymore
		os.remove(gamewideCardStoreFilename)

		#We don't need the card info in memory anymore, hopefully this way the memory used get freed
		del setstore

		#Store the new version data
		with open(os.path.join(GlobalStore.scriptfolder, 'data', 'MTGversion.json'), 'w') as versionFile:
			versionFile.write(json.dumps({'formatVersion': self.dataFormatVersion, 'dataVersion': self.getLatestVersionNumber()[1], 'lastUpdateTime': time.time()}))

		replytext = "MtG card database successfully updated (Changelog: http://mtgjson.com/changelog.html)"
		if shouldUpdateDefinitions:
			#Download the definitions too, and add them to the definitions we found in the card texts
			success, downloadedDefinitions = self.downloadDefinitions(definitions)
			if success:
				replytext += ", definitions also updated"
			else:
				replytext += ", but an error occurred when trying to download the definitions, check the logs for the error"
			#Save the definitions to file
			for term, definition in downloadedDefinitions.iteritems():
				definitionsFile.write(json.dumps({term: definition}))
				definitionsFile.write('\n')
			#And (try to) clean up the memory used
			del definitions
			del downloadedDefinitions

		#Since we don't need the cardfile anymore now, delete it
		os.remove(cardDatasetFilename)

		#Updating apparently uses up RAM that Python doesn't clear up soon or properly. Force it to
		re.purge()
		gc.collect()

		self.areCardfilesInUse = False
		self.logInfo("[MtG] updating database took {} seconds".format(time.time() - starttime))
		return (True, replytext)

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
			if u'\u2014' in term:  # This is the special dash, which is sometimes used in costs too
				term = term.split(u'\u2014', 1)[0]
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
			("http://mtgsalvation.gamepedia.com/List_of_Magic_slang", "mw-body")]
		try:
			for url, section in definitionSources:
				defHeaders = BeautifulSoup(requests.get(url, timeout=10.0).text.replace('\n', ''), 'html.parser').find(class_=section).find_all(['h3', 'h4'])
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
					paragraphText = u""
					#If there's no next_sibling, 'currentParagraph' is set to None. Check for that
					while currentParagraph and currentParagraph.name in ('p', 'ul', 'dl', 'ol'):
						paragraphText += u" " + currentParagraph.text
						currentParagraph = currentParagraph.next_sibling
					paragraphText = re.sub(" ?\[\d+?]", "", paragraphText).lstrip().rstrip(' .')  #Remove the reference links ('[1]')
					if len(paragraphText) == 0:
						self.logWarning("[MTG] Definition for '{}' is empty, skipping".format(keyword))
						continue
					newDefinitions[keyword] = paragraphText
		except Exception as e:
			self.logError("[MTG] [DefinitionsUpdate] An error ({}) occurred: {}".format(type(e), e.message))
			traceback.print_exc()
			try:
				self.logError("[MTG] request url:", e.request.url)
				self.logError("[MTG] request headers:", e.request.headers)
			except AttributeError:
				self.logError(" no request attribute found")
			return (False, newDefinitions)
		return (True, newDefinitions)
