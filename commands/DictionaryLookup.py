import HTMLParser, json

import requests

from CommandTemplate import CommandTemplate
import GlobalStore
import SharedFunctions


class Command(CommandTemplate):
	triggers = ['dictionary', 'dict', 'word']
	helptext = "Looks up the definition of the provided word"

	def execute(self, message):
		"""
		:type message: IrcMessage.IrcMessage
		"""

		if 'mashape' not in GlobalStore.commandhandler.apikeys:
			self.logError("[Dictionary] No API key for MashApe found!")
			message.bot.sendMessage(message.source, "Sorry, I don't seem to have the key required to be able to use this module. Inform my owner, they'll fix it!")
			return

		MAX_MSG_LENGTH = 320

		if message.messagePartsLength == 0:
			message.bot.sendMessage(message.source, "Look up which word? I'm not just going to pick a random one")
			return

		#API doesn't seem to handle spaces. So handle infinitive verbs ('to do') by using the second word instead of the first
		if message.messagePartsLength == 2 and message.messageParts[0].lower() == 'to':
			word = message.messageParts[1].lower()
		elif message.messagePartsLength != 1:
			message.bot.sendMessage(message.source, "I can only look up single words, sorry!")
			return
		else:
			word = message.messageParts[0].lower()
		params = {'mashape-key': GlobalStore.commandhandler.apikeys['mashape'], "word": word}
		apireply = requests.get("https://montanaflynn-dictionary.p.mashape.com/define", params=params)
		print apireply.url
		#Docs for the API: https://market.mashape.com/montanaflynn/dictionary#
		#The API returns a list of dictionaries, each with the actual definition ('text') and an attribution ('attribution')
		try:
			#Load in the slightly cleaned-up text (In some places there are double spaces, for instance)
			definitionDictList = json.loads(apireply.text.replace(u':  ', u': ').replace(u'.  ', u'. '))['definitions']
		except ValueError:
			self.logError("[Dictionary] Unable to parse dictionary API reply as valid JSON: '{}'".format(apireply.text))
			message.bot.sendMessage(message.source, "Hmm, sorry, I can't seem to understand the definition lookup reply. Please try again in a bit, or wait for my owner to fix it!")
			return
		except KeyError:
			self.logError("[Dictionary] Definitions aren't in the expected 'definitions' key: {}".format(apireply.text))
			message.bot.sendMessage(message.source, "This looks... different. Tell my owner the API probably changed, and they need to fix this module")
			return

		definitionsCount = len(definitionDictList)
		if definitionsCount == 0:
			replytext = "I couldn't find a definition for '{}', sorry. Did you maybe make a typo? Or are you just making stuff up?".format(message.message)
		#Ok, now we KNOW there's at least one definition. Let's show it!
		elif definitionsCount == 1:
			replytext = "{}: {}".format(message.message, definitionDictList[0]['text'])
		else:
			#multiple definitions
			replytext = "{:,} definitions: ".format(definitionsCount)

			definitions = []
			lengthCount = len(replytext)

			#Only add definitions if they wouldn't exceed max length (add 3 to account for the separator)
			for i in xrange(definitionsCount):
				definition = definitionDictList.pop(0)['text'].strip()
				if lengthCount + len(definition) + 3 < MAX_MSG_LENGTH:
					definitions.append(definition)
					lengthCount += len(definition) + 3

			replytext += SharedFunctions.addSeparatorsToString(definitions)

			#Say when we had to skip some definitions for length reasons
			if len(definitions) < definitionsCount:
				replytext += " ({:,} skipped)".format(definitionsCount - len(definitions))

		#Fix any HTML entities (like '&amp;')
		replytext = HTMLParser.HTMLParser().unescape(replytext)
		message.bot.sendMessage(message.source, replytext)
