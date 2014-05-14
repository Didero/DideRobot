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
	scheduledFunctionTime = 172800.0 #Every other day, since it doesn't update too often

	isUpdating = False


	def executeScheduledFunction(self):
		GlobalStore.reactor.callInThread(self.updateCardFile)
		GlobalStore.reactor.callInThread(self.updateDefinitions)

	def execute(self, message):
		"""
		:type message: IrcMessage
		"""
		starttime = time.time()
		replytext = u""
		maxCardsToListInChannel = 20
		maxCardsToListInPm = 50

		searchType = u""
		if message.messagePartsLength > 0:
			searchType = message.messageParts[0].lower()

		if message.messagePartsLength == 0:
			message.bot.say(message.source, u"Please provide a card name to search for")
			return
		#Check for update command before file existence, to prevent message that card file is missing after update, which doesn't make much sense
		elif searchType == 'update' or searchType == 'forceupdate':
			if self.isUpdating:
				replytext = u"I'm already updating!"
			elif not message.bot.factory.isUserAdmin(message.user):
				replytext = u"Sorry, only admins can use my update function"
			else:
				replytext = self.updateCardFile(message.message.lower()=='forceupdate')
				replytext += " " + self.updateDefinitions(message.message.lower()=='forceupdate')
			message.bot.say(message.source, replytext)
			return
		#Check if the data file even exists
		elif not os.path.exists(os.path.join('data', 'MTGcards.json')):
			if self.isUpdating:
				replytext = u"I don't have my card database, but I'm solving that problem as we speak! Try again in, oh,  10, 15 seconds"
			else:
				replytext = u"Sorry, I don't appear to have my card database. I'll try to retrieve it though! Give me 20 seconds, tops"
				GlobalStore.reactor.callInThread(self.updateCardFile, True)
			message.bot.say(message.source, replytext)
			return
		#We can also search for definitions
		elif searchType == 'define':
			if not os.path.exists(os.path.join('data', 'MTGdefinitions.json')):
				replytext = u"I'm sorry, I don't seem to have my definitions file. I'll go retrieve it now, try again in a couple of seconds"
				self.updateDefinitions(True)
			elif message.messagePartsLength < 2:
				replytext = u"Please add a definition to search for"
			else:
				searchDefinition =  " ".join(message.messageParts[1:])
				with open(os.path.join('data', 'MTGdefinitions.json'), 'r') as definitionsFile:
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
				message.bot.say(message.source, 'Please provide an advanced search query too, in JSON format, so "key1: value1, key2:value2". Look at www.mtgjson.com for available fields')
				return

			searchDict = SharedFunctions.stringToDict(" ".join(message.messageParts[1:]))
			if len(searchDict) == 0:
				message.bot.say(message.source, "That is not a valid search query. It should be entered like JSON, so \"'key': 'value', 'key2': 'value2',...\"")
				return
		#If the only parameter is 'random', just get all cards
		elif searchType == 'random' and message.messagePartsLength == 1:
			searchDict['name'] = '.*'
		#No fancy search string, just search for a matching name
		elif searchType != 'randomcommander':
			searchDict['name'] = message.message.lower()

		#Commander search. Regardless of everything else, it has to be a legendary creature
		if searchType == 'randomcommander':
			if 'type' not in searchDict:
				searchDict['type'] = u""
			#Don't just search for 'legendary creature.*', because there are legendary artifact creatures too
			searchDict['type'] = 'legendary.*creature.*' + searchDict['type']

		#Correct some values, to make searching easier (so a search for 'set' or 'sets' both work)
		searchTermsToCorrect = {"set": "sets", "color": "colors", "colour": "colors", "colours": "colors"}
		for searchTermToCorrect, correctTerm in searchTermsToCorrect.iteritems():
			if searchTermToCorrect in searchDict and correctTerm not in searchDict:
				searchDict[correctTerm] = searchDict[searchTermToCorrect]
				searchDict.pop(searchTermToCorrect)

		print "[MtG] Search Dict: ", searchDict
				
		#Turn the search strings into actual regexes
		regexDict = {}
		errors = []
		for attrib, query in searchDict.iteritems():													
			regex = None
			try:
				regex = re.compile(str(query), re.IGNORECASE)
			except:
				#replytext = u"That is not a valid search term. Brush up on your regex, or just leave out any weird characters"
				errors.append(attrib)
			else:
				regexDict[attrib] = regex
		if len(errors) > 0:
			replytext = u"(Error(s) occured with attributes: {}) ".format(", ".join(errors))
			print "[MtG] " + replytext
		regexAttribCount = len(regexDict)
		print "Parsed search terms at {} seconds in".format(time.time() - starttime)

		#All entered data is valid, look through the stored cards
		with open(os.path.join('data', 'MTGcards.json')) as jsonfile:
			cardstore = json.load(jsonfile)
		print "Opened file at {} seconds in".format(time.time() - starttime)
		
		#First do an initial name search, to limit the amount of cards we have to search through
		cardNamesToSearchThrough = []
		if 'name' in searchDict:
			#If the name is literally there, use that
			if searchDict['name'] in cardstore:
				print "regex '{}' is a literal name in the card database".format(searchDict['name'])
				cardNamesToSearchThrough = [searchDict['name']]
			#Otherwise, try to find a match
			else:
				for cardname in cardstore.keys():
					if regexDict['name'].search(cardname):
						cardNamesToSearchThrough.append(cardname)
			#Remove the 'name' element from the regex dict to save on search time later
			regexDict.pop('name')
			regexAttribCount = len(regexDict)
		else:
			cardNamesToSearchThrough = cardstore.keys()
		print "Determined that we have to search through {} cards at {} seconds in".format(len(cardNamesToSearchThrough), time.time() - starttime)

		#The actual search!
		matchingCards = {}
		#Check to see if we need to make any other checks
		if regexAttribCount > 1 or 'name' not in regexDict:
			for cardname in cardNamesToSearchThrough:
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

		print "Searched through cards at {} seconds in".format(time.time() - starttime)

		cardnamesFound = len(matchingCards)
		if cardnamesFound > 0:
			#If the user wants a random card, pick one from the matches
			if searchType == 'random' or searchType == 'randomcommander':
				allcards = []
				for cardname in matchingCards.keys():
					allcards.extend(matchingCards[cardname])
				randomCard = random.choice(allcards)
				matchingCards = {}
				matchingCards[randomCard['name']] = [randomCard]
			cardnamesFound = len(matchingCards)

		print "Cleaned up found cards at {} seconds in, {} found cards left".format(time.time() - starttime, cardnamesFound)
		#Determine the proper response
		if cardnamesFound == 0:
			replytext += u"Sorry, no card matching your query was found"
		elif cardnamesFound == 1:
			cardsFound = matchingCards[matchingCards.keys()[0]]
			if len(cardsFound) == 1:
				replytext += self.getFormattedCardInfo(cardsFound[0], message.trigger=='mtgf')
			else:
				replytext += u"Multiple cards with the same name were found: "
				setlist = u""
				for cardFound in cardsFound:
					setlist = "'{}'".format(cardFound['sets'].split(', ',1)[0])
					if cardFound['sets'].count(',') > 0:
						setlist += u" (and more)"
					replytext += u"{} [set {}]; ".format(cardFound['name'].encode('utf-8'), setlist)
				replytext = replytext[:-2]
		#Check if listing all the found cardnames is viable. The limit is higher for private messages than for channels
		elif cardnamesFound <= maxCardsToListInChannel or (cardnamesFound <= maxCardsToListInPm and message.isPrivateMessage):
			cardnamestring = u""
			for cardname in sorted(matchingCards.keys()):
				cardlist = matchingCards[cardname]
				cardnamestring += cardlist[0]['name']
				if len(cardlist) > 1:
					cardnamestring += u" [from sets "
					for card in cardlist:
						cardnamestring += u"'{}', ".format(card['sets'].split(',',1)[0])
					cardnamestring = cardnamestring[:-2] + u"]"
				cardnamestring += u"; "
			cardnamestring = cardnamestring[:-2]

			replytext += u"Search returned {} cards: {}".format(cardnamesFound, cardnamestring)
		else:
			replytext += u"Your searchterm returned {} cards, please be more specific".format(cardnamesFound)

		re.purge()  #Clear the stored regexes, since we don't need them anymore
		gc.collect()  #Make sure memory usage doesn't slowly creep up from loading in the data file (hopefully)
		print "[MtG] Execution time: {} seconds".format(time.time() - starttime)
		message.bot.say(message.source, replytext)

	def getFormattedCardInfo(self, card, addExtendedInfo=False):
		replytext = u"{card[name]} "
		if 'type' in card and len(card['type']) > 0:
			replytext += u"[{card[type]}]"
		if 'manacost' in card:
			replytext += u" ({card[manacost]} mana"
			#Only add the cummulative mana cost if it's different from the total cost (No need to say '3 mana, 3 total'). Manacost is stored with parentheses('{3}'), remove those
			if 'cmc' in card and (len(card['manacost']) <2 or card['cmc'] != card['manacost'][1:-1]):
				replytext += u", {card[cmc]} total"
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
				names = card['names'].split('; ')
				if card['name'] in names:
					names.remove(card['name'])
				names = '; '.join(names)
				replytext += u", also contains {names}".format(names=names)
			replytext += u")"
		replytext += u"."
		if 'text' in card and len(card['text']) > 0:
			replytext += u" {card[text]}"
		if addExtendedInfo and 'flavor' in card:
			replytext += u" Flavor: {card[flavor]}"
		if 'sets' in card:
			sets = card['sets'].split(',')
			if addExtendedInfo:
				if len(sets) == 1:
					replytext += u" [in set {card[sets]}]"
				elif len(sets) < 5:
					replytext += u" [in sets {card[sets]}]"
				else:
					replytext += u" [in sets {shortSetList} and {setCount} more]".format(shortSetList="; ".join(sets[:5]), setCount=len(sets)-5)
			else:
				for illegalSet in ['Unglued', 'Unhinged', 'Happy Holidays']:
					if illegalSet in sets:
						replytext += u" [in illegal set '{illegalSet}'!]".format(illegalSet=illegalSet)
						break
		#FILL THAT SHIT IN
		replytext = replytext.format(card=card)
		#Clean up the text			Remove brackets around mana cost	Remove newlines but make sure sentences are separated by a period	Prevent double spaces
		replytext = replytext.replace('}{', ' ').replace('{', '').replace('}','').replace('.\n','\n').replace('\n\n','\n').replace('\n','. ').replace(u'  ', u' ').strip()
		#replytext = re.sub('[{}]', '', replytext)
		#replytext = re.sub('\.?(\n)+ *', '. ', replytext)
		return replytext


	def updateCardFile(self, forceUpdate=False):
		starttime = time.time()
		self.isUpdating = True
		replytext = u""
		cardsJsonFilename = os.path.join('data', 'MTGcards.json')
		updateNeeded = False
		
		versionFilename = os.path.join('data', 'MTGversion-full.json')
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
		newversionfilename = os.path.join('data', url.split('/')[-1])
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
			replytext =  u"Something went wrong, the latest MtG database version number could not be retrieved."
		else:
			#Replace the old version file with the new one
			if os.path.exists(versionFilename):
				os.remove(versionFilename)
			os.rename(newversionfilename, versionFilename)

		if forceUpdate or latestVersion != currentVersion or not os.path.exists(cardsJsonFilename):
			updateNeeded = True

		if updateNeeded:
			print "[MtG] Updating card database!"
			url = "http://mtgjson.com/json/AllSets-x.json.zip"
			cardzipFilename = os.path.join('data', url.split('/')[-1])
			urllib.urlretrieve(url, cardzipFilename)

			#Since it's a zip, extract it
			zipWithJson = zipfile.ZipFile(cardzipFilename, 'r')
			newcardfilename = os.path.join('data', zipWithJson.namelist()[0])
			if os.path.exists(newcardfilename):
				os.remove(newcardfilename)
			zipWithJson.extractall('data')
			zipWithJson.close()
			#We don't need the zip anymore
			os.remove(cardzipFilename)

			#Load in the new file so we can save it in our preferred format (not per set, but just a dict of cards)
			downloadedCardstore = {}
			with open(newcardfilename, 'r') as newcardfile:
				downloadedCardstore = json.load(newcardfile)
			newcardstore = {}
			print "Going through cards"
			for setcode, set in downloadedCardstore.iteritems():
				for card in set['cards']:
					cardname = card['name'].encode('utf-8').lower()
					addCard = True
					if cardname not in newcardstore:
						newcardstore[cardname] = []
					else:
						for sameNamedCard in newcardstore[cardname]:
							#There are three possibilities: Both text, if the same they're duplicates; Neither text, they're duplicates; One text other not, not duplicates
							#  Since we later ensure that all cards have a 'text' field, instead of checking for 'text in sameNameCard', we check whether 'text' is an empty string
							if ('text' not in card and sameNamedCard['text'] == u"") or (sameNamedCard['text'] != u"" and 'text' in card and sameNamedCard['text'] == card['text']):
								#Since it's a duplicate, update the original card with info on the set it's also in, if it's not in there already
								if set['name'] not in sameNamedCard['sets'].split(', '):
									sameNamedCard['sets'] += ", {}".format(set['name'])
								addCard = False
								break

					if addCard:
						#Remove some other useless data to save some space, memory and time
						keysToRemove = ['imageName', 'variations', 'foreignNames', 'originalText', 'originalType'] #Last three are from the database with extras
						for keyToRemove in keysToRemove:
							card.pop(keyToRemove, None)
						keysToMakeLowerCase = ['manaCost']
						#Make sure all keys are fully lowercase, to make matching them easy
						for keyToMakeLowerCase in keysToMakeLowerCase:
							if keyToMakeLowerCase in card:
								card[keyToMakeLowerCase.lower()] = card[keyToMakeLowerCase]
								card.pop(keyToMakeLowerCase)

						#make sure all stored values are strings, that makes searching later much easier
						for attrib in card:
							#Re.search stumbles over numbers, convert them to strings first
							if isinstance(card[attrib], (int, long, float)):
								card[attrib] = str(card[attrib])
							#Regexes can't search lists either, make them strings too
							elif isinstance(card[attrib], list):
								oldlist = card[attrib]
								newlist = []
								for entry in oldlist:
									#There's lists of strings and lists of ints, handle both
									if isinstance(entry, (int, long, float)):
										newlist.append(str(entry))
									#There's even lists of dictionaries
									elif isinstance(entry, dict):
										newlist.append(SharedFunctions.dictToString(entry))
									else:
										newlist.append(entry.encode('utf-8'))
								card[attrib] = "; ".join(newlist)
							#If lists are hard for the re module, don't even mention dictionaries. A bit harder to convert, but not impossible
							elif isinstance(card[attrib], dict):
								card[attrib] = SharedFunctions.dictToString(card[attrib])

						#To make searching easier later, without all sorts of key checking, make sure these keys always exist
						keysToEnsure = ['text']
						for keyToEnsure in keysToEnsure:
							if keyToEnsure not in card:
								card[keyToEnsure] = u""
						
						card['sets'] = set['name']
						#Finally, put the card in the new storage
						newcardstore[cardname].append(card)


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

			replytext = u"MtG card database successfully updated to version {} (Changelog: http://mtgjson.com/#changeLog).".format(latestVersion)
		else:
			replytext = u"No card update needed, I already have the latest MtG card database version (v {}).".format(latestVersion)

		urllib.urlcleanup()
		self.isUpdating = False
		print "[MtG] updating database took {} seconds".format(time.time() - starttime)
		return replytext

	def updateDefinitions(self, forceUpdate=False):
		starttime = time.time()
		definitionsFileLocation = os.path.join("data", "MTGdefinitions.json")

		#Check if a new rules file exists
		rulespage = requests.get("http://www.wizards.com/Magic/TCG/Article.aspx?x=magic/rules")
		textfileMatch = re.search('<a.*href="(?P<url>http://media.wizards.com/images/magic/tcg/resources/rules/MagicCompRules_(?P<date>\d+)\.txt)">TXT</a>', rulespage.text)
		if not textfileMatch:
			print "[MtG] [definitions update] Unable to locate the URL to the rules text file!"
		else:
			textfileLocation = textfileMatch.group('url')
			date = textfileMatch.group('date')

			oldDefinitionDate = ""
			if not forceUpdate and os.path.exists(definitionsFileLocation):
				with open(definitionsFileLocation, 'r') as definitionsFile:
					definitions = json.load(definitionsFile)
				if '_date' in definitions:
					oldDefinitionDate = definitions['_date']

			if forceUpdate or oldDefinitionDate != date:
				rulesfilelocation = os.path.join("data", "MtGrules.txt")
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

				print "[MtG] Updated definitions file to version {} in {} seconds".format(date, time.time() - starttime)
				return "Definitions successfully updated to the version from {}.".format(date)
			else:
				#No update neccessary
				print "[MtG] No need to update definitions file, {} is still newest. Check took {} seconds".format(date, time.time() - starttime)
				return "No definitions update needed, version {} is still up-to-date.".format(date)