import html
import xml.etree.ElementTree as ElementTree

import requests
from bs4 import BeautifulSoup

from commands.CommandTemplate import CommandTemplate
from IrcMessage import IrcMessage
from StringWithSuffix import StringWithSuffix
from util import IrcFormattingUtil, StringUtil
import Constants


class Command(CommandTemplate):
	triggers = ['boardgame']
	helptext = "Searches info on the provided board game name on BoardGameGeek.com (which can be pretty slow, sorry about that)"

	def execute(self, message):
		"""
		:type message: IrcMessage
		"""

		if message.messagePartsLength == 0:
			message.reply("There's far too many boardgames to just pick a random one! Please provide a search query")
			return

		#Since the API's search is a bit crap and doesn't sort properly, scrape the web search page
		try:
			request = requests.get("https://boardgamegeek.com/geeksearch.php", params={"action": "search", "objecttype": "boardgame", "q": message.message}, timeout=10.0)
		except requests.exceptions.Timeout:
			message.reply("Either your search query was too extensive for BoardGameGeek, or they're distracted by a boardgame. Either way, they took too long to respond, sorry")
			return
		if request.status_code != 200:
			message.reply("Something seems to have gone wrong. At BoardGameGeek, I mean, because I never make mistaks. Try again in a little while")
			return
		page = BeautifulSoup(request.content, "html.parser")

		#Get the first result row
		row = page.find(class_="collection_objectname")
		if row is None:
			message.reply("BoardGameGeek doesn't think a game called '{}' exists. Maybe you made a typo?".format(message.message))
			return
		#Then get the link to the board game page from that, to get the game ID from the URL
		# Format of the url is '/boardgame/[ID]/[NAME]'
		gameId = row.find('a')['href'].split('/', 3)[2]

		#Now query the API to get info on this game
		try:
			request = requests.get("https://www.boardgamegeek.com/xmlapi2/thing", params={'id': gameId}, timeout=10.0)
		except requests.exceptions.Timeout:
			message.reply("I know you need some patience for boardgames, but not for info about boardgames. BoardGameGeek took too long to respond, sorry")
			return
		try:
			xml = ElementTree.fromstring(request.content)
		except ElementTree.ParseError:
			message.reply("I don't know how to read the data returned by BoardGameGeek, which is weird because I'm coded very well. Try again in a little while, see if it works then?")
			return

		item = xml.find('item')
		if item is None:  #Specific check otherwise Python prints a warning
			message.reply("I'm sorry, I didn't find any games called '{}'. Did you make a typo? Or did you just invent a new game?!".format(message.message))
			return

		replytext = "{} ({} players, {} min, {}): ".format(IrcFormattingUtil.makeTextBold(item.find('name').attrib['value']), self.getValueRangeDescription(item, 'minplayers', 'maxplayers'),
															self.getValueRangeDescription(item, 'minplaytime', 'maxplaytime'), item.find('yearpublished').attrib['value'])
		#Fit in as much of the description as we can
		description = html.unescape(item.find('description').text)
		#Some descriptions start with a disclaimer that it's from the publisher, remove that to save space
		if description.startswith("Game description from the publisher") or description.startswith("From the manufacturer's website"):
			description = description.split('\n', 1)[1].lstrip()
		#Remove newlines
		description = StringUtil.removeNewlines(description)
		#Show the result
		message.replyWithLengthLimit(StringWithSuffix(replytext + description, (Constants.GREY_SEPARATOR, "https://boardgamegeek.com/boardgame/", gameId)))

	@staticmethod
	def getValueRangeDescription(item, lowerBoundFieldname, higherBoundFieldname):
		lowerbound = item.find(lowerBoundFieldname).attrib['value']
		higherbound = item.find(higherBoundFieldname).attrib['value']
		if lowerbound == higherbound:
			return lowerbound
		return "{}-{}".format(lowerbound, higherbound)
