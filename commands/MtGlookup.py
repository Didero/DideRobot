# -*- coding: utf-8 -*-

import gc, json, os, random, re, time, urllib, zipfile

import requests
from bs4 import BeautifulSoup

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
			shouldForceUpdate = True if message.message.lower() == 'forceupdate' else False
			if self.areCardfilesInUse:
				replytext = u"I'm already updating!"
			elif not message.bot.factory.isUserAdmin(message.user):
				replytext = u"Sorry, only admins can use my update function"
			else:
				replytext = self.updateCardFile(shouldForceUpdate)
				replytext += u" " + self.updateDefinitions()
				#Since we're checking now, set the automatic check to start counting from now on
				self.scheduledFunctionTimer.reset()
			message.bot.say(message.source, replytext)
			return

		#We can also search for definitions
		elif searchType == 'define':
			if not os.path.exists(os.path.join(GlobalStore.scriptfolder, 'data', 'MTGdefinitions.json')):
				if self.areCardfilesInUse:
					replytext = u"I'm sorry, but my definitions file seems to missing. Don't worry, I'm making up-I mean reading up on the rules as we speak. Try again in a bit!"
				else:
					message.bot.sendMessage(message.source, u"I'm sorry, I don't seem to have my definitions file. I'll go retrieve it now, try again in a couple of seconds")
					replytext = self.updateDefinitions()
			elif message.messagePartsLength < 2:
				replytext = u"Please add a definition to search for"
			else:
				with open(os.path.join(GlobalStore.scriptfolder, 'data', 'MTGdefinitions.json'), 'r') as definitionsFile:
					definitions = json.load(definitionsFile)
				searchterm = u" ".join(message.messageParts[1:]).lower()
				searchRegex = re.compile(searchterm)
				possibleDefinitions = []
				for keyword in definitions.keys():
					if re.search(searchRegex, keyword):
						possibleDefinitions.append(keyword)
				if len(possibleDefinitions) == 0:
					#If nothing was found, search again, but this time check the definitions themselves
					for keyword, defdict in definitions.iteritems():
						if re.search(searchRegex, defdict['short']):
							possibleDefinitions.append(keyword)
						elif 'extra' in defdict and re.search(searchRegex, defdict['extra']):
							possibleDefinitions.append(keyword)
				possibleDefinitionsCount = len(possibleDefinitions)
				if possibleDefinitionsCount == 0:
					replytext = u"Sorry, I don't have any info on that term. If you think it's important, poke my owner(s)!"
				elif possibleDefinitionsCount == 1:
					keyword = possibleDefinitions[0]
					replytext = u"{}: {}.".format(keyword, definitions[keyword]['short'])
					currentReplyLength = len(replytext)
					if message.trigger == 'mtgf' and 'extra' in definitions[keyword]:
						replytext += u" " + definitions[keyword]['extra']
						#MORE INFO
						maxLength = 300
						if not message.isPrivateMessage and currentReplyLength + len(definitions[keyword]['extra']) > maxLength:
							textLeft = replytext[maxLength:]
							replytext = replytext[:maxLength] + u" [continued in notices]"
							counter = 1
							while len(textLeft) > 0:
								GlobalStore.reactor.callLater(0.2 * counter, message.bot.sendMessage, message.userNickname, u"({}) {}".format(counter + 1, textLeft[:maxLength]), 'notice')
								textLeft = textLeft[maxLength:]
								counter += 1
				else:
					if searchterm in possibleDefinitions:
						possibleDefinitions.remove(searchterm)
						possibleDefinitionsCount -= 1
						replytext = u"{}: {}; {} more matching definitions found".format(searchterm, definitions[searchterm]['short'], possibleDefinitionsCount)
					else:
						replytext = u"Your search returned {} results, please be more specific".format(possibleDefinitionsCount)
					if possibleDefinitionsCount < 10:
						replytext += u": {}".format(u"; ".join(possibleDefinitions))
					replytext += u"."

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
		searchTermsToCorrect = {'sets': ['set'], 'colors': ['color', 'colour', 'colours'], 'type': ['types', 'supertypes', 'subtypes'], 'flavor': ['flavour']}
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
		replytext = u"{card[name]}"
		if 'type' in card and len(card['type']) > 0:
			replytext += u" [{card[type]}]"
		if addExtendedInfo and 'rarity' in card:
			replytext += u" [{card[rarity]}]"
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
					shortSetList = sorted(random.sample(sets, maxSetsToDisplay))
					replytext += u" [in sets {shortSetList} and {setCount} more]".format(shortSetList=u"; ".join(shortSetList), setCount=setCount-maxSetsToDisplay)
			#Cards in illegal sets only appear in that set, so there aren't multiple sets listed
			elif setCount == 1 and sets[0] in ['Unglued', 'Unhinged', 'Happy Holidays']:
				replytext += u" [in illegal set '{illegalSet}'!]".format(illegalSet=sets[0])
		#FILL THAT SHIT IN
		replytext = replytext.format(card=card)
		return replytext

	def updateCardFile(self, forceUpdate=False):
		starttime = time.time()
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
						return u"Something went wrong when reading the stored version number."
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
					return u"Something went wrong when trying to read the downloaded version file"
		#print "[MtG] Latest version: '{}'".format(latestVersion)
		if latestVersion == "":
			return u"Something went wrong, the latest MtG database version number could not be retrieved."

		if forceUpdate or latestVersion != currentVersion or not os.path.exists(cardsJsonFilename):
			updateNeeded = True

		print "[MTG] Done version-checking at {} seconds in".format(time.time() - starttime)

		if not updateNeeded:
			replytext = u"No card update needed, I already have the latest MtG card database version (v {}).".format(latestVersion)
			os.remove(newversionfilename)
		else:
			self.areCardfilesInUse = True
			print "[MtG] Updating card database!"
			url = "http://mtgjson.com/json/AllSets.json.zip"  #Use the small dataset, since we don't use the rulings anyway and this way RAM usage is WAY down
			cardzipFilename = os.path.join(GlobalStore.scriptfolder, 'data', url.split('/')[-1])
			urllib.urlretrieve(url, cardzipFilename)

			print "[MTG] Done with downloading card database at {} seconds in".format(time.time() - starttime)

			#Since it's a zip, extract it
			zipWithJson = zipfile.ZipFile(cardzipFilename, 'r')
			newcardfilename = os.path.join(GlobalStore.scriptfolder, 'data', zipWithJson.namelist()[0])
			if os.path.exists(newcardfilename):
				os.remove(newcardfilename)
			zipWithJson.extractall(os.path.join(GlobalStore.scriptfolder, 'data'))
			zipWithJson.close()
			#We don't need the zip anymore
			os.remove(cardzipFilename)

			print "[MTG] Done unzipping downloaded card database at {} seconds in".format(time.time() - starttime)

			#Load in the new file so we can save it in our preferred format (not per set, but just a dict of cards)
			downloadedCardstore = {}
			with open(newcardfilename, 'r') as newcardfile:
				downloadedCardstore = json.load(newcardfile)
			print "[MTG] Done loading the new cards into memory at {} seconds in".format(time.time() - starttime)
			newcardstore = {}
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
							if keyToRemove in card:
								del card[keyToRemove]

						#The 'Colors' field benefits from some ordering, for readability.
						if 'colors' in card:
							card['colors'] = sorted(card['colors'])

						#Make sure all stored values are strings, that makes searching later much easier
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

						#Make 'manaCost' lowercase, since we make the searchstring lowercase too, and we don't want to miss this
						if 'manaCost' in card:
							card['manacost'] = card['manaCost']
							del card['manaCost']

						#To make searching easier later, without all sorts of key checking, make sure the 'text' key always exists
						if 'text' not in card:
							card['text'] = u""

						card['sets'] = setData['name']
						#Finally, put the card in the new storage
						newcardstore[cardname].append(card)

			#Clean up the text formatting, so we don't have to do that every time
			for cardlist in newcardstore.values():
				for card in cardlist:
					keysToFormatNicer = ['manacost', 'text', 'flavor']
					for keyToFormat in keysToFormatNicer:
						if keyToFormat in card:
							newText = card[keyToFormat]
							#Remove brackets around mana cost
							if '{' in newText:
								newText = newText.replace('}{', ' ').replace('{', '').replace('}', '')
							#Replace newlines with spaces. If the sentence adds in a letter, add a period
							newText = re.sub('(?<=\w)\n', '. ', newText).replace('\n', ' ')
							#Prevent double spaces
							newText = newText.replace(u'  ', u' ').strip()
							card[keyToFormat] = newText

			#First delete the original file
			if os.path.exists(cardsJsonFilename):
				os.remove(cardsJsonFilename)
			#Save the new database to disk
			print "[MTG] Done parsing cards at {} seconds in, saving file to disk".format(time.time() - starttime)
			with open(cardsJsonFilename, 'w') as cardfile:
				#json.dump(cards, cardfile) #This is dozens of seconds slower than below
				cardfile.write(json.dumps(newcardstore))
			print "[MTG] Done saving file to disk at {} seconds in".format(time.time() - starttime)

			#Remove the file downloaded from MTGjson.com
			os.remove(newcardfilename)

			#Replace the old version file with the new one
			if os.path.exists(versionFilename):
				os.remove(versionFilename)
			os.rename(newversionfilename, versionFilename)

			replytext = u"MtG card database successfully updated from version {} to {} (Changelog: http://mtgjson.com/#changeLog).".format(currentVersion, latestVersion)

		urllib.urlcleanup()
		self.areCardfilesInUse = False
		print "[MtG] updating database took {} seconds".format(time.time() - starttime)
		return replytext

	def updateDefinitions(self):
		starttime = time.time()
		definitions = {}
		textCutoffLength = 200
		replytext = u"Nothing happened..."

		self.areCardfilesInUse = True
		definitionSources = [("http://en.m.wikipedia.org/wiki/List_of_Magic:_The_Gathering_keywords", "content", 4),
			("http://mtgsalvation.gamepedia.com/List_of_Magic_slang", "mw-body", 6)]
		try:
			for url, section, charsToRemoveFromEnd in definitionSources:
				headers = BeautifulSoup(requests.get(url).text.replace('\n', '')).find(class_=section).find_all(['h3', 'h4'])
				for header in headers:
					keyword = header.text[:-charsToRemoveFromEnd].lower()
					if keyword in definitions:
						print "[MTG] [DefinitionsUpdate] Duplicate definition: '{}'".format(keyword)
						continue
					#definitions[keyword] = u""
					#Cycle through all the paragraphs following the header
					currentParagraph = header.next_sibling
					paragraphText = u""
					#If there's no next_sibling, 'currentParagraph' is set to None. Check for that
					while currentParagraph and currentParagraph.name in ['p', 'ul', 'dl']:
						paragraphText += u" " + currentParagraph.text
						currentParagraph = currentParagraph.next_sibling
					paragraphText = re.sub(" ?\[\d+?]", "", paragraphText).lstrip().rstrip(' .')  #Remove the reference links ('[1]')

					#Split the found text into a short definition and a longer description
					definitions[keyword] = {}
					if len(paragraphText) < textCutoffLength:
						definitions[keyword]['short'] = paragraphText
					else:
						splitIndex = paragraphText.rfind('.', 0, textCutoffLength)
						definitions[keyword]['short'] = paragraphText[:splitIndex].lstrip()
						definitions[keyword]['extra'] = paragraphText[splitIndex + 1:].lstrip()
			print "[MTG] Updating definitions took {} seconds".format(time.time() - starttime)
		except Exception as e:
			print "[MTG] [DefinitionsUpdate] An error occured: ", e
			replytext = u"Definitions file NOT updated, check log for errors"
		else:
			#Save the data to disk
			with open(os.path.join(GlobalStore.scriptfolder, "data", "MTGdefinitions.json"), 'w') as definitionsFile:
				definitionsFile.write(json.dumps(definitions))
			replytext = u"Definitions file successfully updated"
		finally:
			self.areCardfilesInUse = False
		return replytext