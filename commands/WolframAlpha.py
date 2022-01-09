# -*- coding: utf-8 -*-

import re
import urllib
import xml.etree.ElementTree as ElementTree

import requests

from CommandTemplate import CommandTemplate
import Constants
import GlobalStore
from IrcMessage import IrcMessage
from CustomExceptions import CommandException


class Command(CommandTemplate):
	triggers = ['wolfram', 'wolframalpha', 'wa']
	helptext = "Sends the provided query to Wolfram Alpha and shows the results, if any"
	callInThread = True  #WolframAlpha can be a bit slow

	def onLoad(self):
		GlobalStore.commandhandler.addCommandFunctions(__file__, "fetchWolframAlphaData", self.fetchWolframData, "searchWolframAlpha", self.searchWolfram)

	def execute(self, message):
		"""
		:type message: IrcMessage
		"""
		if message.messagePartsLength == 0:
			message.reply("No query provided. I'm not just gonna make stuff up to send to Wolfram Alpha, I've got an API call limit! Add your query after the command.", "say")
		else:
			message.reply(self.searchWolfram(message.message), "say")

	def fetchWolframData(self, query, podsToFetch=5):
		#First check if there is an API key
		if 'wolframalpha' not in GlobalStore.commandhandler.apikeys:
			raise CommandException("No Wolfram Alpha API key found")

		params = {'appid': GlobalStore.commandhandler.apikeys['wolframalpha'], 'input': query}
		if podsToFetch > 0:
			podIndexParam = ""
			for i in xrange(1, podsToFetch):
				podIndexParam += "{},".format(i)
			podIndexParam = podIndexParam[:-1]
			params['podindex'] = podIndexParam
		try:
			apireturn = requests.get("http://api.wolframalpha.com/v2/query", params=params, timeout=10.0)
		except requests.exceptions.Timeout:
			raise CommandException("Sorry, Wolfram Alpha took too long to respond")
		xmltext = apireturn.text
		#Wolfram sends errors back in HTML apparently. Check for that
		if xmltext.startswith('<!DOCTYPE html>'):
			self.logError("Wolfram API returned an HTML page:")
			self.logError(xmltext)
			raise CommandException("Sorry, Wolfram returned unusable data")
		#Since Wolfram apparently doesn't really understand unicode, fix '\:XXXX' characters by turning them into their proper '\uXXXX' characters
		#  (Thanks, ekimekim!)
		xmltext = re.sub(r"\\:[0-9a-f]{4}", lambda x: unichr(int(x.group(0)[2:], 16)), xmltext)
		# When making changes to the encoding, always test a 'euro to gbp' conversion (euro for utf8, gbp for latin-1),
		# power-of-ten conversion (e.g. minutes to millenia), and pokemon (accented e and Japanese characters)
		xmltext = xmltext.encode('utf8')  #Return a string, not a Unicode object
		return xmltext

	
	def searchWolfram(self, query, podsToParse=5, cleanUpText=True, includeUrl=True):
		replystring = ""
		wolframResult = self.fetchWolframData(query, podsToParse)

		try:
			xml = ElementTree.fromstring(wolframResult)
		except ElementTree.ParseError:
			self.logError("[Wolfram] Unexpected reply, invalid XML:")
			self.logError(wolframResult)
			raise CommandException("Wow, that's some weird data. I don't know what to do with this, sorry. Try reformulating your query, or just try again and see what happens")

		if xml.attrib['error'] != 'false':
			replystring = "Sorry, an error occurred. Tell my owner(s) to check the error log, maybe they can fix it. It could also be an error on WolframAlpha's side though"
			self.logError("[Wolfram] An error occurred for the search query '{}'. Reply: {}".format(query, wolframResult[1]))
		elif xml.attrib['success'] != 'true':
			replystring = "No results found, sorry"
			#Most likely no results were found. See if there are suggestions for search improvements
			if xml.find('didyoumeans') is not None:
				didyoumeans = xml.find('didyoumeans').findall('didyoumean')
				suggestions = []
				for didyoumean in didyoumeans:
					if didyoumean.attrib['level'] != 'low':
						suggestion = didyoumean.text.replace('\n', '').strip()
						if len(suggestion) > 0:
							suggestions.append(suggestion.encode('utf-8'))
				if len(suggestions) > 0:
					replystring += ". Did you perhaps mean: {}".format(", ".join(suggestions))
		else:
			pods = xml.findall('pod')
			resultFound = False
			for pod in pods[1:]:
				if pod.attrib['title'] == "Input":
					continue
				for subpod in pod.findall('subpod'):
					text = subpod.find('plaintext').text
					#If there's no text, or if it's a dumb result ('3 euros' returns coinweight, which is an image), skip this pod
					if text is None or text.startswith('\n'):
						continue
					if cleanUpText:
						text = text.replace('\n', Constants.GREY_SEPARATOR).strip()
					#If there's no text in this pod (for instance if it's just an image)
					if len(text) == 0:
						continue
					replystring += text
					resultFound = True
					break
				if resultFound:
					break

			if not resultFound:
				replystring += "Sorry, results were either images, irrelevant or non-existent"

		if cleanUpText:
			replystring = re.sub(' {2,}', ' ', replystring)

		#Make sure we don't spam the channel, keep message length limited
		#  Shortened URL will be about 25 characters, keep that in mind
		messageLengthLimit = Constants.MAX_MESSAGE_LENGTH
		if includeUrl:
			messageLengthLimit -= 30

		if len(replystring) > messageLengthLimit:
			replystring = replystring[:messageLengthLimit] + '[...]'

		#Add the search url
		if includeUrl:
			replystring += "{}http://www.wolframalpha.com/input/?i={}".format(Constants.GREY_SEPARATOR, urllib.quote_plus(query))
			
		return replystring
