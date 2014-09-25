import json, re, time

import requests
from bs4 import BeautifulSoup

from CommandTemplate import CommandTemplate
import SharedFunctions
from IrcMessage import IrcMessage


class Command(CommandTemplate):
	triggers = ['humble', 'humblebundle']
	helptext = "Displays information about the latest Humble Bundle. Add the 'weekly' parameter to get info on their Weekly sale"
	#callInThread = True

	def execute(self, message):
		"""
		:type message: IrcMessage
		"""
		url = "http://www.humblebundle.com/"
		#Allow for any special bundle search
		if message.messagePartsLength > 0:
			urlSuffix = message.messageParts[0].lower()
			if urlSuffix == 'store':
				message.bot.sendMessage(message.source, "I'm sorry, I can't retrieve store data (yet (maybe))", 'say')
				return
			#Correct a possible typo, since the weekly bundle is called 'weekly' and not 'week'
			elif urlSuffix == 'week':
				url += 'weekly'
			else:
				url += urlSuffix

		pageDownload = requests.get(url)
		if pageDownload.status_code != 200:
			print "[Humble] Page '{}' returned code {}".format(url, pageDownload.status_code)
			message.bot.sendMessage(message.source, "Sorry, I can't retrieve that bundle page. Either their site is down, or that bundle doesn't exist")
			return

		page = BeautifulSoup(pageDownload.content)

		#Get the part of the title up to the first opening parenthesis, since that's where the 'Pay what you wan't message starts
		title = page.title.string[:page.title.string.find('(') - 1]

		#The names of the games (or books) are listed in italics in the description section, get them from there
		gamenames = []
		descriptionElement = page.find(class_='copy-text')
		if not descriptionElement:
			print "[Humble] No description element found!"
		else:
			titleElements = descriptionElement.find_all('em')
			for titleElement in titleElements:
				gamenames.append(titleElement.text)

		#Totals aren't shown on the site immediately, but are edited into the page with Javascript. Get info from there
		totalMoney = -1.0
		contributors = -1
		avgPrice = -1.0
		timeLeft = u""
		for scriptElement in page.find_all('script'):
			script = scriptElement.text
			if script.count("'initial_stats_data':") > 0:
				#This script element contains data like the average price and the time left
				match = re.search("'initial_stats_data':(.+),", script)
				if not match:
					print "[Humble] Expected to find initial values, but failed:"
					print script
				else:
					data = json.loads(match.group(1))
					if 'rawtotal' in data:
						totalMoney = data['rawtotal']
					else:
						print "[Humble] Sales data found, but total amount is missing!"
						print data
					if 'numberofcontributions' in data and 'total' in data['numberofcontributions']:
						contributors = int(data['numberofcontributions']['total'])
					else:
						print "[Humble] Contributor data not found!"
						print data

					if totalMoney > -1.0 and contributors > -1:
						avgPrice = totalMoney / contributors

					timeLeftMatch = re.search('var timing = \{"end": (\d+)\};', script)
					if timeLeftMatch:
						timeLeft = SharedFunctions.durationSecondsToText(int(timeLeftMatch.group(1)) - time.time())
					break

		if totalMoney == -1.0 or contributors == -1 or avgPrice == -1.0:
			replytext = u"Sorry, the data could not be retrieved. This is either because the site is down, or because of some weird bug. Please try again in a little while"
		else:
			replytext = u"{title} has an average price of ${avgPrice:.2f} and raised ${totalMoney:,} from {contributors:,} people."
			if timeLeft != u"":
				replytext += u" It will end in {timeLeft}."
			#If we didn't find any games, pretend like nothing's wrong
			if len(gamenames) > 0:
				replytext += u" It contains {gamecount} titles: {gamelist}."
			replytext = replytext.format(title=title, avgPrice=round(avgPrice, 2), totalMoney=round(totalMoney, 2),
										 contributors=contributors, timeLeft=timeLeft, gamecount=len(gamenames), gamelist=u"; ".join(gamenames))

		message.bot.say(message.source, replytext)
