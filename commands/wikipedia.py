import re

import requests
from bs4 import BeautifulSoup

from CommandTemplate import CommandTemplate
import GlobalStore

class Command(CommandTemplate):
	triggers = ['wikipedia', 'wiki', 'wikirandom']
	helptext = "Searches for the provided text on Wikipedia, and returns the start of the article, if it's found. " \
			   "{commandPrefix}wiki only returns the first sentence, {commandPrefix}wikipedia returns the first paragraph. " \
			   "{commandPrefix}wikirandom returns a random wikipedia page"

	def onLoad(self):
		GlobalStore.commandhandler.addCommandFunctions(__file__, 'searchWikipedia', self.searchWikipedia,
								'getWikipediaArticle', self.getWikipediaArticle, 'getRandomWikipediaArticle', self.getRandomWikipediaArticle)

	def searchWikipedia(self, searchterm, addExtendedText=False):
		page = requests.get("http://en.m.wikipedia.org/w/index.php", params={'search': searchterm})
		return self.parseWikipediaArticle(page, addExtendedText, searchterm)

	def getWikipediaArticle(self, url, addExtendedText=False):
		if not 'm.wikipedia' in url:
			url = url.replace('wikipedia', 'm.wikipedia')
		return self.parseWikipediaArticle(requests.get(url), addExtendedText)

	def getRandomWikipediaArticle(self, addExtendedText=False):
		page = requests.get('http://en.m.wikipedia.org/wiki/Special:Random/#/random')
		print "[wiki] Random page url: {}".format(page.url)
		return self.parseWikipediaArticle(page, addExtendedText)

	def parseWikipediaArticle(self, page, addExtendedText=False, searchterm=None):
		replytext = u""
		replyLengthLimit = 300
		minimumSentenceLength = 50
		maximumSearchResults = 3

		wikitext = BeautifulSoup(page.content)
		if searchterm and len(page.history) == 0:
			#We're still on the search page, so the search didn't lead to an article
			replytext = u"Sorry, no article with that name was found. "
			#If it's a simple typo, Wikipedia offers suggestions
			suggestions = wikitext.find(class_="searchdidyoumean")
			if suggestions:
				replytext += suggestions.text + u"?"
			#Otherwise, list the first few search results, if there are any
			else:
				searchresultContainer = wikitext.find(class_="searchresults")
				if searchresultContainer and not searchresultContainer.find(class_="mw-search-nonefound"):
					searchresults = searchresultContainer.find(class_="mw-search-results").find_all('a', limit=maximumSearchResults)
					replytext += u"Perhaps try: "
					for result in searchresults:
						replytext += result.text + u"; "
					replytext = replytext[:-2]

					resultinfo = wikitext.find(class_="results-info")
					if resultinfo:
						resultCount = int(resultinfo.find_all('b')[1].text.replace(',', ''))
						resultCount -= len(searchresults)
						replytext += u" ({:,} more possible results)".format(resultCount)
		else:
			articleContainer = wikitext.find(id="content")  #The actual article is in a div with id 'content'
			articleContainer = articleContainer.find('div')  #For some reason it's nested in another div tag
			replytext = articleContainer.find('p', recursive=False).text  #The article starts with a <p> tag in the root (ignore p-tags in tables)

			#Check if we're on a disambiguation page or on an abbreviation page with multiple meanings
			if replytext.endswith(u"may refer to:") or replytext.endswith(u"may stand for:"):
				title = searchterm
				if not title:
					title = wikitext.find(id='section_0').text
				replytext = u"'{}' has mutliple meanings: {}".format(title, page.url.replace('en.m', 'en', 1))
			else:
				#Remove the links to references ('[1]') from the text (Done before the shortening or linesplitting so it doesn't mess that up)
				replytext = re.sub(r'\[.+?\]', u'', replytext)

				if not addExtendedText:
					#Short reply, just the first sentence
					#If it's too short, add more (Fixes f.i. articles about court cases, 'defendant v. accuser'
					lines = re.split(r"\. (?=[A-Z])", replytext)  #use lookahead ('(?=...)') so the letter isn't cut off
					replytext = lines.pop(0)
					while len(replytext) < minimumSentenceLength and len(lines) > 0:
						replytext += u". " + lines.pop(0)
					replytext = replytext.strip()
					if not replytext.endswith(u'.'):
						replytext += u"."

				#Shorten the reply if it's too long
				if len(replytext) > replyLengthLimit:
					replytext = replytext[:replyLengthLimit]

					#Try not to chop up words
					lastSpaceIndex = replytext.rfind(u' ')
					if lastSpaceIndex > -1:
						replytext = replytext[:lastSpaceIndex]

					replytext += u' [...]'

				if page.url.endswith(u"(disambiguation)"):
					replytext += u" (multiple meanings)"
				#Check if there is a link to a disambiguation page at the top
				#Also check if the link to the disambiguation page doesn't refer to something that also redirects to this page
				#  For instance, if you search for 'British Thermal Unit', it says that BTU redirects there but can also mean other things
				#  If we got there by searching 'British Thermal Unit', don't add 'multiple meanings', if we got there with 'BTU', do
				else:
					notices = articleContainer.find_all("div", class_="hatnote")
					title = searchterm
					if not title:
						title = wikitext.find(id='section_0').text
					disambiguationStringToCompare = u'{} (disambiguation)'.format(title.lower())
					if len(notices) > 0:
						for notice in notices:
							if disambiguationStringToCompare in notice.text.lower():
								replytext += u" (multiple meanings)"
								break

				#Add the URL to the end of the reply, so you can easily click to the full article
				# (On the full Wikipedia, not the mobile version we're using)
				replytext += u" ({})".format(page.url.replace('m.wikipedia', 'wikipedia', 1))
		return replytext

	def execute(self, message):
		"""
		:type message: IrcMessage
		"""

		if message.messagePartsLength == 0 and message.trigger != 'wikirandom':
			replytext = u"Please provide a term to search for"
		else:
			wikiPage = None
			if message.trigger == 'wikirandom':
				replytext = self.getRandomWikipediaArticle()
			else:
				replytext = self.searchWikipedia(message.message, message.trigger=='wikipedia')
		message.bot.say(message.source, replytext)
