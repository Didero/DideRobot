import requests

from CommandTemplate import CommandTemplate
from IrcMessage import IrcMessage
import Constants


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

		#Getting a random page only needs a wiki name
		if message.trigger == 'wikiarandom':
			return message.reply(Command.getRandomWikiaArticle(message.messageParts[0])[1])

		#Searches need a search term
		if message.messagePartsLength == 1:
			return message.reply("What do you want me to search for on the {} Wikia wiki?".format(message.messageParts[0]), "say")

		searchterm = " ".join(message.messageParts[1:])
		success, articleTitleOrError = self.searchForArticleTitle(message.messageParts[0], searchterm)
		if not success:
			#Searching for the article went wrong, just say the error message
			return message.reply(articleTitleOrError, "say")
		#Found an article name, retrieve and say the article abstract (or the error message if something goes wrong)
		message.reply(self.retrieveArticleAbstract(message.messageParts[0], articleTitleOrError)[1], "say")

	@staticmethod
	def isPageDisambiguationPage(url, title, pageText):
		if url.endswith("_(disambiguation)"):
			return True
		if pageText.startswith("{} may refer to:".format(title)):
			return True
		if pageText.startswith("This is a disambiguation page"):
			return True
		return False

	@staticmethod
	def isUrlInvalidWikiaPage(url):
		return url.startswith("http://community.wikia.com/wiki/Community_Central:Not_a_valid_community?from=")

	@staticmethod
	def retrieveApiResult(wikiName, apiUrl, params, timeout=10.0):
		try:
			r = requests.get("http://{}.wikia.com/api/v1/{}".format(wikiName, apiUrl), timeout=10.0, params=params)
		except requests.exceptions.Timeout:
			return (False, "Wikia apparently got confused about that query, since it's taking ages. Maybe try again in a bit?")

		#If the wiki doesn't exist, we get redirected to a different page
		if Command.isUrlInvalidWikiaPage(r.url):
			return (False, "Apparently the wiki '{}' doesn't exist on Wikia. You invented a new fandom!".format(wikiName))

		#Loading worked, return the API reply
		return (True, r.json())

	@staticmethod
	def searchForArticleTitle(wikiName, query):
		#Retrieve the API result for this search (or an error message of something went wrong)
		apiResultTuple = Command.retrieveApiResult(wikiName, "Search/List", {"query": query, "limit": "1"})
		if not apiResultTuple[0]:
			return apiResultTuple
		apireply = apiResultTuple[1]

		#Check if no results were found
		if 'items' not in apireply:
			return (False, "The term '{}' doesn't seem to exist in the {} fandom. Time to write fanfic about it!".format(query, wikiName))

		#Found at least one article match, return the name of the top one
		return (True, apireply['items'][0]['title'])

	@staticmethod
	def retrieveArticleAbstract(wikiName, articleName):
		#Retrieve the API result for this search (or an error message of something went wrong)
		apiResultTuple = Command.retrieveApiResult(wikiName, "Articles/Details", {"titles": articleName.replace(" ", "_"), "abstract": Constants.MAX_MESSAGE_LENGTH})
		if not apiResultTuple[0]:
			return apiResultTuple
		apireply = apiResultTuple[1]

		#If the requested page doesn't exist, the return is empty
		if len(apireply['items']) == 0:
			return (False, "Apparently the page '{}' doesn't exist. Seems you know more about {} than the fandom. Or maybe you made a typo?".format(articleName, wikiName))

		articleId = apireply['items'].keys()[0]
		articleInfo = apireply['items'][articleId]

		#Apparently the page exists. It could still be a redirect page though
		if articleInfo['abstract'].startswith("REDIRECT "):
			redirectArticleName = articleInfo['abstract'].split(' ', 1)[1]
			return Command.retrieveArticleAbstract(wikiName, redirectArticleName)

		#From here it's a success. We need the URL to append
		url = "{}{}".format(apireply['basepath'], articleInfo['url'])

		#Check if it isn't a disambiguation page
		if Command.isPageDisambiguationPage(url, articleInfo['title'], articleInfo['abstract']):
			return (True, "Apparently that can mean multiple things. Who knew? Here's the list of what it can refer to: {}".format(articleName, url))

		#Seems we got an actual article start. Clamp it to the maximum message length
		maxAbstractLength = Constants.MAX_MESSAGE_LENGTH - len(Constants.GREY_SEPARATOR) - len(url)
		articleAbstract = articleInfo['abstract'][:maxAbstractLength].rsplit(' ', 1)[0]
		return (True, articleAbstract + Constants.GREY_SEPARATOR + url)

	@staticmethod
	def getRandomWikiaArticle(wikiName):
		try:
			page = requests.get('http://{}.wikia.com/wiki/Special:Random'.format(wikiName), timeout=10.0)
		except requests.exceptions.Timeout:
			return (False, "Apparently Wikia couldn't pick between all of its interesting articles, so it took too long to reply. Sorry!")

		if Command.isUrlInvalidWikiaPage(page.url):
			return (False, "That doesn't appear to be a valid Wikia wiki. Seems like you're good enough at making up random stuff that you don't need me!")

		#Get the part of the URL that is the article title
		articleName = page.url.split('/wiki/', 1)[1]
		#And retrieve the abstract of the article in a more easily parsable format
		return Command.retrieveArticleAbstract(wikiName, articleName)
