# -*- coding: utf-8 -*-

import gc, json, os, random, re, sys, time, urllib, zipfile

import requests

from CommandTemplate import CommandTemplate
import GlobalStore
import SharedFunctions
from IrcMessage import IrcMessage


class Command(CommandTemplate):
	triggers = ['mtg', 'mtgf']
	helptext = "Looks up info on 'Magic The Gathering' cards. Provide a card name or a regex match to search for. Or search for 'random', and see what comes up. "
	helptext += "With the parameter 'search', you can enter JSON-style data to search for other attributes, see http://mtgjson.com/ for what's available. {commandPrefix}mtgf adds the flavor text to the result"
	scheduledFunctionTime = 172800.0  #Every other day, since it doesn't update too often

	areCardfilesInUse = False

	def executeScheduledFunction(self):
		GlobalStore.reactor.callInThread(self.updateCardFile)
		GlobalStore.reactor.callInThread(self.updateDefinitions)

	def execute(self, message):
		"""
		:type message: IrcMessage
		"""
		starttime = time.time()
		replytext = u""
		maxCardsToListInChannel = 10
		maxCardsToListInPm = 20

		searchType = u""
		if message.messagePartsLength > 0:
			searchType = message.messageParts[0].lower()

		if message.messagePartsLength == 0:
			message.bot.say(message.source, "This command " + self.helptext[0].lower() + self.helptext[1:])
			return
		#Check for update command before file existence, to prevent message that card file is missing after update, which doesn't make much sense
		elif searchType == 'update' or searchType == 'forceupdate':
			if self.areCardfilesInUse:
				replytext = u"I'm already updating!"
			elif not message.bot.factory.isUserAdmin(message.user):
				replytext = u"Sorry, only admins can use my update function"
			else:
				replytext = self.updateCardFile(message.message.lower()=='forceupdate')
				replytext += u" " + self.updateDefinitions(message.message.lower()=='forceupdate')
			message.bot.say(message.source, replytext)
			return
		#Check if the data file even exists
		elif not os.path.exists(os.path.join(GlobalStore.scriptfolder, 'data', 'MTGcards.json')):
			if self.areCardfilesInUse:
				replytext = u"I don't have my card database, but I'm solving that problem as we speak! Try again in, oh,  10, 15 seconds"
			else:
				replytext = u"Sorry, I don't appear to have my card database. I'll try to retrieve it though! Give me 20 seconds, tops"
				GlobalStore.reactor.callInThread(self.updateCardFile, True)
			message.bot.say(message.source, replytext)
			return
		#We can also search for definitions
		elif searchType == 'define':
			if not os.path.exists(os.path.join(GlobalStore.scriptfolder, 'data', 'MTGdefinitions.json')):
				if self.areCardfilesInUse:
					replytext = u"I'm sorry, but my definitions file seems to missing. Don't worry, I'm making up-I mean reading up on the rules as we speak. Try again in a bit!"
				else:
					replytext = u"I'm sorry, I don't seem to have my definitions file. I'll go retrieve it now, try again in a couple of seconds"
				self.updateDefinitions(True)
			elif message.messagePartsLength < 2:
				replytext = u"Please add a definition to search for"
			else:
				searchDefinition = " ".join(message.messageParts[1:])
				with open(os.path.join(GlobalStore.scriptfolder, 'data', 'MTGdefinitions.json'), 'r') as definitionsFile:
					definitions = json.load(definitionsFile)
				if searchDefinition.lower() in definitions:
					replytext = u"'{}': {}".format(searchDefinition, definitions[searchDefinition.lower()]['short'])
					if message.trigger == 'mtgf':
						extendedDefinition = definitions[searchDefinition.lower()]['extended']
						#Let's not spam channels with MtG definitions, shall we
						if message.isPrivateMessage or len(replytext) + len(extendedDefinition) < 500:
							replytext += " " + extendedDefinition
						else:
							message.bot.sendNotice(message.userNickname, replytext)
							while len(extendedDefinition) > 0:
								message.bot.sendNotice(message.userNickname, extendedDefinition[:800])
								extendedDefinition = extendedDefinition[800:]
							replytext += u" [definition too long, rest sent in notice]"
				else:
					replytext = u"I'm sorry, I'm not familiar with that term. Tell my owner, maybe they'll add it!"
			message.bot.say(message.source, replytext)
			return

		#If we reached here, we're gonna search through the card store
		searchDict = {}
		if searchType == 'search' or (searchType == 'random' and message.messagePartsLength > 1) or (searchType == 'randomcommander' and message.messagePartsLength > 1):
			#Advanced search!
			if message.messagePartsLength <= 1:
				message.bot.say(message.source, u"Please provide an advanced search query too, in JSON format, so 'key1: value1, key2: value2'. Look on www.mtgjson.com for available fields")
				return

			#Turn the search string (not the argument) into a usable dictionary, case-insensitive,
			searchDict = SharedFunctions.stringToDict(u" ".join(message.messageParts[1:]).lower(), True)
			if len(searchDict) == 0:
				message.bot.say(message.source, u"That is not a valid search query. It should be entered like JSON, so 'key: value, key2: value2,...'")
				return
		#If the only parameter is 'random', just get all cards
		elif searchType == 'random' and message.messagePartsLength == 1:
			searchDict['name'] = u'.*'
		#No fancy search string, just search for a matching name
		elif searchType != 'randomcommander':
			searchDict['name'] = message.message.lower()

		#Commander search. Regardless of everything else, it has to be a legendary creature
		if searchType == 'randomcommander':
			if 'type' not in searchDict:
				searchDict['type'] = u""
			#Don't just search for 'legendary creature.*', because there are legendary artifact creatures too
			searchDict['type'] = u'legendary.*creature.*' + searchDict['type']

		#Correct some values, to make searching easier (so a search for 'set' or 'sets' both work)
		searchTermsToCorrect = {'set': ['sets'], 'colors': ['color', 'colour', 'colours'], 'type': ['types', 'supertypes', 'subtypes'], 'flavor': ['flavour']}
		for correctTerm, listOfWrongterms in searchTermsToCorrect.iteritems():
			for wrongTerm in listOfWrongterms:
				if wrongTerm in searchDict:
					if correctTerm not in searchDict:
						searchDict[correctTerm] = searchDict[wrongTerm]
					searchDict.pop(wrongTerm)

		print u"[MtG] Search Dict: ", searchDict
				
		#Turn the search strings into actual regexes
		regexDict = {}
		errors = []
		for attrib, query in searchDict.iteritems():													
			regex = None
			try:
				regex = re.compile(query, re.IGNORECASE | re.UNICODE)
			except (re.error, SyntaxError):
				print "[MTG] Regex error when trying to parse '{}'".format(query)
				errors.append(attrib)
			else:
				regexDict[attrib] = regex
		#If there were errors parsing the regular expressions, don't continue, to prevent errors further down
		if len(errors) > 0:
			#If there was only one search element to begin with, there's no need to specify
			if len(searchDict) == 1:
				replytext = u"An error occurred when trying to parse your search query. Please check if it is a valid regular expression"
			#If there were more elements but only one error, specify
			elif len(errors) == 1:
				replytext = u"An error occurred while trying to parse the query for the '{}' field. Please check if it is a valid regular expression".format(errors[0])
			#Multiple errors, list them all
			else:
				replytext = u"Errors occurred while parsing attributes: {}. Please check your regex for errors".format(u", ".join(errors))
			print "[MtG] " + replytext
			message.bot.say(message.source, replytext)
			return

		print "[MTG] Parsed search terms at {} seconds in".format(time.time() - starttime)

		#All entered data is valid, look through the stored cards
		with open(os.path.join(GlobalStore.scriptfolder, 'data', 'MTGcards.json')) as jsonfile:
			cardstore = json.load(jsonfile)
		print "[MTG] Opened file at {} seconds in".format(time.time() - starttime)
		
		#First do an initial name search, to limit the amount of cards we have to search through
		cardNamesToSearchThrough = []
		if 'name' in searchDict:
			for cardname in cardstore.keys():
				if regexDict['name'].search(cardname):
					cardNamesToSearchThrough.append(cardname)
			#Remove the 'name' element from the regex dict to save on search time later
			regexDict.pop('name')
		#No name specified, search through all the cards
		else:
			cardNamesToSearchThrough = cardstore.keys()
		print "[MTG] Determined that we have to search through {} cards at {} seconds in".format(len(cardNamesToSearchThrough), time.time() - starttime)

		regexAttribCount = len(regexDict)
		matchingCards = {}
		#If we only had to check for a name, copy the cards directly into the results dict
		if regexAttribCount == 0:
			for i in xrange(0, len(cardNamesToSearchThrough)):
				cardname = cardNamesToSearchThrough.pop(0)
				matchingCards[cardname] = cardstore[cardname]
		#If there's more attributes we need to check, go through every card
		else:
			for i in xrange(0, len(cardNamesToSearchThrough)):
				cardname = cardNamesToSearchThrough.pop(0)
				for card in cardstore[cardname]:
					matchingAttribsFound = 0
					for attrib, regex in regexDict.iteritems():
						if attrib in card and regex.search(card[attrib]):
							matchingAttribsFound += 1
					#Only store the card if all provided attributes match
					if matchingAttribsFound == regexAttribCount:
						if cardname not in matchingCards:
							matchingCards[cardname] = [card]
						else:
							matchingCards[cardname].append(card)

		print "[MTG] Searched through cards at {} seconds in".format(time.time() - starttime)

		numberOfCardsFound = len(matchingCards)
		#If the user wants a random card, pick one from the matches
		if numberOfCardsFound > 0 and searchType in ['random', 'randomcommander']:
			#Pick a random name
			randomCardname = random.choice(matchingCards.keys())
			#Since there is the possibility there's multiple cards with the same name, pick a random card with the chosen name
			matchingCards = {randomCardname: [random.choice(matchingCards[randomCardname])]}
			numberOfCardsFound = 1
			print "[MTG] Picked a random card at {} seconds in".format(time.time() - starttime)

		#Determine the proper response
		if numberOfCardsFound == 0:
			replytext += u"Sorry, no card matching your query was found"
		elif numberOfCardsFound == 1:
			cardsFound = matchingCards[matchingCards.keys()[0]]
			if len(cardsFound) == 1:
				replytext += self.getFormattedCardInfo(cardsFound[0], message.trigger=='mtgf')
			else:
				replytext += u"Multiple cards with the same name were found: "
				for cardFound in cardsFound:
					setlist = u"'{}'".format(cardFound['sets'].split(u'; ',1)[0])
					if cardFound['sets'].count(u';') > 0:
						setlist += u" (and more)"
					replytext += u"{} [set {}]; ".format(cardFound['name'], setlist)
				replytext = replytext[:-2]
		else:
			#If the entered name is literally in the results, show the full info on that, after the normal list of results
			nameMatchedCard = None
			if 'name' in searchDict and searchDict['name'] in matchingCards and len(matchingCards[searchDict['name']]) == 1:
				nameMatchedCard = matchingCards.pop(searchDict['name'])[0]
				replytext = self.getFormattedCardInfo(nameMatchedCard, message.trigger=='mtgf')
				numberOfCardsFound -= 1
				print u"[MTG] Literal match found. Searched name: '{}', found card name: '{}'".format(searchDict['name'], nameMatchedCard['name'])

			cardlimit = maxCardsToListInPm if message.isPrivateMessage else maxCardsToListInChannel
			cardnamelist = []
			#If there's only a few cards found, show them sensibly sorted alphabetically
			if numberOfCardsFound <= cardlimit:
				cardnamelist = sorted(matchingCards.keys())
			#If there are a lot of cards, have some fun and pick a few random ones, also sorted
			else:
				cardnamelist = sorted(random.sample(matchingCards.keys(), cardlimit))

			#Replace each lower-cased card name with the proper stored one,
			#  by taking the first name and putting the proper name at the end, until all cardnames are fixed
			for i in xrange(0, len(cardnamelist)):
				cardname = cardnamelist.pop(0)
				cardnamelist.append(cardstore[cardname][0]['name'])
			cardnamelist = u"; ".join(cardnamelist)
			if nameMatchedCard:
				replytext += u"\n{:,} more matching cards found: {}".format(numberOfCardsFound, cardnamelist)
			else:
				replytext = u"Search returned {:,} cards: {}".format(numberOfCardsFound, cardnamelist)
			if numberOfCardsFound > cardlimit:
				replytext += u"; and {:,} more".format(numberOfCardsFound - cardlimit)


		re.purge()  #Clear the stored regexes, since we don't need them anymore
		gc.collect()  #Make sure memory usage doesn't slowly creep up from loading in the data file (hopefully)
		print "[MtG] Execution time: {} seconds".format(time.time() - starttime)
		message.bot.say(message.source, replytext)

	@staticmethod
	def getFormattedCardInfo(card, addExtendedInfo=False):
		replytext = u"{card[name]} "
		if 'type' in card and len(card['type']) > 0:
			replytext += u"[{card[type]}]"
		if 'manacost' in card:
			replytext += u" ({card[manacost]}"
			#Only add the cumulative mana cost if it's different from the total cost (No need to say '3 mana, 3 total')
			if 'cmc' in card and card['cmc'] != card['manacost']:
				replytext += u", {card[cmc]} total"
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
				names = card['names'].split(u'; ')
				if card['name'] in names:
					names.remove(card['name'])
				names = u'; '.join(names)
				replytext += u", also contains {names}".format(names=names)
			replytext += u")"
		replytext += u"."
		if 'text' in card and len(card['text']) > 0:
			replytext += u" {card[text]}"
		if addExtendedInfo and 'flavor' in card:
			replytext += u" Flavor: {card[flavor]}"
		if 'sets' in card:
			sets = card['sets'].split(u'; ')
			setCount = len(sets)
			maxSetsToDisplay = 4
			if addExtendedInfo:
				if setCount == 1:
					replytext += u" [in set {card[sets]}]"
				elif setCount <= maxSetsToDisplay:
					replytext += u" [in sets {card[sets]}]"
				else:
					replytext += u" [in sets {shortSetList} and {setCount} more]".format(shortSetList=u"; ".join(sets[:maxSetsToDisplay]), setCount=setCount-maxSetsToDisplay)
			else:
				for illegalSet in ['Unglued', 'Unhinged', 'Happy Holidays']:
					if illegalSet in sets:
						replytext += u" [in illegal set '{illegalSet}'!]".format(illegalSet=illegalSet)
						break
		#FILL THAT SHIT IN
		replytext = replytext.format(card=card)
		return replytext

	def updateCardFile(self, forceUpdate=False):
		starttime = time.time()
		self.areCardfilesInUse = True
		replytext = u""
		cardsJsonFilename = os.path.join(GlobalStore.scriptfolder, 'data', 'MTGcards.json')
		updateNeeded = False
		
		versionFilename = os.path.join(GlobalStore.scriptfolder, 'data', 'MTGversion-full.json')
		currentVersion = "0.00"
		latestVersion = ""			
		#Load in the currently stored version number
		if not os.path.exists(versionFilename):
			print "[MtG] No old card database version file found"
		else:
			with open(versionFilename) as oldversionfile:
				oldversiondata = json.load(oldversionfile)
				if 'version' in oldversiondata:
					currentVersion = oldversiondata['version']
				else:
					print "[MtG] Unexpected content of stored version file:"
					for key, value in oldversiondata.iteritems():
						print "  {}: {}".format(key, value)
		#print "[MtG] Local version: '{}'".format(currentVersion)

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
				print "[MtG] Unexpected contents of downloaded version file:"
				for key, value in versiondata.iteritems():
					print " {}: {}".format(key, value)
		#print "[MtG] Latest version: '{}'".format(latestVersion)
		if latestVersion == "":
			replytext = u"Something went wrong, the latest MtG database version number could not be retrieved."

		if forceUpdate or latestVersion != currentVersion or not os.path.exists(cardsJsonFilename):
			updateNeeded = True

		print "Done version-checking at {} seconds in".format(time.time() - starttime)

		if not updateNeeded:
			replytext = u"No card update needed, I already have the latest MtG card database version (v {}).".format(latestVersion)
			os.remove(newversionfilename)
		else:
			print "[MtG] Updating card database!"
			url = "http://mtgjson.com/json/AllSets.json.zip"  #Use the small dataset, since we don't use the rulings anyway and this way RAM usage is WAY down
			cardzipFilename = os.path.join(GlobalStore.scriptfolder, 'data', url.split('/')[-1])
			urllib.urlretrieve(url, cardzipFilename)

			print "Done with downloading card database at {} seconds in".format(time.time() - starttime)

			#Since it's a zip, extract it
			zipWithJson = zipfile.ZipFile(cardzipFilename, 'r')
			newcardfilename = os.path.join(GlobalStore.scriptfolder, 'data', zipWithJson.namelist()[0])
			if os.path.exists(newcardfilename):
				os.remove(newcardfilename)
			zipWithJson.extractall(os.path.join(GlobalStore.scriptfolder, 'data'))
			zipWithJson.close()
			#We don't need the zip anymore
			os.remove(cardzipFilename)

			print "Done unzipping downloaded card database at {} seconds in".format(time.time() - starttime)

			#Load in the new file so we can save it in our preferred format (not per set, but just a dict of cards)
			downloadedCardstore = {}
			with open(newcardfilename, 'r') as newcardfile:
				downloadedCardstore = json.load(newcardfile)
			print "Done loading the new cards into memory at {} seconds in".format(time.time() - starttime)
			newcardstore = {}
			print "Going through cards"
			#Use the keys instead of iteritems() so we can pop off the set we need, to reduce memory usage
			for setcode in downloadedCardstore.keys():
				setData = downloadedCardstore.pop(setcode)
				#Again, pop off cards when we need them, to save on memory
				for i in xrange(0, len(setData['cards'])):
					card = setData['cards'].pop(0)
					cardname = card['name'].lower()  #lowering the keys makes searching easier later, especially when comparing against the literal searchstring
					addCard = True
					if cardname not in newcardstore:
						newcardstore[cardname] = []
					else:
						for sameNamedCard in newcardstore[cardname]:
							#There are three possibilities: Both text, if the same they're duplicates; Neither text, they're duplicates; One text other not, not duplicates
							#  Since we later ensure that all cards have a 'text' field, instead of checking for 'text in sameNameCard', we check whether 'text' is an empty string
							if ('text' not in card and sameNamedCard['text'] == u"") or (sameNamedCard['text'] != u"" and 'text' in card and sameNamedCard['text'] == card['text']):
								#Since it's a duplicate, update the original card with info on the set it's also in, if it's not in there already
								if setData['name'] not in sameNamedCard['sets'].split(u'; '):
									sameNamedCard['sets'] += u"; {}".format(setData['name'])
								addCard = False
								break

					if addCard:
						#Remove some other useless data to save some space, memory and time
						keysToRemove = ['imageName', 'variations', 'types', 'supertypes', 'subtypes',
										'foreignNames', 'originalText', 'originalType']  #Last three are from the database with extras
						for keyToRemove in keysToRemove:
							card.pop(keyToRemove, None)

						#Make sure all keys are fully lowercase, to make matching them easy
						keysToMakeLowerCase = ['manaCost']
						for keyToMakeLowerCase in keysToMakeLowerCase:
							if keyToMakeLowerCase in card:
								card[keyToMakeLowerCase.lower()] = card[keyToMakeLowerCase]
								card.pop(keyToMakeLowerCase)

						#Some keys, like colors, benefit from some ordering. So order them alphabetically
						keysToSort = ['colors']
						for keyToSort in keysToSort:
							if keyToSort in card:
								card[keyToSort] = sorted(card[keyToSort])

						#make sure all stored values are strings, that makes searching later much easier
						for attrib in card:
							#Re.search stumbles over numbers, convert them to strings first
							if isinstance(card[attrib], (int, long, float)):
								card[attrib] = unicode(card[attrib])
							#Regexes can't search lists either, make them strings too
							elif isinstance(card[attrib], list):
								oldlist = card[attrib]
								newlist = []
								for entry in oldlist:
									#There's lists of strings and lists of ints, handle both
									if isinstance(entry, (int, long, float)):
										newlist.append(unicode(entry))
									#There's even lists of dictionaries
									elif isinstance(entry, dict):
										newlist.append(SharedFunctions.dictToString(entry))
									else:
										newlist.append(entry)
								card[attrib] = u"; ".join(newlist)
							#If lists are hard for the re module, don't even mention dictionaries. A bit harder to convert, but not impossible
							elif isinstance(card[attrib], dict):
								card[attrib] = SharedFunctions.dictToString(card[attrib])

						#To make searching easier later, without all sorts of key checking, make sure these keys always exist
						keysToEnsure = ['text']
						for keyToEnsure in keysToEnsure:
							if keyToEnsure not in card:
								card[keyToEnsure] = u""
						
						card['sets'] = setData['name']
						#Finally, put the card in the new storage
						newcardstore[cardname].append(card)

			#Format the text after the main loop, so we can compare texts to prevent duplicates
			for cardlist in newcardstore.values():
				for card in cardlist:
					#Clean up the text formatting, so we don't have to do that every time
					keysToFormatNicer = ['manacost', 'text', 'flavor']
					for keyToFormat in keysToFormatNicer:
						if keyToFormat in card:
							newText = card[keyToFormat]
							#Remove brackets around mana cost
							if '{' in newText:
								newText = newText.replace('}{', ' ').replace('{', '').replace('}', '')
							#Remove newlines but make sure sentences are separated by a period
							newText = newText.replace('.\n', '\n').replace('\n\n', '\n').replace('\n', '. ')
							#Prevent double spaces
							newText = newText.replace(u'  ', u' ').strip()
							card[keyToFormat] = newText


			#First delete the original file
			if os.path.exists(cardsJsonFilename):
				os.remove(cardsJsonFilename)
			#Save the new database to disk
			print "Done parsing cards, saving file to disk"
			with open(cardsJsonFilename, 'w') as cardfile:
				#json.dump(cards, cardfile) #This is dozens of seconds slower than below
				cardfile.write(json.dumps(newcardstore))
			print "Done saving file to disk"

			#Remove the file downloaded from MTGjson.com
			os.remove(newcardfilename)

			#Replace the old version file with the new one
			if os.path.exists(versionFilename):
				os.remove(versionFilename)
			os.rename(newversionfilename, versionFilename)

			replytext = u"MtG card database successfully updated to version {} (Changelog: http://mtgjson.com/#changeLog).".format(latestVersion)

		urllib.urlcleanup()
		self.areCardfilesInUse = False
		print "[MtG] updating database took {} seconds".format(time.time() - starttime)
		return replytext

	def updateDefinitions(self, forceUpdate=False):
		starttime = time.time()
		definitionsFileLocation = os.path.join(GlobalStore.scriptfolder, "data", "MTGdefinitions.json")

		#Check if a new rules file exists
		rulespage = requests.get("http://www.wizards.com/Magic/TCG/Article.aspx?x=magic/rules")
		textfileMatch = re.search('<a.*href="(?P<url>http://media.wizards.com/images/magic/tcg/resources/rules/MagicCompRules_(?P<date>\d+)\.txt)">TXT</a>', rulespage.text)
		if not textfileMatch:
			print "[MtG] [definitions update] Unable to locate the URL to the rules text file!"
			return u"Definitions file not found."
		else:
			self.areCardfilesInUse = True
			textfileLocation = textfileMatch.group('url')
			date = textfileMatch.group('date')

			oldDefinitionDate = ""
			if not forceUpdate and os.path.exists(definitionsFileLocation):
				with open(definitionsFileLocation, 'r') as definitionsFile:
					definitions = json.load(definitionsFile)
				if '_date' in definitions:
					oldDefinitionDate = definitions['_date']

			if forceUpdate or oldDefinitionDate != date:
				rulesfilelocation = os.path.join(GlobalStore.scriptfolder, "data", "MtGrules.txt")
				#Retrieve the rules document and parse the definitions
				urllib.urlretrieve(textfileLocation, rulesfilelocation)

				definitions = {}
				#Keywords are defined in chapters 701 and 702, in the format '701.2. [keyword]' '701.2a [definition]' '701.2b [more definition]' etc.
				keywordPattern = re.compile("70[12]\.(\d+)\. (.+)")
				definitionPattern = re.compile("70[12]\.\d+[a-z] (.+)")
				
				with open(rulesfilelocation, 'r') as rulesfile:
					for line in rulesfile:
						#Decode to latin-1, because there's some weird quotes in the file for some reason
						keywordMatch = re.search(keywordPattern, line)
						if keywordMatch and keywordMatch.group(1) != '1': #Ignore the first entries, since that's just a description of the chapter
							currentKeyword = keywordMatch.group(2).lower().decode('latin1')
							definitions[currentKeyword] = {}
						else:
							definitionMatch = re.search(definitionPattern, line)
							if definitionMatch:
								definition =  definitionMatch.group(1).decode('latin1')
								#Keep a short description for quick lookups
								if "short" not in definitions[currentKeyword]:
									definitions[currentKeyword]["short"] = definition
								#But too short a description is pretty useless, extend it if it's too short
								elif len(definitions[currentKeyword]['short']) < 100:
									definitions[currentKeyword]['short'] += " " + definition
								#Keep the rest of the definition for complete searches
								elif "extended" not in definitions[currentKeyword]:
									definitions[currentKeyword]["extended"] = definition
								else:
									definitions[currentKeyword]["extended"] += " " + definition

				#Save the definitions to file
				definitions['_date'] = date
				with open(definitionsFileLocation, 'w') as definitionsFile:
					definitionsFile.write(json.dumps(definitions))

				#Clean up the rules file, we don't need it anymore
				os.remove(rulesfilelocation)

				self.areCardfilesInUse = False
				print "[MtG] Updated definitions file to version {} in {} seconds".format(date, time.time() - starttime)
				return u"Definitions successfully updated to the version from {}.".format(date)
			else:
				#No update necessary
				self.areCardfilesInUse = False
				print "[MtG] No need to update definitions file, {} is still newest. Check took {} seconds".format(date, time.time() - starttime)
				return u"No definitions update needed, version {} is still up-to-date.".format(date)