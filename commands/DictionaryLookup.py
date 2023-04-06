import unicodedata

import requests

from CommandTemplate import CommandTemplate
import GlobalStore
import Constants
from CustomExceptions import CommandException, CommandInputException


class Command(CommandTemplate):
	triggers = ['define']
	helptext = "Looks up the definition of the provided word or term. Or tries to, anyway, because language is hard. Add a word type ('noun', 'verb', ect) before your query to get only results of that type"

	termTypeToAbbreviation = {u'adjective': u'adj', u'noun': u'n', u'verb': u'v'}

	def execute(self, message):
		"""
		:type message: IrcMessage.IrcMessage
		"""
		if 'merriamwebster' not in GlobalStore.commandhandler.apikeys:
			self.logError("[DictionaryLookup] Missing key for Merriam-Webster API")
			raise CommandException("Since I don't know a lot of words myself, I need access to the Merriam-Webster Dictionaries, and I don't seem to have the API key required, sorry! "
								 "Poke my owner(s), they can probably add them", False)

		if message.messagePartsLength == 0:
			raise CommandInputException("Since I don't have a wordlist handy, I can't just pick a random word to define, so you'll have to enter something to look up. Thanks!")

		termTypeToSearch = None
		termToDefine = message.message
		if message.messagePartsLength > 1:
			# Check if the first parameter is a word type, if so only show definitions of that type
			firstArg = message.messageParts[0].lower()
			for termType, abbreviation in self.termTypeToAbbreviation.iteritems():
				if firstArg == termType or firstArg == abbreviation:
					termTypeToSearch = termType
					termToDefine = ' '.join(message.messageParts[1:])
					break

		try:
			apiresult = requests.get("https://dictionaryapi.com/api/v3/references/collegiate/json/" + termToDefine, params={'key': GlobalStore.commandhandler.apikeys['merriamwebster']}, timeout=15.0)
		except requests.exceptions.Timeout:
			raise CommandException("Hmm, it took the dictionary site a bit too long to respond. They're probably busy trying to keep up with internet slang or something. Try again in a bit!")
		if apiresult.status_code != 200:
			raise CommandException("Seems like the dictionary site I use isn't feeling well, since they did not send a happy reply. Give them some time to recover, and try again in a bit")
		# An invalid key or an unknown word both return status code 200. An error returns an error string, and an unknown word just returns an empty result
		try:
			apiData = apiresult.json()
		except Exception as e:
			self.logError("[DictionaryLookup] API returned invalid JSON, probably an error: {}".format(apiresult.text))
			raise CommandException("The dictionary API returned an error, for some reason. Maybe try again later, or tell my owner(s)?")
		if not apiData:
			return message.reply("That term doesn't exist in the dictionary I use. Either they're behind on slang, or you invented a new word!")
		if isinstance(apiData[0], (str, unicode)):
			# If the API returned a list of strings, no direct result was found, but it returned suggestions
			return message.reply(u"That exact term isn't in this dictionary, but maybe you meant: {}".format(', '.join(apiData)))

		# The definitions are in a list, each entry being a dictionary
		# Expanded definitions are hidden pretty deep inside a tree, but there's also a 'shortdef' key with a list of short definitions, which is good enough for us
		comparableTermToDefine = unicodedata.normalize('NFKD', unicode(termToDefine.lower(), encoding='utf-8', errors='replace'))
		definitions = []
		relatedTerms = []
		otherTermTypes = []
		for definitionEntry in apiData:
			# The API returns related terms too, skip those (For some reason this field can contain *'s, remove those first)
			headword = definitionEntry['hwi']['hw'].replace('*', '')
			comparableHeadword = unicodedata.normalize('NFKD', headword.lower())
			if comparableHeadword != comparableTermToDefine and comparableTermToDefine not in definitionEntry['meta']['stems']:
				relatedTerms.append(headword)
				continue
			termType = definitionEntry['fl']
			if termTypeToSearch and termTypeToSearch != termType:
				otherTermTypes.append(termType)
				continue
			if termType in self.termTypeToAbbreviation:
				termType = self.termTypeToAbbreviation[termType]
			for shortDefinition in definitionEntry['shortdef']:
				definition = u"{}: ".format(headword) if comparableHeadword != comparableTermToDefine else u""
				definition += u"{} ({})".format(shortDefinition, termType)
				definitions.append(definition)

		if not definitions:
			# Apparently we didn't find any good definitions for some reason
			replytext = u"No exact definitions found, sorry"
			if otherTermTypes:
				replytext += ". I did find definitions for a{} {} though".format('n' if otherTermTypes[0][0] in 'aeiou' else '', " or ".join(otherTermTypes))
			if relatedTerms:
				replytext += u". Maybe you meant: {}?".format(", ".join(relatedTerms))
		else:
			replytext = u""
			# Keep adding definitions to the output text until we run out of message space
			separatorLength = len(Constants.GREY_SEPARATOR)
			numberOfDefinitionsShown = 0
			for definition in definitions:
				if len(replytext) + separatorLength + len(definitions) < Constants.MAX_MESSAGE_LENGTH:
					replytext += definition + Constants.GREY_SEPARATOR
					numberOfDefinitionsShown += 1
			# Remove the last trailing separator
			if replytext.endswith(Constants.GREY_SEPARATOR):
				replytext = replytext[:-separatorLength]
			# Add how many definitions we skipped, if necessary
			if numberOfDefinitionsShown == 0:
				# There are definitions, but all of them are too long to show in one message. Show the first one anyway
				replytext = definitions[0]
			elif len(definitions) > numberOfDefinitionsShown:
				replytext += u" ({:,} more)".format(len(definitions) - numberOfDefinitionsShown)

		#Done! Show our result
		message.reply(replytext)
