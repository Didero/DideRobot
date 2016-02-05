# -*- coding: utf-8 -*-

import re
import urllib
import xml.etree.ElementTree as ElementTree

import requests

from CommandTemplate import CommandTemplate
import GlobalStore
import SharedFunctions


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
		replystring = ""
		if message.messagePartsLength == 0:
			replystring = "No query provided. I'm not just gonna make stuff up to send to Wolfram Alpha, I've got an API call limit! Add your query after the command."
		else:
			replystring = self.searchWolfram(message.message)
		message.bot.sendMessage(message.source, replystring)

	def fetchWolframData(self, query, podsToFetch=5):
		#First check if there is an API key
		if 'wolframalpha' not in GlobalStore.commandhandler.apikeys:
			return (False, "No Wolfram Alpha API key found")

		replystring = ""
		params = {'appid': GlobalStore.commandhandler.apikeys['wolframalpha'], 'input': query}
		if podsToFetch > 0:
			podIndexParam = ""
			for i in xrange(1, podsToFetch):
				podIndexParam += "{},".format(i)
			podIndexParam = podIndexParam[:-1]
			params['podindex'] = podIndexParam
		apireturn = None
		try:
			apireturn = requests.get("http://api.wolframalpha.com/v2/query", params=params, timeout=15.0)
		except requests.exceptions.Timeout:
			return (False, "Sorry, Wolfram Alpha took too long to respond")
		xmltext = apireturn.text
		#Wolfram sends errors back in HTML apparently. Check for that
		if xmltext.startswith('<!DOCTYPE html>'):
			return (False, "Sorry, Wolfram returned unusable data")
		#Since Wolfram apparently doesn't really understand unicode, fix '\:XXXX' characters by turning them into their proper '\uXXXX' characters
		#  (Thanks, ekimekim!)
		xmltext = re.sub(r"\\:[0-9a-f]{4}", lambda x: unichr(int(x.group(0)[2:], 16)), xmltext)
		# When making changes to the encoding, always test a 'euro to gbp' conversion (euro for utf8, gbp for latin-1),
		# power-of-ten conversion (e.g. minutes to millenia), and pokemon (accented e and Japanese characters)
		xmltext = xmltext.encode('utf8')  #Return a string, not a Unicode object
		return (True, xmltext)

	
	def searchWolfram(self, query, podsToParse=5, cleanUpText=True, includeUrl=True):
		replystring = ""
		wolframResult = self.fetchWolframData(query, podsToParse)
		#First check if the query succeeded
		if not wolframResult[0]:
			return wolframResult[1]

		try:
			xml = ElementTree.fromstring(wolframResult[1])
		except ElementTree.ParseError:
			self.logError("[Wolfram] Unexpected reply, invalid XML:")
			self.logError(wolframResult[1])
			return "Wow, that's some weird data. I don't know what to do with this, sorry. Try reformulating your query, or just try again and see what happens"

		if xml.attrib['error'] != 'false':
			replystring = "Sorry, an error occurred. Tell my owner(s) to check the error log"
			self.logError("[Wolfram] An error occurred for the search query '{}'. Reply:".format(query, wolframResult[1]))
		elif xml.attrib['success'] != 'true':
			replystring = "No results found, sorry"
			#Most likely no results were found. See if there are suggestions for search improvements
			if xml.find('didyoumeans') is not None:
				didyoumeans = xml.find('didyoumeans').findall('didyoumean')
				suggestions = []
				for didyoumean in didyoumeans:
					if didyoumean.attrib['level'] != 'low':
						suggestion = didyoumean.text.replace('\n','').strip()
						if len(suggestion) > 0:
							suggestions.append(suggestion)
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
						text = text.replace('\n', ' ').strip()
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
			replystring = replystring.replace('  ', ' ')

		#Make sure we don't spam the channel, keep message length limited
		#  Shortened URL will be about 25 characters, keep that in mind
		messageLengthLimit = 270 if includeUrl else 300
		if len(replystring) > messageLengthLimit:
			replystring = replystring[:messageLengthLimit] + '[...]'

		#Add the search url
		if includeUrl:
			searchUrl = "http://www.wolframalpha.com/input/?i={}".format(urllib.quote_plus(query))
			#If the message would get too long, shorten the result URL
			if len(replystring) + len(searchUrl) > 300:
				searchUrl = SharedFunctions.shortenUrl(searchUrl)[1]
			replystring += " ({})".format(searchUrl)
			
		return replystring
