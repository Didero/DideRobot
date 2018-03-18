import json, urllib

import requests

from CommandTemplate import CommandTemplate
import GlobalStore
import Constants
import SharedFunctions


class Command(CommandTemplate):
	triggers = ['define']
	helptext = "Looks up the definition of the provided word or term in the Oxford Dictionary. Or tries to, anyway, because language is hard"

	def execute(self, message):
		"""
		:type message: IrcMessage.IrcMessage
		"""
		appId = GlobalStore.commandhandler.apikeys.get('oxforddictionaries', {}).get('app_id', None)
		appKey = GlobalStore.commandhandler.apikeys.get('oxforddictionaries', {}).get('app_key', None)
		if not appId or not appKey:
			return message.reply("Since I don't know a lot of words myself, I need access to the Oxford Dictionaries to help you out here, and I don't seem to have API keys required, sorry! "
								 "Poke my owner(s), they can probably add them", "say")

		if message.messagePartsLength == 0:
			return message.reply("Since I don't have a wordlist handy, I can't just pick a random word to define, so you'll have to enter something to look up. Thanks!", "say")

		try:
			apiresult = requests.get("https://od-api.oxforddictionaries.com:443/api/v1/entries/en/" + message.message, headers={"app_id": appId, "app_key": appKey},
									 timeout=10.0)
		except requests.exceptions.Timeout:
			return message.reply("Hmm, it took the Oxford site a bit too long to respond. They're probably busy trying to keep up with internet slang or something. Try again in a bit!", "say")

		if apiresult.status_code == 404:
			return message.reply("Apparently that's not a word Oxford Dictionaries knows about. So either it's one of those words only teenagers use, or it doesn't exist. Or you made a typo, which happens to the best of us",
								 "say")
		elif apiresult.status_code != 200:
			return message.reply("Seems like Oxford Dictionary isn't feeling well, since they did not send a happy reply. Give them some time to recover, and try again in a bit", "say")
		#There's always going to be at least one entry from here on, since otherwise we would've gotten a status code 404 reply

		#The result is in a 'results' field. It can list multiple entries, but since they can be different word types, it could make the output confusing, so just use the first entry for now
		data = apiresult.json()['results'][0]
		#In case the found word is different from the entered word, retrieve it from the dataset
		replytext = SharedFunctions.makeTextBold(data['word'])
		#Get the word type of the first entry, since that's what we're going to get the definition(s) from. Word type is 'Noun', 'Verb', etc
		wordType = data['lexicalEntries'][0]['lexicalCategory'].lower()
		if wordType != 'other':
			replytext += " ({})".format(wordType)
		replytext += ": "

		#The actual definitions are inside the 'lexicalEntries' field, which is a list of dictionaries
		# Each dictionary contains an 'entries' field, which is another list of dictionaries
		# Each of those dicts has a 'senses' dictionary list, which contains a 'definitions' list
		#'Eating' the entires list means the definitions will be added in reverse order, but we will be eating that list too, so it'll be reversed again
		definitions = []
		while data['lexicalEntries'][0]['entries']:
			entry = data['lexicalEntries'][0]['entries'].pop()
			while entry['senses']:
				sense = entry['senses'].pop()
				#Not all words have a definition. Something like 'swum' has a 'crossReferenceMarkers' list that mentions which word it's related to
				if 'definitions' in sense:
					definitions.extend(sense['definitions'])
				elif 'crossReferenceMarkers' in sense:
					definitions.extend(sense['crossReferenceMarkers'])
				else:
					definitions.append("[definition not found]")

		#Keep adding definitions to the output textuntil we run out of message space
		separatorLength = len(Constants.GREY_SEPARATOR)
		while definitions and len(replytext) + separatorLength + len(definitions[0]) < Constants.MAX_MESSAGE_LENGTH:
			replytext += definitions.pop() + Constants.GREY_SEPARATOR
		#Remove the last trailing separator
		replytext = replytext[:-separatorLength]
		#Add how much defitions we skipped, if necessary
		if len(definitions) > 0:
			replytext += " ({:,} more)".format(len(definitions))

		#Done! Show our result
		message.reply(replytext, "say")
