# -*- coding: utf-8 -*-

import gc, json, os, random, re, time, zipfile
import traceback

import requests
from bs4 import BeautifulSoup
import gevent

from CommandTemplate import CommandTemplate
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
	dataFormatVersion = '4.0'

	def executeScheduledFunction(self):
		if not self.areCardfilesInUse and self.shouldUpdate():
			self.updateCardFile()

	def execute(self, message):
		"""
		:type message: IrcMessage
		"""
		#Immediately check if there's any parameters, to prevent useless work
		if message.messagePartsLength == 0:
			message.reply("This command " + self.helptext[0].lower() + self.helptext[1:].format(commandPrefix=message.bot.commandPrefix))
			return

		#If the card set is currently being updated, we probably shouldn't try loading it
		if self.areCardfilesInUse:
			message.reply("I'm currently updating my card datastore, sorry! If you try again in, oh, 10 seconds, I should be done. You'll be the first to look through the new cards!")
			return

		#Check if we have all the files we need
		for fn in ('cards', 'definitions', 'sets', 'version'):
			if not os.path.isfile(os.path.join(GlobalStore.scriptfolder, 'data', 'MTG{}.json'.format(fn))):
				message.reply("Whoops, I don't seem to have all the files I need. I'll update now, retry again in like 15 seconds. Sorry!", "say")
				self.resetScheduledFunctionGreenlet()
				self.updateCardFile(True)
				return

		addExtendedInfo = message.trigger == 'mtgf'
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
			message.reply(self.getDefinition(message, addExtendedInfo))
			return

		elif searchType == 'booster' or message.trigger == 'mtgb':
			if (searchType == 'booster' and message.messagePartsLength == 1) or (message.trigger == 'mtgb' and message.messagePartsLength == 0):
				message.reply("Please provide a set name, so I can open a boosterpack from that set. Or use 'random' to have me pick one")
				return
			setname = ' '.join(message.messageParts[1:]).lower() if searchType == 'booster' else message.message.lower()
			message.reply(self.openBoosterpack(setname)[1])
			return

		#Check if the user passed valid search terms
		parseSuccess, searchDict = self.parseSearchParameters(searchType, message)
		if not parseSuccess:
			#If an error occurred, the second returned parameter isn't the searchdict but an error message
			message.reply(searchDict, "say")
			return
		#Check if the entered search terms can be converted to the regex we need
		parseSuccess, regexDict = self.searchDictToRegexDict(searchDict)
		if not parseSuccess:
			#Again, 'regexDict' is the error string if an error occurred
			message.reply(regexDict)
			return
		matchingCards = self.searchCardStore(regexDict)
		#Clear the stored regexes, since we don't need them anymore
		del regexDict
		re.purge()
		#Done, show the formatted result
		message.reply(self.formatSearchResult(matchingCards, addExtendedInfo, searchType.startswith('random'), 20 if message.isPrivateMessage else 10,
														searchDict.get('name', None), len(searchDict) > 0))

	@staticmethod
	def parseSearchParameters(searchType, message):
		#If we reached here, we're gonna search through the card store
		searchDict = {}
		# If there is an actual search (with colon key-value separator OR a random card is requested with specific search requirements
		if (searchType == 'search' and ':' in message.message) or (searchType in ('random', 'randomcommander') and message.messagePartsLength > 1):
			#Advanced search!
			if message.messagePartsLength <= 1:
				return (False, "Please provide an advanced search query too, in JSON format, so 'key1: value1, key2: value2'. "
							  "Look on http://mtgjson.com/documentation.html#cards for available fields, though not all of them may work. "
							  "The values support regular expressions as well")

			#Turn the search string (not the argument) into a usable dictionary, case-insensitive,
			searchDict = SharedFunctions.stringToDict(" ".join(message.messageParts[1:]).lower(), True)
			if len(searchDict) == 0:
				return (False, "That is not a valid search query. It should be entered like JSON, so 'name: ooze, type: creature,...'. "
							  "For a list of valid keys, see http://mtgjson.com/documentation.html#cards (though not all keys may be available)")
		#If the searchtype is just 'random', don't set a 'name' field so we don't go through all the cards first
		#  Otherwise, set the whole message as the 'name' search, since that's the default search
		elif not searchType.startswith('random'):
			searchDict['name'] = message.message.lower()

		#Commander search. Regardless of everything else, it has to be a legendary creature
		if searchType == 'randomcommander':
			if 'type' not in searchDict:
				searchDict['type'] = ""
			#Don't just search for 'legendary creature.*', because there are legendary artifact creatures too
			searchDict['type'] = 'legendary.+creature.*' + searchDict['type']

		#Correct some values, to make searching easier (so a search for 'set' or 'sets' both work)
		searchTermsToCorrect = {'set': ('sets',), 'colors': ('color', 'colour', 'colours'), 'type': ('types', 'supertypes', 'subtypes'), 'flavor': ('flavour',)}
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
			try:
				#Since the query is a string, and the card data is unicode, convert the query to unicode before turning it into a regex
				# This fixes the module not finding a literal search for 'Ætherling', for instance
				regex = re.compile(unicode(query, encoding='utf8'), re.IGNORECASE)
			except (re.error, SyntaxError):
				#Try parsing the string again as an escaped string, so mismatched brackets for instance aren't a problem
				try:
					regex = re.compile(unicode(re.escape(query), encoding='utf8'), re.IGNORECASE)
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
		setKeys = ('flavor', 'rarity')

		matchingCards = {}
		with open(os.path.join(GlobalStore.scriptfolder, 'data', 'MTGcards.json')) as jsonfile:
			for cardline in jsonfile:
				cardDict = json.loads(cardline)
				cardname = cardDict.keys()[0]

				#First check if we need to see if the sets match
				if setRegex:
					setMatchFound = False
					for setname in cardDict[cardname][1]:
						if setRegex.search(setname):
							setMatchFound = True
							cardDict[cardname][1]['_match'] = setname
							break
					if not setMatchFound:
						continue

				#Then check if the rest of the attributes match
				for attrib in regexDict:
					#Some data is stored in the card data, some in the set data, because it differs per set (rarity e.d.)
					if attrib in setKeys:
						matchesFound = []
						for setname, setdata in cardDict[cardname][1].iteritems():
							if attrib in setdata and regexDict[attrib].search(setdata[attrib]):
								matchesFound.append(setname)
						#No matches found, move on
						if len(matchesFound) == 0:
							break
						#Store the fact that we found a match in a particular set, for future lookup
						else:
							cardDict[cardname][1]['_match'] = random.choice(matchesFound)
					#Most data is stored as general card data
					else:
						if attrib not in cardDict[cardname][0] or not regexDict[attrib].search(cardDict[cardname][0][attrib]):
							#If the wanted attribute is either not in the card, or it doesn't match, move on
							break
				else:
					#If we didn't break from the loop, then the card matched all search criteria. Store it
					matchingCards[cardname] = cardDict[cardname]
		return matchingCards

	def formatSearchResult(self, cardstore, addExtendedCardInfo, pickRandomCard, maxCardsToList=10, nameToMatch=None, addResultCount=True):
		replytext = ""
		numberOfCardsFound = len(cardstore)

		if numberOfCardsFound == 0:
			return "Sorry, no card matching your query was found"

		if pickRandomCard:
			cardname = random.choice(cardstore.keys())
			cardstore = {cardname: cardstore[cardname]}
		#If the name we have to match is in there literally, lift it out
		# (For instance, a search for 'Mirror Entity' returns 'Mirror Entity' and 'Mirror Entity Avatar'.
		# Show the full info on 'Mirror Entity' but also report we found more matches)
		elif nameToMatch and nameToMatch in cardstore:
			cardstore = {nameToMatch: cardstore[nameToMatch]}

		#If there's only one card found, just display it
		# Use 'len()' instead of 'numberOfCardsFound' because 'pickRandomCard' or 'nameToMatch' could've changed it,
		# and we need the cardcount var to show how many cards we found at the end
		if len(cardstore) == 1:
			setname = cardstore[cardstore.keys()[0]][1].pop('_match', None)
			replytext += self.getFormattedCardInfo(cardstore[cardstore.keys()[0]], addExtendedCardInfo, setname, len(replytext))
			#We may have culled the cardstore list, so there may have been more matches initially. List a count of those
			if addResultCount and numberOfCardsFound > 1:
				replytext += " ({:,} more match{} found)".format(numberOfCardsFound - 1, 'es' if numberOfCardsFound > 2 else '')  #==2 because we subtract 1
			return replytext

		#Check if we didn't find more matches than we're allowed to show
		if numberOfCardsFound <= maxCardsToList:
			cardnames = sorted(cardstore.keys())
		else:
			cardnames = sorted(random.sample(cardstore.keys(), maxCardsToList))

		#Create a list of card names
		cardnameText = ""
		for cardname in cardnames:
			cardnameText += cardstore[cardname][0]['name'].encode('utf-8') + "; "
		cardnameText = cardnameText[:-2]

		replytext += "Your search returned {:,} cards: ".format(numberOfCardsFound)
		replytext += cardnameText
		if numberOfCardsFound > maxCardsToList:
			replytext += " and {:,} more".format(numberOfCardsFound - maxCardsToList)
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
			for illegalSet in ('Happy Holidays', 'Unglued', 'Unhinged'):
				if illegalSet in sets:
					cardInfoList.append(u"in illegal set \x0304{illegalSet}\x0f!".format(illegalSet=illegalSet))  #color-code the setname red
					break

		#FILL THAT SHIT IN (encoded properly)
		separator = SharedFunctions.getGreySeparator()
		separatorLength = len(separator)
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
				replytext += separator
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

		#Remove the separator at the end, and make sure it's a string and not unicode
		replytext = replytext.rstrip(separator).rstrip().encode('utf-8')
		return replytext

	def getDefinition(self, message, addExtendedInfo=False):
		with open(os.path.join(GlobalStore.scriptfolder, 'data', 'MTGdefinitions.json'), 'r') as definitionsFile:
			definitions = json.load(definitionsFile)

		maxMessageLength = 300
		possibleDefinitions = []

		searchterm = " ".join(message.messageParts[1:]).lower()
		if searchterm == 'random':
			possibleDefinitions = [random.choice(definitions.keys())]
		else:
			try:
				searchRegex = re.compile(searchterm)
			except re.error:
				return "That is not valid regex. Please check for typos, and try again"

			for term in definitions:
				if re.search(searchRegex, term):
					possibleDefinitions.append(term)
			if len(possibleDefinitions) == 0:
				#If nothing was found, search again, but this time check the definitions themselves
				for term, definition in definitions.iteritems():
					if re.search(searchRegex, definition):
						possibleDefinitions.append(term)

		possibleDefinitionsCount = len(possibleDefinitions)
		if possibleDefinitionsCount == 0:
			return "Sorry, I don't have any info on that term. If you think it's important, poke my owner(s)!"
		elif possibleDefinitionsCount == 1:
			replytext = "{}: {}".format(SharedFunctions.makeTextBold(possibleDefinitions[0]), definitions[possibleDefinitions[0]])
			#Limit the message length
			if len(replytext) > maxMessageLength:
				splitIndex = replytext[:maxMessageLength].rfind(' ')
				textRemainder = replytext[splitIndex+1:]
				replytext = replytext[:splitIndex] + ' [...]'
				#If we do need to add the full definition, split it up properly
				if addExtendedInfo:
					#If it's a private message, we don't have to worry about spamming, so just dump the full thing
					if message.isPrivateMessage:
						gevent.spawn_later(0.2, message.bot.sendMessage, message.userNickname, textRemainder)
					# If it's in a public channel, send the message via notices
					else:
						counter = 1
						while len(textRemainder) > 0:
							gevent.spawn_later(0.2 * counter, message.bot.sendMessage, message.userNickname,
														  u"({}) {}".format(counter + 1, textRemainder[:maxMessageLength]), 'notice')
							textRemainder = textRemainder[maxMessageLength:]
							counter += 1
		#Multiple matching definitions found
		else:
			if searchterm in possibleDefinitions:
				replytext = "{}: {}".format(SharedFunctions.makeTextBold(searchterm), definitions[searchterm])
				if len(replytext) > maxMessageLength - 18:  #-18 to account for the added text later
					replytext = replytext[:maxMessageLength-24] + ' [...]'
				replytext += " ({:,} more matches)".format(possibleDefinitionsCount-1)
			else:
				replytext = "Your search returned {:,} results, please be more specific".format(possibleDefinitionsCount)
				if possibleDefinitionsCount < 10:
					replytext += ": {}".format(u"; ".join(possibleDefinitions))
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
				if setname == '_setsWithBoosterpacks':
					continue
				if askedSetnameRegex.search(setname):
					#Match found! If we hadn't found a match previously, store this name
					if properSetname == u'':
						properSetname = setname
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
		replytext = "{}{}".format(properSetname.encode('utf-8'), SharedFunctions.getGreySeparator())
		for rarity, count in boosterRarities.iteritems():
			cardlist = "; ".join(random.sample(possibleCards[rarity], count)).encode('utf-8')
			replytext += "{}: {}. ".format(SharedFunctions.makeTextBold(rarity.encode('utf-8').capitalize()), cardlist)
		return (True, replytext)

	def downloadCardDataset(self):
		url = "http://mtgjson.com/json/AllSets.json.zip"  # Use the small dataset, since we don't use the rulings anyway and this way RAM usage is WAY down
		cardzipFilename = os.path.join(GlobalStore.scriptfolder, 'data', url.split('/')[-1])
		success, extraInfo = SharedFunctions.downloadFile(url, cardzipFilename)
		if not success:
			self.logError("[MTG] An error occurred while trying to download the card file: " + extraInfo.message)
			return (False, "Something went wrong while trying to download the card file.")

		# Since it's a zip, extract it
		zipWithJson = zipfile.ZipFile(cardzipFilename, 'r')
		newcardfilename = os.path.join(GlobalStore.scriptfolder, 'data', zipWithJson.namelist()[0])
		if os.path.exists(newcardfilename):
			os.remove(newcardfilename)
		zipWithJson.extractall(os.path.join(GlobalStore.scriptfolder, 'data'))
		zipWithJson.close()
		# We don't need the zip anymore
		os.remove(cardzipFilename)
		return (True, newcardfilename)

	def getLatestVersionNumber(self):
		try:
			latestVersion = requests.get("http://mtgjson.com/json/version.json", timeout=10.0).text.replace('"', '')
		except requests.exceptions.Timeout:
			self.logError("[MTG] Fetching card version timed out")
			return (False, "Fetching online card version took too long")
		latestVersion = latestVersion.replace('"', '')  #Version is a quoted string, remove the quotes
		return (True, latestVersion)

	def shouldUpdate(self):
		basepath = os.path.join(GlobalStore.scriptfolder, 'data')
		#If one of the required files doesn't exist, we should update
		for filename in ('MTGversion', 'MTGcards', 'MTGsets', 'MTGdefinitions'):
			if not os.path.exists(os.path.join(basepath, filename + '.json')):
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
		setStoreFilename = os.path.join(GlobalStore.scriptfolder, 'data', 'MTGsets.json')

		#Now let's check if we need to update the cards
		self.areCardfilesInUse = True
		self.logInfo("[MtG] Updating card database!")

		#Download the wrongly-formatted (for our purposes) card data
		success, result = self.downloadCardDataset()
		if not success:
			self.logError("[MTG] An error occurred while trying to download the card file: " + result.message)
			return (False, result)
		else:
			cardDatasetFilename = result

		#Load in the new file so we can save it in our preferred format (not per set, but just a dict of cards)
		with open(cardDatasetFilename, 'r') as newcardfile:
			downloadedCardstore = json.load(newcardfile)

		newcardstore = {}
		setstore = {'_setsWithBoosterpacks': []}
		setKeysToRemove = ('border', 'magicRaritiesCodes', 'mkm_id', 'mkm_name', 'oldCode', 'onlineOnly', 'translations')
		keysToRemove = ('border', 'colorIdentity', 'id', 'imageName', 'mciNumber', 'releaseDate', 'reserved', 'starter', 'subtypes', 'supertypes', 'timeshifted', 'types', 'variations')
		layoutTypesToRemove = ('phenomenon', 'vanguard', 'plane', 'scheme')
		numberKeysToMakeString = ('cmc', 'hand', 'life', 'loyalty', 'multiverseid')
		listKeysToMakeString = ('colors', 'names')
		keysToFormatNicer = ('flavor', 'manacost', 'text')
		raritiesToRemove = ('marketing', 'checklist', 'foil', 'power nine', 'draft-matters', 'timeshifted purple', 'double faced')
		raritiesToRename = {'land': 'basic land', 'urza land': 'land — urza’s'}  #Non-standard rarities are interpreted as regexes for type
		rarityPrefixesToRemove = {'foil ': 5, 'timeshifted ': 12}  #The numbers are the string length, saves a lot of 'len()' calls
		# This function will be called on the 'keysToFormatNicer' keys
		#  Made into a function, because it's used in two places
		def formatNicer(text):
			#Remove brackets around mana cost
			if '{' in text:
				text = text.replace('}{', ' ').replace('{', '').replace('}', '')
			#Replace newlines with spaces. If the sentence ends in a letter, add a period
			text = re.sub('(?<=\w)\n', '. ', text).replace('\n', ' ')
			#Prevent double spaces
			text = text.replace('  ', ' ').strip()
			return text

		#Use the keys instead of iteritems() so we can pop off the set we need, to reduce memory usage
		for setcount in xrange(0, len(downloadedCardstore)):
			setcode, setData = downloadedCardstore.popitem()
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
					self.logError("Error while parsing booster field of set '{}' ({}): {!r}".format(setData['name'], setcode, e))
				else:
					#If no parsing error occurred, add the parsed booster data
					setData['booster'] = countedBoosterData
					# Keep a list of sets that have booster packs
					setstore['_setsWithBoosterpacks'].append(setData['name'].lower())
			setstore[setData['name'].lower()] = setData

			#Again, pop off cards when we need them, to save on memory
			for cardcount in xrange(0, len(cardlist)):
				card = cardlist.pop()
				cardname = card['name'].lower()  #lowering the keys makes searching easier later, especially when comparing against the literal searchstring

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
					for attrib in numberKeysToMakeString:
						if attrib in card:
							card[attrib] = unicode(card[attrib])
					for attrib in listKeysToMakeString:
						if attrib in card:
							card[attrib] = u"; ".join(card[attrib])

					#Make 'manaCost' lowercase, since we make the searchstring lowercase too, and we don't want to miss this
					if 'manaCost' in card:
						card['manacost'] = card['manaCost']
						del card['manaCost']

					for keyToFormat in keysToFormatNicer:
						if keyToFormat in card:
							card[keyToFormat] = formatNicer(card[keyToFormat])
					#To make searching easier later, without all sorts of key checking, make sure the 'text' key always exists
					if 'text' not in card:
						card['text'] = u""

					#Add the card as a new entry, as a tuple with the card data first and set data second
					newcardstore[cardname] = (card, {})

				#New and already listed cards need their set info stored
				cardSetInfo = {'rarity': card.pop('rarity')}
				if 'flavor' in card:
					cardSetInfo['flavor'] = formatNicer(card.pop('flavor'))
				newcardstore[cardname][1][setData['name']] = cardSetInfo

			#Don't hog the execution thread for too long, give it up after each set
			gevent.sleep(0)

		#First delete the original files
		if os.path.exists(cardStoreFilename):
			os.remove(cardStoreFilename)
		if os.path.exists(setStoreFilename):
			os.remove(setStoreFilename)
		#Save the new databases to disk
		with open(cardStoreFilename, 'w') as cardfile:
			#Write each card on a separate line, so we can stream each line instead of loading in the entire file
			for i in xrange(len(newcardstore)):
				cardname, carddata = newcardstore.popitem()
				cardfile.write(json.dumps({cardname: carddata}) + '\n')
		with open(setStoreFilename, 'w') as setsfile:
			setsfile.write(json.dumps(setstore))

		#We don't need the card info in memory anymore, saves memory for the definitions update later
		del downloadedCardstore
		del newcardstore
		del setstore

		#Store the new version data
		with open(os.path.join(GlobalStore.scriptfolder, 'data', 'MTGversion.json'), 'w') as versionFile:
			versionFile.write(json.dumps({'formatVersion': self.dataFormatVersion, 'dataVersion': self.getLatestVersionNumber()[1], 'lastUpdateTime': time.time()}))

		replytext = "MtG card database successfully updated (Changelog: http://mtgjson.com/changelog.html). "
		if shouldUpdateDefinitions:
			#Have the definitions updated too
			replytext += self.updateDefinitions(cardDatasetFilename)[1]

		#Since we don't need the cardfile anymore now, delete it
		os.remove(cardDatasetFilename)

		#Updating apparently uses up RAM that Python doesn't clear up soon or properly. Force it to
		re.purge()
		gc.collect()

		self.areCardfilesInUse = False
		self.logInfo("[MtG] updating database took {} seconds".format(time.time() - starttime))
		return (True, "Successfully updated the card database")

	def updateDefinitions(self, cardstoreLocation=None):
		starttime = time.time()
		self.areCardfilesInUse = True

		if cardstoreLocation is None:
			#Download the file ourselves
			success, result = self.downloadCardDataset()
			if not success:
				self.logError("[MTG] Error occurred while downloading file to update definitions!")
				return (False, "Sorry, I couldn't download the card file to get the definitions from")
			else:
				cardstoreLocation = result
				deleteCardstore = True
		else:
			deleteCardstore = False

		definitions = {}
		with open(cardstoreLocation, 'r') as cardfile:
			cardstore = json.load(cardfile)
		if deleteCardstore:
			os.remove(cardstoreLocation)

		#Go through all the cards to get the reminder text
		for setcount in xrange(0, len(cardstore)):
			setcode, setdata = cardstore.popitem()
			for cardcount in xrange(0, len(setdata['cards'])):
				card = setdata['cards'].pop()
				if 'text' not in card or '(' not in card['text']:
					continue
				lines = card.pop('text').splitlines()
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
						if end.isdigit() or end == 'x':
							term = term.rsplit(" ", 1)[0]
					#For some keywords, the card description just doesn't work that well. Ignore those, and get those from Wikipedia later on
					if term in ('bolster', 'kicker', 'multikicker'):
						continue
					if term not in definitions:
						#If this is a new definition, add it, after cleaning it up a bit
						definition = definition.rstrip(')')
						#Some definitions start with a cost, remove that
						if definition.startswith('{'):
							definition = definition[definition.find(':') + 1:]
						definition = definition.strip()
						#Some explanations mention the current card name. Generalize the definition
						definition = definition.replace(card['name'], 'this card')
						#Finally, add the term and definition!
						definitions[term] = definition
			#Let other code execute after every set
			gevent.sleep(0)

		#Then get possibly missed keyword definitions and slang term meanings from other sites
		definitionSources = [("http://en.m.wikipedia.org/wiki/List_of_Magic:_The_Gathering_keywords", "content"),
			("http://mtgsalvation.gamepedia.com/List_of_Magic_slang", "mw-body")]
		try:
			for url, section in definitionSources:
				defHeaders = BeautifulSoup(requests.get(url).text.replace('\n', ''), 'html.parser').find(class_=section).find_all(['h3', 'h4'])
				for defHeader in defHeaders:
					keyword = defHeader.find(class_='mw-headline').text.lower()
					#On MTGSalvation, sections are sorted into alphabetized subsections. Ignore the letter headers
					if len(keyword) <= 1:
						continue
					#Don't overwrite any definitions
					if keyword in definitions:
						continue
					#Cycle through all the paragraphs following the header
					currentParagraph = defHeader.next_sibling
					paragraphText = u""
					#If there's no next_sibling, 'currentParagraph' is set to None. Check for that
					while currentParagraph and currentParagraph.name in ['p', 'ul', 'dl', 'ol']:
						paragraphText += u" " + currentParagraph.text
						currentParagraph = currentParagraph.next_sibling
					paragraphText = re.sub(" ?\[\d+?]", "", paragraphText).lstrip().rstrip(' .')  #Remove the reference links ('[1]')
					if len(paragraphText) == 0:
						self.logWarning("[MTG] Definition for '{}' is empty, skipping".format(keyword))
						continue

					#Split the found text into a short definition and a longer description
					definitions[keyword] = paragraphText
		except Exception as e:
			self.logError("[MTG] [DefinitionsUpdate] An error ({}) occurred: {}".format(type(e), e.message))
			traceback.print_exc()
			try:
				self.logError("[MTG] request url:", e.request.url)
				self.logError("[MTG] request headers:", e.request.headers)
			except AttributeError:
				self.logError(" no request attribute found")
			replytext = "Definitions file NOT entirely updated, check the log for errors"
		else:
			replytext = "Definitions file successfully updated"
		finally:
			#If we got called without a cardfile, we're the only one updating. Since we're done, turn off the update flag
			if deleteCardstore:
				self.areCardfilesInUse = False

		with open(os.path.join(GlobalStore.scriptfolder, 'data', 'MTGdefinitions.json'), 'w') as defsFile:
			defsFile.write(json.dumps(definitions))

		self.logInfo("[MTG] Updating definitions took {} seconds".format(time.time() - starttime))
		return (True, replytext)
