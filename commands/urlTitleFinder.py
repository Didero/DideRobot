import json, re
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
		timeout = 5.0  #In seconds
		urlmatch = re.search(r"(https?://\S+)", message.message)
		if not urlmatch:
			print "[url] Module triggered, but no url found in message '{}'".format(message.rawText)
		else:
			url = urlmatch.group()
			while url.endswith(")") or url.endswith('/'):
				url = url[:-1]

			try:
				title = None
				#There's some special cases for often used pages.
				if 'twitch.tv' in url:
					channelmatches = re.search("https?://w*\.twitch\.tv/([^/]+)", url)
					if channelmatches:
						channel = channelmatches.group(1)
						channeldata = {}
						isChannelOnline = False
						twitchheaders = {'Accept': 'application/vnd.twitchtv.v2+json'}
						twitchStreamPage = requests.get(u"https://api.twitch.tv/kraken/streams/" + channel, headers=twitchheaders, timeout=timeout)
						streamdata = json.loads(twitchStreamPage.text.encode('utf-8'))
						if 'stream' in streamdata and streamdata['stream'] is not None:
							channeldata = streamdata['stream']['channel']
							isChannelOnline = True
						elif 'error' not in streamdata:
							twitchChannelPage = requests.get(u"https://api.twitch.tv/kraken/channels/" + channel, headers=twitchheaders, timeout=timeout)
							channeldata = json.loads(twitchChannelPage.text.encode('utf-8'))

						if len(channeldata) > 0:
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
				elif 'youtube.com' in url or 'youtu.be' in url:
					if not GlobalStore.commandhandler.apikeys.has_section('google') or not GlobalStore.commandhandler.apikeys.has_option('google', 'apikey'):
						print "[url] ERROR: Google API key not found!"
					else:
						#First we need to determine the video ID from something like this: http://www.youtube.com/watch?v=jmAKXADLcxY or http://youtu.be/jmAKXADLcxY
						videoId = u""
						if url.count('youtu.be') > 0:
							videoId = url[url.rfind('/')+1:]
						else:
							videoIdMatch = re.search('.+v=([^&#]+)', url)
							if videoIdMatch:
								videoId = videoIdMatch.group(1)

						if videoId != u"":
							googleUrl = "https://www.googleapis.com/youtube/v3/videos"
							params = {'part': 'statistics,snippet,contentDetails', 'id': videoId, 'key': GlobalStore.commandhandler.apikeys.get('google', 'apikey'),
									  'fields': 'items/snippet(title,description),items/contentDetails/duration,items/statistics(viewCount,likeCount,dislikeCount)'}
							googleJson = json.loads(requests.get(googleUrl, params=params, timeout=timeout).text.encode('utf-8'))

							if 'error' in googleJson:
								print u"[url] ERROR with Google requests. {}: {}. [{}]".format(googleJson['error']['code'], googleJson['error']['message'], json.dumps(googleJson).replace('\n',' '))
							elif 'items' not in googleJson or len(googleJson['items']) != 1:
								print u"[url] Unexpected reply from Google API: {}".format(json.dumps(googleJson).replace('\n', ' '))
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
				elif 'imgur.com' in url:
					if not GlobalStore.commandhandler.apikeys.has_section('imgur') or not GlobalStore.commandhandler.apikeys.has_option('imgur', 'clientid'):
						print "[url] ERROR: Imgur API key not found!"
					else:
						imageIdMatches = re.search('imgur\.com/([^.]+)', url, re.IGNORECASE)
						if imageIdMatches is None:
							print "[url] No Imgur ID found in '{}'".format(url)
						else:
							imageId = imageIdMatches.group(1)
							isGallery = False
							imageType = 'image'
							if '/' in imageId:
								if 'gallery' in imageId:
									imageType = 'gallery/album'
									isGallery = True
								imageId = imageId[imageId.rfind('/')+1:]
							headers = {"Authorization": "Client-ID " + GlobalStore.commandhandler.apikeys.get('imgur','clientid')}
							imgurUrl = "https://api.imgur.com/3/{type}/{id}".format(type=imageType, id=imageId)
							imgurDataPage = requests.get(imgurUrl, headers=headers, timeout=timeout)
							imgdata = json.loads(imgurDataPage.text.encode('utf-8'))
							if imgdata['success'] is not True or imgdata['status'] != 200:
								print "[UrlTitle Imgur] Error while retrieving image data: {}".format(imgurDataPage.text.encode('utf-8'))
							else:
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
				elif 'twitter.com' in url:
					tweetMatches = re.search('twitter.com/(?P<name>[^/]+)(?:/status/(?P<id>[^/]+).*)?', url)
					if not tweetMatches:
						print "[url] No twitter matches found in '{}'".format(url)
					else:
						if not GlobalStore.commandhandler.apikeys.has_section('twitter') or not GlobalStore.commandhandler.apikeys.has_option('twitter', 'tokentype') or not GlobalStore.commandhandler.apikeys.has_option('twitter', 'token'):
							print "[url] ERROR: Twitter API token info not found!"
						else:
							headers = {"Authorization": "{} {}".format(GlobalStore.commandhandler.apikeys.get('twitter', 'tokentype'),
												 GlobalStore.commandhandler.apikeys.get('twitter', 'token'))}
							if 'id' in tweetMatches.groupdict() and tweetMatches.group('id') is not None:
								#Specific tweet
								twitterUrl = "https://api.twitter.com/1.1/statuses/show.json?id={id}".format(id=tweetMatches.group('id'))
								twitterDataPage = requests.get(twitterUrl, headers=headers, timeout=timeout)
								twitterdata = json.loads(twitterDataPage.text.encode('utf-8'))

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
				elif re.match('https?://.{2}(?:\.m)?\.wikipedia.org', url, re.IGNORECASE):
					title = GlobalStore.commandhandler.runCommandFunction('getWikipediaArticle', None, url, False)

				#If nothing has been found so far, just display whatever is between the <title> tags
				if title is None:
					#Check here and not later because sites like Imgur can have .jpg URLs and we still want to check those
					extensionsToIgnore = ['.jpg', '.jpeg', '.gif', '.png', '.bmp', '.avi', '.wav', '.mp3', '.zip', '.rar', '.7z', '.pdf']
					for ext in extensionsToIgnore:
						if url.endswith(ext):
							return
					titlematch = re.search(r'<title.*?>(.+)</title>', requests.get(url, timeout=timeout).text, re.DOTALL)
					if titlematch:
						title = titlematch.group(1).replace('\n', '').strip()
			except requests.exceptions.Timeout:
				print "[url] '{}' took too long to respond, ignoring".format(url)
			except requests.exceptions.ConnectionError as error:
				print "[url] A connection error occurred while trying to retrieve '{}': {}".format(url, error)

			#Finally, display the result of all the hard work, if there was any
			if title is not None:
				title = title.replace('\n', ' ')
				#Convert weird characters like &#39 back into normal ones like '
				title = HTMLParser.HTMLParser().unescape(title)

				if len(title) > 250:
					title = title[:250] + "..."

				message.bot.say(message.source, u"Title: {}".format(title))