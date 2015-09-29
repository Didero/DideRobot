# -*- coding: utf-8 -*-

import json, os, random, re, time, urllib, zipfile
import traceback

import requests
from bs4 import BeautifulSoup

from CommandTemplate import CommandTemplate
import GlobalStore
import SharedFunctions
from IrcMessage import IrcMessage


class Command(CommandTemplate):
	triggers = ['mtg', 'mtgf', 'mtgb', 'magic']
	helptext = "Looks up info on Magic: The Gathering cards. Provide a card name or regex to search for, or 'random' for a surprise. "
	helptext += "Or use 'search' with key-value attribute pairs for more control, see http://mtgjson.com/ for available attributes. "
	helptext += "{commandPrefix}mtgf adds the flavor text and sets to the output. {commandPrefix}mtgb or '{commandPrefix}mtg booster' opens a boosterpack"
	scheduledFunctionTime = 172800.0  #Every other day, since it doesn't update too often

	areCardfilesInUse = False

	def executeScheduledFunction(self):
		GlobalStore.reactor.callInThread(self.updateCardFile)
		GlobalStore.reactor.callInThread(self.updateDefinitions)

	def execute(self, message):
		"""
		:type message: IrcMessage
		"""
		#Immediately check if there's any parameters, to prevent useless work
		if message.messagePartsLength == 0:
			message.bot.say(message.source, "This command " + self.helptext[0].lower() + self.helptext[1:].format(commandPrefix=message.bot.factory.commandPrefix))
			return

		replytext = ""
		maxCardsToList = 20 if message.isPrivateMessage else 10
		addExtendedInfo = message.trigger == 'mtgf'
		searchType = message.messageParts[0].lower()

		#Check for update command before file existence, to prevent message that card file is missing after update, which doesn't make much sense
		if searchType == 'update' or searchType == 'forceupdate':
			shouldForceUpdate = True if message.message.lower() == 'forceupdate' else False
			if self.areCardfilesInUse:
				replytext = "I'm already updating!"
			elif not message.bot.factory.isUserAdmin(message.user, message.userNickname, message.userAddress):
				replytext = "Sorry, only admins can use my update function"
			else:
				replytext = self.updateCardFile(shouldForceUpdate)
				replytext += " " + self.updateDefinitions()
				#Since we're checking now, set the automatic check to start counting from now on
				self.scheduledFunctionTimer.reset()
			message.bot.say(message.source, replytext)
			return

		#Allow checking of card database version
		elif searchType == 'version':
			if not os.path.exists(os.path.join(GlobalStore.scriptfolder, 'data', 'MTGversion.json')):
				#If we don't have a version file, something's weird. Force an update to recreate all files properly
				message.bot.sendMessage(message.source, "I don't have a version file, for some reason. I'll make sure I have one by updating the card database, give me a minute")
				self.executeScheduledFunction()
				self.scheduledFunctionTimer.reset()
			else:
				#Version file's there, show the version number
				with open(os.path.join(GlobalStore.scriptfolder, 'data', 'MTGversion.json'), 'r') as versionfile:
					versions = json.load(versionfile)
				message.bot.sendMessage(message.source, "My card database is based on version {} from www.mtgjson.com".format(versions['version']))
			#Regardless, we don't need to continue
			return

		#We can also search for definitions
		elif searchType == 'define':
			message.bot.say(message.source, self.getDefinition(message, addExtendedInfo))
			return

		#Check if the data file even exists
		elif not os.path.exists(os.path.join(GlobalStore.scriptfolder, 'data', 'MTGcards.json')):
			if self.areCardfilesInUse:
				replytext = "I don't have my card database, but I'm solving that problem as we speak! Try again in, oh,  10, 15 seconds"
			else:
				replytext = "Sorry, I don't appear to have my card database. I'll try to retrieve it though! Give me 20 seconds, tops"
				GlobalStore.reactor.callInThread(self.updateCardFile, True)
			message.bot.say(message.source, replytext)
			return

		elif searchType == 'booster' or message.trigger == 'mtgb':
			if (searchType == 'booster' and message.messagePartsLength == 1) or (message.trigger == 'mtgb' and message.messagePartsLength == 0):
				message.bot.sendMessage(message.source, "Please provide a set name, so I can open a boosterpack from that set. Or use 'random' to have me pick one")
				return
			if not os.path.exists(os.path.join(GlobalStore.scriptfolder, 'data', 'MTGsets.json')):
				message.bot.sendMessage(message.source, "I'm sorry, I don't seem to have my set file. I'll retrieve it, give me a minute and try again")
				self.executeScheduledFunction()
				self.scheduledFunctionTimer.reset()
				return
			setname = ' '.join(message.messageParts[1:]).lower() if searchType == 'booster' else message.message.lower()
			message.bot.sendMessage(message.source, self.openBoosterpack(setname)[1])
			return


		#If we reached here, we're gonna search through the card store
		searchDict = {}
		# If there is an actual search (with colon key-value separator OR a random card is requested with specific search requirements
		if (searchType == 'search' and ':' in message.message) or (searchType in ['random', 'randomcommander'] and message.messagePartsLength > 1):
			#Advanced search!
			if message.messagePartsLength <= 1:
				message.bot.say(message.source, "Please provide an advanced search query too, in JSON format, so 'key1: value1, key2: value2'. Look on www.mtgjson.com for available fields")
				return

			#Turn the search string (not the argument) into a usable dictionary, case-insensitive,
			searchDict = SharedFunctions.stringToDict(" ".join(message.messageParts[1:]).lower(), True)
			if len(searchDict) == 0:
				message.bot.say(message.source, "That is not a valid search query. It should be entered like JSON, so 'name: ooze, type: creature,...'. "
												"For a list of valid keys, see http://mtgjson.com/#cards (though not all keys may be available)")
				return
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
		searchTermsToCorrect = {'set': ['sets'], 'colors': ['color', 'colour', 'colours'], 'type': ['types', 'supertypes', 'subtypes'], 'flavor': ['flavour']}
		for correctTerm, listOfWrongterms in searchTermsToCorrect.iteritems():
			for wrongTerm in listOfWrongterms:
				if wrongTerm in searchDict:
					if correctTerm not in searchDict:
						searchDict[correctTerm] = searchDict[wrongTerm]
					searchDict.pop(wrongTerm)

		#Turn the search strings into actual regexes
		regexDict = {}
		errors = []
		for attrib, query in searchDict.iteritems():
			regex = None
			try:
				#Since the query is a string, and the card data is unicode, convert the query to unicode before turning it into a regex
				# This fixes the module not finding a literal search for 'Ætherling', for instance
				regex = re.compile(unicode(query, encoding='utf8'), re.IGNORECASE)
			except (re.error, SyntaxError) as e:
				self.logError("[MTG] Regex error when trying to parse '{}': {}".format(query, e))
				errors.append(attrib)
			except UnicodeDecodeError as e:
				self.logError("[MTG] Unicode error in key '{}': {}".format(attrib, e))
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
			message.bot.say(message.source, replytext)
			return

		#All entered data is valid, look through the stored cards
		with open(os.path.join(GlobalStore.scriptfolder, 'data', 'MTGcards.json')) as jsonfile:
			cardstore = json.load(jsonfile)

		#Get the 'setname' search separately, so we can iterate over the rest later
		setRegex = regexDict.pop('set', None)

		setKeys = ['flavor', 'rarity']
		for cardname in cardstore.keys():
			carddata = cardstore[cardname]

			#First check if we need to see if the sets match
			if setRegex:
				setMatchFound = False
				for setname in carddata[1]:
					if setRegex.search(setname):
						setMatchFound = True
						carddata[1]['_match'] = setname
						break
				if not setMatchFound:
					del cardstore[cardname]
					continue

			#Then check if the rest of the attributes match
			for attrib in regexDict:
				#Some data is stored in the card data, some in the set data, because it differs per set (rarity e.d.)
				if attrib in setKeys:
					matchesFound = []
					for setname, setdata in carddata[1].iteritems():
						if attrib in setdata and regexDict[attrib].search(setdata[attrib]):
							matchesFound.append(setname)
					#No matches found, throw out the card and move on
					if len(matchesFound) == 0:
						del cardstore[cardname]
						break
					#Store the fact that we found a match in a particular set, for future lookup
					else:
						carddata[1]['_match'] = random.choice(matchesFound)
				#Most data is stored as general card data
				else:
					if attrib not in carddata[0] or not regexDict[attrib].search(carddata[0][attrib]):
						#If the wanted attribute is either not in the card, or it doesn't match, throw it out
						del cardstore[cardname]
						#No need to keep looking either
						break

		numberOfCardsFound = len(cardstore)
		#Pick a random card if needed and possible
		if searchType.startswith('random') and numberOfCardsFound > 0:
			randomCardname = random.choice(cardstore.keys())
			cardstore = {randomCardname: cardstore[randomCardname]}
			numberOfCardsFound = 1

		if numberOfCardsFound == 0:
			replytext += "Sorry, no card matching your query was found"
		elif numberOfCardsFound == 1:
			setname = cardstore[cardstore.keys()[0]][1].pop('_match', None)
			replytext += self.getFormattedCardInfo(cardstore[cardstore.keys()[0]], addExtendedInfo, setname)
		else:
			nameMatchedCardFound = False
			#If there was a name search, check if the literal name is in the resulting cards
			if 'name' in searchDict and searchDict['name'] in cardstore:
				#If the search returned a setmatch, it's in a '_match' field, retrieve that
				setname = cardstore[searchDict['name']][1].pop('_match', None)
				replytext += self.getFormattedCardInfo(cardstore[searchDict['name']], addExtendedInfo, setname)
				del cardstore[searchDict['name']]
				numberOfCardsFound -= 1
				nameMatchedCardFound = True

			#Pick some cards to show
			cardnames = []
			if numberOfCardsFound <= maxCardsToList:
				cardnames = sorted(cardstore.keys())
			else:
				cardnames = sorted(random.sample(cardstore.keys(), maxCardsToList))
			cardnameText = ""
			for cardname in cardnames:
				cardnameText += cardstore[cardname][0]['name'].encode('utf-8') + "; "
			cardnameText = cardnameText[:-2]

			if nameMatchedCardFound:
				replytext += " ({:,} more match{} found: ".format(numberOfCardsFound, 'es' if numberOfCardsFound > 1 else '')
			else:
				replytext += "Your search returned {:,} cards: ".format(numberOfCardsFound)
			replytext += cardnameText
			if numberOfCardsFound > maxCardsToList:
				replytext += " and {:,} more".format(numberOfCardsFound - maxCardsToList)
			#Since the extra results list is bracketed when a literal match was also found, it needs a closing bracket
			if nameMatchedCardFound:
				replytext += ")"

		re.purge()  #Clear the stored regexes, since we don't need them anymore
		message.bot.say(message.source, replytext)

	@staticmethod
	def getFormattedCardInfo(carddata, addExtendedInfo=False, setname=None):
		card = carddata[0]
		sets = carddata[1]
		#Since the 'name' field is Unicode, this is a Unicode object
		# Keep it like that, since any field may have Unicode characters. Convert at the end to prevent encoding errors
		replytext = card['name']
		if 'type' in card and len(card['type']) > 0:
			replytext += u" [{card[type]}]"
		if 'manacost' in card:
			replytext += u" ({card[manacost]}"
			#Only add the cumulative mana cost if it's different from the total cost (No need to say '3 mana, 3 total')
			if 'cmc' in card and card['cmc'] != card['manacost']:
				replytext += u", CMC {card[cmc]}"
			#If no cmc is shown, specify the number is the manacost
			else:
				replytext += u" mana"
			replytext += u")"
		if 'power' in card and 'toughness' in card:
			replytext += u" ({card[power]}/{card[toughness]} P/T)"
		if 'loyalty' in card:
			replytext += u" ({card[loyalty]} loyalty)"
		if 'hand' in card or 'life' in card:
			replytext += u" ("
			if 'hand' in card:
				replytext += u"{card[hand]} handmod"
			if 'hand' in card and 'life' in card:
				replytext += u", "
			if 'life' in card:
				replytext += u"{card[life]} lifemod"
			replytext += u")"
		if 'layout' in card and card['layout'] != 'normal':
			replytext += u" (Layout is '{card[layout]}'"
			if 'names' in card:
				replytext += u", also contains {names}".format(names=card['names'])
			replytext += u")"
		replytext += u"."
		#All cards have a 'text' key set, it's just empty on ones that didn't have one
		if len(card['text']) > 0:
			replytext += u" {card[text]}"
		if addExtendedInfo:
			if not setname or setname not in sets:
				setname = random.choice(sets.keys())
			if 'flavor' in sets[setname]:
				replytext += u" Flavor: " + sets[setname]['flavor']
			maxSetsToDisplay = 4
			setcount = len(sets)
			setlist = sets.keys()
			if setcount > maxSetsToDisplay:
				setlist = random.sample(setlist, maxSetsToDisplay)
			replytext += u" [in set{} ".format('s' if setcount > 1 else '')
			for setname in setlist:
				#Make the display 'setname [first letter of rarity]', so 'Magic 2015 [R]'
				rarity = sets[setname]['rarity']
				if rarity == 'Basic Land':
					rarity = 'L'
				else:
					rarity = rarity[0]
				replytext += u"{} [{}]; ".format(setname, rarity)
			replytext = replytext[:-2]  #Remove the last ': '
			if setcount > maxSetsToDisplay:
				replytext += u" and {:,} more".format(setcount - maxSetsToDisplay)
			replytext += u"]"
		#No extra set info, but still add a warning if it's in a non-legal set
		else:
			for illegalSet in ['Happy Holidays', 'Unglued', 'Unhinged']:
				if illegalSet in sets:
					replytext += u" [in illegal set {}!]".format(illegalSet)
					break

		#FILL THAT SHIT IN (encoded properly)
		replytext = replytext.format(card=card).encode('utf-8')
		return replytext

	def getDefinition(self, message, addExtendedInfo=False):
		if not os.path.exists(os.path.join(GlobalStore.scriptfolder, 'data', 'MTGdefinitions.json')):
			if self.areCardfilesInUse:
				return "I'm sorry, but my definitions file seems to missing. Don't worry, I'm making up-I mean reading up on the rules as we speak. Try again in a bit!"
			else:
				GlobalStore.reactor.callInThread(self.updateDefinitions)
				return "I'm sorry, I don't seem to have my definitions file. I'll go retrieve it now, try again in a couple of seconds"
		with open(os.path.join(GlobalStore.scriptfolder, 'data', 'MTGdefinitions.json'), 'r') as definitionsFile:
			definitions = json.load(definitionsFile)
		searchterm = " ".join(message.messageParts[1:]).lower()
		try:
			searchRegex = re.compile(searchterm)
		except re.error:
			return "That is not valid regex. Please check for typos, and try again"
		possibleDefinitions = []
		for keyword in definitions:
			if re.search(searchRegex, keyword):
				possibleDefinitions.append(keyword)
		if len(possibleDefinitions) == 0:
			#If nothing was found, search again, but this time check the definitions themselves
			for keyword, defdict in definitions.iteritems():
				if re.search(searchRegex, defdict['short']):
					possibleDefinitions.append(keyword)
		possibleDefinitionsCount = len(possibleDefinitions)
		if possibleDefinitionsCount == 0:
			return "Sorry, I don't have any info on that term. If you think it's important, poke my owner(s)!"
		elif possibleDefinitionsCount == 1:
			keyword = possibleDefinitions[0]
			replytext = "{}: {}.".format(keyword, definitions[keyword]['short'])
			currentReplyLength = len(replytext)
			if addExtendedInfo and 'extra' in definitions[keyword]:
				replytext += " " + definitions[keyword]['extra']
				#MORE INFO
				maxLength = 300
				if not message.isPrivateMessage and currentReplyLength + len(definitions[keyword]['extra']) > maxLength:
					textLeft = replytext[maxLength:]
					replytext = replytext[:maxLength] + " [continued in notices]"
					counter = 1
					while len(textLeft) > 0:
						GlobalStore.reactor.callLater(0.2 * counter, message.bot.sendMessage, message.userNickname, u"({}) {}".format(counter + 1, textLeft[:maxLength]), 'notice')
						textLeft = textLeft[maxLength:]
						counter += 1
			return replytext
		else:
			if searchterm in possibleDefinitions:
				possibleDefinitions.remove(searchterm)
				possibleDefinitionsCount -= 1
				replytext = "{}: {}; {:,} more matching definitions found".format(searchterm, definitions[searchterm]['short'], possibleDefinitionsCount)
			else:
				replytext = "Your search returned {:,} results, please be more specific".format(possibleDefinitionsCount)
			if possibleDefinitionsCount < 10:
				replytext += ": {}".format(u"; ".join(possibleDefinitions))
			replytext += "."
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
				#Match found!
				if askedSetnameRegex.search(setname):
					#If we hadn't found a match previously, store this name
					if properSetname == u'':
						properSetname = setname
					else:
						#A match has been found previously. We can't make a boosterpack from two sets, so show an error
						return (False, "That setname matches at least two sets, '{}' and '{}'. I can't make a boosterpack from more than one set. "
									   "Please be a bit more specific".format(setname, properSetname))
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

		#Get all cards from that set
		with open(os.path.join(GlobalStore.scriptfolder, 'data', 'MTGcards.json'), 'r') as jsonfile:
			cardstore = json.load(jsonfile)
		#A dictionary with the found cards, sorted by rarity
		possibleCards = {}
		#First fill in the required rarities
		for rarity in boosterRarities:
			possibleCards[rarity.lower()] = []
		for i in xrange(0, len(cardstore)):
			cardname, carddata = cardstore.popitem()
			if properSetname not in carddata[1]:
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
				return (False, u"No cards with rarity '{}' found, and I can't make a booster pack without it!".format(rarity))
			elif len(possibleCards[rarity]) < count:
				return (False, u"That set doesn't contain enough '{}'-rarity cards for a boosterpack. "
							   u"I need {:,}, but I only found {:,}".format(rarity, boosterRarities[rarity], len(possibleCards[rarity])))

		#Draw the cards!
		replytext = "Boosterpack for '{}' contains: ".format(properSetname.encode('utf-8'))
		for rarity, count in boosterRarities.iteritems():
			rarityText = SharedFunctions.makeTextBold(rarity.capitalize())
			cardlist = "; ".join(random.sample(possibleCards[rarity], count)).encode('utf-8')
			replytext += "{}: {}. ".format(rarityText, cardlist)
		return (True, replytext)


	def updateCardFile(self, forceUpdate=False):
		starttime = time.time()
		replytext = ""
		cardsJsonFilename = os.path.join(GlobalStore.scriptfolder, 'data', 'MTGcards.json')
		setsJsonFilename = os.path.join(GlobalStore.scriptfolder, 'data', 'MTGsets.json')

		latestFormatVersion = "3.3.1"

		versionFilename = os.path.join(GlobalStore.scriptfolder, 'data', 'MTGversion.json')
		storedVersion = "0.00"
		storedFormatVersion = "0.00"
		latestVersion = ""
		#Load in the currently stored version number
		if not os.path.exists(versionFilename):
			self.logWarning("[MtG] No old card database version file found!")
		else:
			with open(versionFilename) as oldversionfile:
				oldversiondata = json.load(oldversionfile)
				if 'version' in oldversiondata:
					storedVersion = oldversiondata['version']
				else:
					self.logError("[MtG] Unexpected content of stored version file:")
					for key, value in oldversiondata.iteritems():
						self.logError("  {}: {}".format(key, value))
					return "Something went wrong when reading the stored version number."
				if '_formatVersion' in oldversiondata:
					storedFormatVersion = oldversiondata['_formatVersion']
				else:
					self.logWarning("[MTG] No stored format version found")

		#Download the latest version file
		url = "http://mtgjson.com/json/version-full.json"
		newversionfilename = os.path.join(GlobalStore.scriptfolder, 'data', url.split('/')[-1])
		urllib.urlretrieve(url, newversionfilename)

		#Load in that version file
		with open(newversionfilename) as newversionfile:
			versiondata = json.load(newversionfile)
			if 'version' in versiondata:
				latestVersion = versiondata['version']
			else:
				self.logWarning("[MtG] Unexpected contents of downloaded version file:")
				for key, value in versiondata.iteritems():
					self.logWarning(" {}: {}".format(key, value))
				return "Something went wrong when trying to read the downloaded version file"
		if latestVersion == "":
			return "Something went wrong, the latest MtG database version number could not be retrieved."

		self.logInfo("[MTG] Done version-checking at {} seconds in".format(time.time() - starttime))

		#Now let's check if we need to update the cards
		if forceUpdate or latestVersion != storedVersion or latestFormatVersion != storedFormatVersion or not os.path.exists(cardsJsonFilename) or not os.path.exists(setsJsonFilename):
			self.areCardfilesInUse = True
			self.logInfo("[MtG] Updating card database!")
			url = "http://mtgjson.com/json/AllSets.json.zip"  #Use the small dataset, since we don't use the rulings anyway and this way RAM usage is WAY down
			cardzipFilename = os.path.join(GlobalStore.scriptfolder, 'data', url.split('/')[-1])
			urllib.urlretrieve(url, cardzipFilename)

			#Since it's a zip, extract it
			zipWithJson = zipfile.ZipFile(cardzipFilename, 'r')
			newcardfilename = os.path.join(GlobalStore.scriptfolder, 'data', zipWithJson.namelist()[0])
			if os.path.exists(newcardfilename):
				os.remove(newcardfilename)
			zipWithJson.extractall(os.path.join(GlobalStore.scriptfolder, 'data'))
			zipWithJson.close()
			#We don't need the zip anymore
			os.remove(cardzipFilename)

			#Load in the new file so we can save it in our preferred format (not per set, but just a dict of cards)
			downloadedCardstore = {}
			with open(newcardfilename, 'r') as newcardfile:
				downloadedCardstore = json.load(newcardfile)
			#Remove the file downloaded from MTGjson.com, since we've got the data in memory now
			os.remove(newcardfilename)

			newcardstore = {}
			setstore = {'_setsWithBoosterpacks': []}
			keysToChange = {'keysToRemove': ['border', 'id', 'imageName', 'number', 'releaseDate', 'reserved', 'starter',
											 'subtypes', 'supertypes', 'timeshifted', 'types', 'variations'],
							'numberKeysToMakeString': ['cmc', 'hand', 'life', 'loyalty', 'multiverseid'],
							'listKeysToMakeString': ['colors', 'names'],
							'keysToFormatNicer': ['flavor', 'manacost', 'text']}
			raritiesToRemove = ('marketing', 'checklist', 'foil', 'power nine', 'draft-matters', 'timeshifted purple', 'double faced')
			raritiesToRename = {'land': 'basic land', 'urza land': 'land — urza’s'}  #Non-standard rarities are interpreted as regexes for type
			rarityPrefixesToRemove = {'foil ': 5, 'timeshifted ': 12}  #The numbers are the string length, saves a lot of 'len()' calls
			# This function will be called on the 'keysToFormatNicer' keys
			#  Made into a function, because it's used in two places
			def formatNicer(text):
				#Remove brackets around mana cost
				if '{' in text:
					text = text.replace('}{', ' ').replace('{', '').replace('}', '')
				#Replace newlines with spaces. If the sentence adds in a letter, add a period
				text = re.sub('(?<=\w)\n', '. ', text).replace('\n', ' ')
				#Prevent double spaces
				text = text.replace('  ', ' ').strip()
				return text

			#Use the keys instead of iteritems() so we can pop off the set we need, to reduce memory usage
			for setcount in xrange(0, len(downloadedCardstore)):
				setcode, setData = downloadedCardstore.popitem()
				#Put the cardlist in a separate variable, so we can store all the set information easily
				cardlist = setData.pop('cards')
				#The 'booster' set field is a bit verbose, make that shorter and easier to use
				if 'booster' in setData:
					#Keep a list of sets that have booster packs
					setstore['_setsWithBoosterpacks'].append(setData['name'].lower())
					originalBoosterList = setData.pop('booster')
					countedBoosterData = {}
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
										#...and put in the choice without the prefix
										rarity.append(choice[rarityPrefixesToRemove[rp]:])
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
					setData['booster'] = countedBoosterData
				setstore[setData['name'].lower()] = setData

				#Again, pop off cards when we need them, to save on memory
				for cardcount in xrange(0, len(cardlist)):
					card = cardlist.pop(0)
					cardname = card['name'].lower()  #lowering the keys makes searching easier later, especially when comparing against the literal searchstring

					#If the card isn't in the store yet, parse its data
					if cardname not in newcardstore:
						#Remove some useless data to save some space, memory and time
						for keyToRemove in keysToChange['keysToRemove']:
							if keyToRemove in card:
								del card[keyToRemove]

						#No need to store there's nothing special about the card's layout
						if 'layout' in card and card['layout'] == 'normal':
							del card['layout']

						#The 'Colors' field benefits from some ordering, for readability.
						if 'colors' in card:
							card['colors'] = sorted(card['colors'])

						#Remove the current card from the list of names this card also contains (for flip cards)
						# (Saves on having to remove it later, and the presence of this field shows it's in there too)
						if 'names' in card:
							card['names'].remove(card['name'])

						#Make sure all stored values are strings, that makes searching later much easier
						for attrib in keysToChange['numberKeysToMakeString']:
							if attrib in card:
								card[attrib] = unicode(card[attrib])
						for attrib in keysToChange['listKeysToMakeString']:
							if attrib in card:
								card[attrib] = u"; ".join(card[attrib])

						#Make 'manaCost' lowercase, since we make the searchstring lowercase too, and we don't want to miss this
						if 'manaCost' in card:
							card['manacost'] = card['manaCost']
							del card['manaCost']

						for keyToFormat in keysToChange['keysToFormatNicer']:
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

			#First delete the original files
			if os.path.exists(cardsJsonFilename):
				os.remove(cardsJsonFilename)
			if os.path.exists(setsJsonFilename):
				os.remove(setsJsonFilename)
			#Save the new databases to disk
			with open(cardsJsonFilename, 'w') as cardfile:
				#json.dump(cards, cardfile) #This is dozens of seconds slower than below
				cardfile.write(json.dumps(newcardstore))
			with open(setsJsonFilename, 'w') as setsfile:
				setsfile.write(json.dumps(setstore))

			#Replace the old version file with the new one
			versiondata['_formatVersion'] = latestFormatVersion
			with open(versionFilename, 'w') as versionFile:
				versionFile.write(json.dumps(versiondata))

			replytext = "MtG card database successfully updated from version {} to {} (Changelog: http://mtgjson.com/#changeLog).".format(storedVersion, latestVersion)
		#No update was necessary
		else:
			replytext = "No card update needed, I already have the latest MtG card database version (v {}).".format(latestVersion)

		os.remove(newversionfilename)
		urllib.urlcleanup()
		self.areCardfilesInUse = False
		self.logInfo("[MtG] updating database took {} seconds".format(time.time() - starttime))
		return replytext

	def updateDefinitions(self):
		starttime = time.time()
		definitions = {}
		textCutoffLength = 200
		replytext = "Nothing happened..."

		self.areCardfilesInUse = True
		definitionSources = [("http://en.m.wikipedia.org/wiki/List_of_Magic:_The_Gathering_keywords", "content"),
			("http://mtgsalvation.gamepedia.com/List_of_Magic_slang", "mw-body")]
		try:
			for url, section in definitionSources:
				defHeaders = BeautifulSoup(requests.get(url).text.replace('\n', '')).find(class_=section).find_all(['h3', 'h4'])
				for defHeader in defHeaders:
					keyword = defHeader.find(class_='mw-headline').text.lower()
					#On MTGSalvation, sections are sorted into alphabetized subsections. Ignore the letter headers
					if len(keyword) <= 1:
						continue
					#Report duplicate definitions, and keep the original
					if keyword in definitions:
						self.logWarning("[MTG] [DefinitionsUpdate] Duplicate definition: '{}'".format(keyword))
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
					definitions[keyword] = {}
					if len(paragraphText) < textCutoffLength:
						definitions[keyword]['short'] = paragraphText
					else:
						splitIndex = paragraphText.rfind('.', 0, textCutoffLength)
						definitions[keyword]['short'] = paragraphText[:splitIndex].lstrip()
						definitions[keyword]['extra'] = paragraphText[splitIndex + 1:].lstrip()
			self.logInfo("[MTG] Updating definitions took {} seconds".format(time.time() - starttime))
		except Exception as e:
			self.logError("[MTG] [DefinitionsUpdate] An error ({}) occurred: {}".format(type(e), e.message))
			traceback.print_exc()
			try:
				self.logError("[MTG] request url:", e.request.url)
				self.logError("[MTG] request headers:", e.request.headers)
			except AttributeError:
				self.logError(" no request attribute found")
			replytext = "Definitions file NOT updated, check log for errors"
		else:
			#Save the data to disk
			with open(os.path.join(GlobalStore.scriptfolder, "data", "MTGdefinitions.json"), 'w') as definitionsFile:
				definitionsFile.write(json.dumps(definitions))
			replytext = "Definitions file successfully updated"
		finally:
			self.areCardfilesInUse = False
		return replytext
