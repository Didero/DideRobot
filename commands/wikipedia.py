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
			wikipediaPage = requests.get("http://en.wikipedia.org/wiki/Special:Search?search={}".format(msgWithoutFirstWord))
			wikipediaText = wikipediaPage.content

			#Loading the page into BeautifulSoup takes a full core a second or two, so it's not the best solution. So on to regex, yay!

			#First remove all tables, so the output isn't from an intro or side data table
			wikipediaText = re.sub('<table.*?>.+?</table>', '', wikipediaText, flags=re.DOTALL)

			#The main article is put inside <p> tags
			match = re.search(ur'<p.*?>(.+?)</p>', wikipediaText)
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
					##print "First period at index: {}".format(replytext.find(u'. ')+1)
					#Find the first sentence, which is the part until the first period. If it's a one-sentence paragraph, the sentence is the paragraph, otherwise there's a space and a new sentence
					sentence = re.split('\.[ \Z]', replytext)[0].strip()
					if len(sentence) > 0:
						replytext = sentence
						if not replytext.endswith('.'):
							replytext += '.'
					else:
						print "[wiki] single sentence too short"

				#Cap the length to prevent spamming, neatly at the last space so words don't get cut off
				if len(replytext) > replyLengthLimit:
					replytext = replytext[:replyLengthLimit]

					lastSpaceIndex = replytext.rfind(u' ')
					if lastSpaceIndex > -1:
						replytext = replytext[:lastSpaceIndex]
					
					while replytext.endswith(u',') or replytext.endswith(u'.'):
						replytext = replytext[:-1]
					replytext += u' [...]'

				#If there's a link to a disambuigation page or something similar, it's in a div with a 'dablink' class
				if 'dablink' in wikipediaText:
					replytext += " (Multiple meanings)"

				replytext = u"{replytext} ({url})".format(replytext=replytext, url=wikipediaPage.url)

		bot.say(target, replytext)
