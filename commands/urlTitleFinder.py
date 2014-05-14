import json, re, time
import HTMLParser

import requests

from CommandTemplate import CommandTemplate
import GlobalStore
import SharedFunctions
from IrcMessage import IrcMessage

class Command(CommandTemplate):
	
	triggers = ['http://', 'https://', 'www']
	helptext = "Shows the title of the page somebody just posted a link to"
	showInCommandList = False
	claimCommandExecution = False
	callInThread = True  #We can't know how slow sites are, so prevent the bot from locking up on slow sites

	def shouldExecute(self, message, commandExecutionClaimed):
		for trigger in self.triggers:
			if trigger in message.message:
				return True
		return False
	
	def execute(self, message):
		"""
		:type message: IrcMessage
		"""
		starttime = time.time()
		urlmatch = re.search(r"(https?://\S+)", message.message)
		if not urlmatch:
			print "(Title Retrieve module triggered, but no url found)"
		else:
			url = urlmatch.group()
			while url.endswith(")") or url.endswith('/'):
				url = url[:-1]

			try:
				title = None
				#There's some special cases for often used pages.
				#Twitch!
				if url.count('twitch.tv') > 0:
					#Twitch
					channelmatches = re.search("https?://w*\.twitch\.tv/([^/]+)", url)
					if channelmatches:
						channel = channelmatches.group(1)
						channeldata = {}
						isChannelOnline = False
						twitchheaders = {'Accept': 'application/vnd.twitchtv.v2+json'}
						twitchStreamPage = requests.get(u"https://api.twitch.tv/kraken/streams/" + channel, headers=twitchheaders)
						streamdata = json.loads(twitchStreamPage.text.encode('utf-8'))
						print "stream data:"
						#for key, value in streamdata.iteritems():
						#	print u"  {}: {}".format(key, value)
						if 'stream' in streamdata and streamdata['stream'] is not None:
						#	print "using Stream API call"
							channeldata = streamdata['stream']['channel']
							isChannelOnline = True
						elif 'error' not in streamdata:
						#	print "Using Channels API call"
							twitchChannelPage = requests.get(u"https://api.twitch.tv/kraken/channels/" + channel, headers=twitchheaders)
							channeldata = json.loads(twitchChannelPage.text.encode('utf-8'))

						if len(channeldata) > 0:
						#	print "Channel data:"
						#	for key, value in channeldata.iteritems():
						#		print u"  {}: {}".format(key, value)

							title = u"Twitch - {username}"
							if channeldata['game'] is not None:
								title += u", playing {game}"
							if channeldata['mature']:
								title += u" [Mature]"
							if isChannelOnline:
								title += u" (Online)"
							else:
								title += u" (Offline)"
							title = title.format(username=channeldata['display_name'], game=channeldata['game'])
				elif url.count('youtube.com') > 0 or url.count('youtu.be') > 0:
					#Youtube!
					if not GlobalStore.commandhandler.apikeys.has_section('google') or not GlobalStore.commandhandler.apikeys.has_option('google', 'apikey'):
						print "[ERROR] Google API key not found!"
					else:
						#First we need to determine the video ID from something like this: http://www.youtube.com/watch?v=jmAKXADLcxY or http://youtu.be/jmAKXADLcxY
						videoId = u""
						if url.count('youtu.be') > 0:
							videoId = url[url.rfind('/')+1:]
						else:
							videoIdMatch = re.search('.+v=([^&#\Z]+)', url)
							if videoIdMatch:
								videoId = videoIdMatch.group(1)

						if videoId != u"":
							googleUrl = "https://www.googleapis.com/youtube/v3/videos"
							params = {'part': 'statistics,snippet,contentDetails', 'id': videoId, 'key': GlobalStore.commandhandler.apikeys.get('google', 'apikey')}
							params['fields'] = 'items/snippet(title,description),items/contentDetails/duration,items/statistics(viewCount,likeCount,dislikeCount)'
							googleJson = json.loads(requests.get(googleUrl, params=params).text.encode('utf-8'))

							if 'error' in googleJson:
								print u"ERROR with Google requests. {}: {}. [{}]".format(googleJson['error']['code'], googleJson['error']['message'], json.dumps(googleJson).replace('\n',' '))
							elif 'items' not in googleJson or len(googleJson['items']) != 1:
								print u"Unexpected reply from Google API: {}".format(json.dumps(googleJson).replace('\n', ' '))
							else:
								videoData = googleJson['items'][0]
								durationtimes = SharedFunctions.parseIsoDate(videoData['contentDetails']['duration'])
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

								#likePercentage = int(videoData['statistics']['likeCount']) / int(videoData['statistics']['dislikeCount'])

								title = u"{title} [{duration}, {viewcount:,} views]: {description}".format(title=videoData['snippet']['title'].strip(), duration=durationstring, viewcount=int(videoData['statistics']['viewCount']), description=description)
				elif url.count('imgur.com') > 0:
					if not GlobalStore.commandhandler.apikeys.has_section('imgur') or not GlobalStore.commandhandler.apikeys.has_option('imgur', 'clientid'):
						print "[ERROR] Imgur API key not found!"
					else:
						imageIdMatches = re.search('imgur\.com/([^.]+)', url, re.IGNORECASE)
						if imageIdMatches is None:
							print "No Imgur ID found in '{}'".format(url)
						else:
							imageId = imageIdMatches.group(1)
							print "[imgur] initial id: '{}'".format(imageId)
							isGallery = False
							imageType = 'image'
							if '/' in imageId:
								if 'gallery' in imageId:
									imageType = 'gallery/album'
									isGallery = True
								imageId = imageId[imageId.rfind('/')+1:]
								print "Modified Imgur id: '{}'".format(imageId)
							headers = {"Authorization": "Client-ID "+GlobalStore.commandhandler.apikeys.get('imgur','clientid')}
							imgurUrl = "https://api.imgur.com/3/{type}/{id}".format(type=imageType, id=imageId)
							print "url: {}".format(url)
							imgurDataPage = requests.get(imgurUrl, headers=headers)
							print "page: {}".format(imgurDataPage.text.encode('utf-8'))
							imgdata = json.loads(imgurDataPage.text.encode('utf-8'))
							if imgdata['success'] != True or imgdata['status'] != 200:
								print "[UrlTitle Imgur] Error while retrieving image data: {}".format(imgurDataPage.text.encode('utf-8'))
							else:
								#print imgurData
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

								if 'animated' in imgdata and imgdata['animated'] == True:
									title += u" (Animated)"
								
								if 'nsfw' in imgdata and imgdata['nsfw'] == True:
									title += u" (NSFW!)"
								title = title.format(imgdata=imgdata)
				elif url.count('twitter.com') > 0:
					tweetMatches = re.search('twitter.com/(?P<name>[^/]+)(?:/status/(?P<id>[^/]+).*)?', url)
					if not tweetMatches:
						print "No twitter matches found in '{}'".format(url)
					else:
						print "Tweetmatches: {}".format(tweetMatches.groupdict())
						#print "[UrlTitleFinder Twitter] Username is '{}', tweet id is '{}'".format(tweetMatches.group('name'), tweetMatches.group('id'))						
						if not GlobalStore.commandhandler.apikeys.has_section('twitter') or not GlobalStore.commandhandler.apikeys.has_option('twitter', 'tokentype') or not GlobalStore.commandhandler.apikeys.has_option('twitter', 'token'):
							print "[UrlTitleFinder] ERROR: Twitter API token info not found!"
						else:
							headers = {"Authorization": "{} {}".format(GlobalStore.commandhandler.apikeys.get('twitter', 'tokentype'),
												 GlobalStore.commandhandler.apikeys.get('twitter', 'token'))}
							if 'id' in tweetMatches.groupdict() and tweetMatches.group('id') is not None:
								#Specific tweet
								twitterUrl = "https://api.twitter.com/1.1/statuses/show.json?id={id}".format(id=tweetMatches.group('id'))
								twitterDataPage = requests.get(twitterUrl, headers=headers)
								twitterdata = json.loads(twitterDataPage.text.encode('utf-8'))
								print twitterdata

								title = u"@{username} ({name}): {text} [{timestamp}]".format(username=twitterdata['user']['screen_name'], name=twitterdata['user']['name'],
																		text=twitterdata['text'], timestamp=twitterdata['created_at'])
							else:
								#User page
								twitterUrl = u"https://api.twitter.com/1.1/users/show.json?screen_name={name}".format(name=tweetMatches.group('name'))
								twitterDataPage = requests.get(twitterUrl, headers=headers)
								twitterdata = json.loads(twitterDataPage.text.encode('utf-8'))

								title = u"{name} (@{screen_name}): {description} ({statuses_count:,} tweets posted, {followers_count:,} followers, following {friends_count:,})"
								if 'verified' in twitterdata and twitterdata['verified'] == True:
									title += u". Verified account"
								title = title.format(**twitterdata)

				#If nothing has been found so far, just display whatever is between the <title> tags
				if title is None:
					print "Using default title search"
					#Check here and not later because sites like Imgur can have .jpg URLs and we still want to check those
					extensionsToIgnore = ['.jpg', '.jpeg', '.gif', '.png', '.bmp', '.avi', '.wav', '.mp3', '.zip', '.rar', '.7z', '.pdf']
					for ext in extensionsToIgnore:
						if url.endswith(ext):
							print "Skipping title search, ignorable extension"
							return
					titlematch = re.search(r'<title.*?>(.+)</title>', requests.get(url).text)
					if not titlematch:
						print "No title found on page '{}'".format(url)
					else:
						title = titlematch.group(1).strip()
			except requests.exceptions.ConnectionError as error:
				print "(A connection error occurred while trying to retrieve '{}': {})".format(url, error)

			#Finally, display the result of all the hard work, if there was any
			if title is not None:
				title = title.replace('\n', ' ')
				#Convert weird characters like &#39 back into normal ones like '
				title = HTMLParser.HTMLParser().unescape(title)

				if len(title) > 250:
					title = title[:250] + "..."

				print "[urlTitleFinder] Time taken: {} seconds".format(time.time() - starttime)
				message.bot.say(message.source, u"Title: {}".format(title))