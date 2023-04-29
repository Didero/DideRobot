import json

import requests

from commands.CommandTemplate import CommandTemplate
from IrcMessage import IrcMessage


class Command(CommandTemplate):
	triggers = ['translate']
	helptext = "Translates the provided text. The first argument should be a two-letter country code ('it' for Italy, etc.) if you want to translate from English, " \
			   "or the source language and the target language separated by a '|' (So 'fi|en' to translate from Finnish to English)"

	def execute(self, message):
		"""
		:type message: IrcMessage
		"""

		#API reference: http://mymemory.translated.net/doc/spec.php
		if message.messagePartsLength == 0:
			replytext = "This module " + self.helptext[0].lower() + self.helptext[1:]
		elif message.messagePartsLength == 1:
			replytext = "That's not enough parameters, I'm gonna need both a language identifier and some text"
		elif '|' not in message.messageParts[0] and len(message.messageParts[0]) != 2:
			replytext = "If you only provide a single language code, it should be a two-letter language identifier, I'm not sure how to interpret '{}'".format(message.messageParts[0])
		elif '|' in message.messageParts[0] and len(message.messageParts[0]) != 5:
			replytext = "If you provide two language codes with a separator, both codes can only be two letters long, I'm not sure which languages '{}' refers to".format(message.messageParts[0])
		else:
			#Let's just assume everything is right, we've done enough checks. Send in the data!
			lang = message.messageParts[0]
			if '|' not in lang:
				lang = 'en|' + lang

			params = {'q': ' '.join(message.messageParts[1:]), 'langpair': lang, 'of': 'json'}
			try:
				result = json.loads(requests.get('http://api.mymemory.translated.net/get', params=params, timeout=15.0).text)
			except requests.exceptions.Timeout:
				message.reply("Apparently that's such a difficult {} the translation API had some trouble with it and/or has given up. "
							  "Either way the API took too long to respond, sorry".format('sentence' if ' ' in params['q'] else 'word'))
				return
			if result['responseStatus'] != 200:
				#Something went wrong, the error is in 'responseDetails' (though sometimes that field is not there)
				#  It's in all-caps though, so reduce the shouting a bit
				error = result.get('responseDetails')
				if not error:
					error = "Unknown Error"
				error = error.lower()
				#An invalid language code gives an error message that's too long and a bit confusing. Correct that
				if 'is an invalid target language' in error:
					error = error[:error.index(' . example')] + '. Look for the right ISO 639-1 code here: https://en.wikipedia.org/wiki/List_of_ISO_639-1_codes'
				replytext = "Something went wrong with your query: " + error
			else:
				#The main translation returned doesn't take quality into account. Look through the matches ourselves
				translationMatchIndex = -1.0
				translation = ""
				for match in result['matches']:
					#Stored quality can either be an integer or a string
					currentQuality = match['quality']
					if not isinstance(currentQuality, int):
						try:
							currentQuality = int(currentQuality)
						except (ValueError, TypeError):
							continue
					#Ignore bad translations
					if currentQuality <= 50:
						continue
					if match['match'] > translationMatchIndex:
						translationMatchIndex = match['match']
						translation = match['translation']
				if len(translation) == 0:
					replytext = "Translation is empty, sorry. Are you sure you entered something? If so, sorry!"
				else:
					replytext = "Translation: " + translation

		message.bot.sendMessage(message.source, replytext)