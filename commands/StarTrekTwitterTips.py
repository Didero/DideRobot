import json, os, random, re, time

from CommandTemplate import CommandTemplate
import GlobalStore
import SharedFunctions
from IrcMessage import IrcMessage


class Command(CommandTemplate):
	triggers = ['startrektip', 'startrektips', 'sttip', 'sttips']
	helptext = "Shows a tip from the provided Star Trek character, or a random one. Add a (regex) search after the name to search for a specific tip"
	scheduledFunctionTime = 21600.0  #Six hours in seconds

	twitterUsernames = {'data': 'Data_Tips', 'guinan': 'GuinanTips', 'laforge': 'LaForgeTips', 'locutus': 'LocutusTips', 'picard': 'PicardTips',
						'quark': 'QuarkTips', 'riker': 'RikerTips', 'rikergoogling': 'RikerGoogling','worf': 'WorfTips', 'worfemail': 'WorfEmail'}
	# Not all 'tips' are actually tips. This is a list of a replacement term to use if 'tip' is not accurate. It replaces the entire part before the colon
	resultPrefix = {'rikergoogling': "Riker searched", 'worfemail': "Worf's Outbox"}
	isUpdating = False

	def onLoad(self):
		#Add the available names to the helptext
		self.helptext += ". Available names are: " + ", ".join(sorted(self.twitterUsernames.keys()))

	def executeScheduledFunction(self):
		GlobalStore.reactor.callInThread(self.updateTwitterMessages)

	def execute(self, message):
		"""
		:type message: IrcMessage
		"""

		if self.isUpdating:
			message.reply("Sorry, but I'm updating my data (hah) at the moment. Try again in a bit!", "say")
			return

		name = "random"
		if message.messagePartsLength > 0:
			name = message.messageParts[0].lower()
		if name == 'update':
			self.executeScheduledFunction()
			self.scheduledFunctionTimer.reset()
			message.bot.sendMessage(message.source, "Ok, I'll update my list of Star Trek Tips. But since they have to come from the future, it might take a while. Try again in, oh, half a minute or so, just to be sure")
			return
		searchterm = None if message.messagePartsLength <= 1 else " ".join(message.messageParts[1:])
		message.reply(self.getTip(name, searchterm), "say")

	def getTweets(self, name='random', searchterm=None):
		name = name.lower()
		if name == 'random':
			name = random.choice(self.twitterUsernames.keys())
		if name not in self.twitterUsernames:
			return (False, "I don't know anybody by the name of '{}', sorry. ".format(name))
		tweetFileName = os.path.join(GlobalStore.scriptfolder, 'data', 'tweets', '{}.txt'.format(self.twitterUsernames[name]))
		if not os.path.exists(tweetFileName):
			self.executeScheduledFunction()
			return (False, "I don't seem to have the tweets for '{}', sorry! I'll retrieve them right away, try again in a bit".format(name))
		tweets = SharedFunctions.getAllLinesFromFile(tweetFileName)
		if searchterm is not None:
			#Search terms provided! Go through all the tweets to find matches
			regex = None
			try:
				regex = re.compile(searchterm, re.IGNORECASE)
			except (re.error, SyntaxError):
				self.logWarning("[STtip] '{}' is an invalid regular expression. Using it literally".format(searchterm))
			for i in xrange(0, len(tweets)):
				#Take a tweet from the start, and only put it back at the end if it matches the regex
				tweet = tweets.pop(0)
				if regex and regex.search(tweet) or searchterm in tweet:
					tweets.append(tweet)
		if len(tweets) == 0:
			return (False, "Sorry, no tweets matching your search were found")
		else:
			return (True, tweets)

	def getTip(self, name='random', searchterm=None):
		name = name.lower()
		if name == 'random':
			name = random.choice(self.twitterUsernames.keys())
		getTweetsReply = self.getTweets(name, searchterm)
		if not getTweetsReply[0]:
			return getTweetsReply[1]
		else:
			tweets = getTweetsReply[1]
			tweetCount = len(tweets)
			replytext = random.choice(tweets).strip()
			#Always make sure the result starts with "[name] tip: "
			if not replytext.lower().startswith(name):
				#Get the special prefix, if any. Otherwise, just do the default "[name] tip: "
				tipPrefix = self.resultPrefix.get(name, u"{} tip".format(name.capitalize()))
				replytext = u"{}: {}".format(tipPrefix, replytext)
			#Only add a tweet count if a search term was provided and there's more than one
			if searchterm is not None and tweetCount > 1:
				replytext += u" [{:,} more matching tweet{}]".format(tweetCount - 1, u's' if tweetCount > 2 else u'')
			replytext = replytext.encode('utf-8', 'replace')
			return replytext


	def updateTwitterMessages(self):
		starttime = time.time()
		self.isUpdating = True
		#First load all the stored tweet data, if it exists
		twitterInfoFilename = os.path.join(GlobalStore.scriptfolder, 'data', 'tweets', 'metadata.json')
		if os.path.exists(twitterInfoFilename):
			with open(twitterInfoFilename, 'r') as twitterInfoFile:
				storedInfo = json.load(twitterInfoFile)
		else:
			storedInfo = {}
			#Create the 'tweets' folder if it doesn't exist already, so we can create our files in there once we're done
			if not os.path.exists(os.path.dirname(twitterInfoFilename)):
				os.makedirs(os.path.dirname(twitterInfoFilename))
		#Go through all the names we need to update
		for name, username in self.twitterUsernames.iteritems():
			highestIdDownloaded = 0
			if username not in storedInfo:
				storedInfo[username] = {'linecount': 0}
			elif "highestIdDownloaded" in storedInfo[username]:
				highestIdDownloaded = storedInfo[username]['highestIdDownloaded']
			tweetResponse = SharedFunctions.downloadTweets(username, downloadNewerThanId=highestIdDownloaded)
			if not tweetResponse[0]:
				self.logError("[STTip] Something went wrong while downloading new tweets for '{}', skipping".format(username))
				continue
			#If there aren't any tweets, stop here
			if len(tweetResponse[1]) == 0:
				continue
			tweets = tweetResponse[1]
			#Reverse tweets so they're from old to new. That way when we write them to file, the entire file will be old to new
			# Not necessary but neat
			tweets.reverse()
			#All tweets downloaded. Time to process them
			tweetfile = open(os.path.join(GlobalStore.scriptfolder, 'data', 'tweets', "{}.txt".format(username)), "a")
			for tweet in tweets:
				tweetfile.write(tweet['text'].replace('\n', ' ').encode(encoding='utf-8', errors='replace') + '\n')
			tweetfile.close()
			#Get the id of the last tweet in the list (the newest one), so we know where to start downloading from next time
			storedInfo[username]['highestIdDownloaded'] = tweets[-1]['id']
			storedInfo[username]['linecount'] += len(tweets)

		#Save the stored info to disk too, for future lookups
		with open(twitterInfoFilename, 'w') as twitterFile:
			twitterFile.write(json.dumps(storedInfo))

		self.isUpdating = False
		self.logInfo("[STtip] Updating tweets took {} seconds".format(time.time() - starttime))
		return True
