import re

import requests
from bs4 import BeautifulSoup

from CommandTemplate import CommandTemplate

class Command(CommandTemplate):
	triggers = ['wikipedia', 'wiki']
	helptext = "Searches for the provided text on Wikipedia, and returns the start of the article, if it's found. {commandPrefix}wiki only returns the first sentence, {commandPrefix}wikipedia returns the first paragraph"

	def execute(self, bot, user, target, triggerInMsg, msg, msgWithoutFirstWord, msgParts, msgPartsLength):

		replytext = u""
		replyLengthLimit = 300

		if msgPartsLength == 1:
			replytext = u"Please provide a term to search for"
		else:
			searchresponse = requests.get("http://en.wikipedia.org/wiki/Special:Search?search={}".format(msgWithoutFirstWord))
			#print searchpage.content
			print "Number of redirects: {}".format(len(searchresponse.history))
			print "Final URL: {}".format(searchresponse.url)

			#Loading the page into BeautifulSoup takes a full core a second or two, so it's not the best solution. So on to regex, yay!

			match = re.search(ur'<p.*?>(.+?)</p>', searchresponse.content)
			if not match:
				replytext = u"No paragraph matches found!"
			else:
				#Get the part between the <p> tags, the first paragraph of the article
				replytext = match.group(1)
				#Remove all the HTML tags
				replytext = re.sub(ur'<.+?>', '', replytext)
				#Remove the source references (the [1]'s)
				replytext = re.sub(ur'\[\d+\]', '', replytext)
				#Turn the thing back into unicode
				replytext = replytext.decode('utf-8')
				#print "[wiki] replytext before shortening: '{}'".format(replytext)
				if triggerInMsg == 'wiki':
					#Get just the first sentence
					print "First period at index: {}".format(replytext.find(u'. ')+1)
					#Find the first sentence, which is the part until the first period. If it's a one-sentence paragraph, the sentence is the paragraph, otherwise there's a space and a new sentence
					sentence = re.split('\. ?', replytext)[0]
					if len(sentence) > 0:
						replytext = sentence + '.'
					else:
						print "[wiki] single sentence too short"

				#Cap the length to prevent spamming
				if len(replytext) > replyLengthLimit:
					replytext = replytext[:replyLengthLimit] + '[...]'

					'''
					lastSpaceIndex = replytext.rfind(u' ')
					if lastSpaceIndex > -1:
						replytext = replytext[:lastSpaceIndex]
					
					while replytext.endswith(u',') or replytext.endswith(u'.'):
						replytext = replytext[:-1]
					replytext += u'...'
					'''				

				replytext = u"{replytext} ({url})".format(replytext=replytext, url=searchresponse.url)

		bot.say(target, replytext)
