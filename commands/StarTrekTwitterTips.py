import os, random, re, time

from CommandTemplate import CommandTemplate
import GlobalStore
import SharedFunctions
from IrcMessage import IrcMessage


class Command(CommandTemplate):
	triggers = ['startrektip', 'startrektips', 'sttip', 'sttips']
	helptext = "Shows a randomly chosen tip from one of the Star Trek Tips accounts, or of a specific one if a name is provided. Add a regex search after the name to search for a specific tip"
	twitterUsernames = {'data': 'Data_Tips', 'guinan': 'GuinanTips', 'laforge': 'LaForgeTips', 'locutus': 'LocutusTips',
						'picard': 'PicardTips', 'quark': 'QuarkTips', 'riker': 'RikerTips', 'rikergoogling': 'RikerGoogling','worf': 'WorfTips'}
	scheduledFunctionTime = 21600.0  #Six hours in seconds

	isUpdating = False

	def execute(self, message):
		"""
		:type message: IrcMessage
		"""

		if self.isUpdating:
			message.bot.sendMessage(message.source, "Sorry, but I'm updating my data (hah) at the moment. Try again in a bit!")
			return

		name = ""
		if message.messagePartsLength > 0:
			name = message.messageParts[0].lower()
		if name == 'update':
			self.executeScheduledFunction()
			self.scheduledFunctionTimer.reset()
			message.bot.sendMessage(message.source, "Ok, I'll update my list of Star Trek Tips. But since they have to come from the future, it might take a while. Try again in, oh, half a minute or so, just to be sure")
			return
		if name == 'random':
			name = random.choice(self.twitterUsernames.keys())

		replytext = ""
		if not name in self.twitterUsernames:
			if name != "":
				replytext = "I don't know anybody by the name of '{}', sorry. ".format(message.messageParts[0])
			replytext += "Type '{}{} <name>' to hear one of <name>'s tips, or use 'random' to have me pick a name for you. ".format(message.bot.factory.commandPrefix, message.trigger)
			replytext += "Available tip-givers: {}".format(", ".join(sorted(self.twitterUsernames.keys())))
		else:
			tweets = SharedFunctions.getAllLinesFromFile(os.path.join(GlobalStore.scriptfolder, 'data', 'tweets-{}.txt'.format(self.twitterUsernames[name])))
			if message.messagePartsLength > 1:
				#Search terms provided! Go through all the tweets to find matches
				try:
					regex = re.compile(" ".join(message.messageParts[1:]), re.IGNORECASE)
				except (re.error, SyntaxError):
					message.bot.sendMessage(message.source, "That is an invalid regular expression, sorry. Please check for typos, and try again", 'say')
					return
				for i in xrange(0, len(tweets)):
					#Take a tweet from the start, and only put it back at the end if it matches the regex
					tweet = tweets.pop(0)
					if regex.search(tweet):
						tweets.append(tweet)
			tweetCount = len(tweets)
			if tweetCount == 0:
				replytext = u"Sorry, no tweets matching your search were found"
			else:
				replytext = random.choice(tweets).strip()
				if not replytext.lower().startswith(name):
					replytext = u"{} tip: {}".format(name[0:1].upper() + name[1:], replytext)
				#Only add a tweet count if a search term was provided and there's more than one
				if message.messagePartsLength > 1 and tweetCount > 1:
					replytext += u" [{} more tweets]".format(tweetCount-1)

		replytext = replytext.encode('utf-8', 'replace')
		message.bot.say(message.source, replytext)


	def executeScheduledFunction(self):
		GlobalStore.reactor.callInThread(self.updateTwitterMessages)

	def updateTwitterMessages(self):
		starttime = time.time()
		self.isUpdating = True
		for name, username in self.twitterUsernames.iteritems():
			SharedFunctions.downloadNewTweets(username)
		self.isUpdating = False
		print "[STtip] Updating tweets took {} seconds".format(time.time() - starttime)
		return True
