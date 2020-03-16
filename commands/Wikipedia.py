import json, re

import requests

from CommandTemplate import CommandTemplate
import Constants
import GlobalStore


class Command(CommandTemplate):
	triggers = ['wikipedia', 'wiki', 'wikirandom']
	helptext = "Searches for the provided text on Wikipedia, and returns the start of the article, if it's found. " \
			   "{commandPrefix}wiki only returns the first sentence, {commandPrefix}wikipedia returns the first paragraph. " \
			   "{commandPrefix}wikirandom returns a random wikipedia page"

	def onLoad(self):
		GlobalStore.commandhandler.addCommandFunctions(__file__, 'searchWikipedia', self.searchWikipedia,
								'getWikipediaArticle', self.getArticleText, 'getRandomWikipediaArticle', self.getRandomWikipediaArticle)

	def getRandomWikipediaArticle(self, addExtendedText=False):
		try:
			page = requests.get('http://en.m.wikipedia.org/wiki/Special:Random/#/random', timeout=10.0)
		except requests.exceptions.Timeout:
			return (False, "Apparently Wikipedia couldn't pick between all of its interesting articles, so it took too long to reply. Sorry!")
		self.logDebug("[wiki] Random page url: {}".format(page.url))
		articleName = re.search(ur"<title.*?>(.+?) - Wikipedia</title>", page.text, re.IGNORECASE).group(1)
		return self.getArticleText(articleName, addExtendedText)

	def searchWikipedia(self, searchterm, addExtendedText=False):
		if not isinstance(searchterm, unicode):
			searchterm = searchterm.decode('utf-8', errors='replace')
		url = u"https://en.wikipedia.org/w/api.php"
		params = {u'format': u'json', u'utf8': 1, u'action': u'query', u'list': u'search', u'srwhat': u'nearmatch',
				 u'srlimit': 1, u'srsearch': searchterm}
		try:
			result = requests.get(url, params=params, timeout=10.0)
		except requests.exceptions.Timeout:
			return (False, "Either that's a difficult search query, or Wikipedia is tired. Either way, that search took too long, sorry")
		result = json.loads(result.text)
		if 'error' in result:
			self.logError("[wiki] An error occurred while searching. Search term: '{}'; Search url: '{}'; error: '{}'".format(searchterm, url, result['error']['info']))
			return (False, "Sorry, an error occurred while searching. Please tell my owner(s) to check my logs ({})".format(result['error']['code']))
		#Check if any results were found
		elif 'search' not in result['query'] or len(result['query']['search']) == 0:
			return (False, "No search results for '{}'".format(searchterm))
		else:
			return self.getArticleText(result['query']['search'][0]['title'], addExtendedText)

	def getArticleText(self, pagename, addExtendedText=False, limitLength=True):

		url = u'https://en.wikipedia.org/w/api.php'
		params = {'format': 'json', 'utf8': '1', 'action': 'query', 'prop': 'extracts', 'redirects': '1',
				  'exintro': '1', 'explaintext': '1', 'exsectionformat': 'plain', 'titles': pagename}
		#If we need to be verbose, get as many characters as we can
		if addExtendedText:
			params['exchars'] = int(Constants.MAX_MESSAGE_LENGTH * 1.2)  #Get some extra characters since we may remove some later
		#Otherwise just get the first sentence
		else:
			params['exsentences'] = '1'
		try:
			apireply = requests.get(url, params=params, timeout=10.0)
		except requests.exceptions.Timeout:
			return (False, "Article retrieval took too long, sorry")
		result = json.loads(apireply.text)
		if 'error' in result:
			self.logError("[wiki] An error occurred while retrieving an article. Page name: '{}'; url: '{}'; error: '{}'".format(pagename, url, result['error']['info']))
			return (False, "Sorry, an error occurred while retrieving the page. Please tell my owner(s) to check my logs ({})".format(result['error']['info']))
		result = result['query']
		if 'pages' not in result or '-1' in result['pages']:
			return (False, "No page about '{}' found, sorry".format(pagename))
		else:
			#The 'pages' dictionary contains a single key-value pair. The key is the (unknown) revision number. So just get the single entry
			pagedata = result['pages'].popitem()[1]
			replytext = pagedata['extract']
			#Check if it's not a disambiguation page (rstrip('.') because sometimes it ends with dots and we want to catch that too)
			if replytext.split('\n', 1)[0].rstrip('.').endswith("may refer to:"):
				replytext = "'{}' has multiple meanings".format(pagename)
			else:
				replytext = replytext.replace('\n', ' ').replace('  ', ' ')
				#Some articles contain a link to a pronunciation sound file. Since that doesn't work here, remove it
				replytext = replytext.replace(" ( listen)", "")
				#Sometimes this leaves empty brackets, remove those too
				replytext = replytext.replace(" ()", "")
			#Make sure the text isn't too long
			if limitLength and len(replytext) > Constants.MAX_MESSAGE_LENGTH:
				replytext = replytext[:Constants.MAX_MESSAGE_LENGTH]
				#Try not to chop up words
				lastSpaceIndex = replytext.rfind(' ')
				if lastSpaceIndex > -1:
					replytext = replytext[:lastSpaceIndex]
				replytext += ' [...]'
			#Add the URL
			replytext += u'{}http://en.wikipedia.org/wiki/{}'.format(Constants.GREY_SEPARATOR, pagedata['title'].replace(u' ', u'_'))
			return (True, replytext)


	def execute(self, message):
		if message.trigger == 'wikirandom':
			replytext = self.getRandomWikipediaArticle()[1]
		elif message.messagePartsLength == 0:
			replytext = "Please provide a term to search for"
		else:
			replytext = self.searchWikipedia(message.message, message.trigger=='wikipedia')[1]
		message.reply(replytext, "say")
