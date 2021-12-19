import re

import requests

from CommandTemplate import CommandTemplate
from IrcMessage import IrcMessage
from CommandException import CommandException, CommandInputException
import Constants


class Command(CommandTemplate):
	# 'Fandom.com' used to be called 'Wikia.com', support both the old and the new name
	triggers = ['wikipedia', 'wikipediarandom', 'fandom', 'fandomrandom', 'wikia', 'wikiarandom']
	helptext = "Searches Wikipedia or a wiki on Fandom.com for the best-matching article. " \
			   "Usage: '{commandPrefix}wikipedia [searchquery]' or {commandPrefix}fandom [wiki-name] [searchquery]'. " \
			   "Or use '{commandPrefix}wikipediarandom' or '{commandPrefix}fandomrandom [wiki-name]' to get a random article from that wiki" \
			   "'wikia' instead of 'fandom' is also supported because Fandom used to be called Wikia"

	def execute(self, message):
		"""
		:type message: IrcMessage
		"""
		if message.trigger == 'wikipedia' or message.trigger == 'wikipediarandom':
			wikiDisplayName = 'Wikipedia'
			wikiApiUrl = "https://en.wikipedia.org/w/api.php"
			searchQuery = message.message
		elif message.messagePartsLength == 0:
			return message.reply("Please tell me which Fandom wiki you want me to use, there's a LOT of them. Turns out humans write a lot of stories!", "say")
		else:
			wikiName = message.messageParts[0]
			wikiDisplayName = "the {} Fandom wiki".format(wikiName)
			wikiApiUrl = "https://{}.fandom.com/api.php".format(wikiName)
			searchQuery = u" ".join(message.messageParts[1:])

		shouldPickRandomPage = message.trigger.endswith('random')
		#Searches need a search term
		if not shouldPickRandomPage and not searchQuery:
			return message.reply("What do you want me to search for? Or if you don't know what you want, use the '{}random' command and be surprised!".format(message.trigger), "say")

		# We want 1200 characters because that's the maximum allowed, and because we don't know how much we have to chop off because they're preceding images
		# We also want the sectionformat to be 'wiki' so we can see where the intro paragraph ends (We can't use 'exintro' for this because images can come first so we'd only get their caption)
		requestParams = {'format': 'json', 'utf8': True, 'redirects': True, 'action': 'query', 'prop': 'extracts|info',
						 'exchars': 1200, 'exlimit': 1, 'explaintext': True, 'exsectionformat': 'wiki', 'inprop': 'url'}
		# Namespace: 0 means that it only looks at 'actual' articles, and ignores meta pages, user pages, and the like
		if shouldPickRandomPage:
			requestParams['generator'] ='random'
			requestParams['grnnamespace'] =  0
		else:
			requestParams['generator'] = 'search'
			requestParams['gsrnamespace'] = 0
			requestParams['gsrlimit'] = 1
			requestParams['gsrsearch'] = searchQuery

		try:
			apiResult = requests.get(wikiApiUrl, params=requestParams, timeout=10.0)
		except requests.exceptions.Timeout:
			raise CommandException("{} took too long to respond. Maybe try again in a little while?".format(wikiDisplayName))

		if apiResult.status_code == 404:
			# Should only happen for Fandom searches and a non-existent wiki
			raise CommandInputException("{} doesn't appear to exist. Maybe you made a typo? Or maybe you made a whole new fandom!".format(wikiDisplayName))
		if apiResult.status_code != 200:
			self.logError(u"[MediaWiki] {} returned an unexpected result for commandtrigger '{}' and query '{}'. Status code is {}, response is {}".format(wikiApiUrl, message.trigger, searchQuery, apiResult.status_code, apiResult.text))
			raise CommandException("Uh oh, something went wrong with retrieving data from {}. Either they're having issues, or I am. If this keeps happening, please tell my owner(s) to look into this!".format(wikiDisplayName))

		try:
			apiData = apiResult.json()
		except ValueError:
			self.logError(u"[MediaWiki] Invalid JSON reply from API. Wiki url is {}, query was '{}', response is {}".format(wikiApiUrl, searchQuery, apiResult.text))
			raise CommandException("Hmm, the data that {} returned isn't exactly what I expected, I'm not sure what to do with this. If this keeps happening, please tell my owner(s) about this!".format(wikiDisplayName))

		if 'query' not in apiData or 'pages' not in apiData['query'] or "-1" in apiData['query']['pages']:
			raise CommandInputException("Seems like {} doesn't have any information on '{}'. Either you made a typo, or you know more about this than all the wiki editors combined!".format(wikiDisplayName, searchQuery))

		# Get the article text, and clean it up a bit
		articleData = apiData['query']['pages'].popitem()[1]
		articleText = articleData["extract"]
		articleUrl = articleData["canonicalurl"]
		# If we got more text than just from the first section, it's got newlines and a header indicator (multiple '='s in MediaWiki formatting). Only get the first section
		if u'\n=' in articleText:
			articleText = re.split('\n+=+', articleText, maxsplit=1)[0]
		# Some articles put images and captions at the start of the article, separated by tabs, so we have to remove those
		if u'\t' in articleText:
			articleText = articleText.rsplit(u'\t', 1)[1].strip()
		# Replace any remaining newlines with spaces
		if u'\n' in articleText:
			articleText = re.sub('\s*\n+\s*', ' ', articleText)
		# Limit the article text length to a single IRC message
		maxArticleTextLength = Constants.MAX_MESSAGE_LENGTH - len(Constants.GREY_SEPARATOR) - len(articleUrl)
		if len(articleText) > maxArticleTextLength:
			articleText = articleText[:maxArticleTextLength - 5] + u"[...]"

		message.reply(articleText + Constants.GREY_SEPARATOR + articleUrl)
