import json, urllib

import requests

from CommandTemplate import CommandTemplate
from IrcMessage import IrcMessage
import Constants


class WikiaApiErrors(object):
	TIMEOUT = 0
	INVALID_WIKIA_NAME = 1
	INVALID_API_CALL = 2
	API_DISABLED = 3
	NO_RESULTS_FOUND = 4
	GENERIC_ERROR = 100


class Command(CommandTemplate):
	triggers = ['wikiasearch', 'wikia', 'wikiarandom']
	helptext = "Searches a wiki on Wikia.com for the best-matching article. Usage: '{commandPrefix}wikiasearch [wiki-name] [search]'. " \
			   "Or use '{commandPrefix}wikiarandom [wiki-name]' to get a random article from that wiki"

	def execute(self, message):
		"""
		:type message: IrcMessage
		"""

		#First check if enough parameters were passed
		if message.messagePartsLength == 0:
			return message.reply("Please tell me which Wikia wiki you want me to search, there's a BILLION of 'em", "say")

		#Searches need a search term
		if message.trigger != 'wikiarandom' and message.messagePartsLength == 1:
			return message.reply("What do you want me to search for on the {} Wikia wiki?".format(message.messageParts[0]), "say")

		wikiName = message.messageParts[0]
		#For 'wikiarandom', retrieve a random page title
		if message.trigger == 'wikiarandom':
			success, result = self.getRandomWikiaArticleName(wikiName)
			searchterm = result if success else None
		#Otherwise, use the provided search term to look for a matching page title
		else:
			searchterm = " ".join(message.messageParts[1:])
			success, result = self.searchForArticleTitle(wikiName, searchterm)

		#If we found a title, use that to retrieve the actual article text
		if success:
			success, result = self.retrieveArticleAbstract(wikiName, result)
		#Check if either call returned an error
		if not success:
			result = self.errorCodeToMessage(result, wikiName, searchterm)
		message.reply(result, "say")

	@staticmethod
	def isPageDisambiguationPage(url, title, pageText):
		if url.endswith("_(disambiguation)"):
			return True
		if pageText.startswith(u"{} may refer to:".format(title)):
			return True
		if pageText.startswith(u"This is a disambiguation page"):
			return True
		return False

	@staticmethod
	def isUrlInvalidWikiaPage(url):
		return url.startswith("http://community.wikia.com/wiki/Community_Central:Not_a_valid_community?from=")

	@staticmethod
	def errorCodeToMessage(errorCode, wikiName, searchterm=None):
		#Show an error message depending on the error returned
		if errorCode == WikiaApiErrors.TIMEOUT:
			return "Wikia apparently got confused, since it's taking ages to respond. Maybe try again in a bit?"
		elif errorCode == WikiaApiErrors.INVALID_WIKIA_NAME:
			return "Apparently the wiki '{}' doesn't exist on Wikia. You invented a new fandom!".format(wikiName)
		elif errorCode == WikiaApiErrors.INVALID_API_CALL:
			return "Huh, seems like something changed at Wikia, it doesn't seem to understand me. You should probably poke my owner(s) so they can look into that"
		elif errorCode == WikiaApiErrors.API_DISABLED:
			return "Aw, seems like the {0} Wikia disabled their API, so I can't look up info for you. You'll have to look it up yourself, sorry: https://{0}.wikia.com".format(wikiName)
		elif errorCode == WikiaApiErrors.NO_RESULTS_FOUND:
			if searchterm:
				return "Apparently the page '{}' doesn't exist. Seems you know more about {} than the fandom! Or maybe you made a typo?".format(searchterm, wikiName)
			else:
				#We won't have a search term if 'wikiarandom' was used
				return "Weirdly, the random page I thought I found doesn't seem to exist? I'm as confused as you are..."
		return "Something went wrong with looking up '{}' on the {} Wikia, and I'm not sure what... Poke my owner(s) about this, see if they can figure out what's up".format(searchterm, wikiName)

	@staticmethod
	def retrieveApiResult(wikiName, apiUrl, params, timeout=10.0):
		"""
		Tries to retrieve data from the Wikia API
		:param wikiName: The name of the Wikia wiki to get data from
		:param apiUrl: The path to the specific API call
		:param params: A dictionary of parameters to pass along to the API
		:param timeout: A timeout in seconds for the API call
		:return: A tuple. The first entry is a boolean, True if the call was successful, False if something went wrong.
				If the call succeeded, the second entry is the dictionary the API call returned, otherwise it's an integer from the WikiaApiErrors enum class saying which error occurred
		"""
		try:
			r = requests.get("http://{}.wikia.com/api/v1/{}".format(wikiName, apiUrl), timeout=10.0, params=params)
		except requests.exceptions.Timeout:
			return (False, WikiaApiErrors.TIMEOUT)

		#If the wiki doesn't exist, we get redirected to a different page
		if Command.isUrlInvalidWikiaPage(r.url):
			return (False, WikiaApiErrors.INVALID_WIKIA_NAME)

		apireply = r.json()
		#Check if the API returned results or an error
		if 'exception' in apireply:
			exceptionType = apireply['exception'].get('type', None)
			if exceptionType == u"MethodNotFoundException":
				#Check the type here instead of the code since it's a 404 too, just like NO_RESULTS_FOUND
				return (False, WikiaApiErrors.INVALID_API_CALL)
			exceptionCode = apireply['exception'].get('code', None)
			if exceptionCode == 403:
				return (False, WikiaApiErrors.API_DISABLED)
			elif exceptionCode == 404:
				return (False, WikiaApiErrors.NO_RESULTS_FOUND)
			#If we reached here, it's an unknown error
			Command.logWarning("[Wikia] An unknown exception was returned by the Wikia API. API result: " + json.dumps(apireply))
			return (False, WikiaApiErrors.GENERIC_ERROR)

		#Loading worked, return the API reply
		return (True, apireply)

	@staticmethod
	def searchForArticleTitle(wikiName, query):
		#Retrieve the API result for this search (or an error message of something went wrong)
		apiResultTuple = Command.retrieveApiResult(wikiName, "Search/List", {"query": query, "limit": "1"})
		if not apiResultTuple[0]:
			return apiResultTuple
		apireply = apiResultTuple[1]  # type: dict

		#If the requested page doesn't exist, the return is empty
		if 'items' not in apireply or len(apireply['items']) == 0:
			return (False, WikiaApiErrors.NO_RESULTS_FOUND)

		#Found at least one article match, return the name of the top one
		return (True, apireply['items'][0]['title'])

	@staticmethod
	def retrieveArticleAbstract(wikiName, articleName):
		#Retrieve the API result for this search (or an error message of something went wrong)
		apiResultTuple = Command.retrieveApiResult(wikiName, "Articles/Details", {"titles": articleName.replace(" ", "_"), "abstract": Constants.MAX_MESSAGE_LENGTH})
		if not apiResultTuple[0]:
			return apiResultTuple
		apireply = apiResultTuple[1]  # type: dict

		#If the requested page doesn't exist, the return is empty
		if 'items' not in apireply or len(apireply['items']) == 0:
			return (False, WikiaApiErrors.NO_RESULTS_FOUND)

		articleId = apireply['items'].keys()[0]
		articleInfo = apireply['items'][articleId]

		#Apparently the page exists. It could still be a redirect page though
		if articleInfo['abstract'].startswith("REDIRECT "):
			redirectArticleName = articleInfo['abstract'].split(' ', 1)[1]
			return Command.retrieveArticleAbstract(wikiName, redirectArticleName)

		#From here it's a success. We need the URL to append
		url = apireply['basepath']
		#The '/wiki/' between Wikia name and article title isn't needed, remove it to save space
		if articleInfo['url'].startswith('/wiki/'):
			url += articleInfo['url'][5:]
		else:
			url += articleInfo['url']

		#Check if it isn't a disambiguation page
		if Command.isPageDisambiguationPage(url, articleInfo['title'], articleInfo['abstract']):
			return (True, "Apparently '{}' can mean multiple things. Who knew? Here's the list of what it can refer to: {}".format(articleName, url))

		#Seems we got an actual article start. Clamp it to the maximum message length
		maxAbstractLength = Constants.MAX_MESSAGE_LENGTH - len(Constants.GREY_SEPARATOR) - len(url)
		articleAbstract = articleInfo['abstract'][:maxAbstractLength].rsplit(' ', 1)[0]
		return (True, articleAbstract + Constants.GREY_SEPARATOR + url)

	@staticmethod
	def getRandomWikiaArticleName(wikiName):
		try:
			page = requests.get('http://{}.wikia.com/wiki/Special:Random'.format(wikiName), timeout=10.0)
		except requests.exceptions.Timeout:
			return (False, WikiaApiErrors.TIMEOUT)

		if Command.isUrlInvalidWikiaPage(page.url):
			return (False, WikiaApiErrors.INVALID_WIKIA_NAME)

		#Get the part of the URL that is the article title
		articleTitle = page.url.split('/wiki/', 1)[1].replace('_', ' ')
		articleTitle = urllib.unquote(articleTitle)
		print "URL: {}; Title: {}".format(page.url, articleTitle)
		return (True, articleTitle)
