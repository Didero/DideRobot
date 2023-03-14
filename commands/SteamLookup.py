import requests

import GlobalStore
from CommandTemplate import CommandTemplate
from CustomExceptions import CommandException, CommandInputException
from IrcMessage import IrcMessage
from util import StringUtil


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
			if searchData[u'total'] == 0 or not searchData[u'items']:
				raise CommandInputException("That search didn't return any results. Maybe you made a typo? Or you've got a game to make")
			matchingApp = searchData[u'items'][0]
			pricesByCountry = {}
			if u'price' in matchingApp:
				pricesByCountry['US'] = u'${:.2f}'.format(matchingApp[u'price'][u'final'] / 100)
			appId = StringUtil.forceToUnicode(matchingApp['id'])
			return message.reply(self.getDescriptionFromAppId(appId, True, pricesByCountry), "say")
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
		if appId not in appData or not appData[appId][u'success']:
			self.logError(u"[Steam] Retrieving data for app ID {} failed, api reply: {}".format(appId, appData))
			raise CommandException("Something went wrong with retrieving extra information, sorry. Try again in a little while, see if it works then")
		appData = appData[appId]['data']

		developerString = u"by {}".format(u", ".join(appData[u'developers']))

		priceString = None
		if appData[u'is_free']:
			priceString = u"Free"
		elif u'price_overview' in appData:
			if pricesByCountry is None:
				pricesByCountry = {}
			priceParts = []
			pricesByCountry['NL'] = appData[u'price_overview'][u'final_formatted']
			for countryCode in self.COUNTRY_PRICES_TO_RETRIEVE:
				if countryCode not in pricesByCountry:
					pricesByCountry[countryCode] = self.getPriceForCountry(appId, countryCode)
				if pricesByCountry[countryCode]:
					priceParts.append(pricesByCountry[countryCode].replace(' ', '').replace(',','.'))

			discount = appData[u'price_overview']['discount_percent']
			if discount:
				priceParts.append(u'-{}%'.format(discount))
			priceString = u" ".join(priceParts)

		supportedPlatforms = []
		for platform, isSupported in appData[u'platforms'].iteritems():
			if isSupported:
				supportedPlatforms.append(platform.title())

		genres = []
		if u'genres' in appData:
			genreCount = 0
			for genreEntry in appData[u'genres']:
				genre = genreEntry[u'description']
				# Skip adding 'Free to Play', since that's already shown in the price
				if genre != u'Free to Play':
					genreCount += 1
					if genreCount < self.MAX_GENRES:
						genres.append(genre)
			if genreCount > self.MAX_GENRES:
				genres.append(u'+{:,}'.format(genreCount))

		# Collected and parsed all data, now use it to build the description string
		replyParts = [appData[u'name'], developerString, appData[u'release_date'][u'date'], u" ".join(supportedPlatforms)]
		if priceString:
			replyParts.append(priceString)
		if appData[u'type'] != u'game':
			replyParts.append(appData[u'type'])
		if genres:
			replyParts.append(u", ".join(genres))
		if u'fullgame' in appData:
			replyParts.append(u"DLC for {}".format(appData[u'fullgame'][u'name']))
		replyParts.append(appData[u'short_description'])

		replySuffixes = None
		if includeUrl:
			replySuffixes = (u" | ", u"https://store.steampowered.com/app/", appId)
		return StringUtil.limitStringLength(u" | ".join(replyParts), suffixes=replySuffixes)

	def getPriceForCountry(self, appId, countryCode):
		try:
			apiReply = requests.get('https://store.steampowered.com/api/appdetails', params={'appids': appId, 'cc': countryCode, 'filters': 'price_overview'}, timeout=5)
		except requests.exceptions.Timeout:
			return None
		return apiReply.json()[appId][u'data'][u'price_overview'][u'final_formatted']

