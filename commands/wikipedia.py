import re, time

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
				replytext = wikitext.find(id="content")  #The actual article is in a div with id 'content'
				replytext = replytext.find('div')  #For some reason it's nested in another div tag
				replytext = replytext.find('p', recursive=False)  #The article starts with a <p> tag in the root (ignore p-tags in tables)
				replytext = replytext.text  #Get the actual text, without any HTML

				if message.trigger != 'wikipedia':
					#Short reply
					replytext = replytext.split(". ", 1)[0] + "."

				#Shorten the reply if it's too long
				if len(replytext) > replyLengthLimit:
					replytext = replytext[:replyLengthLimit]

					#Try not to chop up words
					lastSpaceIndex = replytext.rfind(u' ')
					if lastSpaceIndex > -1:
						replytext = replytext[:lastSpaceIndex]

					replytext += u' [...]'

				#Add the URL to the end of the reply, so you can easily click to the full article
				# (On the full Wikipedia, not the mobile version we're using)
				replytext += u" ({})".format(wikiPage.url.replace('en.m', 'en', 1))

		message.bot.say(message.source, replytext)
