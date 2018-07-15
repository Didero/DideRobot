import json, os, time

import requests

import GlobalStore
import SharedFunctions
from CommandTemplate import CommandTemplate

class Command(CommandTemplate):
	triggers = ['twitchwatcher', 'twitchwatch']
	helptext = "Follows Twitch streamers. '<add/remove> [streamername]' to add/remove (add 'autoreport' for automatic live mention). " \
			   "'<list/live>' to see all or live followed streamers. '<toggle/autoreport> [streamername]' to toggle autoreporting. " \
			   "'<setnick> [streamername] [nick]' to set a nickname for a streamer, '<removenick> [streamername]' to remove it. " \
			   "Any other parameter is interpreted as a streamer name and will return stream info, if they're live."
	scheduledFunctionTime = 300
	callInThread = True

	#Dict to keep the info on all the streamers we need to follow
	# Keys are lowercase names
	# Values are info dicts, containing:
	#   -'clientId' which the API uses instead of channel names
	#   -'followChannels', a list of strings with the server and channel, separated by a space, where that streamer is followed but not autoreported going live
	#   -'reportChannels', a list of strings with server-channel, separated by a space, where streamers going live should be auto-reported
	#	-'hasBeenReportedLive', a boolean that indicates whether this is the first time this stream has been seen live or not. If this is missing, no IRC channel wants autoreporting
	watchedStreamersData = {}
	#Keep track of the last time we updated, so we don't report on streams that have been live for a while, just because we've been offline for several update cycles
	# Gets stored in the watch data when the module gets unloaded, and gets removed from the watch data when the module is loaded, to make iterating over it easier
	lastLiveCheckTime = None

	def onLoad(self):
		if 'twitch' not in GlobalStore.commandhandler.apikeys:
			self.logError("[TwitchWatcher] Twitch API key not found! TwitchWatch module will not work")
			#Disable the automatic scheduled function if we don't have an API key because that won't work
			self.scheduledFunctionTime = None
			return
		datafilepath = os.path.join(GlobalStore.scriptfolder, 'data', 'TwitchWatcherData.json')
		if os.path.isfile(datafilepath):
			with open(datafilepath, 'r') as datafile:
				self.watchedStreamersData = json.load(datafile)
			self.lastLiveCheckTime = self.watchedStreamersData.pop('_lastUpdateTime', None)

	def onUnload(self):
		self.watchedStreamersData['_lastUpdateTime'] = self.lastLiveCheckTime
		self.saveWatchedStreamerData()

	def saveWatchedStreamerData(self):
		with open(os.path.join(GlobalStore.scriptfolder, 'data', 'TwitchWatcherData.json'), 'w') as datafile:
			datafile.write(json.dumps(self.watchedStreamersData))

	def doesStreamerHaveNickname(self, streamername, serverChannelString):
		return 'nicknames' in self.watchedStreamersData[streamername] and serverChannelString in self.watchedStreamersData[streamername]['nicknames']

	def execute(self, message):
		"""
		:type message: IrcMessage.IrcMessage
		"""

		#Making this work in PMs requires either a different storage method than "server channel",
		# or a better lookup method than 'if channel in bot.channelUserList'
		if message.isPrivateMessage:
			message.reply("I'm sorry, this module doesn't work in private messages (yet?). Poke my owner if you want it added!", "say")
			return

		if message.messagePartsLength == 0:
			message.reply("Please add a parameter. Use 'list' to see which streamers I'm watching, or 'add' to add one of your own", "say")
			return

		parameter = message.messageParts[0].lower()
		if (parameter == "add" or parameter == "live") and 'twitch' not in GlobalStore.commandhandler.apikeys:
			message.reply("Oh, I'm sorry, I seem to have lost my access key to Twitch. Inform my owner(s), they can probably find it for me!", "say")
			return

		#All options need this for lookup
		serverChannelString = "{} {}".format(message.bot.serverfolder, message.source)
		streamername = None if message.messagePartsLength < 2 else message.messageParts[1]

		if parameter == "list":
			replytext = self.listFollowedStreamer(serverChannelString)
		elif parameter == "add" or parameter == "follow":
			if message.messagePartsLength < 2:
				# At the risk of ruining the joke, the '26 hours' is a reference to Star Trek DS9, not a mistake
				replytext = "Watch which streamer? I'm on Twitch 26 hours a day so you're going to have to be more specific"
			else:
				shouldAutoReport = message.messagePartsLength > 2 and message.messageParts[2].lower() == 'autoreport'
				replytext = self.startFollowingStreamer(serverChannelString, streamername, shouldAutoReport)[1]
		elif parameter == "remove":
			if message.messagePartsLength < 2:
				replytext = "I'm not going to remove all the streamers I watch! Please be more specific"
			else:
				replytext = self.stopFollowingStreamer(serverChannelString, streamername)[1]
		elif parameter == "toggle" or parameter == "autoreport":
			#Toggle auto-reporting
			if message.messagePartsLength < 2:
				replytext = "I can't toggle autoreporting for everybody, that'd get confusing! Please provide a streamer name too"
			else:
				replytext = self.toggleStreamerAutoreport(serverChannelString, streamername)[1]
		elif parameter == "setnick":
			if message.messagePartsLength < 3:
				replytext = "I'm not going to make up a nick! Please add a nickname too"
			else:
				replytext = self.setStreamerNickname(serverChannelString, streamername, message.messageParts[2])[1]
		elif parameter == "removenick":
			if message.messagePartsLength < 2:
				replytext = "I'm not going to delete everybody's nickname! Add the name of the streamer whose nick you want removed"
			else:
				replytext = self.removeStreamerNickname(serverChannelString, streamername)[1]
		elif parameter == "live":
			replytext = self.getCurrentlyLiveStreamers(serverChannelString)[1]
		elif parameter == "lookup":
			replytext = self.getStreamerInfo(streamername)[1]
		else:
			replytext = "I don't know what to do with the parameter '{}', sorry. Try (re)reading the help text, or check for typos?".format(parameter)
		#Show the result of whatever command was called
		message.reply(replytext, "say")

	def listFollowedStreamer(self, serverChannelString):
		"""
		Returns a string with a list of streamer names followed for this server and channel
		:param serverChannelString: The server name followed by the channel name, separated by a space
		:return: A list of the streamers followed for the provided channel
		"""
		followedStreamers = []
		for streamername, streamerdata in self.watchedStreamersData.iteritems():
			# Get the streamer's nickname, if any
			if self.doesStreamerHaveNickname(streamername, serverChannelString):
				streamername = u"{}({})".format(streamerdata['nicknames'][serverChannelString], streamername)
			# Check to see if this streamer is followed in the channel the command came from
			if serverChannelString in streamerdata['followChannels']:
				followedStreamers.append(streamername)
			elif serverChannelString in streamerdata['reportChannels']:
				followedStreamers.append(streamername + u"[a]")
		if len(followedStreamers) == 0:
			return u"I'm not watching anybody for this channel. You can add streamers for me to watch with the 'add' parameter"
		elif len(followedStreamers) == 1:
			return u"I'm only following a single stream for this channel, namely {}".format(followedStreamers[0])
		else:
			followedStreamers.sort()
			return u"I'm watching {:,} streamers: {}".format(len(followedStreamers), u", ".join(followedStreamers))

	def startFollowingStreamer(self, serverChannelString, streamername, shouldAutoReport=False):
		"""
		Make the bot start checking if the provided streamer is online for the provided channel. That way they'll show up in the live list,
		and the bot will optionally mention in the channel whenever the streamer starts streaming
		:param serverChannelString: The server name followed by the channel name, separated by a space
		:param streamername: The username of the Twitch streamer that should be followed for this channel
		:param shouldAutoReport: If set to True, the bot will mention in the provided channel whenever the streamer goes live. Otherwise they will only show up in the livelist
		:return: A tuple, first entry is a success boolean, second one is the result string with either the error message or the success message
		"""
		#Make the streamer name lowercase for easier matching
		streamername = streamername.lower()

		streamerdata = self.watchedStreamersData.get(streamername, None)
		# Check if they're already being followed
		if streamerdata and (serverChannelString in streamerdata['followChannels'] or serverChannelString in streamerdata['reportChannels']):
			return (False, u"I'm already following {}. Seems you're not the only who likes them!".format(streamername))

		# If we don't have data on this streamer yet, retrieve it
		if not streamerdata:
			isSuccess, result = self.retrieveStreamerId(streamername)
			if not isSuccess:
				return (False, result)
			# No errors, got the streamer data. Store it
			self.watchedStreamersData[streamername] = {'clientId': result, 'hasBeenReportedLive': False, 'followChannels': [], 'reportChannels': []}
			# Update the convenience variable too since that's 'None' now
			streamerdata = self.watchedStreamersData[streamername]

		# We know we have the basics for the streamer set up, at least, or more if they were already in our files
		# Add the current server-channel pair in there too
		channelType = 'reportChannels' if shouldAutoReport else 'followChannels'
		streamerdata[channelType].append(serverChannelString)
		self.saveWatchedStreamerData()
		replytext = u"All right, I'll keep an eye on {}".format(streamername)
		if shouldAutoReport:
			replytext += u", and I'll shout in here when they go live"
		return (True, replytext)

	def stopFollowingStreamer(self, serverChannelString, streamername):
		"""
		Make the bot stop checking if the provided streamer is online for the provided channel
		:param serverChannelString: The server name followed by the channel name, separated by a space
		:param streamername: The username of the Twitch streamer that should no longer be followed for this channel
		:return: A tuple, first entry is a success boolean, second one is the result string with either the error message or the success message
		"""
		streamername = streamername.lower()
		streamerdata = self.watchedStreamersData.get(streamername, None)
		if not streamerdata:
			return (False, u"I don't even know who {} is. So task completed, I guess?".format(streamername))
		# Determine if the streamer is followed or autoreported
		channelType = None
		if serverChannelString in streamerdata['followChannels']:
			channelType = 'followChannels'
		elif serverChannelString in streamerdata['reportChannels']:
			channelType = 'reportChannels'
		if not channelType:
			return (False, u"I'm already not watching {}. You're welcome!".format(streamername))
		# The streamer is being followed. Remove them from the channel type list they were in
		streamerdata[channelType].remove(serverChannelString)
		# If there's no channel watching this streamer anymore, remove it entirely
		if len(streamerdata['followChannels']) == 0 and len(streamerdata['reportChannels']) == 0:
			del self.watchedStreamersData[streamername]
		self.saveWatchedStreamerData()
		return (True, u"Ok, I'll stop watching {} then".format(streamername))

	def toggleStreamerAutoreport(self, serverChannelString, streamername):
		"""
		Make the bot toggle whether it should be reported when the provided streamer starts streaming
		:param serverChannelString: The server name followed by the channel name, separated by a space
		:param streamername: Which streamer to toggle autoreporting for
		:return: A tuple, first entry is a success boolean, second one is the result string with either the error message or the success message
		"""
		streamername = streamername.lower()
		streamerdata = self.watchedStreamersData.get(streamername, None)
		if not streamerdata or (serverChannelString not in streamerdata['followChannels'] and serverChannelString not in streamerdata['reportChannels']):
			return (False, u"I'm not following {}, so I can't toggle autoreporting for them either. Maybe you made a typo, or you forgot to add them with 'add'?")
		else:
			if serverChannelString in streamerdata['followChannels']:
				streamerdata['followChannels'].remove(serverChannelString)
				streamerdata['reportChannels'].append(serverChannelString)
				replytext = u"All right, I'll shout in here when {} goes live. You'll never miss a stream of them again!".format(streamername)
			else:
				streamerdata['reportChannels'].remove(serverChannelString)
				streamerdata['followChannels'].append(serverChannelString)
				replytext = u"Ok, I'll stop mentioning every time {} goes live. But don't blame me if you miss a stream of them!".format(streamername)
			self.saveWatchedStreamerData()
			return (True, replytext)

	def setStreamerNickname(self, serverChannelString, streamername, nickname):
		"""
		Set a nickname for a streamer, since their nick in the channel and their Twitch nick don't always match
		:param serverChannelString: The server name followed by the channel name, separated by a space
		:param streamername: Which streamer to set a nickname for
		:param nickname: The nickname to store for this streamer
		:return: A tuple, first entry is a success boolean, second one is the result string with either the error message or the success message
		"""
		streamername = streamername.lower()
		streamerdata = self.watchedStreamersData.get(streamername, None)
		if not streamerdata or (serverChannelString not in streamerdata['followChannels'] and serverChannelString not in streamerdata['reportChannels']):
			return (False, u"I don't even follow {}, so setting a nickname is slightly premature. "
						   u"Please introduce me to them first with the 'add' parameter".format(streamername))
		if 'nicknames' not in streamerdata:
			streamerdata['nicknames'] = {}
		streamerdata['nicknames'][serverChannelString] = nickname
		self.saveWatchedStreamerData()
		return (True, u"All right, I'll call {} '{}' from now on".format(streamername, nickname))

	def removeStreamerNickname(self, serverChannelString, streamername):
		"""
		Remove the nickname for a streamer, if one is set
		:param serverChannelString: The server name followed by the channel name, separated by a space
		:param streamername: Which streamer to remove the nickname of
		:return: A tuple, first entry is a success boolean, second one is the result string with either the error message or the success message
		"""
		streamername = streamername.lower()
		streamerdata = self.watchedStreamersData.get(streamername, None)
		# Maybe they entered the nickname instead of the streamer name. Check if we can find it
		if not streamerdata:
			for streamername, streamerdata in self.watchedStreamersData.iteritems():
				if self.doesStreamerHaveNickname(streamername, serverChannelString) and streamername == streamerdata['nicknames'][serverChannelString].lower():
					# Found a match. If we break now, streamername and streamerdata will be set correctly
					break
			else:
				return (False, u"I'm sorry, I don't know who {} is. Maybe you made a typo, "
							   u"or you forgot to add the streamer with the 'add' parameter?".format(streamername))
		if not self.doesStreamerHaveNickname(streamername, serverChannelString):
			return (True, u"I don't have a nickname stored for {}, so mission accomplished, I guess?".format(streamername))
		nickname = streamerdata['nicknames'][serverChannelString]
		del streamerdata['nicknames'][serverChannelString]
		if len(streamerdata['nicknames']) == 0:
			del streamerdata['nicknames']
		self.saveWatchedStreamerData()
		return (True, u"Ok, I removed the nickname '{}', I'll call them by their Twitch username '{}' from now on".format(nickname, streamername))

	def getCurrentlyLiveStreamers(self, serverChannelString):
		"""
		Get a string with all the currently live streamers that the provided channel follows. If there's only a few streamers live, more expansive info is shown per streamer
		:param serverChannelString: The server name followed by the channel name, separated by a space
		:return: A tuple, first entry is a success boolean, second one is the result string with either the error message or the currently live streamers
		"""
		streamerIdsToCheck = []
		for streamername, streamerdata in self.watchedStreamersData.iteritems():
			if serverChannelString in streamerdata['followChannels'] or serverChannelString in streamerdata['reportChannels']:
				streamerIdsToCheck.append(streamerdata['clientId'])
		isSuccess, result = self.retrieveStreamDataForIds(streamerIdsToCheck)
		if not isSuccess:
			self.logError(u"[TwitchWatch] An error occurred during a manual live check. " + result)
			return (False, "I'm sorry, I wasn't able to retrieve data from Twitch. It's probably entirely their fault, not mine though. Try again in a little while")
		if len(result) == 0:
			return (True, "Nobody's live, it seems. Time for videogames and/or random streams, I guess!")
		#One or more streamers are live, show info on each of them
		reportStrings = []
		shouldUseShortReportString = len(result) >= 4  # Use shorter report strings if there's 4 or more people live
		for streamername, streamerdata in result.iteritems():
			displayname = streamerdata['channel']['display_name']
			if self.doesStreamerHaveNickname(streamername, serverChannelString):
				displayname = self.watchedStreamersData[streamername]['nicknames'][serverChannelString]
			if shouldUseShortReportString:
				reportStrings.append(u"{} ({})".format(displayname, streamerdata['channel']['url']))
			else:
				reportStrings.append(u"{displaynameBold}: {status} [{game}] ({url})".format(displaynameBold=SharedFunctions.makeTextBold(displayname),
																							**streamerdata['channel']))
		return (True, SharedFunctions.joinWithSeparator(reportStrings))

	def getStreamerInfo(self, streamername):
		"""
		Get info on the provided streamer, if they're live
		:param streamername: The name of the streamer to get info on
		:return: A tuple, first entry is a success boolean, second one is the result string with either the error message or the currently live streamers
		"""
		# Check if we happen to have the streamer's ID on file, saves retrieving it
		if streamername in self.watchedStreamersData:
			streamerId = self.watchedStreamersData[streamername]['clientId']
		else:
			isSuccess, result = self.retrieveStreamerId(streamername)
			if not isSuccess:
				return (False, result)
			streamerId = result

		# Get stream info
		isSuccess, result = self.retrieveStreamDataForIds([streamerId])
		if not isSuccess:
			return (False, result)
		if len(result) == 0:
			return (True, u"{0} doesn't appear to be streaming at the moment. Maybe they've got some old streams you can watch though, "
						  u"here: https://www.twitch.tv/{0}/videos/all".format(streamername))
		#Streamer is live, return info on them
		return (True, u"{display_name}: {status} [{game}] ({url})".format(**result[streamername]['channel']))

	def executeScheduledFunction(self):
		#Go through all our stored streamers, and see if we need to report online status somewhere
		#  If we do, check if they're actually online
		streamerIdsToCheck = {}  #Store as a clientId-to-streamername dict to facilitate reverse lookup in self.streamerdata later
		for streamername, data in self.watchedStreamersData.iteritems():
			if len(data['reportChannels']) > 0:
				#Ok, store that we need to check whether this stream is online or not
				# Because doing the check one time for all streamers at once is far more efficient
				streamerIdsToCheck[data['clientId']] = streamername

		if len(streamerIdsToCheck) == 0:
			#Nothing to do! Let's stop now
			return

		isSuccess, result = self.retrieveStreamDataForIds(streamerIdsToCheck.keys())
		if not isSuccess:
			self.logError(u"[TwitchWatch] An error occurred during the scheduled live check. " + result)
			#Still update the last checked time, so we do get results when the connection works again
			self.lastLiveCheckTime = time.time()
			return

		#If the last time we checked for updates was (far) longer ago than the time between update checks, we've probably been offline for a while
		# Any data we retrieve could be old, so don't report it, but just log who's streaming and who isn't
		if self.lastLiveCheckTime:
			shouldReport = time.time() - self.lastLiveCheckTime <= self.scheduledFunctionTime * 6
		else:
			shouldReport = True

		if not shouldReport:
			self.logDebug("[TwitchWatcher] Skipping reporting on live streams, since our last check was {} seconds ago, which is too long".format(self.lastLiveCheckTime - time.time()))

		self.lastLiveCheckTime = time.time()

		channelMessages = {}  #key is string with server-channel, separated by a space. Value is a list of tuples with data on streams that are live
		for streamername, streamdata in result.iteritems():
			channeldata = streamdata.pop('channel')
			#Remove this stream from the list of streamers we need to check, so afterwards we can verify which streams we didn't get data on
			del streamerIdsToCheck[str(channeldata['_id'])]
			# Only store data for channels that have gone live since our last check
			if self.watchedStreamersData[streamername]['hasBeenReportedLive']:
				continue
			#We will report that this stream is live, so store that we'll have done that
			self.watchedStreamersData[streamername]['hasBeenReportedLive'] = True
			#Only construct a live report message when we should report
			if shouldReport:
				#Store current stream description data for each name, so we can check afterwards which channels we need to send it to
				#  Don't store it as a string, so we can shorten it if one channel would get a lot of live streamer reports
				for serverChannelString in self.watchedStreamersData[streamername]['reportChannels']:
					#Add this stream's data to the channel's reporting output
					if serverChannelString not in channelMessages:
						channelMessages[serverChannelString] = []
					displayname = channeldata['display_name']
					if self.doesStreamerHaveNickname(streamername, serverChannelString):
						displayname = self.watchedStreamersData[streamername]['nicknames'][serverChannelString]
					channelMessages[serverChannelString].append((displayname, channeldata['status'], channeldata['game'], channeldata['url']))

		#Now we've got all the stream data we need!
		# First set the offline streams to offline
		for clientId, streamername in streamerIdsToCheck.iteritems():
			self.watchedStreamersData[streamername]['hasBeenReportedLive'] = False

		self.saveWatchedStreamerData()

		if shouldReport:
			#And now report each online stream to each channel that wants it
			for serverChannelString, streamdatalist in channelMessages.iteritems():
				server, channel = serverChannelString.rsplit(" ", 1)
				#First check if we're even in the server and channel we need to report to
				if server not in GlobalStore.bothandler.bots or channel not in GlobalStore.bothandler.bots[server].channelsUserList:
					continue

				reportStrings = []
				#If we have a lot of live streamers to report, keep it short. Otherwise, we can be a bit more verbose
				if len(streamdatalist) >= 4:
					#A lot of live streamers to report, keep it short. Just the streamer name and the URL
					for streamdata in streamdatalist:
						reportStrings.append(u"{0} ({3})".format(*streamdata))
				else:
					#Only a few streamers live, we can be a bit more verbose
					for streamdata in streamdatalist:
						reportStrings.append(u"{streamernameBolded}: {1} [{2}] ({3})".format(streamernameBolded=SharedFunctions.makeTextBold(streamdata[0]), *streamdata))
				#Now make the bot say it
				GlobalStore.bothandler.bots[server].sendMessage(channel.encode("utf8"), u"Streamer{} went live: ".format(u's' if len(reportStrings) > 1 else u'') +
																SharedFunctions.joinWithSeparator(reportStrings), "say")

	def retrieveStreamerId(self, streamername):
		try:
			r = requests.get("https://api.twitch.tv/kraken/users", params={"client_id": GlobalStore.commandhandler.apikeys['twitch'],
																		   "api_version": 5, "login": streamername}, timeout=10.0)
		except requests.exceptions.Timeout:
			return (False, u"Apparently Twitch is distracted by its own streams, because it's too slow to respond. Try again in a bit?")
		twitchData = r.json()
		if 'error' in twitchData:
			self.logError(u"[TwitchWatch] Something went wrong when trying to find the clientID of user '{}'. {}".format(streamername,
																														 twitchData['message'] if 'message' in twitchData else "No error message provided"))
			return (False, u"Sorry, something went wrong when trying to look up info on that user. Please try again in a bit, maybe it'll go better then")
		if twitchData['_total'] != 1:
			return (False, u"That... doesn't match anybody on file. Twitch's file, I mean. Maybe you misspelled the streamer's name?")
		# No errors, got the streamer data. Return it
		return (True, twitchData['users'][0]['_id'])

	def retrieveStreamDataForIds(self, idList):
		# Add a 'limit' parameter in case we need to check more streamers than the default limit allows
		try:
			r = requests.get("https://api.twitch.tv/kraken/streams/", params={"client_id": GlobalStore.commandhandler.apikeys['twitch'], "api_version": 5,
								 "limit": len(idList), "stream_type": "live", "channel": ",".join(idList)}, timeout=10.0)
		except requests.exceptions.Timeout:
			return (False, "Twitch took too long to respond")
		apireply = r.json()
		if "error" in apireply:
			errormessage = apireply["message"] if "message" in apireply else u"No error message provided"
			return (False, errormessage)

		if not apireply['streams']:
			#No live streams
			return (True, {})
		streamernameToData = {}
		for streamdata in apireply['streams']:
			streamername = streamdata['channel']['name'].lower()
			streamernameToData[streamername] = streamdata
		return (True, streamernameToData)
