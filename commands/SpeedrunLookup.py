import requests

from CommandTemplate import CommandTemplate
from IrcMessage import IrcMessage
from util import IrcFormattingUtil
from CommandException import CommandException
import Constants


class Command(CommandTemplate):
	triggers = ['speedrunlookup', 'speedrun']
	helptext = "Looks up speedruns for the provided game name on www.speedrun.com"

	_SKIPPED_TEXT = " | {} more"
	_SKIPPED_TEXT_LENGTH = len(_SKIPPED_TEXT)

	def execute(self, message):
		"""
		:type message: IrcMessage
		"""

		if message.messagePartsLength == 0:
			message.reply("Please provide a game name to look up the speedruns for, there's too many games for me to just guess one")
			return

		providedGameName = " ".join(message.messageParts)
		# Get the game ID for the provided game name (Use '_bulk: True' to reduce the reply size)
		apiJson = self._retrieveAndVerify("https://www.speedrun.com/api/v1/games", {'name': providedGameName, 'max': 1, '_bulk': True})
		if not apiJson.get('data', None):
			message.reply("Speedrun.com couldn't find any data on the provided game name '{}'. Maybe you made a typo?".format(providedGameName))
			return
		apiData = apiJson['data'][0]
		returnedGameName = apiData['names'].get('international', providedGameName)
		gameUrl = apiData['weblink'].replace("/www.speedrun.com", "/speedrun.com")
		gameId = apiData['id']

		# Get all the speedrun records for each category of the found game
		apiJson = self._retrieveAndVerify("https://www.speedrun.com/api/v1/games/{}/records".format(gameId),
										  {'top': 1, 'miscellaneous': True, 'skip-empty': True, 'scope': 'full-game', 'embed': 'category'})
		if not apiJson.get('data', None):
			message.reply("'{}' doesn't have any records yet. This is your chance to become a record-holding speedrunner! Check here for the game's categories: {}".format(returnedGameName, gameUrl))
			return
		# The API should return the speedrun categories and records in display order
		replytext = "{} | {}".format(IrcFormattingUtil.makeTextBold(returnedGameName), gameUrl)
		skippedCategoryCount = 0
		currentReplyLength = len(replytext) + self._SKIPPED_TEXT_LENGTH
		for entry in apiJson['data']:
			categoryName = entry['category']['data']['name']
			runTimeString = entry['runs'][0]['run']['times']['primary'].lower()
			if runTimeString.startswith('pt'):
				runTimeString = runTimeString[2:]
			runDisplayString = " | {}: {}".format(categoryName, runTimeString)
			runDisplayStringLength = len(runDisplayString)
			if currentReplyLength + runDisplayStringLength <= Constants.MAX_MESSAGE_LENGTH:
				replytext += runDisplayString
				currentReplyLength += runDisplayStringLength
			else:
				skippedCategoryCount += 1
		if skippedCategoryCount > 0:
			replytext += self._SKIPPED_TEXT.format(skippedCategoryCount)
		message.reply(replytext)

	def _retrieveAndVerify(self, url, params):
		"""
		Retrieves JSON data from the provided url with the provided parameters, and does some checks to see if it's a valid response. Raises CommandException when something went wrong
		:param url: The url to retrieve
		:param params: The parameters to add to the url
		:return: A dict with the JSON response from the API
		"""
		try:
			response = requests.get(url, params=params, timeout=10.0)
		except requests.exceptions.Timeout:
			raise CommandException("Hmm, www.speedrun.com took too long to respond. Maybe their API is on break? Try again in a little while")
		except requests.ConnectionError:
			raise CommandException("Hmm, I couldn't connect to www.speedrun.com for some reason. Maybe try again in a little while?")

		if response.status_code != 200:
			raise CommandException("Hmm, that speedrun.com API reply doesn't look good. Maybe try again in a little while? (Status code was {})".format(response.status_code))

		try:
			return response.json()
		except ValueError as e:
			self.logError("[Speedrun] API returned invalid JSON: {}".format(response.text))
			raise CommandException("That's a very weird API reply, I have no idea how to parse that. So either the speedrun.com site broke (hopefully temporarily), or their API changed. I'd try again in a little while and see which one it is")
