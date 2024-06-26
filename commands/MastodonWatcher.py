import datetime, json, os, re

import requests
from bs4 import BeautifulSoup

from commands.CommandTemplate import CommandTemplate
import Constants
import GlobalStore
import PermissionLevel
from util import DateTimeUtil, IrcFormattingUtil
from IrcMessage import IrcMessage
from CustomExceptions import CommandException, CommandInputException
from StringWithSuffix import StringWithSuffix


class Command(CommandTemplate):
	triggers = ['mastodonwatcher', 'mastodonwatch']
	helptext = "Automatically reports when watched accounts post new messages. Use parameter 'add' to add an account to watch and 'remove' to stop watching an account. 'latest' shows latest message (optionally with a search query). " \
			   "Use 'setname' and 'removename' to set and remove a display name. These parameters need to be followed by a full Mastodon username. 'list' lists all accounts being watched"
	scheduledFunctionTime = 300.0  #Check every 5 minutes
	runInThread = True

	watchDataFilePath = os.path.join(GlobalStore.scriptfolder, 'data', 'MastodonWatcherData.json')
	watchData = {}  # keys are usernames, contains fields with highest ID of last message retrieved, which channel(s) to report new messages to, and a display name if specified
	MAX_MESSAGES_TO_MENTION = 3
	USERNAME_REGEX = re.compile("@?(?P<name>[^@]+)@(?P<server>.+)")
	SECONDS_AGE_FOR_FULL_DATE = 604800  # After 7 days, don't list a tweet as '6 days, 7 hours ago', but as the full date
	LATEST_MESSAGES_SEARCH_COUNT = 5  # With 'last' and a search query, how many messages to retrieve to search through

	def onLoad(self):
		GlobalStore.commandhandler.addCommandFunction(__file__, 'getMastodonMessageDescription', self.getMessageDescription)

		# Retrieve which accounts we should follow, if that file exists
		if os.path.exists(self.watchDataFilePath):
			with open(self.watchDataFilePath, 'r', encoding='utf-8') as watchDataFile:
				self.watchData = json.load(watchDataFile)

	def executeScheduledFunction(self):
		self.reportNewMessages()

	def execute(self, message):
		"""
		:type message: IrcMessage
		"""
		if message.messagePartsLength == 0:
			message.reply(self.helptext)
			return

		parameter = message.messageParts[0].lower()
		serverChannelPair = [message.bot.serverfolder, message.source]  # List not tuple, because JSON can't save tuples and converts them to a list

		#Start with the commands that don't need a username parameter
		if parameter == 'help':
			message.reply(self.helptext)
			return
		if parameter == 'list':
			#List all the users we're watching for this channel
			watchlist = []
			for username, usernameData in self.watchData.items():
				if serverChannelPair in usernameData['targets']:
					watchlist.append(username)
			watchlistLength = len(watchlist)
			if watchlistLength == 0:
				reply = "I'm not watching any Mastodon users for this channel. You could make me watch somebody with the 'add' subcommand, if you want"
			elif watchlistLength == 1:
				reply = "I only watch for the messages of {} at the moment".format(watchlist[0])
			else:
				watchlist.sort()
				reply = "I watch {:,} Mastodon users: {}".format(watchlistLength, "; ".join(watchlist))
			message.reply(reply)
			return
		# 'update' forces an update check, but it's only available to admins. Also doesn't need a username
		if parameter == 'update':
			if not message.doesSenderHavePermission(PermissionLevel.BOT):
				reply = "Only my admin(s) can force an update, sorry!"
			elif self.scheduledFunctionIsExecuting:
				reply = "I was updating already! Lucky you, now it'll be done quicker"
			else:
				self.resetScheduledFunctionGreenlet()
				self.reportNewMessages()
				reply = "Finished forced update check"
			message.reply(reply)
			return

		# All the other parameters need an account name, so check for that now
		if message.messagePartsLength == 1:
			raise CommandInputException("Please add a Mastodon username too, so I know where to look")

		providedName = message.messageParts[1]
		storedUsername = providedName.lower()
		# Mastodon accountnames are '@username@server'. For ease of use, allow the @ at the start to be omitted, and add it back here
		if '@' in storedUsername and not storedUsername.startswith('@'):
			storedUsername = '@' + storedUsername
		isUserBeingWatchedHere = storedUsername in self.watchData and serverChannelPair in self.watchData[storedUsername]['targets']
		# Also allow referring to accounts by their displayname
		if not isUserBeingWatchedHere:
			usernameFromDisplayname = self.findUsernameFromDisplayname(providedName, serverChannelPair)
			if usernameFromDisplayname:
				storedUsername = usernameFromDisplayname
				isUserBeingWatchedHere = True

		if parameter == 'add':
			if isUserBeingWatchedHere:
				reply = "I'm already keeping a close eye on {}. On their messages, I mean".format(providedName)
			elif not message.doesSenderHavePermission(PermissionLevel.CHANNEL):
				raise CommandInputException("I'm sorry, only my channel admins are allowed to make me watch people's Mastodon messages")
			else:
				if storedUsername in self.watchData:
					# Existing account, all we need to do is add this channel to the target list
					self.watchData[storedUsername]['targets'].append(serverChannelPair)
				else:
					# New account, retrieve all the needed data and make a new watch entry
					userMatch = self.USERNAME_REGEX.match(providedName)
					if not userMatch:
						raise CommandInputException("'{}' is not a valid Mastodon username, please enter usernames in the form of '@username@server', so I know precisely where to look".format(providedName))
					userId = self.retrieveUserId(storedUsername)
					if not userId:
						raise CommandException("I'm sorry, I couldn't find the user '{}'. Maybe you made a typo? Make sure the username is formatted like '@username@server'".format(providedName), False)
					self.watchData[storedUsername] = {'userId': userId, 'targets': [serverChannelPair], 'server': userMatch.group('server'), 'displayname': userMatch.group('name')}
					# Retrieve the latest message, so we know from where we should start reporting messages as new
					latestMessage = self.retrieveMessagesForUser(providedName, userId, self.watchData[storedUsername]['server'], messageCount=1)
					if latestMessage:
						self.watchData[storedUsername]['highestMessageId'] = latestMessage[0]['id']
				# If a display name was provided, add that too
				if message.messagePartsLength > 2:
					self.watchData[storedUsername]['displayname'] = " ".join(message.messageParts[2:])
				# Save the whole thing
				self.saveWatchData()
				reply = "Ok, I'll keep you informed about any new messages {}... posts? Toots? What's the verb here?".format(self.getDisplayName(storedUsername))
		elif parameter == 'remove':
			if not isUserBeingWatchedHere:
				reply = "I already wasn't watching {}! That was easy".format(providedName)
			elif not message.doesSenderHavePermission(PermissionLevel.CHANNEL):
				raise CommandInputException("Sorry, only my channel admins are allowed to make me stop watching people's Mastodon messages")
			else:
				self.watchData[storedUsername]['targets'].remove(serverChannelPair)
				# If this channel was the only place we were reporting this user's messages to, remove it all together
				if len(self.watchData[storedUsername]['targets']) == 0:
					del self.watchData[storedUsername]
				self.saveWatchData()
				reply = "Ok, I won't keep you updated on whatever {} posts. Toots. Messages? I don't know the correct verb".format(providedName)
		elif parameter == 'latest' or parameter == 'last':
			# Download the latest message for the provided username
			if isUserBeingWatchedHere:
				userId = self.watchData[storedUsername]['userId']
				server = self.watchData[storedUsername]['server']
			else:
				# No user info stored, retrieve it
				userMatch = self.USERNAME_REGEX.match(providedName)
				if not userMatch:
					raise CommandInputException("'{}' is not a valid Mastodon username, please enter usernames in the form of '@username@server', so I know precisely where to look".format(providedName))
				userId = self.retrieveUserId(storedUsername)
				if not userId:
					raise CommandException("I'm sorry, I couldn't find the user '{}'. Maybe you made a typo? Make sure the username is formatted like '@username@server'".format(providedName), False)
				server = userMatch.group('server')
			searchQuery = None
			if message.messagePartsLength > 2:
				# A search query was added, so we need to retrieve more messages to see if we can find a match
				searchQuery = " ".join(message.messageParts[2:]).lower()
			try:
				latestMessages = self.retrieveMessagesForUser(providedName, userId, server, self.LATEST_MESSAGES_SEARCH_COUNT if searchQuery else 1)
			except Exception as e:
				reply = "Whoops, something went wrong there. Tell my owner(s), maybe it's something they can fix. Or maybe the Mastodon instance is having issues, in which case all we can do is wait"
			else:
				if not latestMessages:
					reply = "Seems like {} hasn't posted anything yet".format(providedName)
				elif searchQuery:
					# Search through the messages to find a message with the query
					matchingMessage = None
					for messageToCheck in latestMessages:
						messageTextParts = self.getMessageText(messageToCheck)
						for textPart in messageTextParts:
							if searchQuery in textPart.lower():
								matchingMessage = messageToCheck
								break
						if matchingMessage:
							break
					if not matchingMessage:
						userUrl = latestMessages[0]['url'].rsplit('/', 1)[0]
						reply = f"Hmm, '{searchQuery}' doesn't appear in {providedName}'s last {self.LATEST_MESSAGES_SEARCH_COUNT} messages, sorry. You could check their post history (histootry?) to check older messages: {userUrl}"
					else:
						reply = self.formatMessage(providedName, matchingMessage, addMessageAge=True)
				else:
					reply = self.formatMessage(providedName, latestMessages[0], addMessageAge=True)
		elif parameter == 'setname':
			# Allow users to set a display name
			if not isUserBeingWatchedHere:
				reply = "I'm not watching {}, so I can't change the display name. Add them with the 'add' parameter first".format(providedName)
			elif not message.doesSenderHavePermission(PermissionLevel.CHANNEL):
				raise CommandInputException("Only my channel admins are allowed to set a display name, sorry")
			elif message.messagePartsLength < 2:
				reply = "Please add a display name for '{}' too. You don't want me thinking up nicknames for people".format(providedName)
			else:
				self.watchData[storedUsername]['displayname'] = " ".join(message.messageParts[2:])
				self.saveWatchData()
				reply = "Ok, I will call {} '{}' from now on".format(providedName, self.watchData[storedUsername]['displayname'])
		elif parameter == 'removename':
			if not isUserBeingWatchedHere:
				reply = "I wasn't calling {} anything special anyway, since I'm not watching them".format(providedName)
			elif not message.doesSenderHavePermission(PermissionLevel.CHANNEL):
				raise CommandInputException("Only my channel admins are allowed to remove a display name, sorry")
			elif 'displayname' not in self.watchData[storedUsername]:
				reply = "I didn't have a display name listed for {} anyway, so I guess I did what you asked?".format(providedName)
			else:
				del self.watchData[storedUsername]['displayname']
				self.saveWatchData()
				reply = "Ok, I will just call {} by their account name from now on".format(storedUsername)
		else:
			reply = "I don't know what to do with the parameter '{}', sorry. Try (re)reading the help text?".format(parameter)

		message.replyWithLengthLimit(reply)

	def reportNewMessages(self, usernamesToCheck=None):
		if not usernamesToCheck:
			usernamesToCheck = self.watchData
		now = datetime.datetime.utcnow()
		watchDataChanged = False
		messageAgeCutoff = self.scheduledFunctionTime * 1.5  # Give message age a little grace period, so messages can't fall between checks
		# Retrieve the latest messages for every account.
		for username in usernamesToCheck:
			if username not in self.watchData:
				self.logWarning("[MastodonWatcher] Asked to check account '{}' for new messages, but it is not in the watchlist".format(username))
				continue
			messageList = self.retrieveNewMessagesForStoredUser(username, self.MAX_MESSAGES_TO_MENTION + 1)  # +1 so we can know if there are more than can be reported
			# If there aren't any new messages, or something went wrong, move on
			if not messageList:
				continue
			# Always store the highest message ID, so we don't encounter the same message twice
			watchDataChanged = True
			self.watchData[username]['highestMessageId'] = messageList[0]['id']
			# Go through the messages to check if they're not too old to report
			firstOldMessageIndex = -1
			for index, message in enumerate(messageList):
				if (now - self.getMessagePostTime(message['created_at'])).total_seconds() > messageAgeCutoff:
					firstOldMessageIndex = index
					break
			# If all message are old, stop here
			if firstOldMessageIndex == 0:
				continue
			# Otherwise remove all the messages older than our age cutoff
			elif firstOldMessageIndex > -1:
				messageList = messageList[:firstOldMessageIndex]

			# To prevent spam, only mention the latest few messages, in case of somebody posting a LOT in a short timespan
			numberOfMessagesSkipped = 0
			if len(messageList) > self.MAX_MESSAGES_TO_MENTION:
				numberOfMessagesSkipped = len(messageList) - self.MAX_MESSAGES_TO_MENTION
				messageList = messageList[-self.MAX_MESSAGES_TO_MENTION:]

			# Reverse the messages so we get them old to new, instead of new to old
			messageList.reverse()
			# Report the new messages where they should be reported
			for target in self.watchData[username]['targets']:
				# 'target' is a tuple with the server name at [0] and the channel name at [1]
				# Just ignore it if we're either not on the server or not in the channel
				if target[0] not in GlobalStore.bothandler.bots:
					continue
				targetbot = GlobalStore.bothandler.bots[target[0]]
				if target[1] not in targetbot.channelsUserList:
					continue
				targetchannel = target[1]
				# Now go tell that channel all about the new messages
				for messageData in messageList:
					formattedMessage  = self.formatMessage(username, messageData)
					targetbot.sendLengthLimitedMessage(targetchannel, formattedMessage.mainString, formattedMessage.suffix)
				# If we skipped a few message, make a mention of that too
				if numberOfMessagesSkipped > 0:
					targetbot.sendMessage(targetchannel, "(skipped at least {:,} of {}'s messages)".format(numberOfMessagesSkipped, self.getDisplayName(username)))
		if watchDataChanged:
			self.saveWatchData()

	def retrieveNewMessagesForStoredUser(self, username, messageCount):
		if username not in self.watchData:
			self.logWarning("[MastodonWatcher] Asked to retrieve messages of  '{}', but they are not stored in the watchdata".format(username))
			return None
		userdata = self.watchData[username]
		return self.retrieveMessagesForUser(username, userdata['userId'], userdata['server'], messageCount, userdata.get('highestMessageId', None))

	def retrieveMessagesForUser(self, username, userId, server, messageCount, messagesSinceId=None):
		requestParameters = {'limit': messageCount, 'exclude_replies': True, 'exclude_reblogs': True}
		if messagesSinceId:
			requestParameters['min_id'] = messagesSinceId
		response = requests.get("https://{server}/api/v1/accounts/{userId}/statuses".format(server=server, userId=userId), params=requestParameters)
		if response.status_code != 200:
			self.logError("Error while retrieving data for user {} from server {}, status code {}".format(username, server, response.status_code))
			return None
		responseData = response.json()
		if 'error' in responseData:
			self.logError("[MastodonWatcher] Error while retrieving messages for user '{}': {}".format(username, responseData['error']))
			return None
		return responseData

	def retrieveUserId(self, username):
		userMatch = self.USERNAME_REGEX.match(username)
		if not userMatch:
			raise ValueError("Invalid Mastodon username '{}' provided, it should be formatted as '@accountname@server'".format(username))
		name = userMatch.group('name')
		server = userMatch.group('server')
		try:
			response = requests.get("https://{server}/api/v1/accounts/lookup".format(server=server), params={'acct': name}, timeout=30)
		except Exception as e:
			self.logError("Request to server '{}' threw an {} error: {}".format(server, type(e).__name__, e))
			return None
		if response.status_code != 200:
			self.logError("[MastodonWatcher] Server '{}' returned error code {}".format(server, response.status_code))
			return None
		responseData = response.json()
		if 'error' in responseData:
			return None
		return responseData['id']

	def getMessageText(self, messageData):
		"""
		Get the message text from the provided message data, which should be a reply from a Mastodon API
		:param messageData: The message data
		:return: A list of lines, the text of the message
		"""
		# Mastodon messages are HTML, so remove all the tags and resolve all the special characters ('&amp;' to '&' for instance)
		parsedMessage = BeautifulSoup(re.sub(' *<br ?/?> *', Constants.GREY_SEPARATOR, messageData['content']), 'html.parser')
		# Mastodon organises newlines into <p> paragraphs, so iterate over those and get the text from them
		messageTextParts = []
		for paragraph in parsedMessage.find_all('p'):
			paragraphText = paragraph.get_text().strip()
			if paragraphText:
				messageTextParts.append(paragraphText)
		return messageTextParts

	def formatMessage(self, username, messageData, addMessageAge=False, addUrl=True):
		formattedMessageText = Constants.GREY_SEPARATOR.join(self.getMessageText(messageData))
		# Add the username
		formattedMessageText = "{}: {}".format(IrcFormattingUtil.makeTextBold(self.getDisplayName(username)), formattedMessageText)
		suffixes = []
		# If there's an attached image or video, mention that
		if len(messageData['media_attachments']) > 0:
			suffixes.append(" (has {})".format(messageData['media_attachments'][0]['type']))
		# Add the message age, if requested
		if addMessageAge:
			postDateTime = self.getMessagePostTime(messageData['created_at'])
			messageAge = datetime.datetime.utcnow() - postDateTime
			# For older tweets, list the post date, otherwise list how old it is
			messageAgeString = " | "
			if messageAge.total_seconds() > self.SECONDS_AGE_FOR_FULL_DATE:
				messageAgeString += postDateTime.strftime('%Y-%m-%d')
			elif messageAge.total_seconds() <= 60:
				messageAgeString += "posted just now"
			else:
				messageAgeString += f"{DateTimeUtil.durationSecondsToText(messageAge.total_seconds(), precision=DateTimeUtil.MINUTES)} ago"
			suffixes.append(IrcFormattingUtil.makeTextColoured(messageAgeString, IrcFormattingUtil.Colours.GREY))
		# Only add the URL if requested
		if addUrl:
			suffixes.append(Constants.GREY_SEPARATOR)
			suffixes.append(messageData['url'])
		return StringWithSuffix(formattedMessageText, suffixes)

	def getMessageDescription(self, server, username, messageId, addUrl=True):
		"""
		Get a StringWithSuffix describing the Mastodon message from the provided server, user, and ID
		:param server: The url to the Mastodon instance
		:param username: The username of the person that posted the Mastodon message
		:param messageId: The ID of the Mastodon message
		:param addUrl: If True (the default), the URL to the Mastodon message will be appended to the end of the display string
		:return: A StringWithSuffix for the Mastodon message, or None if it couldn't be retrieved
		"""
		if not server.startswith('http'):
			server = "https://" + server
		try:
			response = requests.get("{}/api/v1/statuses/{}".format(server, messageId), timeout=10, headers={"User-Agent": "DideRobot"})
		except Exception as e:
			self.logError("[MastodonWatcher] Error while retrieving message id '{}' from Mastodon instance '{}': {}".format(messageId, server, e))
			return None
		if response.status_code != 200:
			self.logWarning("[MastodonWatcher] Non-OK status code received from instance '{}': {}. Content: {}".format(server, response.status_code, response.content if response.content else "[empty]"))
			return None
		return self.formatMessage(username, response.json(), addMessageAge=True, addUrl=addUrl)

	@staticmethod
	def getMessagePostTime(createdAtString):
		return datetime.datetime.strptime(createdAtString, "%Y-%m-%dT%H:%M:%S.%fZ")

	def getDisplayName(self, username, alternativeName=None):
		if username not in self.watchData:
			return username
		if 'displayname' in self.watchData[username]:
			return self.watchData[username]['displayname']
		if alternativeName:
			return alternativeName
		return username

	def findUsernameFromDisplayname(self, displayname, serverChannel):
		loweredDisplayname = displayname.lower()
		for username, userdata in self.watchData.items():
			if 'displayname' in userdata and serverChannel in userdata['targets'] and userdata['displayname'].lower() == loweredDisplayname:
				return username
		return None

	def saveWatchData(self):
		with open(self.watchDataFilePath, 'w', encoding='utf-8') as watchDataFile:
			watchDataFile.write(json.dumps(self.watchData))
