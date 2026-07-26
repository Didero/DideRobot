import html
import xml.etree.ElementTree as ElementTree

import requests
from bs4 import BeautifulSoup

import GlobalStore
from commands.CommandTemplate import CommandTemplate
from CustomExceptions import CommandException
from IrcMessage import IrcMessage
from StringWithSuffix import StringWithSuffix
from util import IrcFormattingUtil, StringUtil
import Constants


class Command(CommandTemplate):
	triggers = ['boardgame']
	helptext = "Searches info on the provided board game name on https://BoardGameGeek.com"

	def execute(self, message):
		"""
		:type message: IrcMessage
		"""

		if message.messagePartsLength == 0:
			message.reply("There's far too many boardgames to just pick a random one! Please provide a search query")
			return

		apiKey = GlobalStore.commandhandler.getApiKey('boardgamegeek')
		if not apiKey:
			self.logError("[BoardGameGeekLookup] Missing key for API")
			raise CommandException("While I've played a lot of boardgames, I don't know all of them. And to look them up on BoardGameGeek, I need an API key, which seems to be missing. Sorry!", False)
		headers = {"Authorization": f"Bearer {apiKey}"}

		# Search the API to get a game ID
		try:
			searchResponse = requests.get("https://boardgamegeek.com/xmlapi2/search", headers=headers, params={"query": message.message}, timeout=10.0)
		except requests.exceptions.Timeout:
			message.reply("Either your search query was too extensive for BoardGameGeek, or they're distracted by a boardgame. Either way, they took too long to respond, sorry")
			return
		if searchResponse.status_code != 200:
			message.reply("Something seems to have gone wrong. At BoardGameGeek, I mean, because I never make mistaks. Try again in a little while")
			return
		searchXml = ElementTree.fromstring(searchResponse.content)
		if len(searchXml) == 0:
			message.reply("BoardGameGeek doesn't think a game called '{}' exists. Maybe you made a typo?".format(message.message))
			return
		elif len(searchXml) == 1:
			# One result, use that
			gameId = searchXml[0].attrib["id"]
		else:
			nameToFind = message.message.lower()
			# Go through all results trying to find an exact match, otherwise use the first result
			# Do this instead of adding 'exact=1' to the search query, so we can fall back on something in case no exact match is found
			for item in searchXml:
				if item[0].attrib["value"].lower() == nameToFind:
					gameId = item.attrib["id"]
					break
			else:
				# If no exact match was found, just use the first item from the search results
				gameId = searchXml[0].attrib["id"]

		#Now query the API to get info on this game
		try:
			gameResponse = requests.get("https://boardgamegeek.com/xmlapi2/thing", headers=headers, params={'id': gameId}, timeout=10.0)
		except requests.exceptions.Timeout:
			message.reply("I know you need some patience for boardgames, but not for info about boardgames. BoardGameGeek took too long to respond, sorry")
			return
		try:
			xml = ElementTree.fromstring(gameResponse.content)
		except ElementTree.ParseError as e:
			self.logError(f"[BoardGameGeekLookup] Unable to parse text {gameResponse.content!r} as XML: {e}")
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
