import json, re
import HTMLParser

import requests

from CommandTemplate import CommandTemplate
import Constants
import GlobalStore
from util import DateTimeUtil
from IrcMessage import IrcMessage
from CommandException import CommandException

class Command(CommandTemplate):

	triggers = ['http://', 'https://', 'www']
	helptext = "Shows the title of the page somebody just posted a link to"
	showInCommandList = False
	callInThread = True  #We can't know how slow sites are, so prevent the bot from locking up on slow sites

	#The maximum time a title look-up is allowed to take
	lookupTimeoutSeconds = 5.0

	def shouldExecute(self, message):
		if message.isPrivateMessage:
			return False
		if message.messageType != 'say':
			return False
		for trigger in self.triggers:
			if trigger in message.message:
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
			url = urlmatch.group()
			while url.endswith(")") or url.endswith('/'):
				url = url[:-1]

			title = None
			try:
				#There's some special cases for often used pages.
				if 'twitch.tv' in url:
					title = self.retrieveTwitchTitle(url)
				elif 'youtube.com' in url or 'youtu.be' in url:
					title = self.retrieveYoutubetitle(url)
				elif 'imgur.com' in url:
					title = self.retrieveImgurTitle(url)
				elif 'twitter.com' in url:
					title = self.retrieveTwitterTitle(url)
				elif re.match('https?://.{2}(?:\.m)?\.wikipedia.org', url, re.IGNORECASE):
					title = GlobalStore.commandhandler.runCommandFunction('getWikipediaArticle', None, url, False)
				#If nothing has been found so far, just display whatever is between the <title> tags
				if title is None:
					title = self.retrieveGenericTitle(url)
			except requests.exceptions.Timeout:
				self.logError("[url] '{}' took too long to respond, ignoring".format(url))
			except requests.exceptions.ConnectionError as error:
				self.logError("[url] A connection error occurred while trying to retrieve '{}': {}".format(url, error))

			#Finally, display the result of all the hard work, if there was any
			if title is not None:
				title = Command.cleanUpRetrievedTitle(title)
				message.reply(u"Title: {}".format(title))

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
		for ext in ('.jpg', '.jpeg', '.gif', '.png', '.bmp', '.avi', '.wav', '.mp3', '.ogg', '.zip', '.rar', '.7z', '.pdf', '.swf'):
			if url.endswith(ext):
				return None
		titlematch = re.search(r'<title ?.*?>(.+?)</title>', requests.get(url, timeout=Command.lookupTimeoutSeconds).text, re.DOTALL | re.IGNORECASE)
		if titlematch:
			return titlematch.group(1)  #No need to do clean-up, that's handled in the main 'execute' function
		return None

	@staticmethod
	def retrieveTwitchTitle(url):
		channelmatches = re.search("https?://(?:www\.)?twitch\.tv/([^/]+)/?$", url)
		if channelmatches:
			channel = channelmatches.group(1)
			#Make the TwitchWatcher module look up the streamer info
			# If that doesn't work for some reason (TwitchWatcher not loaded, Twitch API being down), return None to fall back on the generic lookup
			try:
				return GlobalStore.commandhandler.runCommandFunction('getTwitchStreamInfo', None, channel)
			except CommandException:
				return None

	@staticmethod
	def retrieveYoutubetitle(url):
		if 'google' not in GlobalStore.commandhandler.apikeys:
			CommandTemplate.logError("[url] Google API key not found!")
			return None
		#First we need to determine the video ID from something like this: http://www.youtube.com/watch?v=jmAKXADLcxY or http://youtu.be/jmAKXADLcxY
		videoId = u""
		if url.count('youtu.be') > 0:
			videoId = url[url.rfind('/')+1:]
		else:
			videoIdMatch = re.search('.+v=([^&#]+)', url)
			if videoIdMatch:
				videoId = videoIdMatch.group(1)

		if videoId == u"":
			CommandTemplate.logError(u"[url] No Youtube videoId found in '{}'".format(url))
			return None
		googleUrl = "https://www.googleapis.com/youtube/v3/videos"
		params = {'part': 'statistics,snippet,contentDetails', 'id': videoId, 'key': GlobalStore.commandhandler.apikeys['google'],
				  'fields': 'items/snippet(title,description),items/contentDetails/duration,items/statistics(viewCount,likeCount,dislikeCount)'}
		googleJson = json.loads(requests.get(googleUrl, params=params, timeout=Command.lookupTimeoutSeconds).text.encode('utf-8'))

		if 'error' in googleJson:
			CommandTemplate.logError(u"[url] ERROR with Google requests. {}: {}. [{}]".format(googleJson['error']['code'],
																				   googleJson['error']['message'],
																				   json.dumps(googleJson).replace('\n',' ')))
			return None
		if 'items' not in googleJson or len(googleJson['items']) != 1:
			CommandTemplate.logError(u"[url] Unexpected reply from Google API: {}".format(json.dumps(googleJson).replace('\n', ' ')))
			return None
		videoData = googleJson['items'][0]
		durationtimes = DateTimeUtil.parseIsoDate(videoData['contentDetails']['duration'])
		durationstring = u""
		if durationtimes['day'] > 0:
			durationstring += u"{day} d, "
		if durationtimes['hour'] > 0:
			durationstring += u"{hour:02}:"
		durationstring += u"{minute:02}:{second:02}"
		durationstring = durationstring.format(**durationtimes)
		#Check if there's a description
		description = videoData['snippet']['description'].strip()
		if description == u"":
			description = u"<No description>"

		return u"{title} [{duration}, {viewcount:,} views]: {description}".format(title=videoData['snippet']['title'].strip(),
																				  duration=durationstring,
																				  viewcount=int(videoData['statistics']['viewCount']),
																				  description=description)

	@staticmethod
	def retrieveImgurTitle(url):
		if 'imgur' not in GlobalStore.commandhandler.apikeys or 'clientid' not in GlobalStore.commandhandler.apikeys['imgur']:
			CommandTemplate.logError("[url] Imgur API key not found!")
			return None
		imageIdMatches = re.search('imgur\.com/([^.]+)', url, re.IGNORECASE)
		if imageIdMatches is None:
			CommandTemplate.logError("[url] No Imgur ID found in '{}'".format(url))
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
		imgdata = json.loads(imgurDataPage.text.encode('utf-8'))
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
			CommandTemplate.logWarning("[url] No twitter matches found in '{}'".format(url))
			return None
		apikeys = GlobalStore.commandhandler.apikeys
		if 'twitter' not in apikeys or 'tokentype' not in apikeys['twitter'] or 'token' not in apikeys['twitter']:
			CommandTemplate.logError("[url] Twitter API token info not found!")
			return None
		headers = {"Authorization": "{} {}".format(apikeys['twitter']['tokentype'], apikeys['twitter']['token'])}
		if 'id' in tweetMatches.groupdict() and tweetMatches.group('id') is not None:
			#Specific tweet
			twitterUrl = "https://api.twitter.com/1.1/statuses/show.json?id={id}".format(id=tweetMatches.group('id'))
			twitterDataPage = requests.get(twitterUrl, headers=headers, timeout=Command.lookupTimeoutSeconds)
			twitterdata = json.loads(twitterDataPage.text.encode('utf-8'))

			return u"@{username} ({name}): {text} [{timestamp}]".format(username=twitterdata['user']['screen_name'], name=twitterdata['user']['name'],
													text=twitterdata['text'], timestamp=twitterdata['created_at'])
		else:
			#User page
			twitterUrl = u"https://api.twitter.com/1.1/users/show.json?screen_name={name}".format(name=tweetMatches.group('name'))
			twitterDataPage = requests.get(twitterUrl, headers=headers, timeout=Command.lookupTimeoutSeconds)
			twitterdata = json.loads(twitterDataPage.text.encode('utf-8'))

			title = u"{name} (@{screen_name}): {description} ({statuses_count:,} tweets posted, {followers_count:,} followers, following {friends_count:,})"
			if 'verified' in twitterdata and twitterdata['verified'] is True:
				title += u". Verified account"
			return title.format(**twitterdata)
