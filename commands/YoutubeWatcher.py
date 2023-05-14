import copy, datetime, json, os, re

import requests

import Constants
import GlobalStore
from util import DateTimeUtil, DictUtil, IrcFormattingUtil, StringUtil
from commands.CommandTemplate import CommandTemplate
from CustomExceptions import CommandException, CommandInputException
from StringWithSuffix import StringWithSuffix


class Command(CommandTemplate):
	triggers = ['youtubewatcher', 'youtubewatch']
	helptext = "Regularly checks for new Youtube videos. '<add/remove> [channelname/playlist URL]' to add/remove channels or playlists to watch for new videos. " \
			   "'<list>' to see all watched channels and playlists. '<last/latest> [channelname/playlistname] shows the latest video uploaded by the channel or to the playlist. " \
			   "<show/link> [channelname/playlistname] gives a link to the matching channel's uploaded videos or to the matching playlist."
	scheduledFunctionTime = 900
	callInThread = True

	datafilepath = os.path.join(GlobalStore.scriptfolder, 'data', 'YoutubeWatcherData.json')
	# Format: {"(playlist_id)": "channelname": "(channelname to display when there's a new video)", "playlistname": "(playlist name to display when there's a new video) [[optional, only if not Uploads playlist]]",
	# 	"latestVideoId": "(video_id)", "latestVideoTitle": "(Video Title)", "latestVideoUploadTime": (timestamp), "reportChannels": ["DesertBusCommunityServer #desertbus"]}}
	watchedPlaylistsData = {}
	datetimeFormatString = "%Y-%m-%dT%H:%M:%S%fZ"
	newVideoReportCutoffAge = scheduledFunctionTime * 20

	#The 'add' command accepts either a  channel name, or a playlist url. These regexes should match any playlist url. URL formats:
	#  https://www.youtube.com/playlist?list=PLV_qemO0oatisNFQMcP3hl4P7XvP3pqem
	#  https://www.youtube.com/watch?v=ufvjjMp1rUg&list=PLV_qemO0oatisNFQMcP3hl4P7XvP3pqem
	playlistUrlMatcher = re.compile(r"^https?://(?:www\.)?youtube.com/.+[?&]list=(?P<playlistid>[^&]+)(?:&.+)*$")
	newVideoPrefix = IrcFormattingUtil.makeTextBold('New: ')

	def parseVideoPublishDateTime(self, publishedAtDateTimeString):
		"""
		Parse the provided video published-at date time string as a datetime instance
		:param publishedAtDateTimeString: The video publish datetime as a string
		:type publishedAtDateTimeString: str
		:return: The publish date time as a datetime object instance
		"""
		#The publish date sometimes seems to have a period and sometimes not. Remove it if it's there
		return datetime.datetime.strptime(publishedAtDateTimeString.replace('.', ''), self.datetimeFormatString)

	def onLoad(self):
		GlobalStore.commandhandler.addCommandFunction(__file__, 'getYoutubeVideoDescription', self.getVideoDisplayString)

		if 'google' not in GlobalStore.commandhandler.apikeys:
			self.logError("[YoutubeWatcher] Google API key not found! YoutubeWatcher module will not work")
			#Disable the automatic scheduled function if we don't have an API key because that won't work
			self.scheduledFunctionTime = None
			return
		if os.path.isfile(self.datafilepath):
			with open(self.datafilepath, 'r', encoding='utf-8') as datafile:
				self.watchedPlaylistsData = json.load(datafile)
			#Turn all the video timestamps into datetime objects, for easy comparison later
			for playlistId in self.watchedPlaylistsData:
				self.watchedPlaylistsData[playlistId]['latestVideoUploadTime'] = self.parseVideoPublishDateTime(self.watchedPlaylistsData[playlistId]['latestVideoUploadTime'])

	def executeScheduledFunction(self):
		newVideosPerServerChannelString = {}
		shouldSaveWatchedData = False
		now = datetime.datetime.now()
		#Retrieve the latest videos of each of the channels we're watching
		for playlistId, playlistData in self.watchedPlaylistsData.items():
			videosList = self.retrieveLatestVideos(playlistId, 2)
			newVideoList = []
			#Check if these videos are newer than the latest video we have stored
			while videosList:
				videoDict = videosList.pop(0)
				videoDict['publishedAt'] = self.parseVideoPublishDateTime(videoDict['publishedAt'])
				if videoDict['publishedAt'] > playlistData['latestVideoUploadTime']:
					#Store the video info in the 'new' list, but only the data we need
					newVideoList.append(DictUtil.getValuesFromDict(videoDict, 'publishedAt', 'videoId', 'title', 'playlistId'))
				else:
					#This video isn't newer than the stored video, and subsequent videos are assumed to be older, so no need to check those
					break
			if newVideoList:
				latestVideoDict = newVideoList[0]
				#Update the stored info on the latest video for the next check (This assumes the first video is the newest, which it should be)
				playlistData['latestVideoId'] = latestVideoDict['videoId']
				playlistData['latestVideoTitle'] = latestVideoDict['title']
				playlistData['latestVideoUploadTime'] = latestVideoDict['publishedAt']
				shouldSaveWatchedData = True
				# Store the new videos by serverchannel string, since we need to report on those
				while newVideoList:
					newVideoDict = newVideoList.pop(0)
					#If this video (and the subsequent older ones) is very old, don't report on it
					if (now - newVideoDict['publishedAt']).total_seconds() > self.newVideoReportCutoffAge:
						break
					#If it's not that old, store it to report to each IRC channel that wants to know about it
					for serverChannelString in playlistData['reportChannels']:
						if serverChannelString not in newVideosPerServerChannelString:
							newVideosPerServerChannelString[serverChannelString] = [newVideoDict]
						else:
							newVideosPerServerChannelString[serverChannelString].append(newVideoDict)
		videoIdToDescription = {}
		#Now we can report the newly found videos to each IRC channel
		while newVideosPerServerChannelString:
			serverChannelString, videoList = newVideosPerServerChannelString.popitem()
			for videoDict in videoList:
				videoId = videoDict['videoId']
				server, channel = serverChannelString.rsplit(' ', 1)
				if server in GlobalStore.bothandler.bots:
					if videoId not in videoIdToDescription:
						description = self.getVideoDisplayString(videoId, includeViewCount=False, includeUploadDate=False, includeUrl=True)
						description.mainString = self.newVideoPrefix + description.mainString
						videoIdToDescription[videoId] = description
					GlobalStore.bothandler.bots[server].sendLengthLimitedMessage(channel, videoIdToDescription[videoId].mainString, videoIdToDescription[videoId].suffix)
		if shouldSaveWatchedData:
			#New video info was stored, so save it to disk too
			self.saveWatchedChannelsData()

	def execute(self, message):
		"""
		:type message: IrcMessage.IrcMessage
		"""

		if message.isPrivateMessage:
			return message.reply("This module doesn't work in private messages, only in channels. Sorry!")
		#If no parameters were passed, show the help text
		if message.messagePartsLength == 0:
			return message.reply(self.getHelp(message))

		subcommand = message.messageParts[0].lower()
		serverChannelString = "{} {}".format(message.bot.serverfolder, message.source)

		if subcommand == 'list':
			return message.reply(self.getWatchList(serverChannelString))

		replytext = ""
		#Commands from here down need a channel name, check if one is provided
		if message.messagePartsLength < 2:
			replytext = "Please also add a channel name or playlist URL, so I know who you're talking about. Thanks!"
		else:
			channelName = " ".join(message.messageParts[1:])
			if subcommand == 'add':
				#Check if the parameter is a URL to a playlist
				playlistUrlMatch = self.playlistUrlMatcher.match(channelName)
				if playlistUrlMatch:
					#Add playlist by URL
					replytext = self.addWatchedPlaylist(serverChannelString, playlistUrlMatch.groupdict()['playlistid'])
				else:
					#Add Uploads playlist of the provided channel name
					replytext = self.addWatchedChannel(serverChannelString, channelName)
			elif subcommand == 'remove':
				if self.scheduledFunctionIsExecuting:
					replytext = "Sorry, I'm currently checking for new videos, so we best not change the watch list. Try again in a minute or so"
				else:
					replytext = self.removeWatchedChannel(serverChannelString, channelName)
			elif subcommand == 'last' or subcommand == 'latest':
				replytext = self.getLatestStoredVideo(serverChannelString, channelName)
			elif subcommand == 'show' or subcommand == 'link':
				replytext = self.getLinkToPlaylist(serverChannelString, channelName)
			elif subcommand == 'forcecheck':
				if self.scheduledFunctionIsExecuting:
					replytext = "I'm already checking at the moment! You're welcome"
				elif not message.bot.isUserAdmin(message.user, message.userNickname, message.userAddress):
					replytext = "I'm sorry, only my admins can force a manual check for new videos"
				else:
					#Reset the scheduled timer first
					self.resetScheduledFunctionGreenlet()
					self.executeScheduledFunction()
					replytext = "Ok, I'll check for new videos right now"
		if not replytext:
			replytext = "I don't know the subcommand '{}'. {}".format(subcommand, self.getHelp(message))
		return message.reply(replytext)

	def getWatchList(self, serverChannelString):
		watchedChannelNames = []
		for playlistId, playlistData in self.watchedPlaylistsData.items():
			if serverChannelString in playlistData['reportChannels']:
				if 'playlistname' in playlistData:
					#This isn't just the normal Uploads playlist, but a specific one, so add the playlist name too
					watchedChannelNames.append("{} playlist of {}".format(playlistData['playlistname'], playlistData['channelname']))
				else:
					watchedChannelNames.append(playlistData['channelname'])
		if not watchedChannelNames:
			return "I'm not watching any Youtube channels at the moment. Feel free to add some with the 'add' subcommand!"
		elif len(watchedChannelNames) == 1:
			return "I'm currently only watching a single Youtube channel: {}".format(watchedChannelNames[0])
		watchedChannelNames.sort()
		return "I'm currently watching {:,} Youtube channels: {}".format(len(watchedChannelNames), "; ".join(watchedChannelNames))

	def addWatchedChannel(self, serverChannelString, channelName):
		#First check if we're already following this Youtube channel
		lowercaseChannelName = channelName.lower()
		for playlistId, playlistData in self.watchedPlaylistsData.items():
			#Check for the 'playlistname' key, because if it's absent it means this is just the Uploads playlist, and this method should watch the Uploads playlist
			if 'playlistname' not in playlistData and lowercaseChannelName == playlistData['channelname'].lower():
				if serverChannelString in playlistData['reportChannels']:
					return "I'm already watching that Youtube channel! Maybe they just haven't uploaded a video in a while, so it may seem like I'm not keeping an eye on them, but just give them time"
				# We're already watching this Youtube channel, just not for this IRC channel. Just add this server-channel to the report channels
				playlistData['reportChannels'].add(serverChannelString)
				self.saveWatchedChannelsData()
				return "Ok, I'll start watching the {} Youtube channel, and I'll shout when they upload a new video".format(channelName)
		#We're not watching this Youtube channel yet, so we need to retrieve some info on it first
		uploadsPlaylistId = self.findChannelInfoByChannelName(channelName)
		latestVideoInfo = self.retrieveLatestVideos(uploadsPlaylistId, 1)[0]
		latestVideoUploadTime = None if not latestVideoInfo else self.parseVideoPublishDateTime(latestVideoInfo['publishedAt'])
		self.watchedPlaylistsData[uploadsPlaylistId] = {'channelname': channelName, 'latestVideoId': latestVideoInfo.get('videoId'), 'latestVideoTitle': latestVideoInfo.get('title'),
														  'latestVideoUploadTime': latestVideoUploadTime, 'reportChannels': [serverChannelString]}
		self.saveWatchedChannelsData()
		return "I hadn't heard of that channel before. I'll start keeping an eye on {}, and I'll shout when they upload a new video".format(channelName)

	def addWatchedPlaylist(self, serverChannelString, playlistId):
		if playlistId in self.watchedPlaylistsData:
			playlistData = self.watchedPlaylistsData[playlistId]
			if serverChannelString in playlistData['reportChannels']:
				return "I'm already watching the '{}' playlist of {}! Seems somebody else has the same taste you have".format(playlistData['playlistname'], playlistData['channelname'])
			self.watchedPlaylistsData[playlistId]['reportChannel'].add(serverChannelString)
			self.saveWatchedChannelsData()
			return "Ok, I'll keep an eye on the '{}' playlist of {}, and I'll shout in here when a new video gets added to it".format(playlistData['playlistname'], playlistData['channelname'])
		#We're not watching this playlist yet, so we should add a new entry to the watch dict
		#We need to retrieve the channel name and the playlist name
		playlistInfo = self.retrievePlaylistInfoById(playlistId)
		#Retrieve info on the latest video in the playlist too
		latestVideoInfo = self.retrieveLatestVideos(playlistId, 1)[0]
		latestVideoUploadTime = None if not latestVideoInfo else self.parseVideoPublishDateTime(latestVideoInfo['publishedAt'])
		self.watchedPlaylistsData[playlistId] = {'playlistname': playlistInfo['title'], 'channelname': playlistInfo['channelTitle'],'latestVideoId': latestVideoInfo.get('videoId'),
												 'latestVideoTitle': latestVideoInfo.get('title'), 'latestVideoUploadTime': latestVideoUploadTime, 'reportChannels': [serverChannelString]}
		self.saveWatchedChannelsData()
		return "All right, I'll start watching the '{}' playlist of {}, and I'll give a shout when a new video gets added to that playlist".format(playlistInfo['title'], playlistInfo['channelTitle'])

	def removeWatchedChannel(self, serverChannelString, playlistOrChannelName):
		matchingPlaylistIds = self.getPlaylistIdsFromNameSearch(playlistOrChannelName, serverChannelString)
		if not matchingPlaylistIds:
			# No match found, apparently we weren't watching that Youtube channel for this IRC channel
			return "I already wasn't watching the {} channel, so job done before I even started!".format(playlistOrChannelName)
		elif len(matchingPlaylistIds) > 1:
			return "That matches {:,} channels or playlists, can you be more specific?".format(len(matchingPlaylistIds))
		#Found a single match, we can remove this serverChannelString from it
		matchingPlaylistId = matchingPlaylistIds.pop()
		removedChannelDescriptor = "{playlistname} playlist of the {channelname}" if 'playlistname' in self.watchedPlaylistsData[matchingPlaylistId] else "{channelname}"
		removedChannelDescriptor = removedChannelDescriptor.format(playlistname=self.watchedPlaylistsData[matchingPlaylistId].get('playlistname'), channelname=self.watchedPlaylistsData[matchingPlaylistId]['channelname'])
		if len(self.watchedPlaylistsData[matchingPlaylistId]['reportChannels']) == 1:
			# This IRC channel is the only channel watching the Youtube channel, so we can remove all the details from it
			del self.watchedPlaylistsData[matchingPlaylistId]
		else:
			# Otherwise, just remove this IRC channel from the report channels list
			self.watchedPlaylistsData[matchingPlaylistId]['reportChannels'].remove(serverChannelString)
		self.saveWatchedChannelsData()
		return "Ok, I'll stop watching the {} channel then. If you want me to tell you when they upload a new video again, just add them back with the 'add' subcommand".format(removedChannelDescriptor)

	def getLatestStoredVideo(self, serverChannelString, playlistOrChannelName):
		matchingPlaylistIds = self.getPlaylistIdsFromNameSearch(playlistOrChannelName, serverChannelString)
		if len(matchingPlaylistIds) != 1:
			return self.getReplyWhenNoSingleSearchMatch(playlistOrChannelName, matchingPlaylistIds)
		playlistData = self.watchedPlaylistsData[matchingPlaylistIds[0]]
		if not playlistData['latestVideoId']:
			replytext = "{channelname} hasn't uploaded anything{playlistnameIfPresent} yet"
		else:
			replytext = "{channelname} uploaded '{videoTitle}'{playlistnameIfPresent} {videoAge} ago: https://youtu.be/{videoId}"
		playlistnameIfPresent = "" if 'playlistname' not in playlistData else " to the '{}' playlist".format(playlistData['playlistname'])
		return replytext.format(channelname=playlistData['channelname'], videoTitle=playlistData['latestVideoTitle'], playlistnameIfPresent=playlistnameIfPresent,
								videoAge=self.getVideoAge(playlistData['latestVideoUploadTime']), videoId=playlistData['latestVideoId'])

	def getLinkToPlaylist(self, serverChannelString, playlistOrChannelName):
		matchingPlaylistIds = self.getPlaylistIdsFromNameSearch(playlistOrChannelName, serverChannelString)
		if len(matchingPlaylistIds) != 1:
			return self.getReplyWhenNoSingleSearchMatch(playlistOrChannelName, matchingPlaylistIds)
		playlistData = self.watchedPlaylistsData[matchingPlaylistIds[0]]
		if 'playlistname' in playlistData:
			return "Sure, here's the '{}' playlist of {}: https://youtube.com/playlist?list={}".format(playlistData['playlistname'], playlistData['channelname'], matchingPlaylistIds[0])
		else:
			return "Sure, here's all the videos that {0} has uploaded: https://youtube.com/user/{0}/videos".format(playlistData['channelname'])

	def getReplyWhenNoSingleSearchMatch(self, searchQuery, matchingPlaylistIds):
		if not matchingPlaylistIds:
			return "Sorry, I don't know anybody with the playlist or channel name '{}'. If you want to introduce me to them, you can do so with the 'add' subcommand".format(searchQuery)
		elif len(matchingPlaylistIds) > 1:
			return "That matches {:,} channels I'm watching, can you be more specific?".format(len(matchingPlaylistIds))

	def saveWatchedChannelsData(self):
		#We need to turn the timestamps from a datetime object into a string timestamp, so we need a copy of the watch data
		saveData = copy.deepcopy(self.watchedPlaylistsData)
		for channelId in saveData:
			saveData[channelId]['latestVideoUploadTime'] = saveData[channelId]['latestVideoUploadTime'].strftime(self.datetimeFormatString)
		with open(self.datafilepath, 'w', encoding='utf-8') as datafile:
			datafile.write(json.dumps(saveData))

	def findChannelInfoByChannelName(self, channelName):
		"""
		This method returns the playlist ID that points to all the uploaded videos of the provided channel name
		:param channelName: The name of the channel to get the 'Uploads' playlist for
		:return: The ID of the uploads playlist of the provided channel
		:raises CommandException: Raised when something went wrong on Youtube's end
		:raises CommandInputExcepiton: Raised when the provided channel name could not be found
		"""

		#First get the channel ID, which we need to get the playlists
		request = requests.get('https://www.googleapis.com/youtube/v3/search', timeout=10.0, params={'key': GlobalStore.commandhandler.apikeys['google'], 'part': 'snippet', 'maxResults': 1, 'type': 'channel', 'q': channelName})
		if request.status_code != 200:
			self.logError("[YoutubeWatcher] An error occurred while searching for the channel ID of channel '{}': {} (status code {})".format(channelName, request.content, request.status_code))
			raise CommandException("Something went wrong searching for channel {}, sorry (status code {})".format(channelName, request.status_code))
		requestJson = request.json()
		if not requestJson['items']:
			raise CommandInputException("No channel found with the name '{}', maybe you made a typo?".format(channelName))
		channelId = requestJson['items'][0]['snippet']['channelId']

		#Use the found channel ID to retrieve the playlists and in particular the 'Uploads' playlist
		request = requests.get('https://www.googleapis.com/youtube/v3/channels', timeout=10.0, params={'key': GlobalStore.commandhandler.apikeys['google'], 'part': 'contentDetails', 'id': channelId})
		if request.status_code != 200:
			self.logError("[YoutubeWatcher] An error occurred while searching for the upload playlist ID of channel '{}' (ID '{}'): {} (status code {})".format(channelName, channelId, request.content, request.status_code))
			raise CommandException("Something went wrong with searching for the uploads of channel {}, sorry (status code {})".format(channelName, request.status_code))
		requestJson = request.json()
		if not requestJson['items']:
			raise CommandException("No playlists found for channel {}, maybe try again later?".format(channelName), shouldLogError=False)
		return requestJson['items'][0]['contentDetails']['relatedPlaylists']['uploads']

	def retrievePlaylistInfoById(self, playlistId):
		"""
		This method retrieves info on a playlist by its playlist ID
		:param playlistId: The ID of the playlist to retrieve the info of
		:return: A dict with the playlist info
		:raises CommandException: Raised when something goes wrong with accessing teh Youtube API
		"""
		request = requests.get("https://www.googleapis.com/youtube/v3/playlists", timeout=10.0, params={'key': GlobalStore.commandhandler.apikeys['google'], 'part': 'snippet', 'id': playlistId})
		if request.status_code != 200:
			self.logError("[YoutubeWatcher] An error occurred while searching for the playlist info for playlist ID '{}': {} (status code {})".format(playlistId, request.content, request.status_code))
			raise CommandException("Something went wrong searching for info on playlist ID {}, sorry (status code {})".format(playlistId, request.status_code))
		requestJson = request.json()
		if not requestJson['items']:
			raise CommandException("No playlist found with the ID '{}', sorry".format(playlistId))
		return requestJson['items'][0]['snippet']

	def retrieveLatestVideos(self, playlistId, numberOfVideos=5):
		if numberOfVideos < 1 or numberOfVideos > 50:
			numberOfVideos = 5
		request = requests.get('https://www.googleapis.com/youtube/v3/playlistItems', timeout=10.0, params={'key': GlobalStore.commandhandler.apikeys['google'], 'playlistId': playlistId, 'part': 'snippet', 'maxResults': numberOfVideos})
		if request.status_code != 200:
			self.logError("[YoutubeWatcher] An error occurred while retrieving videos from playlist ID '{}': {} (status code {})".format(playlistId, request.content, request.status_code))
			raise CommandException("Something went wrong with the request (Status code {})".format(request.status_code))
		requestJson = request.json()
		#If there's no matching items, just return an empty list
		if len(requestJson['items']) == 0:
			return [{}]
		videoDictList = []
		for item in requestJson['items']:
			snippet = item['snippet']
			#The video ID is hidden in a sub-dict, but that sub-dict doesn't contain anything else important, so move the video ID one dict up
			snippet['videoId'] = snippet.pop('resourceId')['videoId']
			videoDictList.append(snippet)
		return videoDictList

	def getVideoAge(self, videoPublishDatetime, precision=DateTimeUtil.MINUTES):
		return DateTimeUtil.durationSecondsToText((datetime.datetime.now() - videoPublishDatetime).total_seconds(), precision)

	def getPlaylistIdsFromNameSearch(self, channelOrPlaylistNameToSearchFor, serverChannelStringToMatch=None):
		lowerChannelOrPlaylistNameToSearchFor = channelOrPlaylistNameToSearchFor.lower()
		matchingPlaylistIds = []
		for playlistId, playlistData in self.watchedPlaylistsData.items():
			if serverChannelStringToMatch and serverChannelStringToMatch not in playlistData['reportChannels']:
				continue
			if lowerChannelOrPlaylistNameToSearchFor != playlistData['channelname'].lower():
				continue
			matchingPlaylistIds.append(playlistId)
		if not matchingPlaylistIds:
			# If we didn't find a direct channel name match, check if the search query matches (part of) the playlist name
			for playlistId, playlistData in self.watchedPlaylistsData.items():
				if 'playlistname' not in playlistData:
					continue
				if serverChannelStringToMatch and serverChannelStringToMatch not in playlistData['reportChannels']:
					continue
				if lowerChannelOrPlaylistNameToSearchFor not in playlistData['playlistname'].lower():
					continue
				matchingPlaylistIds.append(playlistId)
		return matchingPlaylistIds

	def getVideoDisplayString(self, videoId, includeViewCount=True, includeUploadDate=True, includeUrl=True):
		"""
		Gets a display string describing the video of the provided ID
		:param videoId: The ID to get the display string of
		:param includeViewCount: Whether the view count should be included in the result
		:param includeUploadDate: If True, the date when the video was uploaded will be included in the output
		:param includeUrl: If True, the URL to the video will be added to the end of the output
		:return: The display string describing the video, or None if something went wrong with retrieving the data
		"""
		if 'google' not in GlobalStore.commandhandler.apikeys:
			self.logError("[YoutubeWatcher] Google API key not found!")
			return None

		googleJson = requests.get("https://www.googleapis.com/youtube/v3/videos", timeout=5, params={'part': 'statistics,snippet,contentDetails', 'id': videoId, 'key': GlobalStore.commandhandler.apikeys['google'],
				  'fields': 'items/snippet(title,channelTitle,description,publishedAt),items/contentDetails/duration,items/statistics(viewCount)'}).json()

		if not googleJson or 'error' in googleJson:
			self.logError("[YoutubeWatcher] ERROR while retrieving info for video ID {}. {}: {}. [{}]".format(videoId, googleJson['error']['code'], googleJson['error']['message'], StringUtil.removeNewlines(json.dumps(googleJson))))
			return None
		if 'items' not in googleJson or len(googleJson['items']) != 1:
			CommandTemplate.logError("[YoutubeWatcher] Unexpected reply from Google API: {}".format(StringUtil.removeNewlines(json.dumps(googleJson))))
			return None
		videoData = googleJson['items'][0]
		durationtimes = DateTimeUtil.parseIsoDuration(videoData['contentDetails']['duration'])
		durationstring = ""
		if durationtimes['day'] > 0:
			durationstring += "{day} d, "
		if durationtimes['hour'] > 0:
			durationstring += "{hour:02}:"
		durationstring += "{minute:02}:{second:02}"
		durationstring = durationstring.format(**durationtimes)
		#Check if there's a description
		description = videoData['snippet']['description'].strip()
		if not description:
			description = "<No description>"
		else:
			description = StringUtil.removeNewlines(description)

		snippetData = videoData['snippet']
		resultStringParts = ["{title} {by} {channel}".format(title=snippetData['title'].strip(), by=IrcFormattingUtil.makeTextColoured('by', IrcFormattingUtil.Colours.GREY), channel=snippetData['channelTitle']),
							 durationstring]
		if includeViewCount:
			resultStringParts.append("{:,} views".format(int(videoData['statistics']['viewCount'])))
		if includeUploadDate:
			resultStringParts.append(snippetData['publishedAt'].split('T', 1)[0])
		resultStringParts.append(description)

		suffixes = None
		if includeUrl:
			suffixes = (Constants.GREY_SEPARATOR, "https://youtu.be/", videoId)
		return StringWithSuffix(Constants.GREY_SEPARATOR.join(resultStringParts), suffixes)
