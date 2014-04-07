import json, re

from twisted.words.protocols.irc import assembleFormattedText, attributes as attr
import requests
from bs4 import BeautifulSoup

from CommandTemplate import CommandTemplate

class Command(CommandTemplate):
	triggers = ['humble', 'humblebundle']
	helptext = "Displays information about the latest Humble Bundle. Add the 'weekly' parameter to get info on their Weekly sale"
	callInThread = True

	def execute(self, bot, user, target, triggerInMsg, msg, msgWithoutFirstWord, msgParts, msgPartsLength):
		replytext = u""
		gamenames = []
		page = None
		title = u""
		isWeekly = (msgWithoutFirstWord.lower() == 'weekly' or msgWithoutFirstWord.lower() == 'week')

		url = "http://www.humblebundle.com/"
		if isWeekly:
			url += 'weekly'

		pagetext = requests.get(url).content
		#BeautifulSoup doesn't handle non-standard newlines very well, it inserts </br> at the very end, messing up searching. Prevent that
		pagetext = pagetext.replace("<br>", "<br />")
		page = BeautifulSoup(pagetext)

		#Title is formatted like "Humble Weekly Sale: [company] (pay what...)"
		if isWeekly:
			titlematches = re.search("(.+) \(", page.title.string)
			if not titlematches:
				#print "No title found in '{}'".format(page.title.string)
				title = "Humble Weekly Sale"
			else:
				title = "The {}".format(titlematches.group(1))
		else:
			titlematches = re.search("(.*) \(", page.title.string)
			if not titlematches:
				#print "No title found in '{}'".format(page.title.string)
				title = "The current Humble Bundle"
			else:
				title = "The " + titlematches.group(1)

		gamecontainers = page.find_all(class_="game-boxes")
		for gamecontainer in gamecontainers:
			#Don't show the soundtracks
			if 'class' in gamecontainer.attrs and 'soundtracks' in gamecontainer['class']:
				continue
			gameEntries = gamecontainer.find_all('li', recursive=False)
			for gameEntry in gameEntries:
				gameEntryLink = gameEntry.find('a')
				if not gameEntryLink:
					continue
				else:
					gamename = u""
					gameEntryLinkTexts = gameEntryLink.find_all(text=True, recursive=False)
					for gameEntryLinkText in gameEntryLinkTexts:
						#Only add it if there is something to add, and if the current text isn't a comment
						if len(gameEntryLinkText.strip()) > 0 and 'Comment' not in str(type(gameEntryLinkText)):
							gamename += ' ' + gameEntryLinkText.strip()
					for smallSubtitle in gameEntry.find_all(class_='small-subtitle'):
						gamename += ' ' + smallSubtitle.text.strip()
				if ('class' in gameEntry.attrs and 'bta' in gameEntry['class']) or gameEntry.find(alt="lock icon"):
					gamename += u" [BTA]"
				elif gameEntry.find(class_='hb-lock blue'):
					gamename += u" [fixed price]"

				gamename = gamename.strip()
				if gamename != u"":
					gamenames.append(gamename)


		#Totals aren't shown on the site immediately, but are edited into the page with Javascript. Get info from there
		totalMoney = -1.0
		contributors = -1
		avgPrice = -1.0
		for scriptElement in page.find_all('script'):
			script = scriptElement.text
			if script.count("'initial_stats_data':") > 0:
				#This script element contains the initial data
				match = re.search("'initial_stats_data':(.+),", script)
				if match is None:
					print "Expected to find initial values, but failed!"
					print script
				else:
					#print "matches found: {}".format(len(match.groups()))
					data = json.loads(match.group(1))
					#print data
					if 'rawtotal' in data:
						totalMoney = data['rawtotal']
						#print "Total: '{0}'; formatted: '{1:,}'".format(data['rawtotal'], round(data['rawtotal'], 2))
						#print "Type of 'total': {}".format(type(data['rawtotal']))
					else:
						print "Sales data found, but total amount is missing!"
						print data
					if 'numberofcontributions' in data and 'total' in data['numberofcontributions']:
						contributors = int(data['numberofcontributions']['total'])
					else:
						print "Contributor data not found!"
						print data

					if totalMoney > -1.0 and contributors > -1:
						avgPrice = totalMoney / contributors

					break

		if totalMoney == -1.0 or contributors == -1 or avgPrice == -1.0:
			replytext = "Sorry, the data could not be retrieved. This is either because the site is down, or because of some weird bug. Please try again in a little while"
		else:
			replytext = u"{title} has an average price of ${avgPrice:.2f} and raised ${totalMoney:,} from {contributors:,} people."
			#If we didn't find any games, pretend like nothing's wrong
			if len(gamenames) > 0:
				replytext += u" It contains {gamelist}"
			replytext = replytext.format(title=title, avgPrice=round(avgPrice, 2), totalMoney=round(totalMoney, 2), contributors=contributors, gamelist="; ".join(gamenames))

		bot.say(target, replytext)
