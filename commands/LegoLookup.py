# -*- coding: utf-8 -*-
import json, re

import requests

from CommandTemplate import CommandTemplate
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
			self.logError(u"Brickset API result could not be parsed as JSON, API reply: {}".format(apiResult.text if apiResult else u"[[apiResult not set]]"))
			raise CommandException("Hmm, the Brickset API returned unexpected data, that's weird. Sorry, maybe try again in a while, and/or tell my owner(s)?")
		if apiData[u'status'] != u'success':
			self.logError(u"Non-success result returned from Brickset API: {}".format(apiData))
			raise CommandException("Something went wrong with retrieving the data... Maybe try again in a bit, or tell my owner(s)")
		if apiData[u'matches'] == 0:
			raise CommandInputException("No matching Lego sets were found. Maybe you made a typo?")

		setData = apiData[u'sets'][0]
		availableFrom = None
		availableUntil = None
		prices = []
		for countryCode, currencySymbol in ((u'US', u'$'), (u'UK', u'£'), (u'DE', u'€')):
			countryData = setData[u'LEGOCom'].get(countryCode, None)
			if countryData:
				availableFromInCountry = countryData.get(u'dateFirstAvailable', None)
				if availableFromInCountry and (availableFrom is None or availableFromInCountry < availableFrom):
					availableFrom = availableFromInCountry
			availableUntilInCountry = countryData.get(u'dateLastAvailable', None)
			if availableUntilInCountry and (availableUntil is None or availableUntilInCountry > availableUntil):
				availableUntil = availableUntilInCountry
			if u'retailPrice' in countryData:
				prices.append(u"{}{:,}".format(currencySymbol, countryData[u'retailPrice']))
		replytextParts = [u"{name}", u"{number}-{numberVariant}"]
		if u'subtheme' in setData:
			replytextParts.append(u"{theme} ({subtheme})")
		else:
			replytextParts.append(u"{theme}")
		replytextParts.append(u"{pieces:,} pieces")
		if prices:
			replytextParts.append(u" ".join(prices))
		if availableFrom or availableUntil:
			availableText = u""
			if availableFrom:
				availableText += u"from {}".format(self.formatDateString(availableFrom))
			if availableUntil:
				availableText += u" until {}".format(self.formatDateString(availableUntil))
			replytextParts.append(availableText.lstrip())
		elif u'year' in setData:
			replytextParts.append(u"{year}")
		replytextParts.append(u"{bricksetURL}")
		if apiData[u'matches'] > 1:
			matchesLeft = apiData[u'matches'] - 1
			replytextParts.append(u"{:,} more match{}: https://brickset.com/search?query={}".format(matchesLeft, u'' if matchesLeft == 1 else u'es', message.message.replace(' ', '+')))
		replytext = u" | ".join(replytextParts).format(**setData)
		return message.reply(replytext)

	def formatDateString(self, dateString):
		return dateString.split(u'T', 1)[0]
