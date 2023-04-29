import requests

import Constants, GlobalStore
from commands.CommandTemplate import CommandTemplate
from CustomExceptions import CommandException, CommandInputException
from IrcMessage import IrcMessage
from util import StringUtil
from StringWithSuffix import StringWithSuffix


class Command(CommandTemplate):
	triggers = ['steam']
	helptext = "Looks up info on the provided game on Steam"

	MAX_GENRES = 3
	COUNTRY_PRICES_TO_RETRIEVE = ('US', 'NL', 'UK', 'AU')

	def onLoad(self):
		GlobalStore.commandhandler.addCommandFunction(__file__, 'getSteamAppDescriptionById', self.getDescriptionFromAppId)

	def execute(self, message):
		"""
		:type message: IrcMessage
		"""

		if message.messagePartsLength == 0:
			raise CommandInputException("Please also provide a game name to search for, there's too many games for me to pick one")

		# First search for the app ID
		try:
			searchResult = requests.get("https://store.steampowered.com/api/storesearch", params={'term': message.message, 'cc': 'US'}, timeout=5)
			searchData = searchResult.json()
			if searchData['total'] == 0 or not searchData['items']:
				raise CommandInputException("That search didn't return any results. Maybe you made a typo? Or you've got a game to make")
			matchingApp = searchData['items'][0]
			pricesByCountry = {}
			if 'price' in matchingApp:
				pricesByCountry['US'] = '${:.2f}'.format(matchingApp['price']['final'] / 100)
			appId = StringUtil.forceToString(matchingApp['id'])
			return message.replyWithLengthLimit(self.getDescriptionFromAppId(appId, True, pricesByCountry))
		except requests.exceptions.Timeout:
			raise CommandException("Seems Steam is having some issues, they didn't return the data as quickly as normal. You should try again in a little while", False)

	def getDescriptionFromAppId(self, appId, includeUrl=True, pricesByCountry=None):
		"""
		Get a description of the Steam app specified by the provided app ID
		:param appId: The ID of the app to get the information of
		:param includeUrl: Whether the URL ot the app's page on the Steam website should be included
		:param pricesByCountry: A dictionary of prices already retrieved. The keys should be country codes, the values the price for that country code. If not provided, they'll be retrieved
		:return: A string describing the app belonging to the provided app ID, limited to message length
		"""
		appResult = requests.get("https://store.steampowered.com/api/appdetails", params={'appids': appId, 'cc': 'NL'}, timeout=5.0)
		appData = appResult.json()
		if appId not in appData or not appData[appId]['success']:
			self.logError("[Steam] Retrieving data for app ID {} failed, api reply: {}".format(appId, appData))
			raise CommandException("Something went wrong with retrieving extra information, sorry. Try again in a little while, see if it works then")
		appData = appData[appId]['data']

		developerString = "by {}".format(", ".join(appData['developers']))

		priceString = None
		if appData['is_free']:
			priceString = "Free"
		elif 'price_overview' in appData:
			if pricesByCountry is None:
				pricesByCountry = {}
			priceParts = []
			pricesByCountry['NL'] = appData['price_overview']['final_formatted']
			for countryCode in self.COUNTRY_PRICES_TO_RETRIEVE:
				if countryCode not in pricesByCountry:
					pricesByCountry[countryCode] = self.getPriceForCountry(appId, countryCode)
				if pricesByCountry[countryCode]:
					priceParts.append(pricesByCountry[countryCode].replace(' ', '').replace(',','.'))

			discount = appData['price_overview']['discount_percent']
			if discount:
				priceParts.append('-{}%'.format(discount))
			priceString = " ".join(priceParts)

		supportedPlatforms = []
		for platform, isSupported in appData['platforms'].items():
			if isSupported:
				supportedPlatforms.append(platform.title())

		genres = []
		if 'genres' in appData:
			genreCount = 0
			for genreEntry in appData['genres']:
				genre = genreEntry['description']
				# Skip adding 'Free to Play', since that's already shown in the price
				if genre != 'Free to Play':
					genreCount += 1
					if genreCount < self.MAX_GENRES:
						genres.append(genre)
			if genreCount > self.MAX_GENRES:
				genres.append('+{:,}'.format(genreCount))

		# Collected and parsed all data, now use it to build the description string
		replyParts = [appData['name'], developerString, appData['release_date']['date'], " ".join(supportedPlatforms)]
		if priceString:
			replyParts.append(priceString)
		if appData['type'] != 'game':
			replyParts.append(appData['type'])
		if genres:
			replyParts.append(", ".join(genres))
		if 'fullgame' in appData:
			replyParts.append("DLC for {}".format(appData['fullgame']['name']))
		replyParts.append(appData['short_description'])

		replySuffixes = None
		if includeUrl:
			replySuffixes = (Constants.GREY_SEPARATOR, "https://store.steampowered.com/app/", appId)
		return StringWithSuffix(Constants.GREY_SEPARATOR.join(replyParts), replySuffixes)

	def getPriceForCountry(self, appId, countryCode):
		try:
			apiReply = requests.get('https://store.steampowered.com/api/appdetails', params={'appids': appId, 'cc': countryCode, 'filters': 'price_overview'}, timeout=5)
		except requests.exceptions.Timeout:
			return None
		return apiReply.json()[appId]['data']['price_overview']['final_formatted']
