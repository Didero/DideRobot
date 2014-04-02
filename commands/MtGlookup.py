# -*- coding: utf-8 -*-

import gc
import json, os, random, sys, time, urllib, zipfile
import re

from CommandTemplate import CommandTemplate
import GlobalStore

class Command(CommandTemplate):
	triggers = ['mtg', 'mtgf']
	helptext = "Looks up info on 'Magic The Gathering' cards. Provide a card name or a regex match to search for. Or search for 'random', and see what comes up. "
	helptext += "With the parameter 'search', you can enter JSON-style data to search for other attributes, see http://mtgjson.com/ for what's available. {commandPrefix}mtgf adds the flavor text to the result"

	isUpdating = False

	def onStart(self):
		self.updateCardFile(False)

	def execute(self, bot, user, target, triggerInMsg, msg, msgWithoutFirstWord, msgParts, msgPartsLength):
		starttime = time.time()
		replytext = u""
		maxCardsToListInChannel = 20
		maxCardsToListInPm = 50

		searchType = u""
		if msgPartsLength > 1:
			searchType = msgParts[1].lower()

		if msgPartsLength == 1:
			bot.say(target, u"Please provide a card name to search for")
			return
		#Check for update command before file existence, to prevent message that card file is missing after update, which doesn't make much sense
		elif searchType == 'update' or searchType == 'forceupdate':
			if self.isUpdating:
				replytext = u"I'm already updating!"
			elif not bot.factory.isUserAdmin(user):
				replytext = u"Sorry, only admins can use my update function"
			else:
				replytext = self.updateCardFile(msgWithoutFirstWord.lower()=='forceupdate')
			bot.say(target, replytext)
			return
		#Check if the data file even exists
		elif not os.path.exists('MTGcards.json'):
			replytext = u""
			if self.isUpdating:
				replytext = u"I don't have my card database, but I'm solving that problem as we speak! Try again in, oh,  10, 15 seconds"
			else:
				replytext = u"Sorry, I don't appear to have my card database. I'll try to retrieve it though! Give me 20 seconds, tops"
				GlobalStore.reactor.callInThread(self.updateCardFile, True)
			bot.say(target, replytext)
			return
		
		#All entered data is valid, look through the stored cards
		with open('MTGcards.json') as jsonfile:
			cardStore = json.load(jsonfile)

		searchDict = {}
		if searchType == 'search' or (searchType == 'random' and msgPartsLength > 2) or (searchType == 'randomcommander' and msgPartsLength > 2):
			#Advanced search!
			if msgPartsLength <= 2:
				bot.say(target, 'Please provide an advanced search query too, in JSON format, so "key1: value1, key2:value2". Look at www.mtgjson.com for available fields')
				return


			searchterm = " ".join(msgParts[2:])
			if searchterm.startswith('{'):
				searchterm = searchterm[1:]
			if searchterm.endswith('}'):
				searchterm = searchterm[:-1]
			#If the user didn't add (enough) quotation marks, add them in
			expectedQuoteCount = searchterm.count(':') * 4
			if searchterm.count('"') < expectedQuoteCount and searchterm.count("'") < expectedQuoteCount:
				searchterm = searchterm.replace('"', '').replace("'", "")
				#Add a quotation mark at the start and end of the sentence, and before and after each : and ,
				searchterm = '"' + re.sub('((?P<char>:|,) *)', '"\g<char>"', searchterm) + '"'
			searchterm = '{' + searchterm + '}'


			#Prevent quote errors, because JSON requires " instead of '
			searchterm = searchterm.replace("'", '"')
			searchterm = searchterm.lower()

			try:
				print "Trying to parse '{}'".format(searchterm)
				searchDict = json.loads(searchterm)
			except:
				print "JSON parse error: ", sys.exc_info()
				bot.say(target, "That is not a valid search query. It should be entered like JSON, so \"'key': 'value', 'key2': 'value2',...\"")
				return
		#If the only parameter is 'random', just get all cards
		elif searchType == 'random' and msgPartsLength == 2:
			searchDict['name'] = '.*'
		#No fancy search string, just search for a matching name
		elif searchType != 'randomcommander':
			searchDict['name'] = msgWithoutFirstWord.lower()

		#Commander search. Regardless of everything else, it has to be a legendary creature
		if searchType == 'randomcommander' and 'type' not in searchDict:
			searchDict['type'] = '.*legendary.*creature'

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

		#The actual search!
		matchingCards = {}
		for setcode, set in cardStore.iteritems():
			#If we're searching for a specific set, and this one isn't it, no need to go over the cards
			if 'set' in regexDict and regexDict['set'].search(set['name']) is None:
				continue
			for card in set['cards']:
				regexMatchesFound = 0
				#If we didn't get a 'set' match, we wouldn't even be here, so if we did, assume it IS a match
				if 'set' in regexDict:
					regexMatchesFound += 1
				for attrib, regex in regexDict.iteritems():
					if attrib in card and regex.search(card[attrib]) is not None:
						regexMatchesFound += 1
				if regexMatchesFound == regexAttribCount:
					card['set'] = set['name']
					#If we haven't found any other cards with the same name, store it
					if card['name'] not in matchingCards:
						matchingCards[card['name']] = [card]
					#If we have found a similarly named card, check if the cards are exactly the same
					else:
						addCard = True
						for sameNamedCard in matchingCards[card['name']]:
							if sameNamedCard['text'] == card['text']:
								addCard = False
								break
						if addCard:
							matchingCards[card['name']].append(card)
		#print "Cards: {}".format(matchingCards)

		cardnamesFound = len(matchingCards)
		if cardnamesFound > 0:
			#Sometimes searches for a literal title return multiple cards that only contain part of the search. (Try searching for 'jund', for instance). Fix that
			if 'name' in regexDict and regexAttribCount == 1:
				newMatchingCards = {}
				#print "Checking to see if we have a literal title match for '{}'".format(regexDict['name'].pattern)
				for matchingCardname in matchingCards.keys():
					if regexDict['name'].pattern == matchingCardname.lower():
						#print "Literal match found, making that the singular matching card"
						newMatchingCards[matchingCardname] = matchingCards[matchingCardname]
				if len(newMatchingCards) > 0:
					matchingCards = newMatchingCards

			#If the user wants a random card, pick one from the matches
			if searchType == 'random' or searchType == 'randomcommander':
				allcards = []
				for cardname in matchingCards.keys():
					allcards.extend(matchingCards[cardname])
				randomCard = random.choice(allcards)
				matchingCards = {}
				matchingCards[randomCard['name']] = [randomCard]
			cardnamesFound = len(matchingCards)

		#Determine the proper response
		if cardnamesFound == 0:
			replytext += u"Sorry, no card matching your query was found"
		elif cardnamesFound == 1:
			cardsFound = matchingCards[matchingCards.keys()[0]]
			if len(cardsFound) == 1:
				replytext += self.getFormattedCardInfo(cardsFound[0], triggerInMsg=='mtgf')
			else:
				replytext += u"Multiple cards with the same name were found: "
				for cardFound in cardsFound:
					replytext += u"{} [set '{}']; ".format(cardFound['name'].encode('utf-8'), cardFound['set'].encode('utf-8'))
				replytext = replytext[:-2]
		#Check if listing all the found cardnames is viable. The limit is higher for private messages than for channels
		elif cardnamesFound <= maxCardsToListInChannel or (cardnamesFound <= maxCardsToListInPm and not target.startswith('#')):
			replytext += u"Search returned {} cards: {}".format(cardnamesFound, "; ".join(sorted(matchingCards.keys())))
		else:
			replytext += u"Your searchterm returned {} cards, please be more specific".format(cardnamesFound)

		re.purge() #Clear the stored regexes, since we don't need them anymore
		gc.collect() #Make sure memory usage doesn't slowly creep up from loading in the data file (hopefully)
		print "[MtG] Execution time: {} seconds".format(time.time() - starttime)
		bot.say(target, replytext)

	def getFormattedCardInfo(self, card, addExtendedInfo=False):
		replytext = u"{card[name]} [{card[type]}]"
		if 'manacost' in card:
			replytext += u" ({card[manacost]} mana"
			if 'cmc' in card:
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
				#print "Initial 'names' value: '{}'".format(card['names'])
				names = card['names'].split(', ')
				#print "After split: '{}'".format(names)
				if card['name'] in names:
					names.remove(card['name'])
				#print "Removed own name: '{}'".format(names)
				names = ', '.join(names)
				print "rejoined: '{}'".format(names)
				replytext += u", also contains {names}".format(names=names)
			replytext += u")"
		replytext += u"."
		if 'text' in card and len(card['text']) > 0:
			replytext += u" {card[text]}"
		if addExtendedInfo and 'flavor' in card:
			replytext += u" Flavor: {card[flavor]}"
		if addExtendedInfo and 'set' in card:
			replytext += u" [set '{card[set]}']"
		elif 'set' in card and card['set'] in ['Unglued', 'Unhinged', 'Happy Holidays']:
			replytext += u" [in illegal set '{card[set]}'!]"
		#FILL THAT SHIT IN
		replytext = replytext.format(card=card)
		#Clean up the text			Remove brackets around mana cost	Remove newlines but make sure sentences are separated by a period	Prevent double spaces
		replytext = replytext.replace('{', '').replace('}','').replace('.\n','\n').replace('\n\n','\n').replace('\n','. ').replace(u'  ', u' ').strip()
		#replytext = re.sub('[{}]', '', replytext)
		#replytext = re.sub('\.?(\n)+ *', '. ', replytext)
		return replytext


	def updateCardFile(self, forceUpdate=False):
		starttime = time.time()
		self.isUpdating = True
		replytext = u""
		cardsJsonFilename = 'MTGcards.json'
		updateNeeded = False
		
		versionFilename = 'MTGversion-full.json'
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
		print "[MtG] Local version: '{}'".format(currentVersion)

		#Download the latest version file
		url = "http://mtgjson.com/json/version-full.json"
		newversionfilename = url.split('/')[-1]
		urllib.urlretrieve(url, newversionfilename)
		urllib.urlcleanup()

		#Load in that version file
		with open(newversionfilename) as newversionfile:
			versiondata = json.load(newversionfile)
			if 'version' in versiondata:
				latestVersion = versiondata['version']
			else:
				print "[MtG] Unexpected contents of downloaded version file:"
				for key, value in versiondata.iteritems():
					print " {}: {}".format(key, value)
		print "[MtG] Latest version: '{}'".format(latestVersion)
		if latestVersion == "":
			replytext =  u"Something went wrong, the latest MtG database version number could not be retrieved"
		else:
			#Replace the old version file with the new one
			if os.path.exists(versionFilename):
				os.remove(versionFilename)
			os.rename(newversionfilename, versionFilename)

		if forceUpdate or latestVersion != currentVersion:
			updateNeeded = True

		if updateNeeded:
			print "[MtG] Updating card database!"
			url = "http://mtgjson.com/json/AllSets.json.zip"
			cardzipFilename = url.split('/')[-1]
			urllib.urlretrieve(url, cardzipFilename)#, reportDownloadProgress)

			#Since it's a zip, extract it
			zipWithJson = zipfile.ZipFile(cardzipFilename, 'r')
			newcardfilename = zipWithJson.namelist()[0]
			if os.path.exists(newcardfilename):
				os.remove(newcardfilename)
			zipWithJson.extractall()
			zipWithJson.close()
			#We don't need the zip anymore
			os.remove(cardzipFilename)
			#Nor the original card description file
			if os.path.exists(cardsJsonFilename):
				os.remove(cardsJsonFilename)

			#Load in the new file so we can save it in our preferred format (not per set, but just a dict of cards)
			newcards = {}
			with open(newcardfilename, 'r') as newcardfile:
				newcards = json.load(newcardfile)#, parse_float=None, parse_int=None)
			print "Going through cards"
			for setcode, set in newcards.iteritems():
				for card in set['cards']:
					cardname = card['name'].encode('utf-8')

					#Remove some other useless data to save some space, memory and time
					keysToRemove = ['imageName']
					for keyToRemove in keysToRemove:
						card.pop(keyToRemove, None)
					keysToMakeLowerCase = ['manaCost']
					#Make sure all keys are fully lowercase, to make matching them easy
					for keyToMakeLowerCase in keysToMakeLowerCase:
						if keyToMakeLowerCase in card:
							#print "Turning {nonlower}={value} into {lower}={value}".format(nonlower=keyToMakeLowerCase, lower=keyToMakeLowerCase.lower(), value=card[keyToMakeLowerCase])
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
								else:
									newlist.append(entry.encode('utf-8'))
							card[attrib] = ", ".join(newlist)

					#To make searching easier later, without all sorts of key checking, make sure these keys always exist
					keysToEnsure = ['text']
					for keyToEnsure in keysToEnsure:
						if keyToEnsure not in card:
							card[keyToEnsure] = u""


			#Save the new database to disk
			print "Done parsing cards, saving file to disk"
			with open(cardsJsonFilename, 'w') as cardfile:
				#json.dump(cards, cardfile) #This is dozens of seconds slower than below
				cardfile.write(json.dumps(newcards))
			print "Done saving file to disk"

			#Remove the file downloaded from MTGjson.com
			os.remove(newcardfilename)

			replytext = u"MtG Card database successfully updated to version {} (Changelog: http://mtgjson.com/#changeLog)".format(latestVersion)
		else:
			replytext = u"No update needed, I already have the latest MtG card database version (v {})".format(latestVersion)

		self.isUpdating = False
		print "[MtG] updating database took {} seconds".format(time.time() - starttime)
		return replytext
