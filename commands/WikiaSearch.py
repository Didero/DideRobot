import requests

from CommandTemplate import CommandTemplate
from IrcMessage import IrcMessage
import Constants


class Command(CommandTemplate):
	triggers = ['wikiasearch']
	helptext = "Searches a wiki on Wikia.com. Usage: '{commandPrefix}wikiasearch [wiki-name] [search]'. Wiki names aren't case-sensitive, but searches are, sorry"

	def execute(self, message):
		"""
		:type message: IrcMessage
		"""

		#First check if enough parameters were passed
		if message.messagePartsLength == 0:
			return message.reply("Please tell me which Wikia wiki you want me to search, there's a BILLION of 'em", "say")
		elif message.messagePartsLength == 1:
			return message.reply("What do you want me to search for on the {} Wikia wiki?".format(message.messageParts[0]), "say")

		searchterm = " ".join(message.messageParts[1:])
		articleSearchResult = self.retrieveArticleAbstract(message.messageParts[0], searchterm)
		message.reply(articleSearchResult[1], "say")

	@staticmethod
	def retrieveArticleAbstract(wikiName, articleName):
		#Retrieve the page, if we can
		try:
			r = requests.get("http://{}.wikia.com/api/v1/Articles/Details".format(wikiName), params={"titles": articleName.replace(" ", "_"), "abstract": "200"}, timeout=10.0)
		except requests.exceptions.Timeout:
			return (False, "Apparently Wikia got caught up reading that article, because it didn't get back to me. Maybe try again later")
		#If the wiki doesn't exist, we get redirected to a different page
		if r.url == "http://community.wikia.com/wiki/Community_Central:Not_a_valid_community?from={}.wikia.com".format(wikiName.lower()):
			return (False, "Apparently the wiki '{}' doesn't exist on Wikia. You invented a new fandom!".format(wikiName))

		#Request succeeded, wiki exists
		apireply = r.json()

		#If the requested page doesn't exist, the return is empty
		if len(apireply['items']) == 0:
			return (False, "Apparently the page '{}' doesn't exist. Seems you know more about {} than the fandom. Or maybe you made a typo?".format(articleName, wikiName))

		articleId = apireply['items'].keys()[0]
		articleInfo = apireply['items'][articleId]

		print "[WikiaSearch] article info:", articleInfo

		#Apparently the page exists. It could still be a redirect page though
		if articleInfo['abstract'].startswith("REDIRECT "):
			redirectArticleName = articleInfo['abstract'].split(' ', 1)[1]
			return Command.retrieveArticleAbstract(wikiName, redirectArticleName)

		#From here it's a success. We need the URL to append
		url = "{}{}".format(apireply['basepath'], articleInfo['url'])

		#Check if it isn't a disambiguation page
		if articleInfo['abstract'].startswith("{} may refer to:".format(articleInfo['title'])):
			return (True, "Apparently '{}' can mean multiple things. Who knew? Here's the list of what it can mean: {}".format(articleName, url))

		#Seems we got an article start! Return that
		return (True, articleInfo['abstract'] + Constants.GREY_SEPARATOR + url)
