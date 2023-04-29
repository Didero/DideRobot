# -*- coding: utf-8 -*-
import json, re

import requests

from commands.CommandTemplate import CommandTemplate
from IrcMessage import IrcMessage
from CustomExceptions import CommandException, CommandInputException
import GlobalStore


class Command(CommandTemplate):
	triggers = ['lego']
	helptext = "Looks up info on Lego sets, either by name or by set number"
	
	def execute(self, message):
		"""
		:type message: IrcMessage
		"""

		apiKey = GlobalStore.commandhandler.apikeys['brickset']
		if not apiKey:
			raise CommandException("I don't have an API key for Brickset.com, so I can't retrieve Lego data from there, sorry! Please tell my owner(s) about this, they can hopefully fix it")

		if message.messagePartsLength == 0:
			raise CommandInputException("Plese add a search qeury or set number for me to search for")

		apiParams = {}
		if message.messagePartsLength == 1:
			setNumberMatch = re.match("^(\d{3,}(-\d)?)$", message.messageParts[0])
			if setNumberMatch:
				# Set number
				apiParams['setNumber'] = message.messageParts[0]
				# Brickset needs set numbers to end with a revision number, so add that if none was provided
				if setNumberMatch.group(2) is None:
					apiParams['setNumber'] += '-1'
		if not apiParams:
			# Set name search query, just pass it along as-is
			apiParams['query'] = message.message
			# Sort from new to old, because presumably the latest set is most likely to be the one searched for
			apiParams['orderBy'] = 'YearFromDESC'

		apiResult = None
		try:
			apiResult = requests.get('https://brickset.com/api/v3.asmx/getSets', params={'apiKey': GlobalStore.commandhandler.apikeys['brickset'], 'userHash': '', 'params': json.dumps(apiParams)}, timeout=10)
			apiData = apiResult.json()
		except requests.exceptions.Timeout:
			raise CommandException("My connection to Brickset.com timed out. Try again in a while")
		except ValueError as ve:
			self.logError("Brickset API result could not be parsed as JSON, API reply: {}".format(apiResult.text if apiResult else "[[apiResult not set]]"))
			raise CommandException("Hmm, the Brickset API returned unexpected data, that's weird. Sorry, maybe try again in a while, and/or tell my owner(s)?")
		if apiData['status'] != 'success':
			self.logError("Non-success result returned from Brickset API: {}".format(apiData))
			raise CommandException("Something went wrong with retrieving the data... Maybe try again in a bit, or tell my owner(s)")
		if apiData['matches'] == 0:
			raise CommandInputException("No matching Lego sets were found. Maybe you made a typo?")

		setData = apiData['sets'][0]
		availableFrom = None
		availableUntil = None
		prices = []
		for countryCode, currencySymbol in (('US', '$'), ('UK', '£'), ('DE', '€')):
			countryData = setData['LEGOCom'].get(countryCode, None)
			if countryData:
				availableFromInCountry = countryData.get('dateFirstAvailable', None)
				if availableFromInCountry and (availableFrom is None or availableFromInCountry < availableFrom):
					availableFrom = availableFromInCountry
			availableUntilInCountry = countryData.get('dateLastAvailable', None)
			if availableUntilInCountry and (availableUntil is None or availableUntilInCountry > availableUntil):
				availableUntil = availableUntilInCountry
			if 'retailPrice' in countryData:
				prices.append("{}{:,}".format(currencySymbol, countryData['retailPrice']))
		replytextParts = ["{name}", "{number}-{numberVariant}"]
		if 'subtheme' in setData:
			replytextParts.append("{theme} ({subtheme})")
		else:
			replytextParts.append("{theme}")
		replytextParts.append("{pieces:,} pieces")
		if prices:
			replytextParts.append(" ".join(prices))
		if availableFrom or availableUntil:
			availableText = ""
			if availableFrom:
				availableText += "from {}".format(self.formatDateString(availableFrom))
			if availableUntil:
				availableText += " until {}".format(self.formatDateString(availableUntil))
			replytextParts.append(availableText.lstrip())
		elif 'year' in setData:
			replytextParts.append("{year}")
		replytextParts.append("{bricksetURL}")
		if apiData['matches'] > 1:
			matchesLeft = apiData['matches'] - 1
			replytextParts.append("{:,} more match{}: https://brickset.com/search?query={}".format(matchesLeft, '' if matchesLeft == 1 else 'es', message.message.replace(' ', '+')))
		replytext = " | ".join(replytextParts).format(**setData)
		return message.reply(replytext)

	def formatDateString(self, dateString):
		return dateString.split('T', 1)[0]
