import json, re
import HTMLParser

import requests

from CommandTemplate import CommandTemplate
import Constants
import GlobalStore
from IrcMessage import IrcMessage
from CustomExceptions import CommandException

class Command(CommandTemplate):

	triggers = []
	helptext = "Shows the title of the page somebody just posted a link to"
	showInCommandList = False
	callInThread = True  #We can't know how slow sites are, so prevent the bot from locking up on slow sites

	#The maximum time a title look-up is allowed to take
	urlPrefixes = ('http://', 'https://')
	lookupTimeoutSeconds = 5.0

	def shouldExecute(self, message):
		if message.isPrivateMessage:
			return False
		if message.messageType != 'say':
			return False
		for urlPrefix in self.urlPrefixes:
			if urlPrefix in message.message:
				return True
		return False

	def execute(self, message):
		"""
		:type message: IrcMessage
		"""
		urlmatch = re.search(r"(https?://\S+)", message.message)
		if not urlmatch:
			self.logWarning("[url] Module triggered, but no url found in message '{}'".format(message.message))
		else:
			url = urlmatch.group().rstrip(")/")

			# Go through the methods alphabetically, and use the generic method last
			title = None
			for parseMethod in (self.retrieveImgurTitle, self.retrieveTwitchTitle, self.retrieveTwitterTitle, self.retrieveWikipediaTitle, self.retrieveGenericTitle):
				try:
					title = parseMethod(url)
				except requests.exceptions.Timeout:
					self.logError("[url] '{}' took too long to respond, ignoring".format(url))
				except requests.exceptions.ConnectionError as error:
					self.logError("[url] A connection error occurred while trying to retrieve '{}': {}".format(url, error))
				else:
					if title:
						break

			#Finally, display the result of all the hard work, if there was any
			if title:
				replyText = Command.cleanUpRetrievedTitle(title)
				message.reply(replyText, 'say')

	@staticmethod
	def cleanUpRetrievedTitle(retrievedTitle):
		cleanedUpTitle = retrievedTitle.strip()
		cleanedUpTitle = re.sub(' *\n *', ' ', cleanedUpTitle)
		# Convert weird characters like &#39 back into normal ones like '
		cleanedUpTitle = HTMLParser.HTMLParser().unescape(cleanedUpTitle)
		# Make sure titles aren't too long
		if len(cleanedUpTitle) > Constants.MAX_MESSAGE_LENGTH:
			cleanedUpTitle = cleanedUpTitle[:Constants.MAX_MESSAGE_LENGTH - 5] + "[...]"
		return cleanedUpTitle

	@staticmethod
	def retrieveGenericTitle(url):
		# Remove any URL parameters, so we can check the proper URL extension (if any)
		baseUrl = url.split('?', 1)[0] if '?' in url else url
		for ext in ('.jpg', '.jpeg', '.gif', '.png', '.bmp', '.avi', '.wav', '.mp3', '.ogg', '.zip', '.rar', '.7z', '.pdf', '.swf'):
			if baseUrl.endswith(ext):
				return None
		titlematch = re.search(r'<title ?.*?>(.+?)</title>', requests.get(url, timeout=Command.lookupTimeoutSeconds).text, re.DOTALL | re.IGNORECASE)
		if titlematch:
			return titlematch.group(1)  #No need to do clean-up, that's handled in the main 'execute' function
		return None

	@staticmethod
	def retrieveTwitchTitle(url):
		channelmatches = re.search("https?://(?:www\.)?twitch\.tv/([^/]+)/?$", url)
		if not channelmatches:
			return None
		channel = channelmatches.group(1)
		#Make the TwitchWatcher module look up the streamer info
		# If that doesn't work for some reason (TwitchWatcher not loaded, Twitch API being down), return None to fall back on the generic lookup
		try:
			return GlobalStore.commandhandler.runCommandFunction('getTwitchStreamInfo', None, channel)
		except CommandException:
			return None

	@staticmethod
	def retrieveYoutubeTitle(url):
		if 'youtube.com' not in url and 'youtu.be' not in url:
			return None
		#First we need to determine the video ID from something like this: http://www.youtube.com/watch?v=jmAKXADLcxY or http://youtu.be/jmAKXADLcxY
		videoId = None
		if url.count('youtu.be') > 0:
			videoId = url[url.rfind('/')+1:]
		else:
			videoIdMatch = re.search('.+v=([^&#]+)', url)
			if videoIdMatch:
				videoId = videoIdMatch.group(1)

		if not videoId:
			return None
		return GlobalStore.commandhandler.runCommandFunction('getYoutubeVideoDescription', None, videoId, True)

	@staticmethod
	def retrieveImgurTitle(url):
		imageIdMatches = re.search('imgur\.com/([^.]+)', url, re.IGNORECASE)
		if imageIdMatches is None:
			return None
		if 'imgur' not in GlobalStore.commandhandler.apikeys or 'clientid' not in GlobalStore.commandhandler.apikeys['imgur']:
			CommandTemplate.logError("[url] Imgur API key not found!")
			return None
		imageId = imageIdMatches.group(1)
		isGallery = False
		imageType = 'image'
		if '/' in imageId:
			if 'gallery' in imageId:
				imageType = 'gallery/album'
				isGallery = True
			imageId = imageId[imageId.rfind('/')+1:]
		headers = {"Authorization": "Client-ID " + GlobalStore.commandhandler.apikeys['imgur']['clientid']}
		imgurUrl = "https://api.imgur.com/3/{type}/{id}".format(type=imageType, id=imageId)
		imgurDataPage = requests.get(imgurUrl, headers=headers, timeout=Command.lookupTimeoutSeconds)
		try:
			imgdata = json.loads(imgurDataPage.text.encode('utf-8'))
		except ValueError as e:
			CommandTemplate.logError("[url] Imgur API didn't return JSON for type {} image id {}".format(imageType, imageId))
			return None
		if imgdata['success'] is not True or imgdata['status'] != 200:
			CommandTemplate.logError("[url] Error while retrieving ImgUr image data: {}".format(imgurDataPage.text.encode('utf-8')))
			return None
		imgdata = imgdata['data']
		if imgdata['title'] is None:
			imgdata['title'] = u"No Title"
		title = u"{imgdata[title]} ("
		if isGallery:
			title += u"{imgdata[images_count]} images"
		else:
			imgFilesize = imgdata['size'] / 1024.0
			#Split into two lines because we're only formatting imgFilesize here, and otherwise it errors out on imgdata
			title += u"{imgdata[width]:,}x{imgdata[height]:,}"
			title += u"  {imgFilesize:,.0f} kb".format(imgFilesize=imgFilesize)
		title += u"  {imgdata[views]:,} views"
		title += u")"

		if 'animated' in imgdata and imgdata['animated'] is True:
			title += u" (Animated)"
		if 'nsfw' in imgdata and imgdata['nsfw'] is True:
			title += u" (NSFW!)"
		return title.format(imgdata=imgdata)

	@staticmethod
	def retrieveTwitterTitle(url):
		tweetMatches = re.search('twitter.com/(?P<name>[^/]+)(?:/status/(?P<id>[^/]+).*)?', url)
		if not tweetMatches:
			return None
		return GlobalStore.commandhandler.runCommandFunction('getTweetDescription', None, tweetMatches.group('name'), tweetMatches.group('id'))

	@staticmethod
	def retrieveWikipediaTitle(url):
		if not re.match('https?://en(?:\.m)?\.wikipedia.org/wiki', url, re.IGNORECASE):
			return None
		articleTitle = url.rsplit('/', 1)[-1]
		apiReturn = requests.get("https://en.wikipedia.org/w/api.php", params={'format': 'json', 'utf8': True, 'redirects': True, 'action': 'query', 'prop': 'extracts', 'titles': articleTitle,
																			   'exchars': Constants.MAX_MESSAGE_LENGTH, 'exlimit': 1, 'explaintext': True, 'exsectionformat': 'plain'})
		if apiReturn.status_code != 200:
			return None
		apiData = apiReturn.json()
		if 'query' not in apiData or 'pages' not in apiData['query'] or "-1" in apiData['query']['pages']:
			return None
		articleText = apiData['query']['pages'].popitem()[1]['extract']
		articleText = re.sub('[\n\t]+', ' ', articleText)
		return articleText

