import datetime, json, os
import HTMLParser

from CommandTemplate import CommandTemplate
import Constants
import GlobalStore
from util import DateTimeUtil
from util import IrcFormattingUtil
from util import TwitterUtil
from IrcMessage import IrcMessage


class Command(CommandTemplate):
	triggers = ['twitterwatcher']
	helptext = "Automatically says new tweets of watched accounts. Use parameter 'add' to add an account to watch and 'remove' to stop watching an account. 'latest' shows latest tweet. " \
			   "Use 'setname' and 'removename' to set and remove a display name. These parameters need to be followed by a Twitter name. 'list' lists all accounts being watched"
	scheduledFunctionTime = 300.0  #Check every 5 minutes
	runInThread = True

	watchData = {}  #keys are Twitter usernames, contains fields with highest ID and which channel(s) to report new tweets to, and a display name if specified
	MAX_TWEETS_TO_MENTION = 2

	def onLoad(self):
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

		#Start with 'list' because that doesn't need an account name
		if parameter == 'list':
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
			#Download a specific tweet
			if not isUserBeingWatchedHere:
				replytext = "I'm not watching {}, so I don't know what they've been up to. On Twitter or anywhere else".format(accountName)
			else:
				singleTweet = TwitterUtil.downloadTweet(accountNameLowered, self.watchData[accountNameLowered]['highestId'])
				if not singleTweet[0]:
					self.logError("[TwitterWatcher] Error occured while downloading single tweet id {} of user {}: {}".format(accountName, self.watchData[accountNameLowered]['highestId'], singleTweet[1]))
					replytext = "Woops, something went wrong there. Tell my owner(s), maybe it's something they can fix. Or maybe it's Twitter's fault, in which case all we can do is wait"
				else:
					replytext = self.formatNewTweetText(accountName, singleTweet[1], addTweetAge=True).replace(u'New', u'Latest', 1)
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


	def checkForNewTweets(self, usernamesToCheck=None, reportNewTweets=True):
		if not usernamesToCheck:
			usernamesToCheck = self.watchData  #Don't use '.keys()' so we don't copy the username list
		now = datetime.datetime.utcnow()
		watchDataChanged = False
		tweetAgeCutoff = self.scheduledFunctionTime * 1.1  #Give tweet age a little grace period, so tweets can't fall between checks
		#Retrieve the latest tweets for every account.
		for username in usernamesToCheck:
			if username not in self.watchData:
				self.logWarning("[TwitterWatcher] Asked to check account '{}' for new tweets, but it is not in the watchlist".format(username))
				continue
			tweetsReply = TwitterUtil.downloadTweets(username, maxTweetCount=10, downloadNewerThanId=self.watchData[username].get('highestId', None), includeRetweets=False)
			if not tweetsReply[0]:
				self.logError("[TwitterWatcher] Couldn't retrieve tweets for '{}': {}".format(username, tweetsReply[1]))
				continue
			#If there aren't any new tweets, move on
			if len(tweetsReply[1]) == 0:
				continue

			tweets = tweetsReply[1]
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
				tweets = tweets[:self.MAX_TWEETS_TO_MENTION]
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
			tweetAge = DateTimeUtil.durationSecondsToText(tweetAge.total_seconds())
			tweetAge = ' ({} ago)'.format(tweetAge)
		else:
			tweetAge = ''
		tweetUrl = "http://twitter.com/_/status/{}".format(tweetData['id_str'])  #Use _ instead of username to save some characters
		#Remove newlines
		formattedTweetText = tweetData['full_text'].replace('\n\n', '\n').replace('\n', Constants.GREY_SEPARATOR)
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

	@staticmethod
	def getTweetAge(createdAt, presentTimeToUse=None):
		if not presentTimeToUse:
			presentTimeToUse = datetime.datetime.utcnow()
		return presentTimeToUse - datetime.datetime.strptime(createdAt, "%a %b %d %H:%M:%S +0000 %Y")

	def getDisplayName(self, username, alternativeName=None):
		if not alternativeName:
			alternativeName = username
		if username not in self.watchData:
			self.logDebug("[TwitterWatcher] Asked to look up display name for '{}', but there's no data stored for that name".format(username))
			return ''
		return self.watchData[username].get('displayname', alternativeName)

	def saveWatchData(self):
		watchDataFilePath = os.path.join(GlobalStore.scriptfolder, 'data', 'WatchedTwitterAccounts.json')
		with open(watchDataFilePath, 'w') as watchDataFile:
			watchDataFile.write(json.dumps(self.watchData))
