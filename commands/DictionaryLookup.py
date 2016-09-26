import json, urllib

import requests

from CommandTemplate import CommandTemplate
import GlobalStore
import SharedFunctions


class Command(CommandTemplate):
	triggers = ['define', 'dictionary', 'dict', 'word']
	helptext = "Looks up the definition of the provided word"

	def execute(self, message):
		"""
		:type message: IrcMessage.IrcMessage
		"""

		if message.messagePartsLength == 0:
			return message.reply("Please add a term to search for. You wouldn't want me making up words, trust me")

		#Lower case makes it easier to compare with later
		searchQuery = message.message.lower()

		#Get the data
		try:
			apireply = requests.get("http://api.pearson.com/v2/dictionaries/ldoce5/entries", params={'limit': 100, 'headword': searchQuery}, timeout=15.0)
		except requests.exceptions.Timeout:
			return message.reply("Sorry, the dictionary API took too long to respond. Please try again in a little while. Or a longer while, if the API is temporarily broken")
		#Load the data
		try:
			definitionData = json.loads(apireply.text)
		except ValueError:
			self.logError("[DictLookup] Unexpected reply from Dictionary API:")
			self.logError(apireply.text)
			return message.reply("I'm sorry, the dictionary API I'm using returned some weird data. Tell my owner(s) about it, maybe it's something they can fix? Or just try again in a little while")

		#Check to see if it's a recognised word/term
		if 'total' not in definitionData or definitionData['total'] == 0 or 'results' not in definitionData or len(definitionData['results']) == 0:
			return message.reply("That is apparently not a term this dictionary API is familiar with. Maybe you made a typo? Or maybe you invented a new word!")

		replytext = SharedFunctions.makeTextBold(message.message) + ": "

		#Keep adding definitions until we run out of space
		maxMessageLength = 290  #Be conservative with our max length since we don't take all part lengths into account
		definitionsSkipped = 0
		hasAddedDefinition = False
		fallbackDefinitionEntry = None
		wordTypeReplacements = {'verb': 'v', 'noun': 'n', 'adjective': 'adj', 'adverb': 'adv'}
		for definitionEntry in definitionData['results']:
			#Only add definitions if the search query and the word the entry is about match exactly (so verb forms)
			if definitionEntry['headword'] != searchQuery:
				#Store it in case we end up with no results, then we can show this one
				if fallbackDefinitionEntry is None:
					fallbackDefinitionEntry = definitionEntry
				continue
			for sense in definitionEntry['senses']:
				if 'definition' not in sense:
					continue
				#For some reason 'definition' is a list, usually with only one entry
				for definition in sense['definition']:
					if len(replytext) + len(definition) < maxMessageLength:
						#Add a separator if this isn't the first definition
						if hasAddedDefinition:
							replytext += SharedFunctions.getGreySeparator()
						#Prefix with the word type (verb, noun, etc.)
						if 'part_of_speech' in definitionEntry:
							wordType = definitionEntry['part_of_speech']
							#Shorten the word type so we don't waste space
							if wordType in wordTypeReplacements:
								wordType = wordTypeReplacements[wordType]
							replytext += "[{}] ".format(wordType)
						replytext += definition
						hasAddedDefinition = True
					else:
						definitionsSkipped += 1

		#If we didn't find any definition that matched the search query and wasn't too long, report that
		if not hasAddedDefinition:
			#If we didn't find the literal search query, but we did find at least something, show that
			if fallbackDefinitionEntry is not None and 'senses' in fallbackDefinitionEntry and 'definition' in fallbackDefinitionEntry['senses'][0]:
				replytext = "{}: {}".format(SharedFunctions.makeTextBold(fallbackDefinitionEntry['headword']), fallbackDefinitionEntry['senses'][0]['definition'][0])
				if len(replytext) > maxMessageLength:
					replytext = replytext[:maxMessageLength-5] + "[...]"
				return message.reply(replytext)
			else:
				return message.reply("Sorry, all the definitions I found were either for the wrong word or too long. Maybe try Wiktionary: http://en.wiktionary.org/wiki/Special:Search?search=" + urllib.quote_plus(searchQuery))
		#But if everything is fine and we found some definitions, report 'em!
		else:
			#If we've skipped a few definitions for length, add that info too
			if definitionsSkipped > 0:
				replytext += " ({} skipped)".format(definitionsSkipped)
			return message.reply(replytext)
