import html, json, re

import requests

from commands.CommandTemplate import CommandTemplate
import Constants
import GlobalStore
import MessageTypes
from IrcMessage import IrcMessage
from CustomExceptions import CommandException, WebRequestException
from util import IrcFormattingUtil, StringUtil

class Command(CommandTemplate):

	triggers = []
	helptext = "Shows the title of the page somebody just posted a link to"
	showInCommandList = False
	callInThread = True  #We can't know how slow sites are, so prevent the bot from locking up on slow sites

	#The maximum time a title look-up is allowed to take
	lookupTimeoutSeconds = 5.0

	def shouldExecute(self, message):
		if message.isPrivateMessage:
			return False
		if message.messageType != MessageTypes.SAY and message.messageType != MessageTypes.ACTION:
			return False
		return 'https://' in message.message or 'http://' in message.message

	def execute(self, message):
		"""
		:type message: IrcMessage
		"""
		urlmatches = re.findall(r"(https?://\S+)", message.message)
		if not urlmatches:
			self.logWarning("[url] Module triggered, but no url found in message '{}'".format(message.message))
		else:
			for url in urlmatches:
				# Go through the methods alphabetically, and use the generic method last
				title = None
				for parseMethod in (self.retrieveImgurTitle, self.retrieveMastodonTitle, self.retrieveSteamTitle, self.retrieveTumblrTitle, self.retrieveTwitchTitle,
									self.retrieveTwitterTitle, self.retrieveWikipediaTitle, self.retrieveYoutubeTitle, self.retrieveGenericTitle):
					try:
						title = parseMethod(url)
					except requests.exceptions.Timeout:
						self.logWarning("[url] '{}' took too long to respond, ignoring".format(url))
					except requests.exceptions.ConnectionError as error:
						self.logError("[url] A connection error occurred while trying to retrieve '{}': {}".format(url, error))
					except WebRequestException as error:
						self.logError(f"[UrlTitleFinder] A WebRequestException happened while resolving URL '{url}': {error}")
					# Found a title, so we're done. It could be either a string or a StringWithSuffix, but the reply method can handle both
					if title:
						message.replyWithLengthLimit(title)
						break

	@staticmethod
	def retrieveGenericTitle(url):
		# Remove any URL parameters, so we can check the proper URL extension (if any)
		baseUrl = url.split('?', 1)[0] if '?' in url else url
		for ext in ('.7z', '.avi', '.bmp', '.deb', '.exe', '.gif', '.gifv', '.jpeg', '.jpg', '.mp3', '.mp4', '.ogg', '.pdf', '.png', '.rar', '.swf', '.wav', '.webm', '.webp', '.zip'):
			if baseUrl.endswith(ext):
				return None
		# Only parse text documents, and not images or videos or the like. Retrieve the url header to check the content type
		try:
			headersResponse = requests.head(url, allow_redirects=True, timeout=Command.lookupTimeoutSeconds)
			if headersResponse.status_code != 200:
				return None
			if 'Content-Type' in headersResponse.headers and not headersResponse.headers['Content-Type'].startswith('text'):
				return None
			# The URL (most likely) refers to a HTML page, retrieve it and get the title from it (don't catch timeout since that's handled in the main 'execute' method)
			retrievedPage = requests.get(url, timeout=Command.lookupTimeoutSeconds)
		except requests.exceptions.TooManyRedirects as e:
			Command.logError("[UrlTitleFinder] Too many redirects for url '{}': {}".format(url, e))
			return None
		if retrievedPage.status_code != 200:
			return None
		titlematch = re.search(r'<title ?.*?>(.+?)</title>', retrievedPage.text, re.DOTALL | re.IGNORECASE)
		if not titlematch:
			return None
		title = StringUtil.removeNewlines(titlematch.group(1).strip())
		# Convert weird characters like &#39 back into normal ones like '
		title = html.unescape(title)
		return title

	@staticmethod
	def retrieveTwitchTitle(url):
		channelmatches = re.search("https?://(?:www\.)?twitch\.tv/([^/]+)/?$", url)
		if not channelmatches:
			return None
		channel = channelmatches.group(1)
		#Make the TwitchWatcher module look up the streamer info
		# If that doesn't work for some reason (TwitchWatcher not loaded, Twitch API being down), return None to fall back on the generic lookup
		try:
			return GlobalStore.commandhandler.runCommandFunction('getTwitchStreamInfo', None, channel, shouldIncludeUrl=False)
		except CommandException:
			return None

	@staticmethod
	def retrieveYoutubeTitle(url):
		if 'youtube.com' not in url and 'youtu.be' not in url:
			return None
		#First we need to determine the video ID from something like this: 'http://www.youtube.com/watch?v=[videoID]' or 'http://youtu.be/[videoID]'
		if url.count('youtu.be') > 0:
			videoIdMatch = re.search('youtu\.be/([^?/#]+)', url)
		else:
			videoIdMatch = re.search('.+v=([^&#]+)', url)
			if not videoIdMatch:
				# Live videos and Shorts have a different format: https://www.youtube.com/[type]/[videoID]
				videoIdMatch = re.search('(?:live|shorts)/([^?/#]+)', url)
		if not videoIdMatch:
			return None
		videoId = videoIdMatch.group(1)
		return GlobalStore.commandhandler.runCommandFunction('getYoutubeVideoDescription', None, videoId, includeViewCount=True, includeUploadDate=True, includeUrl=False)

	@staticmethod
	def retrieveImgurTitle(url):
		imageIdMatches = re.search('imgur\.com/([^.]+)', url, re.IGNORECASE)
		if imageIdMatches is None:
			return None
		apiClientId = GlobalStore.commandhandler.getApiKey('clientid', 'imgur')
		if not apiClientId:
			CommandTemplate.logError("[url] Imgur API key not found")
			return None
		imageId = imageIdMatches.group(1)
		isGallery = False
		imageType = 'image'
		if '/' in imageId:
			if 'gallery' in imageId:
				imageType = 'gallery/album'
				isGallery = True
			imageId = imageId[imageId.rfind('/')+1:]
		headers = {"Authorization": "Client-ID " + apiClientId}
		imgurUrl = "https://api.imgur.com/3/{type}/{id}".format(type=imageType, id=imageId)
		imgurDataPage = requests.get(imgurUrl, headers=headers, timeout=Command.lookupTimeoutSeconds)
		try:
			imgdata = imgurDataPage.json()
		except ValueError as e:
			CommandTemplate.logError("[url] Imgur API didn't return JSON for type {} image id {}: {}".format(imageType, imageId, e))
			return None
		if imgdata['success'] is not True or imgdata['status'] != 200:
			CommandTemplate.logError("[url] Error while retrieving Imgur image data: {}".format(imgurDataPage.text))
			return None
		imgdata = imgdata['data']
		titleParts = [imgdata['title'] if imgdata['title'] else "No Title"]
		if isGallery:
			titleParts.append("{:,} image{}".format(imgdata['images_count'], 's' if imgdata['images_count'] > 1 else ''))
		else:
			titleParts.append("{:,} x {:,}".format(imgdata['width'], imgdata['height']))
			titleParts.append("{:,.0f} kb".format(imgdata['size'] / 1024.0))
		titleParts.append("{:,} views".format(imgdata['views']))
		if 'animated' in imgdata and imgdata['animated'] is True:
			titleParts.append("Animated")
		if 'nsfw' in imgdata and imgdata['nsfw'] is True:
			titleParts.append(IrcFormattingUtil.makeTextBold(IrcFormattingUtil.makeTextColoured('NSFW', IrcFormattingUtil.Colours.RED)))
		return Constants.GREY_SEPARATOR.join(titleParts)

	@staticmethod
	def retrieveTwitterTitle(url):
		tweetMatches = re.search('twitter.com/(?P<name>[^/]+)(?:/status/(?P<id>[^/?]+).*)?', url)
		if not tweetMatches:
			return None
		return GlobalStore.commandhandler.runCommandFunction('getTweetDescription', None, tweetMatches.group('name'), tweetMatches.group('id'), False)

	@staticmethod
	def retrieveWikipediaTitle(url):
		if not re.match('https?://en(?:\.m)?\.wikipedia.org/wiki', url, re.IGNORECASE):
			return None
		articleTitle = url.rsplit('/', 1)[-1]
		# Limit length to maximum line length instead of maximum message length because it will be auto-shortened automatically
		apiReturn = requests.get("https://en.wikipedia.org/w/api.php", params={'format': 'json', 'utf8': True, 'redirects': True, 'action': 'query', 'prop': 'extracts', 'titles': articleTitle,
																			   'exchars': Constants.MAX_LINE_LENGTH, 'exlimit': 1, 'explaintext': True, 'exsectionformat': 'plain'})
		if apiReturn.status_code != 200:
			return None
		apiData = apiReturn.json()
		if 'query' not in apiData or 'pages' not in apiData['query'] or "-1" in apiData['query']['pages']:
			return None
		articleText = apiData['query']['pages'].popitem()[1]['extract']
		articleText = re.sub('[\n\t]+', ' ', articleText)
		return articleText

	@staticmethod
	def retrieveMastodonTitle(url):
		urlMatch = re.match('https://(?P<server>[^.]+\.[^/]+)/@(?P<user>[^/@]+)(?:@[^/]+)?/(?P<messageid>\d+)', url, re.IGNORECASE)
		if not urlMatch:
			return None
		return GlobalStore.commandhandler.runCommandFunction('getMastodonMessageDescription', None, urlMatch.group('server'), urlMatch.group('user'), urlMatch.group('messageid'), False)

	@staticmethod
	def retrieveSteamTitle(url):
		urlMatch = re.match('https://store.steampowered.com/app/(?P<appid>\d+)(?:/.*)?', url, re.IGNORECASE)
		if not urlMatch:
			return None
		return GlobalStore.commandhandler.runCommandFunction('getSteamAppDescriptionById', None, urlMatch.group('appid'), False)

	@staticmethod
	def retrieveTumblrTitle(url):
		urlMatch = re.match('https://(?:www\.)?tumblr.com/(?P<user>[^/]+)/(?P<postId>\d+)', url, re.IGNORECASE)
		if not urlMatch:
			return None
		apiKey = GlobalStore.commandhandler.getApiKey('tumblr')
		if not apiKey:
			Command.logWarning("[UrlTitleFinder] No Tumblr API key stored")
			return None
		apiReply = requests.get("https://api.tumblr.com/v2/blog/{}/posts".format(urlMatch.group('user')), params={'api_key': apiKey, 'id': urlMatch.group('postId'), 'filter': 'text', 'npf': True})
		if apiReply.status_code != 200:
			Command.logError("[UrlTitleFinder] Tumblr API returned error result, status code {}: {}".format(apiReply.status_code, apiReply.text))
			return None
		try:
			postData = apiReply.json()['response']['posts']
		except json.JSONDecodeError as e:
			Command.logError(f"[UrlTitleFinder] Unable to parse API reply as JSON: {e}; API reply: {apiReply.text}")
			postData = None
		if not postData:
			# No posts found, apparently
			return None
		# We only care about the first post, which should also be the only post
		postData = postData[0]

		# If the 'trail' entry is filled, it's a reblog. The 'trail' dict contains all the info we need of the original post, so use that instead of the toplevel data
		if 'trail' in postData and postData['trail']:
			postData = postData['trail'][0]

		# Format the post text
		postText = None
		if 'content' in postData:
			# Start with the poster's name
			postTextParts = []
			# This list contains dicts with the type and content of each entry. Only parse the text entries
			for contentEntry in postData['content']:
				if contentEntry['type'] == 'text' and 'text' in contentEntry:
					postTextParts.append(contentEntry['text'].strip())
			if postTextParts:
				postText = IrcFormattingUtil.makeTextBold(postData['blog']['name']) + ': ' + Constants.GREY_SEPARATOR.join(postTextParts)
		elif 'summary' in postData:
			postText = postData['summary']
		else:
			Command.logWarning(f"[UrlTitleFinder] No usable data found in Tumblr API reply for url '{url}': {apiReply.json()}")

		# Send the result, if any
		return StringUtil.removeNewlines(postText) if postText else None
