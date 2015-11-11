import os, random, re, time

from CommandTemplate import CommandTemplate
import GlobalStore
import SharedFunctions
from IrcMessage import IrcMessage


class Command(CommandTemplate):
	triggers = ['startrektip', 'startrektips', 'sttip', 'sttips']
	helptext = "Shows a randomly chosen tip from one of the Star Trek Tips accounts, or of a specific one if a name is provided. Add a regex search after the name to search for a specific tip"
	scheduledFunctionTime = 21600.0  #Six hours in seconds

	twitterUsernames = {'data': 'Data_Tips', 'guinan': 'GuinanTips', 'laforge': 'LaForgeTips', 'locutus': 'LocutusTips', 'picard': 'PicardTips',
						'quark': 'QuarkTips', 'riker': 'RikerTips', 'rikergoogling': 'RikerGoogling','worf': 'WorfTips', 'worfemail': 'WorfEmail'}
	# Not all 'tips' are actually tips. This is a list of a replacement term to use if 'tip' is not accurate. It replaces the entire part before the colon
	resultPrefix = {'rikergoogling': "Riker searched", 'worfemail': "Worf's Outbox"}
	isUpdating = False

	def executeScheduledFunction(self):
		GlobalStore.reactor.callInThread(self.updateTwitterMessages)

	def execute(self, message):
		"""
		:type message: IrcMessage
		"""

		if self.isUpdating:
			message.bot.sendMessage(message.source, "Sorry, but I'm updating my data (hah) at the moment. Try again in a bit!")
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
		message.bot.say(message.source, self.getTip(name, searchterm))

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
		for name, username in self.twitterUsernames.iteritems():
			SharedFunctions.downloadNewTweets(username)
		self.isUpdating = False
		self.logInfo("[STtip] Updating tweets took {} seconds".format(time.time() - starttime))
		return True
