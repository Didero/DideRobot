import json
import logging
import os
import time

import gevent
import gevent.socket

import Constants
import GlobalStore
from IrcMessage import IrcMessage
from MessageLogger import MessageLogger


class DideRobot(object):
	def __init__(self, serverfolder):
		self.logger = logging.getLogger('DideRobot')
		self.logger.info("New bot for server '{}' created".format(serverfolder))

		#Initialize some variables (in init() instead of outside it to prevent object sharing between instances)
		self.serverfolder = serverfolder
		self.settings = {}
		self.ircSocket = None
		self.nickname = None  # Will get set once we connect, when we know if we have the nickname we want
		self.channelsUserList = {}  # Will be a dict with joined channels as keys and a list of users in those channels as values
		self.isUpdatingChannelsUserList = False
		self.isMuted = False

		self.connectedAt = None  # Will be set to the timestamp on which we connect. 'None' means we're not connected
		self.connectionManagerGreenlet = None  # This will get a reference to the greenlet keeping the connection alive. If this ends, the bot is closed down
		self.shouldReconnect = True
		self.reconnectionAttempCount = None  # Will keep a count of how many times we've tried to connect, to see if we've exceeded the limit (if any)
		self.maxConnectionRetries = None  # None means unlimited attempts, can be set by settings file

		self.secondsBetweenLineSends = None  # If it's 'None', there's no rate limiting, otherwise it's a float of seconds between line sends
		self.linesToSend = None  # A list with all the lines to send if there is a queue and rate limiting
		self.lineSendingGreenlet = None  # Will store the greenlet that is currently working its way through the message queue, or is None if there is none

		self.commandPrefix = ""  # Pulled from the settings file, separate variable because it's referenced a lot
		self.commandPrefixLength = 0  # The length if the prefix is also often needed, prevent constant recalculation

		#Load the settings, and only connect to the server if that succeeded
		if self.loadSettings(False):
			self.messageLogger = MessageLogger(self)
			self.connectionManagerGreenlet = gevent.spawn(self.keepServerConnectionAlive)
		else:
			self.logger.error("|{}| Invalid settings file, shutting down".format(self.serverfolder))
			#Also tell the bot manager that we'll stop existing
			GlobalStore.bothandler.unregisterBot(self.serverfolder)


	#SETTINGS FUNCTIONS
	def verifySettings(self, settings=None):
		if not settings:
			settings = self.settings
		#First make sure the required settings are in there
		for settingToEnsure in ("server", "port", "nickname", "keepSystemLogs", "keepChannelLogs", "keepPrivateLogs", "commandPrefix", "admins"):
			if settingToEnsure not in settings:
				return (False, "Required option '{}' not found in settings.json file for server '{}'".format(settingToEnsure, self.serverfolder))
			elif isinstance(settings[settingToEnsure], (list, unicode)) and len(settings[settingToEnsure]) == 0:
				return (False, "Option '{}' in settings.json for server '{}' is empty when it shouldn't be".format(settingToEnsure, self.serverfolder))
		return (True, "Settings verified")

	def loadSettings(self, updateLogger=True):
		if not os.path.exists(os.path.join(GlobalStore.scriptfolder, "serverSettings", "globalsettings.json")):
			self.logger.error("globalsettings.json not found!")
			return False
		if not os.path.exists(os.path.join(GlobalStore.scriptfolder, "serverSettings", self.serverfolder, "settings.json")):
			self.logger.error("No settings.json file in '{}' server folder!".format(self.serverfolder))
			return False

		#First load in the default settings
		with open(os.path.join(GlobalStore.scriptfolder, 'serverSettings', "globalsettings.json"), 'r') as globalSettingsFile:
			settings = json.load(globalSettingsFile)
		#Then update the defaults with the server-specific ones
		with open(os.path.join(GlobalStore.scriptfolder, 'serverSettings', self.serverfolder, "settings.json"), 'r') as serverSettingsFile:
			serverSettings = json.load(serverSettingsFile)
			settings.update(serverSettings)

		verifyResult, verifyMessage = self.verifySettings(settings)
		if not verifyResult:
			self.logger.error("|{}| Error in settings file: {}".format(self.serverfolder, verifyMessage))
			return False
		self.settings = settings

		self.parseSettings()
		if updateLogger:
			self.messageLogger.updateLogSettings()
		return True

	def parseSettings(self):
		#All the strings should be strings and not unicode, which makes it a lot easier to use later
		for key, value in self.settings.iteritems():
			if isinstance(value, unicode):
				self.settings[key] = value.encode('utf-8')

		#The command prefix is going to be needed often, as will its length. Put that in an easy-to-reach place
		self.commandPrefix = self.settings['commandPrefix']
		self.commandPrefixLength = len(self.commandPrefix)

		# If the command whitelist or blacklist is empty, set that to 'None' so you can easily check if they're filled
		for l in ('commandWhitelist', 'commandBlacklist'):
			if self.settings[l] is not None and len(self.settings[l]) == 0:
				self.settings[l] = None

		#Load in the maximum connection settings to try, if there is any
		self.maxConnectionRetries = self.settings.get('maxConnectionRetries', -1)
		#Assume values smaller than zero mean endless retries
		if self.maxConnectionRetries < 0:
			self.maxConnectionRetries = None

		#Time in seconds (can have decimals) between line sends, because some servers are rate limited
		self.secondsBetweenLineSends = self.settings.get('minSecondsBetweenMessages', -1)
		if self.secondsBetweenLineSends <= 0:
			self.secondsBetweenLineSends = None

	def saveSettings(self):
		#First get only the keys that are different from the globalsettings
		settingsToSave = {}
		with open(os.path.join(GlobalStore.scriptfolder, 'serverSettings', 'globalsettings.json'), 'r') as globalSettingsFile:
			globalsettings = json.load(globalSettingsFile)
		for key, value in self.settings.iteritems():
			if key not in globalsettings or value != globalsettings[key]:
				settingsToSave[key] = value

		settingsFilename = os.path.join(GlobalStore.scriptfolder, 'serverSettings', self.serverfolder, 'settings.json')
		#Make sure there's no name collision
		if os.path.exists(settingsFilename + '.new'):
			os.remove(settingsFilename + '.new')
		#Save the data to a new file, so we don't end up without a settings file if something goes wrong
		with open(settingsFilename + '.new', 'w') as f:
			f.write(json.dumps(settingsToSave, indent=2))
		#Remove the previous backup file
		if os.path.exists(settingsFilename + '.old'):
			os.remove(settingsFilename + '.old')
		#Keep the old settings file around, just in case we need to put it back
		os.rename(settingsFilename, settingsFilename + '.old')
		#Set the new settings file as the in-use one
		os.rename(settingsFilename + '.new', settingsFilename)


	#CONNECTION FUNCTIONS
	def keepServerConnectionAlive(self):
		while True:
			# Open a connection
			self.ircSocket = gevent.socket.socket(gevent.socket.AF_INET, gevent.socket.SOCK_STREAM)
			self.logger.info("Connecting to {} ({} on port {})".format(self.serverfolder, self.settings['server'], self.settings['port']))
			self.ircSocket.connect((self.settings['server'], self.settings['port']))
			#Connecting was successful, authenticate
			if 'password' in self.settings and len(self.settings['password']) > 0:
				self.sendLineToServer("PASS " + self.settings['password'])
			self.sendLineToServer("NICK {}".format(self.settings['nickname']))
			#Use the specified realname, or fall back to the username if none is provided
			realname = self.settings.get('realname', self.settings['nickname'])
			self.sendLineToServer("USER {} 4 * :{}".format(self.settings['nickname'], realname))  #The '4' means we want WALLOPS messages but not invisibility

			#Start listening for replies
			self.handleConnection()

			# We lost the connection, so close the socket and store that we lost connection
			self.ircSocket.shutdown(gevent.socket.SHUT_RDWR)
			self.ircSocket.close()
			self.ircSocket = None
			self.connectedAt = None

			#If the connection couldn't be established or got closed, check if we need to re-establish it
			if not self.shouldReconnect:
				self.logger.info("Connection to '{}' closed, shouldn't reconnecting, shutting down".format(self.serverfolder))
				break
			#If we reached the maximum reconnection attempts, abort
			if self.reconnectionAttempCount and self.maxConnectionRetries and self.reconnectionAttempCount > self.maxConnectionRetries:
				self.logger.info("Reached max connection retry attempts ({}) for '{}', closing".format(self.maxConnectionRetries, self.serverfolder))
				break

			#Re-establish the connection
			self.logger.info("Lost connection to server '{}', reconnecting".format(self.serverfolder))
			#If we've exceeded the allowed number of attempts, give up
			if self.reconnectionAttempCount is None:
				self.reconnectionAttempCount = 1
			else:
				self.reconnectionAttempCount += 1
			#Wait increasingly long between reconnection attempts, to give the server a chance to restart
			self.logger.info("Reconnecting to '{}', attempt {}, max is {}".format(self.serverfolder, self.reconnectionAttempCount,
																				  self.maxConnectionRetries if self.maxConnectionRetries else "not set"))
			gevent.sleep(self.reconnectionAttempCount ** 3)
		#If we ever leave this loop, the bot is shut down. Unregister ourselves
		GlobalStore.bothandler.unregisterBot(self.serverfolder)

	def handleConnection(self):
		#Keep reading for possible incoming messages
		incomingData = ""
		while True:
			incomingData += self.ircSocket.recv(2048)
			# A closed connection just makes recv return an empty string. Check for that
			if incomingData == "":
				return
			# Handle all completely sent messages (delimited by \r\n), leave any unfinished messages for the next loop
			while '\r\n' in incomingData:
				line, incomingData = incomingData.split('\r\n', 1)
				# First deal with the simplest type of message, PING. Just reply PONG
				if line.startswith("PING"):
					self.sendLineToServer(line.replace("PING", "PONG", 1), False)
				else:
					# Let's find out what kind of message this is!
					lineParts = line.split(" ")
					# A line consists at least of 'source messageType [target] content'
					messageSource = lineParts[0]
					# It usually starts with a colon, remove that
					if messageSource.startswith(":"):
						messageSource = messageSource[1:]
					messageType = lineParts[1]
					#Convert numerical replies to human-readable ones, if applicable
					messageType = Constants.IRC_numeric_to_name.get(messageType, messageType)
					#Check if we have a function to deal with this type of message
					messageTypeFunction = getattr(self, "irc_" + messageType, None)
					#The IRC protocol uses ':' to denote the start of a multi-word string. Join those here too, for easier parsing later
					messageParts = lineParts[2:]
					for messagePartIndex, messagePart in enumerate(messageParts):
						if messagePart.startswith(':'):
							#Join all the separate parts of the wordgroup, and remove the starting colon
							wordgroup = " ".join(messageParts[messagePartIndex:])[1:]
							messageParts[messagePartIndex] = wordgroup
							messageParts = messageParts[:messagePartIndex+1]
							break
					if messageTypeFunction:
						messageTypeFunction(messageSource, messageParts)
					else:
						#No function for this type of message, fall back to a generic function
						self.irc_unknown_message_type(messageSource, messageType, lineParts)

	def irc_RPL_WELCOME(self, source, parameters):
		"""Called when we finished connecting to the server"""
		self.logger.info("|{}| Successfully connected".format(self.serverfolder))
		# We successfully connected, reset the reconnection count
		self.reconnectionAttempCount = None
		self.connectedAt = time.time()
		# Get the nickname we got assigned from the message
		self.nickname = parameters[0]
		if self.nickname != self.settings['nickname']:
			self.logger.info("|{} Nickname not available. Wanted '{}', got '{}'".format(self.serverfolder, self.settings['nickname'], self.nickname))
		# Inform all the modules that we connected
		message = IrcMessage("RPL_WELCOME", self, None, source, " ".join(parameters))
		GlobalStore.commandhandler.handleMessage(message)
		# Join the channels we should, if there are any
		if len(self.settings['joinChannels']) == 0:
			self.logger.info("|{}| No join channels specified, idling".format(self.serverfolder))
		else:
			for channel in self.settings['joinChannels']:
				self.joinChannel(channel)

	def joinChannel(self, channelname):
		if not channelname.startswith("#"):
			channelname = "#" + channelname
		if channelname in self.channelsUserList:
			self.logger.warning("|{}| Asked to join '{}' but I'm already there".format(self.serverfolder, channelname))
		else:
			self.sendLineToServer("JOIN {}".format(channelname))

	def leaveChannel(self, channelName, leaveMessage="Leaving..."):
		if channelName not in self.channelsUserList:
			self.logger.warning("|{}| Asked to leave '{}', but I'm not there".format(self.serverfolder, channelName))
		else:
			self.sendLineToServer("PART {} :{}".format(channelName, leaveMessage))

	def setNick(self, nickname):
		self.sendLineToServer("NICK " + nickname)

	def irc_ERR_NICKNAMEINUSE(self, source, parameters):
		# The nickname we want is apparently in use. Just append an underscore and try again
		newNicknameAttempt = parameters[1] + "_"
		self.logger.info("|{}| Requested nickname '{}' in use, retrying with nickname '{}'".format(self.serverfolder, parameters[1], newNicknameAttempt))
		self.nickname = newNicknameAttempt
		self.sendLineToServer("NICK " + newNicknameAttempt)

	#Create a list of user addresses per channel
	def retrieveChannelUsers(self, channel):
		self.isUpdatingChannelsUserList = True
		#Make sure we don't get duplicate data
		if channel in self.channelsUserList:
			self.channelsUserList.pop(channel)
		self.sendLineToServer("WHO {}".format(channel))

	def quit(self, quitMessage=None):
		self.shouldReconnect = False
		if quitMessage:
			self.sendLineToServer("QUIT :" + quitMessage)
		else:
			self.sendLineToServer("QUIT")


	#MESSAGE TYPE HANDLING FUNCTIONS
	def irc_unknown_message_type(self, source, messageType, messageParts):
		self.logger.info("|{}| Received unknown message type '{}' from {}: {}".format(self.serverfolder, messageType, source, " ".join(messageParts)))

	def ctcp_unknown_message_type(self, ctcpType, user, messageTarget, message):
		self.logger.info("|{}| Received unknown CTCP command '{}' on {} from {}, message '{}'".format(self.serverfolder, ctcpType, messageTarget, user, message))

	def irc_RPL_MOTD(self, prefix, params):
		self.messageLogger.log("Server message of the day: " + params[1])

	def irc_JOIN(self, prefix, params):
		"""Called when a user or the bot joins a channel"""
		# 'prefix' is the user, 'params' is a list with apparently just one entry, the channel
		message = IrcMessage('join', self, prefix, params[0])
		self.messageLogger.log("JOIN: {nick} ({address})".format(nick=message.userNickname, address=prefix), params[0])
		# If we just joined a channel, or if don't have a record of this channel yet, get all the users in it
		if message.userNickname == self.nickname or params[0] not in self.channelsUserList:
			self.retrieveChannelUsers(params[0])
		# If we don't know this user yet, add it to our list
		elif prefix not in self.channelsUserList[params[0]]:
			self.channelsUserList[params[0]].append(prefix)
		GlobalStore.commandhandler.handleMessage(message)

	def irc_PART(self, prefix, params):
		"""Called when a user or the bot leaves a channel"""
		# 'prefix' is the user, 'params' is a list with only the channel
		message = IrcMessage('part', self, prefix, params[0])
		self.messageLogger.log("PART: {nick} ({address})".format(nick=message.userNickname, address=prefix), params[0])
		# If a user parts before we have a proper channellist built, catch that error
		if params[0] not in self.channelsUserList:
			self.logger.warning("|{}| Unexpected PART, user '{}' parted from channel '{}' but we had no record of them".format(self.serverfolder, prefix, params[0]))
			# Schedule a rebuild of the userlist
			if not self.isUpdatingChannelsUserList:
				self.retrieveChannelUsers(params[0])
		# Keep track of the channels we're in
		elif message.userNickname == self.nickname:
			self.channelsUserList.pop(params[0])
		# Keep track of channel users
		elif prefix in self.channelsUserList[params[0]]:
			self.channelsUserList[params[0]].remove(prefix)
		GlobalStore.commandhandler.handleMessage(message)

	def irc_QUIT(self, prefix, params):
		"""Called when a user quits"""
		# 'prefix' is the user address, 'params' is a single-item list with the quit messages
		# log for every channel the user was in that they quit
		message = IrcMessage('quit', self, prefix, None, params[0])
		logMessage = "QUIT: {nick} ({address}): '{quitmessage}' ".format(nick=message.userNickname, address=prefix, quitmessage=params[0])
		for channel, userlist in self.channelsUserList.iteritems():
			if prefix in userlist:
				self.messageLogger.log(logMessage, channel)
				userlist.remove(prefix)
		GlobalStore.commandhandler.handleMessage(message)

	def irc_KICK(self, prefix, params):
		"""Called when a user is kicked"""
		# 'prefix' is the kicker, params[0] is the channel, params[1] is the user address of the kicked, params[-1] is the kick reason
		message = IrcMessage('kick', self, prefix, params[0], params[-1])
		kickedUserNick = params[1].split("!", 1)[0]
		self.messageLogger.log("KICK: {} was kicked by {}, reason: '{}'".format(kickedUserNick, message.userNickname, params[-1]), params[0])
		# Keep track of the channels we're in
		if kickedUserNick == self.nickname:
			if params[0] in self.channelsUserList:
				self.channelsUserList.pop(params[0])
		elif params[1] in self.channelsUserList[params[0]]:
			self.channelsUserList[params[0]].remove(params[1])
		GlobalStore.commandhandler.handleMessage(message)

	def irc_NICK(self, prefix, params):
		"""Called when a user or me change their nickname"""
		# 'prefix' is the full user address with the old nickname, params[0] is the new nickname
		message = IrcMessage('nickchange', self, prefix, None, params[0])
		oldnick = message.userNickname
		newnick = params[0]
		# New nick plus old address
		newaddress = newnick + "!" + prefix.split("!", 1)[1]
		# If it's about us, apparently a nick change was successful
		if oldnick == self.nickname:
			self.nickname = newnick
			self.logger.info("|{}| Our nick got changed from '{}' to '{}'".format(self.serverfolder, oldnick, self.nickname))
		# Log the change in every channel where it's relevant
		for channel, userlist in self.channelsUserList.iteritems():
			if prefix in userlist:
				# Update the userlists for all channels this user is in
				userlist.append(newaddress)
				userlist.remove(prefix)
				self.messageLogger.log("NICK CHANGE: {oldnick} changed their nick to {newnick}".format(oldnick=oldnick, newnick=newnick), channel)
		GlobalStore.commandhandler.handleMessage(message)

	def irc_TOPIC(self, prefix, params):
		self.logger.debug("irc_TOPIC called, prefix is '{}', params is '{}'".format(prefix, params))

	def irc_RPL_TOPIC(self, prefix, params):
		self.logger.debug("irc_RPL_TOPIC called, prefix is '{}', params is '{}'".format(prefix, params))

	def irc_RPL_NOTOPIC(self, prefix, params):
		self.logger.debug("irc_RPL_NOTOPIC called, prefix is '{}', params is '{}'".format(prefix, params))

	def irc_RPL_WHOREPLY(self, prefix, params):
		#'prefix' is the server, 'params' is a list, with meaning [own_nick, channel, other_username, other_address, other_server, other_nick, flags, hops realname]
		# Flags can be H for active or G for away, and a * for oper, + for voiced
		if params[1] not in self.channelsUserList:
			self.channelsUserList[params[1]] = []
		self.channelsUserList[params[1]].append("{nick}!{username}@{address}".format(nick=params[5], username=params[2], address=params[3]))

	def irc_RPL_ENDOFWHO(self, prefix, params):
		self.isUpdatingChannelsUserList = False
		self.logger.info("|{}| Userlist for channels {} collected".format(self.serverfolder, ", ".join(self.channelsUserList.keys())))


	#HUMAN COMMUNICATION FUNCTIONS
	def irc_PRIVMSG(self, user, messageParts):
		# First part of the messageParts is the channel the message came in from, or the user if it was a PM
		# Second part is the actual message
		messageTarget = messageParts[0]
		# If the actual message (past the first colon) starts with 'chr(1)', it means it's a special CTCP message (like an action)
		if len(messageParts[1]) > 0 and messageParts[1][0] == Constants.CTCP_DELIMITER:
			#First section is the CTCP type
			ctcpType, messageParts[1] = messageParts[1].split(" ", 1)
			ctcpType = ctcpType[1:]  #Remove the CTCP delimiter
			#The message should also end with a 'chr(1)', remove that
			if messageParts[1].endswith(Constants.CTCP_DELIMITER):
				messageParts[1] = messageParts[1][:-1]
			#Check if we have a function to handle this type of CTCP message, otherwise fall back on a default
			ctcpFunction = getattr(self, "ctcp_" + ctcpType, None)
			if ctcpFunction:
				ctcpFunction(user, messageTarget, messageParts[1])
			else:
				self.ctcp_unknown_message_type(ctcpType, user, messageTarget, messageParts[1])
		#Normal message
		else:
			self.handleMessage(user, messageTarget, messageParts[1], "say")

	def irc_NOTICE(self, user, messageParts):
		self.handleMessage(user, messageParts[0], messageParts[1], 'notice')

	def ctcp_ACTION(self, user, messageTarget, message):
		self.handleMessage(user, messageTarget, message, 'action')

	def handleMessage(self, user, channel, messageText, messageType="say"):
		"""Called when the bot receives a message, which can be either in a channel or in a private message, as text or an action."""
		usernick = user.split("!", 1)[0]
		logsource = channel
		if channel == self.nickname or channel == '*':  #If a server wants to send a message to you before it knows your nick, it uses *
			logsource = usernick
		logtext = "({source}) "
		if messageType == 'say':
			logtext = "{user}: {message}"
		elif messageType == 'action':
			logtext = "*{user} {message}"
		elif messageType == 'notice':
			logtext = "[notice] {user}: {message}"

		self.messageLogger.log(logtext.format(user=usernick, message=messageText), logsource)
		message = IrcMessage(messageType, self, user, channel, messageText)
		#Let the CommandHandler see if a module needs to do something with this message
		GlobalStore.commandhandler.handleMessage(message)


	#SENDING OUT MESSAGES
	def sendLineToServer(self, lineToSend, shouldLogMessage=True):
		if not self.ircSocket:
			self.logger.error("|{}| Asked to send line '{}' to server, but socket closed".format(self.serverfolder, lineToSend))
			return
		if shouldLogMessage:
			self.logger.debug("|{}| > {}".format(self.serverfolder, lineToSend))
		self.ircSocket.send(lineToSend + "\r\n")

	@staticmethod
	def formatCtcpMessage(ctcpType, messageText):
		return "{delim}{ctcpType} {msg}{delim}".format(delim=Constants.CTCP_DELIMITER, ctcpType=ctcpType, msg=messageText)

	def sendLineFromQueue(self):
		try:
			while True:
				#Verify that we're still connected and there is still a message in the queue, otherwise reset everything
				if self.connectedAt is None or not self.linesToSend or len(self.linesToSend) == 0:
					self.linesToSend = None
					self.lineSendingGreenlet = None
					break
				#Remove the first queued message and send it
				self.sendLineToServer(self.linesToSend.pop(0))
				#Keep going through the message queue until it's empty
				gevent.sleep(self.secondsBetweenLineSends)
		except gevent.GreenletExit:
			self.logger.info("|{}| Line sender greenlet was killed".format(self.serverfolder))

	def queueLineToSend(self, lineToSend):
		#If there's no rate limiting, there's no need for queueing either. Send the message now
		if not self.secondsBetweenLineSends:
			self.sendLineToServer(lineToSend)
			return
		#If there are no lines queued, the list is set to 'None'. Create a new list
		if not self.linesToSend:
			self.linesToSend = [lineToSend]
		# Add the message to the queue
		else:
			self.linesToSend.append(lineToSend)
		# If there's not yet a greenlet clearing the message queue, create one
		if not self.lineSendingGreenlet:
			self.lineSendingGreenlet = gevent.spawn(self.sendLineFromQueue)

	def sendMessage(self, target, messageText, messageType='say'):
		#Only say something if we're not muted, or if it's a private message or a notice
		if not self.isMuted or not target.startswith('#') or messageType == 'notice':
			#Make sure we're not trying to send Unicode
			if isinstance(messageText, unicode):
				try:
					messageText = messageText.encode(encoding='utf-8', errors='replace')
				except (UnicodeDecodeError, UnicodeEncodeError):
					self.logger.warning("|{}| [sendMessage] Error encoding message to string (is now type '{}'): '{}'".format(self.serverfolder, type(messageText), messageText))
			#It can't handle unicode message targets either
			if isinstance(target, unicode):
				target = target.encode('utf-8')
			logtext = ""
			messageCommand = "PRIVMSG"
			if messageType == 'action':
				#An action is just a special type of Say
				logtext += "*"
				messageText = self.formatCtcpMessage("ACTION", messageText)
			elif messageType == 'notice':
				logtext += "[notice] "
				messageCommand = "NOTICE"
			logtext += "{user}: {message}"
			line = "{} {} :{}".format(messageCommand, target, messageText)
			if not target.startswith('#'):
				#If it's a PM, bypass the message queue
				self.sendLineToServer(line)
			else:
				self.queueLineToSend(line)
			self.messageLogger.log(logtext.format(user=self.nickname, message=messageText), target)


	#USER LIST CHECKING FUNCTIONS
	def isUserAdmin(self, user, userNick=None, userAddress=None):
		return self.isUserInList(self.settings['admins'], user, userNick, userAddress)

	def shouldUserBeIgnored(self, user, userNick=None, userAddress=None):
		return self.isUserInList(self.settings['userIgnoreList'], user, userNick, userAddress)

	@staticmethod
	def isUserInList(userlist, user, userNick=None, userAddress=None):
		if user is None:
			return False
		if user in userlist or user.lower() in userlist:
			return True
		#If a usernick is provided, use that, otherwise split the full user address ourselves (if possible)
		if '!' not in user:
			return False
		if userNick is None or userAddress is None:
			userNick, userAddress = user.split('!', 1)
		if userNick in userlist or userNick.lower() in userlist or userAddress in userlist or userAddress.lower() in userlist:
			return True
		return False
