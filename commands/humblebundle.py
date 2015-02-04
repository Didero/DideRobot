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

		try:
			pageDownload = requests.get(url)
		except requests.ConnectionError:
			message.bot.sendMessage(message.source, "Sorry, I couldn't connect to the Humble Bundle site. Try again in a little while!")
			return

		if pageDownload.status_code != 200:
			print "[Humble] Page '{}' returned code {}".format(url, pageDownload.status_code)
			message.bot.sendMessage(message.source, "Sorry, I can't retrieve that bundle page. Either their site is down, or that bundle doesn't exist")
			return

		page = BeautifulSoup(pageDownload.content)

		#Get the part of the title up to the first opening parenthesis, since that's where the 'Pay what you wan't message starts
		title = page.title.string[:page.title.string.find('(') - 1]

		#First (try to) get a list of all the games with price requirements
		lockedGames = {'BTA': [], 'Fixed': []}
		for lockedGameElement in page.find_all('i', class_='hb-lock'):
			lockType = None
			if 'green' in lockedGameElement.attrs['class']:
				lockType = 'BTA'
			elif 'blue' in lockedGameElement.attrs['class']:
				lockType = 'Fixed'
			else:
				#print "[Humble] Unknown Lock type for game '{}': '{}'".format(" ".join(lockedGameElement.stripped_strings), lockedGameElement.attrs['class'])
				continue
			#If the game name consists of a single line (and it's not empty) store that
			if lockedGameElement.string and len(lockedGameElement.string) > 0:
				lockedGames[lockType].append(lockedGameElement.string.strip())
			#Multiple lines. Add both the first line, and a combination of all the lines
			else:
				lockedGames[lockType].append(list(lockedGameElement.stripped_strings)[0].strip())
				lockedGames[lockType].append(" ".join(lockedGameElement.stripped_strings))

		#The names of the games (or books) are listed in italics in the description section, get them from there
		gamePriceCategories = {"PWYW": [], "BTA": [], "Fixed": [], "Unknown": []}
		descriptionElement = page.find(class_='bundle-info-text')
		gameFound = False
		if not descriptionElement:
			print "[Humble] No description element found!"
		else:
			for paragraph in descriptionElement.find_all('p'):
				strongElement = paragraph.find('strong')
				#If there is a strong element, and it's at the start of the paragraph, AND we've already found names, we're done
				if strongElement and paragraph.text.startswith(strongElement.text) and gameFound:
						break
				#Otherwise, add all the titles listed to the collection
				for titleElement in paragraph.find_all('em'):
					gameFound = True
					gamename = titleElement.text
					#See if this title is in the locked-games lists we found earlier
					if gamename in lockedGames['BTA']:
						gamePriceCategories['BTA'].append(gamename)
					elif gamename in lockedGames['Fixed']:
						gamePriceCategories['Fixed'].append(gamename)
					else:
						gamePriceCategories['PWYW'].append(gamename)

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

			#The time variable is in a different script than the other data, search for it separately
			timeLeftMatch = re.search('var timing = \{"start": \d+, "end": (\d+)\};', script)
			if timeLeftMatch:
				timeLeft = SharedFunctions.durationSecondsToText(int(timeLeftMatch.group(1)) - time.time(), 'm')

			#If we found all the data we need, we can stop
			if avgPrice > -1.0 and timeLeft != u"":
				break

		if totalMoney == -1.0 or contributors == -1 or avgPrice == -1.0:
			replytext = u"Sorry, the data could not be retrieved. This is either because the site is down, or because of some weird bug. Please try again in a little while"
		else:
			replytext = u"{} has an average price of ${:.2f} and raised ${:,} from {:,} people.".format(title, round(avgPrice, 2), round(totalMoney, 2), contributors)
			if timeLeft != u"":
				replytext += u" It will end in {}.".format(timeLeft)
			replytext += u" It contains {:,} titles. ".format(sum(len(v) for v in gamePriceCategories.itervalues()))
			#Add a list of all the games found
			for priceType in ['PWYW', 'BTA', 'Fixed', 'Unknown']:
				if len(gamePriceCategories[priceType]) > 0:
					replytext += u"{}: {}. ".format(priceType, u" | ".join(gamePriceCategories[priceType]))

		message.bot.say(message.source, replytext)
