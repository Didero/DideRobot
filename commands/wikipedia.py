import re

import requests
from bs4 import BeautifulSoup

from CommandTemplate import CommandTemplate


class Command(CommandTemplate):
	triggers = ['wikipedia', 'wiki', 'randomwiki']
	helptext = "Searches for the provided text on Wikipedia, and returns the start of the article, if it's found. " \
			   "{commandPrefix}wiki only returns the first sentence, {commandPrefix}wikipedia returns the first paragraph. " \
			   "{commandPrefix}randomwiki returns a random wikipedia page"

	def execute(self, message):
		"""
		:type message: IrcMessage
		"""
		replytext = u""
		replyLengthLimit = 300

		if message.messagePartsLength == 0 and message.trigger != 'randomwiki':
			replytext = u"Please provide a term to search for"
		else:
			wikiPage = None
			if message.trigger == 'randomwiki':
				wikiPage = requests.get('http://en.m.wikipedia.org/wiki/Special:Random/#/random')
			else:
				wikiPage = requests.get("http://en.m.wikipedia.org/w/index.php", params={'search': message.message})
			wikitext = BeautifulSoup(wikiPage.content)
			if len(wikiPage.history) == 0:
				#We're still on the search page, so the search didn't lead to an article
				replytext = u"Sorry, no article with that name found found. "
				suggestions = wikitext.find(class_="searchdidyoumean")
				if suggestions:
					replytext += suggestions.text + u"?"
			else:
				articleContainer = wikitext.find(id="content")  #The actual article is in a div with id 'content'
				articleContainer = articleContainer.find('div')  #For some reason it's nested in another div tag
				replytext = articleContainer.find('p', recursive=False).text  #The article starts with a <p> tag in the root (ignore p-tags in tables)

				#Check if we're on a disambiguation page
				if replytext.endswith(u"may refer to:"):
					replytext = u"'{}' can refer to multiple things: {}".format(message.message, wikiPage.url.replace('en.m', 'en', 1))
				else:
					if message.trigger != u'wikipedia':
						#Short reply
						replytext = replytext.split(u". ", 1)[0]
						if not replytext.endswith(u'.'):
							replytext += u"."

					#Remove the links to references ('[1]') from the text
					replytext = re.sub(r'\[.+\]', u'', replytext)

					#Shorten the reply if it's too long
					if len(replytext) > replyLengthLimit:
						replytext = replytext[:replyLengthLimit]

						#Try not to chop up words
						lastSpaceIndex = replytext.rfind(u' ')
						if lastSpaceIndex > -1:
							replytext = replytext[:lastSpaceIndex]

						replytext += u' [...]'

					#Check if there is a link to a disambiguation page at the top
					#Also check if the link to the disambiguation page doesn't refer to something that also redirects to this page
					#  For instance, if you search for 'British Thermal Unit', it says that BTU redirects there but can also mean other things
					#  If we got there by searching 'British Thermal Unit', don't add 'multiple meanings', if we got there with 'BTU', do
					notices = articleContainer.find_all("div", class_="hatnote")
					disambiguationStringToCompare = u'{} (disambiguation)'.format(message.message.lower())
					if len(notices) > 0:
						for notice in notices:
							if disambiguationStringToCompare in notice.text.lower():
								replytext += u" (multiple meanings)"
								break

					#Add the URL to the end of the reply, so you can easily click to the full article
					# (On the full Wikipedia, not the mobile version we're using)
					replytext += u" ({})".format(wikiPage.url.replace('en.m', 'en', 1))

		message.bot.say(message.source, replytext)
