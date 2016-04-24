import xml.etree.ElementTree as ElementTree

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

		#First check if we have the required data
		if 'dictionarylookup' not in GlobalStore.commandhandler.apikeys:
			self.logError("[Dictionary] No API key for DictionaryLookup found!")
			return message.reply("Sorry, I don't seem to have the key required to be able to use this module. Inform my owner, they'll fix it!")
		if message.messagePartsLength == 0:
			return message.reply("Look up which word? I'm not just going to pick a random one")

		searchQuery = message.message.lower()
		#Retrieve the definition
		apireply = requests.get('http://www.dictionaryapi.com/api/v1/references/collegiate/xml/{}?key={}'.format(searchQuery, GlobalStore.commandhandler.apikeys['dictionarylookup']))
		xmltext = apireply.text.encode('utf8')
		#<fw> tags are useless and mess everything up. They're links to other definitions on the site, but in here they just confuse the XML parser
		#There's also a few fields only used to indicate a certain layout. Remove those too
		for field in ('fw', 'd_link', 'i_link', 'dx_ety', 'dx_def', 'it', 'bold', 'bit'):
			xmltext = xmltext.replace('<{}>'.format(field), '').replace('</{}>'.format(field), '')
		xmldata = ElementTree.fromstring(xmltext)

		maxMessageLength = 290

		#Check if we have actual results or if the user made a typo or something. If there is one or more 'suggestion' entry, it's not an existing word
		if xmldata.find('suggestion') is not None:
			replytext = "That term doesn't seem to exist. Did you perhaps mean: "
			#List all the suggestions, at least until we run out of room
			for suggestionNode in xmldata.findall('suggestion'):
				suggestion = suggestionNode.text
				if len(replytext) + len(suggestion) < maxMessageLength:
					replytext += suggestion + '; '
			replytext = replytext[:-2]  #Remove the last semicolon
			return message.reply(replytext)

		#Check if there are any definitions
		if xmldata.find('entry') is None:
			return message.reply("No definition of that term found, sorry".format(message.message))

		#Definition(s) found. List as many as we can
		entriesSkipped = 0
		definitionsSkipped = 0
		replytext = SharedFunctions.makeTextBold(message.message) + ':'
		for entry in xmldata.findall('entry'):
			#The API returns terms containing the search term too. If the entry isn't literally the search term, skip it
			entryword = entry.find('ew').text.lower()
			if entryword != searchQuery:
				continue
			#First check if the required fields exist
			if entry.find('fl') is None:
				#Maybe it suggests an alternative spelling?
				cognate = entry.find('cx')
				if cognate is None or cognate.find('cl') is None or cognate.find('ct') is None:
					continue
				replytext += " {} {}".format(cognate.find('cl').text, cognate.find('ct').text)
				continue
			#Prefix the type of word it is
			wordType = entry.find('fl').text
			if entriesSkipped > 0 and len(replytext) + len(wordType) >= maxMessageLength:
				entriesSkipped += 1
			else:
				replytext += ' [{}] '.format(wordType)
				#Now go through all the <def>initions, to get the actual definitions
				for definitionNode in entry.find('def').findall('dt'):
					definition = definitionNode.text.strip().strip(':').strip()  #Whether an item stars with a space and then a colon or vice versa is inconsistent
					if len(definition) == 0:
						continue
					if len(replytext) + len(definition) >= maxMessageLength:
						definitionsSkipped += 1
					else:
						replytext += definition + '; '
				#Check if it doesn't just end with the wordType indicator
				if replytext.endswith('] '):
					replytext = replytext[:replytext.rfind('[')].rstrip()
					entriesSkipped += 1  #Increment this because we didn't add anything from this entry
				else:
					replytext = replytext.rstrip('; ')  #Remove the trailing separator
		if entriesSkipped > 0 or definitionsSkipped > 0:
			replytext += " ({:,} skipped)".format(entriesSkipped + definitionsSkipped)

		message.reply(replytext)
