import base64, datetime, json, os, re
import HTMLParser

import requests

from CommandTemplate import CommandTemplate
import Constants
import GlobalStore
from util import DateTimeUtil
from util import IrcFormattingUtil
from IrcMessage import IrcMessage
from CustomExceptions import WebRequestException


class Command(CommandTemplate):
	triggers = ['twitterwatcher', 'twitterwatch']
	helptext = "Automatically says new tweets of watched accounts. Use parameter 'add' to add an account to watch and 'remove' to stop watching an account. 'latest' shows latest tweet. " \
			   "Use 'setname' and 'removename' to set and remove a display name. These parameters need to be followed by a Twitter name. 'list' lists all accounts being watched"
	scheduledFunctionTime = 300.0  #Check every 5 minutes
	runInThread = True

	watchData = {}  #keys are Twitter usernames, contains fields with highest ID and which channel(s) to report new tweets to, and a display name if specified
	MAX_TWEETS_TO_MENTION = 3

	def onLoad(self):
		GlobalStore.commandhandler.addCommandFunction(__file__, 'getTweetDescription', self.getTweetDescription)

		#First retrieve which Twitter accounts we should follow, if that file exists
		watchedFilepath = os.path.join(GlobalStore.scriptfolder, 'data', 'WatchedTwitterAccounts.json')
		if os.path.exists(watchedFilepath):
			with open(watchedFilepath, 'r') as watchedFile:
				self.watchData = json.load(watchedFile)
		#If we can't identify to Twitter, stop right here
		if 'twitter' not in GlobalStore.commandhandler.apikeys:
			self.logWarning("[TwitterWatcher] Twitter API credentials not found!")
			return

	def executeScheduledFunction(self):
		self.checkForNewTweets()

	def execute(self, message):
		"""
		:type message: IrcMessage
		"""
		if message.messagePartsLength == 0:
			message.reply(self.helptext, 'say')
			return

		parameter = message.messageParts[0].lower()
		serverChannelPair = [message.bot.serverfolder, message.source]  #List not tuple, because JSON can't save tuples and converts them to a list

		#Start with the commands that don't need a username parameter
		if parameter == 'help':
			message.reply(self.helptext, 'say')
			return
		if parameter == 'list':
			#List all the accounts we're watching for this channel
			watchlist = []
			for username, usernameData in self.watchData.iteritems():
				if serverChannelPair in usernameData['targets']:
					watchlist.append(self.getDisplayName(username))
			watchlistLength = len(watchlist)
			if watchlistLength == 0:
				replytext = "I'm not watching any Twitter users for this channel"
			elif watchlistLength == 1:
				replytext = "I just watch {} for the people here".format(watchlist[0])
			else:
				watchlist.sort()
				replytext = "I watch {:,} Twitter users for this channel: {}".format(watchlistLength, "; ".join(watchlist))
			message.reply(replytext, 'say')
			return
		#'update' forces an update check, but it's only available to admins. Also doesn't need a username
		if parameter == 'update':
			if not message.bot.isUserAdmin(message.user, message.userNickname, message.userAddress):
				replytext = "Only my admin(s) can force an update, sorry!"
			elif self.scheduledFunctionIsExecuting:
				replytext = "I was updating already! Lucky you, now it'll be done quicker"
			else:
				self.checkForNewTweets()
				self.resetScheduledFunctionGreenlet()
				replytext = "Finished forced TwitterWatcher update check"
			message.reply(replytext, 'say')
			return

		#All the other parameters need an account name, so check for that now
		if message.messagePartsLength == 1:
			message.reply("Please add a Twitter account name too, so I know where to look", 'say')
			return

		accountName = message.messageParts[1]
		accountNameLowered = accountName.lower()
		isUserBeingWatchedHere = accountNameLowered in self.watchData and serverChannelPair in self.watchData[accountNameLowered]['targets']

		if parameter == 'add':
			if isUserBeingWatchedHere:
				replytext = "I'm already keeping a close eye on {}. On their tweets, I mean".format(self.getDisplayName(accountNameLowered, accountName))
			else:
				#New account
				if accountNameLowered not in self.watchData:
					self.watchData[accountNameLowered] = {'targets': [serverChannelPair]}
				#Existing account
				else:
					self.watchData[accountNameLowered]['targets'].append(serverChannelPair)
				#If a display name was provided, add that too
				if message.messagePartsLength > 2:
					self.watchData[accountNameLowered]['displayname'] = " ".join(message.messageParts[2:])
				elif accountName != accountNameLowered:
					self.watchData[accountNameLowered]['displayname'] = accountName
				#Save the whole thing
				self.saveWatchData()
				self.checkForNewTweets([accountNameLowered], False)
				replytext = "Ok, I'll keep you informed about any new tweets {}... makes? Tweets? What's the verb here?".format(self.getDisplayName(accountNameLowered))
		elif parameter == 'remove':
			if not isUserBeingWatchedHere:
				replytext = "I already wasn't watching {}! Not even secretly".format(accountName)
			else:
				self.watchData[accountNameLowered]['targets'].remove(serverChannelPair)
				#If this channel was the only place we were reporting this user's tweets to, remove it all together
				if len(self.watchData[accountNameLowered]['targets']) == 0:
					del self.watchData[accountNameLowered]
				self.saveWatchData()
				replytext = "Ok, I won't keep you updated on whatever {} posts. Tweets. Messages? I don't know the proper verb".format(accountName)
		elif parameter == 'latest':
			#Download the latest tweet for the provided username
			try:
				tweets = self.downloadTweets(accountNameLowered, 1)
			except WebRequestException as wre:
				self.logError("[TwitterWatcher] Error occured while downloading single tweet for user {}: {}".format(accountName, wre))
				replytext = "Woops, something went wrong there. Tell my owner(s), maybe it's something they can fix. Or maybe it's Twitter's fault, in which case all we can do is wait"
			else:
				if not tweets:
					replytext = "Sorry, I couldn't find any tweets by {}. Maybe they haven't tweeted yet, or maybe you made a typo?".format(accountName)
				else:
					replytext = self.formatNewTweetText(accountName, tweets[0], addTweetAge=True)
		elif parameter == 'setname':
			#Allow users to set a display name
			if not isUserBeingWatchedHere:
				replytext = "I'm not watching {}, so I can't change the display name. Add them with the 'add' parameter first".format(accountName)
			elif message.messagePartsLength < 2:
				replytext = "Please add a display name for '{}' too. You don't want me thinking up nicknames for people".format(accountName)
			else:
				self.watchData[accountNameLowered]['displayname'] = " ".join(message.messageParts[2:])
				self.saveWatchData()
				replytext = "Ok, I will call {} '{}' from now on".format(accountName, self.watchData[accountNameLowered]['displayname'])
		elif parameter == 'removename':
			if not isUserBeingWatchedHere:
				replytext = "I wasn't calling them anything anyway, since I'm not following {}".format(accountName)
			elif 'displayname' not in self.watchData[accountNameLowered]:
				replytext = "I didn't have a nickname listed for {} anyway, so I guess I did what you asked?".format(accountNameLowered)
			else:
				del self.watchData[accountNameLowered]['displayname']
				self.saveWatchData()
				replytext = "Ok, I will just call them by their account name, {}".format(accountName)
		else:
			replytext = "I don't know what to do with the parameter '{}', sorry. Try rereading the help text?".format(parameter)

		message.reply(replytext, 'say')

	def updateTwitterToken(self):
		apikeys = GlobalStore.commandhandler.apikeys
		if 'twitter' not in apikeys or 'key' not in apikeys['twitter'] or 'secret' not in apikeys['twitter']:
			self.logError("[TwitterWatcher] No Twitter API key and/or secret found!")
			return False

		credentials = base64.b64encode("{}:{}".format(apikeys['twitter']['key'], apikeys['twitter']['secret']))
		headers = {"Authorization": "Basic {}".format(credentials), "Content-Type": "application/x-www-form-urlencoded;charset=UTF-8"}
		data = "grant_type=client_credentials"

		req = requests.post("https://api.twitter.com/oauth2/token", data=data, headers=headers)
		reply = json.loads(req.text)
		if 'access_token' not in reply:
			self.logError("[TwitterWatcher] An error occurred while retrieving Twitter token: " + json.dumps(reply))
			return False

		if 'twitter' not in apikeys:
			apikeys['twitter'] = {}
		apikeys['twitter']['token'] = reply['access_token']
		apikeys['twitter']['tokentype'] = reply['token_type']

		GlobalStore.commandhandler.saveApiKeys()
		return True

	def downloadTweets(self, username, maxTweetCount=200, downloadNewerThanId=None, downloadOlderThanId=None, includeReplies=False, includeRetweets=False):
		# First check if we can even connect to the Twitter API
		if 'twitter' not in GlobalStore.commandhandler.apikeys or \
				'token' not in GlobalStore.commandhandler.apikeys['twitter'] or \
				'tokentype' not in GlobalStore.commandhandler.apikeys['twitter']:
			self.logInfo("[TwitterWatcher] No twitter token found, retrieving a new one")
			tokenUpdateSuccess = self.updateTwitterToken()
			if not tokenUpdateSuccess:
				self.logError("Unable to retrieve a new Twitter token!")
				raise WebRequestException("Unable to retrieve Twitter authentication token!")

		# Now download tweets!
		headers = {'Authorization': "{} {}".format(GlobalStore.commandhandler.apikeys['twitter']['tokentype'], GlobalStore.commandhandler.apikeys['twitter']['token'])}
		params = {'screen_name': username, 'count': min(200, maxTweetCount), 'trim_user': 'true', 'tweet_mode': 'extended',
				  'exclude_replies': 'false' if includeReplies else 'true',
				  'include_rts': True}  # Always get retweets, remove them later if necessary. Needed because 'count' always includes retweets, even if you don't want them
		if downloadOlderThanId:
			params['max_id'] = downloadOlderThanId

		tweets = []
		if downloadNewerThanId:
			params['since_id'] = downloadNewerThanId
		req = None
		while len(tweets) < maxTweetCount:
			params['count'] = maxTweetCount - len(tweets)  # Get as many tweets as we still need
			try:
				req = requests.get("https://api.twitter.com/1.1/statuses/user_timeline.json", headers=headers, params=params, timeout=20.0)
				apireply = json.loads(req.text)
			except requests.exceptions.Timeout:
				self.logError("[TwitterWatcher] Twitter API reply took too long to arrive")
				raise WebRequestException("Twitter took too long to respond")
			except ValueError:
				self.logError(u"[TwitterWatcher] Didn't get parsable JSON return from Twitter API: {}".format(req.text.replace('\n', '|') if req else "[no response retrieved]"))
				raise WebRequestException("Twitter API returned unexpected data")
			except Exception as e:
				self.logError("[TwitterWatcher] Tweet download threw an unexpected error of type '{}': {}".format(type(e), str(e)))
				raise WebRequestException("Unknown error occurred while retrieving Twitter API data")

			if len(apireply) == 0:
				# No more tweets to parse!
				break
			# Check for errors
			if isinstance(apireply, dict) and 'errors' in apireply:
				errorMessages = '; '.join(e['message'] for e in apireply['errors'])
				self.logError("[TwitterWatcher] Error occurred while retrieving tweets for {}. Parameters: {}; apireply: {}; errors: {}".format(username, params, apireply, errorMessages))
				raise WebRequestException("The Twitter API reply contained errors")
			# Sometimes the API does not return a list of tweets for some reason. Catch that
			if not isinstance(apireply, list):
				self.logError("[TwitterWatcher] Unexpected reply from Twitter API. Expected tweet list, got {}: {}".format(type(apireply), apireply))
				raise WebRequestException("The Twitter API reply contained unexpected data")
			# Tweets are sorted reverse-chronologically, so we can get the highest ID from the first tweet
			params['since_id'] = apireply[0]['id']
			# Remove retweets if necessary (done manually to make the 'count' variable be accurate)
			if not includeRetweets:
				apireply = [t for t in apireply if 'retweeted_status' not in t]
			# There are tweets, store those
			tweets.extend(apireply)
		return tweets

	def checkForNewTweets(self, usernamesToCheck=None, reportNewTweets=True):
		if not usernamesToCheck:
			usernamesToCheck = self.watchData  #Don't use '.keys()' so we don't copy the username list
		if not usernamesToCheck:
			return

		now = datetime.datetime.utcnow()
		watchDataChanged = False
		tweetAgeCutoff = self.scheduledFunctionTime * 1.1  #Give tweet age a little grace period, so tweets can't fall between checks
		#Retrieve the latest tweets for every account.
		for username in usernamesToCheck:
			if username not in self.watchData:
				self.logWarning("[TwitterWatcher] Asked to check account '{}' for new tweets, but it is not in the watchlist".format(username))
				continue
			try:
				tweets = self.downloadTweets(username, maxTweetCount=10, downloadNewerThanId=self.watchData[username].get('highestId', None), includeRetweets=False)
			except WebRequestException as wre:
				self.logError("[TwitterWatcher] Couldn't retrieve tweets for '{}': {}".format(username, wre))
				continue
			#If there aren't any new tweets, move on
			if len(tweets) == 0:
				continue
			#Always store the highest ID, so we don't encounter the same tweet twice
			watchDataChanged = True
			self.watchData[username]['highestId'] = tweets[0]['id']
			#If we don't have to actually report the tweets, then we have nothing left to do
			if not reportNewTweets:
				continue

			#Go through the tweets to check if they're not too old to report
			firstOldTweetIndex = -1
			for index, tweet in enumerate(tweets):
				if self.getTweetAge(tweet['created_at'], now).total_seconds() > tweetAgeCutoff:
					firstOldTweetIndex = index
					break
			#If all tweets are old, stop here
			if firstOldTweetIndex == 0:
				continue
			#Otherwise remove the old tweet and every older tweet
			elif firstOldTweetIndex > -1:
				tweets = tweets[:firstOldTweetIndex]

			#To prevent spam, only mention the latest few tweets, in case of somebody posting a LOT in a short timespan
			if len(tweets) > self.MAX_TWEETS_TO_MENTION:
				tweetsSkipped = len(tweets) - self.MAX_TWEETS_TO_MENTION
				tweets = tweets[-self.MAX_TWEETS_TO_MENTION:]
			else:
				tweetsSkipped = 0

			#Reverse the tweets so we get them old to new, instead of new to old
			tweets.reverse()
			#New recent tweets! Shout about it (if we're in the place where we should shout)
			for target in self.watchData[username]['targets']:
				#'target' is a tuple with the server name at [0] and the channel name at [1]
				#Just ignore it if we're either not on the server or not in the channel
				if target[0] not in GlobalStore.bothandler.bots:
					continue
				targetbot = GlobalStore.bothandler.bots[target[0]]
				if target[1] not in targetbot.channelsUserList:
					continue
				targetchannel = target[1].encode('utf-8')  #Make sure it's not a unicode object
				#Now go tell that channel all about the tweets
				for tweet in tweets:
					tweetAge = self.getTweetAge(tweet['created_at'], now)
					targetbot.sendMessage(targetchannel, self.formatNewTweetText(username, tweet, tweetAge), 'say')
				#If we skipped a few tweets, make a mention of that too
				if tweetsSkipped > 0:
					targetbot.sendMessage(targetchannel, "(skipped {:,} of {}'s tweets)".format(tweetsSkipped, self.getDisplayName(username)))
		if watchDataChanged:
			self.saveWatchData()

	def formatNewTweetText(self, username, tweetData, tweetAge=None, addTweetAge=False):
		if addTweetAge:
			if not tweetAge:
				tweetAge = self.getTweetAge(tweetData['created_at'])
			tweetAge = DateTimeUtil.durationSecondsToText(tweetAge.total_seconds(), precision='m')
			tweetAge = ' ({} ago)'.format(tweetAge)
		else:
			tweetAge = ''
		tweetUrl = "https://twitter.com/_/status/{}".format(tweetData['id_str'])  #Use _ instead of username to save some characters
		#Remove newlines
		formattedTweetText = re.sub('\s*\n+\s*', ' | ', tweetData['full_text'])
		#Fix special characters (convert '&amp;' to '&' for instance)
		formattedTweetText = HTMLParser.HTMLParser().unescape(formattedTweetText)
		#Remove the link to the photo at the end, but mention that there is one
		if 'media' in tweetData['entities']:
			for mediaItem in tweetData['entities']['media']:
				formattedTweetText = formattedTweetText.replace(mediaItem['url'], u'')
				formattedTweetText += u"(has {})".format(mediaItem['type'])
		#Add in all the text around the tweet now, so we get a better sense of message length
		formattedTweetText = u"{name}: {text}{age}{sep}{url}".format(name=IrcFormattingUtil.makeTextBold(self.getDisplayName(username)), text=formattedTweetText,
																	 age=tweetAge, sep=Constants.GREY_SEPARATOR, url=tweetUrl)
		#Expand URLs (if it'd fit)
		if 'urls' in tweetData['entities']:
			for urldata in tweetData['entities']['urls']:
				if len(formattedTweetText) - len(urldata['url']) + len(urldata['expanded_url']) < 325:
					formattedTweetText = formattedTweetText.replace(urldata['url'], urldata['expanded_url'])
		return formattedTweetText

	def getTweetDescription(self, twitterUsername, tweetId):
		"""
		Get a display string describing the tweet from the provided ID
		:param tweetId: The tweet ID to get a description of
		:return: A display string for the tweet, or None if the tweet couldn't be retrieved
		"""
		if not isinstance(tweetId, int):
			tweetId = int(tweetId, 10)
		tweetList = self.downloadTweets(username=twitterUsername, downloadNewerThanId=tweetId-1, downloadOlderThanId=tweetId+1, maxTweetCount=1)
		if not tweetList:
			return None
		return self.formatNewTweetText(twitterUsername, tweetList[0], addTweetAge=True)

	@staticmethod
	def getTweetAge(createdAt, presentTimeToUse=None):
		if not presentTimeToUse:
			presentTimeToUse = datetime.datetime.utcnow()
		return presentTimeToUse - datetime.datetime.strptime(createdAt, "%a %b %d %H:%M:%S +0000 %Y")

	def getDisplayName(self, username, alternativeName=None):
		if username not in self.watchData:
			return username
		return self.watchData[username].get('displayname', alternativeName if alternativeName else username)

	def saveWatchData(self):
		watchDataFilePath = os.path.join(GlobalStore.scriptfolder, 'data', 'WatchedTwitterAccounts.json')
		with open(watchDataFilePath, 'w') as watchDataFile:
			watchDataFile.write(json.dumps(self.watchData))
