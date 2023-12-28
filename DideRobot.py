import logging
import time
from typing import List, Tuple, Union

import gevent
import gevent.socket

import Constants
import GlobalStore
from BotSettingsManager import BotSettingsManager
from IrcMessage import IrcMessage
from MessageLogger import MessageLogger
import MessageTypes
import PermissionLevel
from util import IrcFormattingUtil, StringUtil


class DideRobot(object):
	def __init__(self, serverfolder):
		self.logger = logging.getLogger('DideRobot')
		self.logger.info("New bot for server '{}' created".format(serverfolder))

		#Initialize some variables (in init() instead of outside it to prevent object sharing between instances)
		self.serverfolder = serverfolder
		self.ircSocket = None
		self.nickname = None  # Will get set once we connect, when we know if we have the nickname we want
		self.channelsUserList = {}  # Will be a dict with joined channels as keys and a list of users in those channels as values
		self.isUpdatingChannelsUserList = False
		self.isMuted = False

		self.connectedAt = None  # Will be set to the timestamp on which we connect. 'None' means we're not connected
		self.connectionManagerGreenlet = None  # This will get a reference to the greenlet keeping the connection alive. If this ends, the bot is closed down
		self.shouldStayConnected = True  # Can be set to 'False' if the connection should be closed from our side, regardless of the server state
		self.shouldReconnect = True  # If we somehow get disconnected, should we try to re-establish a connection?
		self.reconnectionAttempCount = None  # Will keep a count of how many times we've tried to connect, to see if we've exceeded the limit (if any)
		self.maxConnectionRetries = None  # None means unlimited attempts, can be set by settings file

		self.secondsBetweenLineSends = None  # If it's 'None', there's no rate limiting, otherwise it's a float of seconds between line sends
		self.linesToSend = None  # A list with all the lines to send if there is a queue and rate limiting
		self.lineSendingGreenlet = None  # Will store the greenlet that is currently working its way through the message queue, or is None if there is none

		#Load the settings, and only connect to the server if that succeeded
		self.settings = BotSettingsManager(self.serverfolder)
		if self.settings.loadedSuccessfully:
			self.parseSettings()
			self.messageLogger = MessageLogger(self)
			self.connectionManagerGreenlet = gevent.spawn(self.keepServerConnectionAlive)
		else:
			self.logger.error("|{}| Invalid settings file, shutting down".format(self.serverfolder))
			#Also tell the bot manager that we'll stop existing
			GlobalStore.bothandler.unregisterBot(self.serverfolder)

	def parseSettings(self):
		"""Retrieve some frequently-used values, to store them in a more easily-accessible way"""
		#Load in the maximum connection settings to try, if there is any
		self.maxConnectionRetries = self.settings.get('maxConnectionRetries', -1)
		#Assume values smaller than zero mean endless retries
		if self.maxConnectionRetries < 0:
			self.maxConnectionRetries = None

		#Time in seconds (can have decimals) between line sends, because some servers are rate limited
		self.secondsBetweenLineSends = self.settings.get('minSecondsBetweenMessages', -1)
		if self.secondsBetweenLineSends <= 0:
			self.secondsBetweenLineSends = None

	def reloadSettings(self):
		self.settings.reloadSettings(True)
		if self.settings.loadedSuccessfully:
			self.parseSettings()
			return True
		else:
			return False

	#CONNECTION FUNCTIONS
	def keepServerConnectionAlive(self):
		while True:
			self.shouldStayConnected = True
			# Open a connection
			self.ircSocket = gevent.socket.socket(gevent.socket.AF_INET, gevent.socket.SOCK_STREAM)
			self.ircSocket.settimeout(20.0)  #Set the timout to establishing a connection, gets increased when we successfully connect
			self.logger.info("Connecting to {} ({} on port {})".format(self.serverfolder, self.settings['server'], self.settings['port']))
			try:
				self.ircSocket.connect((self.settings['server'], self.settings['port']))
			except (gevent.socket.timeout, gevent.socket.error, gevent.socket.herror, gevent.socket.gaierror) as e:
				self.logger.error("Unable to connect to server '{}' ({}:{}), reason: {}".format(self.serverfolder, self.settings['server'], self.settings['port'], e))
			else:
				#Connecting was successful, authenticate
				if self.settings.get('serverpassword', None):
					self.sendLineToServer("PASS " + self.settings['serverpassword'])
				self.sendLineToServer("NICK {}".format(self.settings['nickname']))
				#Use the specified realname, or fall back to the username if none is provided
				realname = self.settings.get('realname', self.settings['nickname'])
				self.sendLineToServer("USER {} 4 * :{}".format(self.settings['nickname'], realname))  #The '4' means we want WALLOPS messages but not invisibility
				if self.settings.get('nicknamepassword', None):  #Use 'get' instead of 'in' so we also check for empty strings
					self.sendMessage("nickserv", "identify {}".format(self.settings['nicknamepassword']))

				#Start listening for replies
				self.handleConnection()
				#If we reach here, 'handleConnection' returned, so we apparently lost the connection (either accidentally or intentionally)

				#Check if we were still sending messages
				if self.lineSendingGreenlet:
					# Kill the message sending greenlet to prevent errors
					self.lineSendingGreenlet.kill()
					self.lineSendingGreenlet = None
					#Also clear the message queue, just in case something in there caused the disconnect
					self.linesToSend = None

				#Clear the channels and users lists
				self.channelsUserList = {}
				self.isUpdatingChannelsUserList = False

				#Shutdown here because it only makes sense if we have been connected previously
				self.ircSocket.shutdown(gevent.socket.SHUT_RDWR)

			# We lost the connection, so close the socket and store that we lost connection
			self.ircSocket.close()
			self.ircSocket = None
			self.connectedAt = None

			#If the connection couldn't be established or got closed, check if we need to re-establish it
			if not self.shouldReconnect:
				self.logger.info("|{}| Connection closed, shouldn't reconnect, closing down this bot".format(self.serverfolder))
				break
			#If we reached the maximum reconnection attempts, abort
			if self.reconnectionAttempCount and self.maxConnectionRetries and self.reconnectionAttempCount >= self.maxConnectionRetries:
				self.logger.info("|{}| Reached max connection retry attempts ({}), closing".format(self.maxConnectionRetries, self.serverfolder))
				break

			if self.reconnectionAttempCount is None:
				self.reconnectionAttempCount = 1
			else:
				self.reconnectionAttempCount += 1
			#Wait increasingly long between reconnection attempts, to give the server a chance to restart
			sleepTime = self.reconnectionAttempCount ** 3
			self.logger.info("Will try reconnecting to '{}' for attempt {} in {} seconds, max attempts is {}".format(
				self.serverfolder, self.reconnectionAttempCount, sleepTime, self.maxConnectionRetries if self.maxConnectionRetries else "not set"))
			gevent.sleep(sleepTime)
		#If we ever leave this loop, the bot is shut down. Unregister ourselves
		GlobalStore.bothandler.unregisterBot(self.serverfolder)

	def handleConnection(self):
		#Keep reading for possible incoming messages
		incomingData = b""
		# Set the timeout to 10 minutes, so if our computer loses connection to the server/internet, we notice
		self.ircSocket.settimeout(600)
		while self.shouldStayConnected:
			try:
				incomingData += self.ircSocket.recv(2048)
			except gevent.socket.timeout:
				self.logger.warning("|{}| Our connection to the server timed out".format(self.serverfolder))
				return
			# A closed connection just makes recv return an empty string. Check for that
			if incomingData == b"":
				self.logger.info("|{}| Server closed the connection".format(self.serverfolder))
				return
			# Handle all completely sent messages (delimited by \r\n), leave any unfinished messages for the next loop
			while b'\r\n' in incomingData:
				line, incomingData = incomingData.split(b'\r\n', 1)
				# First deal with the simplest type of message, PING. Just reply PONG
				if line.startswith(b"PING"):
					self.sendLineToServer(line.replace(b"PING", b"PONG", 1), False)
				else:
					# Let's find out what kind of message this is!
					lineParts = line.decode('utf-8').split(" ")
					# A line consists at least of 'source messageType [target] content'
					messageSource = lineParts[0]
					# It usually starts with a colon, remove that
					if messageSource.startswith(":"):
						messageSource = messageSource[1:]
					messageType = lineParts[1]
					#Convert numerical replies to human-readable ones, if applicable. Otherwise make it uppercase, since that's the standard
					messageType = MessageTypes.IRC_NUMERIC_TO_TYPE.get(messageType, messageType.upper())
					#The IRC protocol uses ':' to denote the start of a multi-word string. Join those here too, for easier parsing later
					messageParts = lineParts[2:]
					for messagePartIndex, messagePart in enumerate(messageParts):
						if messagePart.startswith(':'):
							#Join all the separate parts of the wordgroup, and remove the starting colon
							wordgroup = " ".join(messageParts[messagePartIndex:])[1:]
							messageParts[messagePartIndex] = wordgroup
							messageParts = messageParts[:messagePartIndex+1]
							break
					#Check if we have a function to deal with this type of message
					messageTypeFunction = getattr(self, "irc_" + messageType, None)
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
			self.logger.info("|{}| Nickname not available. Wanted '{}', got '{}'".format(self.serverfolder, self.settings['nickname'], self.nickname))
		# Inform all the modules that we connected
		message = IrcMessage(MessageTypes.RPL_WELCOME, self, None, source, " ".join(parameters))
		GlobalStore.commandhandler.handleMessage(message)
		# Join the channels we should, if there are any
		if len(self.settings['joinChannels']) == 0:
			self.logger.info("|{}| No join channels specified, idling".format(self.serverfolder))
		else:
			for channel in self.settings['joinChannels']:
				self.joinChannel(channel)

	def joinChannel(self, channelname):
		if channelname[0] not in Constants.CHANNEL_PREFIXES:
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
		self.sendLineToServer("NICK " + newNicknameAttempt)

	#Create a list of user addresses per channel
	def retrieveChannelUsers(self, channel):
		self.isUpdatingChannelsUserList = True
		#Make sure we don't get duplicate data
		if channel in self.channelsUserList:
			self.channelsUserList[channel].clear()
		self.sendLineToServer("WHO {}".format(channel))

	def quit(self, quitMessage=None):
		self.shouldReconnect = False
		#If we are connected to a server, let it know we want to quit
		if self.connectedAt is not None:
			if quitMessage:
				self.sendLineToServer("QUIT :" + quitMessage)
			else:
				self.sendLineToServer("QUIT")
		# If we're not connected (yet?), stop trying to connect
		elif self.connectionManagerGreenlet:
			self.logger.info("|{}| Asked to quit, but not connected. Stopping wait before next connection attempt".format(self.serverfolder))
			self.connectionManagerGreenlet.kill()
			GlobalStore.bothandler.unregisterBot(self.serverfolder)
		else:
			#I don't know how we'd end up without a connection greenlet, but best handle it anyway
			self.logger.info("|{}| Asked to quit and don't have a connection greenlet. Unregistering".format(self.serverfolder))
			GlobalStore.bothandler.unregisterBot(self.serverfolder)

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
		message = IrcMessage(MessageTypes.JOIN, self, prefix, params[0])
		self.messageLogger.log("JOIN: {nick} ({address})".format(nick=message.userNickname, address=prefix), params[0])
		# If we just joined a channel, or if don't have a record of this channel yet, get all the users in it
		if message.userNickname == self.nickname or params[0] not in self.channelsUserList:
			# Already create a userlist entry, so the rest of the bot knows we're in this channel, even if retrieving the channel users goes wrong somehow (Looking at you, Twitch Chat)
			self.channelsUserList[params[0]] = []
			# Then try to fill the userlist
			self.retrieveChannelUsers(params[0])
		# If we don't know this user yet, add it to our list
		elif prefix not in self.channelsUserList[params[0]]:
			self.channelsUserList[params[0]].append(prefix)
		GlobalStore.commandhandler.handleMessage(message)

	def irc_PART(self, prefix, params):
		"""Called when a user or the bot leaves a channel"""
		# 'prefix' is the user, 'params' is a list with only the channel
		message = IrcMessage(MessageTypes.PART, self, prefix, params[0])
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
		message = IrcMessage(MessageTypes.QUIT, self, prefix, None, params[0])
		logMessage = "QUIT: {nick} ({address}): '{quitmessage}' ".format(nick=message.userNickname, address=prefix, quitmessage=params[0])
		for channel, userlist in self.channelsUserList.items():
			if prefix in userlist:
				self.messageLogger.log(logMessage, channel)
				userlist.remove(prefix)
		GlobalStore.commandhandler.handleMessage(message)

	def irc_KICK(self, prefix, params):
		"""Called when a user is kicked"""
		# 'prefix' is the kicker, params[0] is the channel, params[1] is the user address of the kicked, params[-1] is the kick reason
		message = IrcMessage(MessageTypes.KICK, self, prefix, params[0], params[-1])
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
		message = IrcMessage(MessageTypes.NICK, self, prefix, None, params[0])
		oldnick = message.userNickname
		newnick = params[0]
		# New nick plus old address
		newaddress = newnick + "!" + prefix.split("!", 1)[1]
		# If it's about us, apparently a nick change was successful
		if oldnick == self.nickname:
			self.nickname = newnick
			self.logger.info("|{}| Our nick got changed from '{}' to '{}'".format(self.serverfolder, oldnick, self.nickname))
		# Log the change in every channel where it's relevant
		for channel, userlist in self.channelsUserList.items():
			if prefix in userlist:
				# Update the userlists for all channels this user is in
				userlist.remove(prefix)
				userlist.append(newaddress)
				self.messageLogger.log("NICK CHANGE: {oldnick} changed their nick to {newnick}".format(oldnick=oldnick, newnick=newnick), channel)
		GlobalStore.commandhandler.handleMessage(message)

	def irc_MODE(self, prefix, params):
		#There are two possible MODE commands
		# The first is server-wide. Here the prefix is our user address, the first param is our username, and the second param is the mode change
		if len(params) == 2:
			self.logger.info("|{}| Our mode got set to '{}'".format(self.serverfolder, params[1]))
		# The second is channel-specific. Here the prefix is who or what is making the change, the first param is the channel,
		#  the second param is the mode change, and the rest of the params are the nicks whose mode got changed
		else:
			#It's not always a user making the change, check if it's a user address
			modeChanger = prefix
			if '!' in modeChanger:
				modeChanger = modeChanger.split('!', 1)[0]
			self.messageLogger.log("{} set mode to '{}' of user(s) {}".format(modeChanger, params[1], ", ".join(params[2:])), params[0])

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


	#CTCP FUNCTIONS
	def ctcp_ACTION(self, user, messageSource, messageText):
		self.handleMessage(user, messageSource, messageText, MessageTypes.ACTION)

	def ctcp_PING(self, user, messageSource, messageText):
		self.messageLogger.log("Received PING request from '{}'".format(user), messageSource)
		usernick = user.split('!', 1)[0]
		self.sendMessage(usernick, "PING " + messageText if messageText else str(time.time()), MessageTypes.NOTICE)

	def ctcp_SOURCE(self, user, messageSource, messageText):
		self.messageLogger.log("Received SOURCE request from '{}'".format(user), messageSource)
		usernick = user.split('!', 1)[0]
		self.sendMessage(usernick, "Thanks for the interest! You can read through my innards at https://github.com/Didero/DideRobot", MessageTypes.NOTICE)

	def ctcp_TIME(self, user, messageSource, messageText):
		self.messageLogger.log("Received TIME request from '{}'".format(user), messageSource)
		usernick = user.split('!', 1)[0]
		self.sendMessage(usernick, time.strftime("%a %d-%m-%Y %H:%M:%S %Z"), MessageTypes.NOTICE)

	def ctcp_VERSION(self, user, messageSource, messageText):
		self.messageLogger.log("Received VERSION request from '{}'".format(user), messageSource)
		usernick = user.split('!', 1)[0]
		self.sendMessage(usernick, "I don't have a set version, since I'm updated pretty frequently. I appreciate the interest though!", MessageTypes.NOTICE)


	#HUMAN COMMUNICATION FUNCTIONS
	def irc_PRIVMSG(self, user, messageParts):
		# First part of the messageParts is the channel the message came in from, or the user if it was a PM
		# Second part is the actual message
		messageSource = messageParts[0]
		# If the actual message (past the first colon) starts with 'chr(1)', it means it's a special CTCP message (like an action)
		if len(messageParts[1]) > 0 and messageParts[1][0] == Constants.CTCP_DELIMITER:
			#First section is the CTCP type
			# Make the type uppercase, since that's the standard (also means 'unknown_message_type' can't accidentally be called)
			ctcpType = messageParts[1].upper()
			messageText = None
			#Sometimes a message is appended (like for an ACTION), check for that
			if " " in ctcpType:
				ctcpType, messageText = messageParts[1].split(" ", 1)
				#The message could also end with a 'chr(1)', remove that
				if messageText.endswith(Constants.CTCP_DELIMITER):
					messageText = messageText[:-1]
			#The CTCP type could end with the CTCP delimiter
			if ctcpType.endswith(Constants.CTCP_DELIMITER):
				ctcpType = ctcpType[:-1]
			ctcpType = ctcpType[1:]  #Remove the CTCP delimiter
			#Check if we have a function to handle this type of CTCP message, otherwise fall back on a default
			ctcpFunction = getattr(self, "ctcp_" + ctcpType, None)
			if ctcpFunction:
				ctcpFunction(user, messageSource, messageText)
			else:
				self.ctcp_unknown_message_type(ctcpType, user, messageSource, messageText)
		#Normal message
		else:
			self.handleMessage(user, messageSource, messageParts[1], MessageTypes.SAY)

	def irc_NOTICE(self, user, messageParts):
		self.handleMessage(user, messageParts[0], messageParts[1], MessageTypes.NOTICE)

	def handleMessage(self, user, channel, messageText, messageType=MessageTypes.SAY):
		"""Called when the bot receives a message, which can be either in a channel or in a private message, as text or an action."""
		usernick = user.split("!", 1)[0]
		logsource = channel
		if channel == self.nickname or channel == '*':  #If a server wants to send a message to you before it knows your nick, it uses *
			logsource = usernick
		logtext = "({source}) "
		if messageType == MessageTypes.SAY:
			logtext = "{user}: {message}"
		elif messageType == MessageTypes.ACTION:
			logtext = "*{user} {message}"
		elif messageType == MessageTypes.NOTICE:
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
		try:
			if isinstance(lineToSend, str):
				lineToSend = lineToSend.encode('utf-8')
			self.ircSocket.send(lineToSend + b"\r\n")
		except gevent.socket.error as socketError:
			self.logger.error("|{}| Socket error occurred when sending line '{}': {}".format(self.serverfolder, lineToSend, socketError))
			#If the socket is giving errors, we should close the socket and make the bot reconnect
			self.shouldStayConnected = False
		except Exception as e:
			self.logger.error("|{}| Tried sending line '{}' to server, but a '{}' exception was raised: {}".format(self.serverfolder, lineToSend, type(e).__name__, e))

	def irc_ERR_NOTEXTTOSEND(self, prefix, params):
		self.logger.error("|{}| We just sent an empty line to the server, which is probably a bug in a module!".format(self.serverfolder))

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

	def sendMessage(self, target, messageText, messageType=MessageTypes.SAY):
		if not target or not messageText:
			self.logger.warning("Asked to send an empty message or send a message to an empty target. Target: '{}', messageText: '{}'".format(target, messageText))
			return
		#Only say something if we're not muted, or if it's a private message or a notice
		if not self.isMuted or target[0] not in Constants.CHANNEL_PREFIXES or messageType == MessageTypes.NOTICE:
			logtext = ""
			messageCommand = MessageTypes.SAY
			if messageType == MessageTypes.ACTION:
				#An action is just a special type of Say
				logtext += "*"
				messageText = self.formatCtcpMessage(MessageTypes.ACTION, messageText)
			elif messageType == MessageTypes.NOTICE:
				logtext += "[notice] "
				messageCommand = MessageTypes.NOTICE
			logtext += "{user}: {message}"
			if self.settings.get('textDecoration', 'irc') != 'irc':
				messageText = IrcFormattingUtil.removeFormatting(messageText)
			extraMessages = None
			# Turn newlines in this message into multiple messages
			if '\n' in messageText or '\r' in messageText:
				extraMessages = messageText.splitlines()
				messageText = extraMessages.pop(0)
			# Check if the message isn't too long to send
			maxMessageLength = Constants.MAX_LINE_LENGTH - self.calculateMessagePrefixLength(target, messageType)
			if len(messageText) > maxMessageLength:
				if not extraMessages:
					extraMessages = []
				extraMessages.insert(0, messageText[maxMessageLength + 1:])
				messageText = messageText[:maxMessageLength + 1]
			line = "{} {} :{}".format(messageCommand, target, messageText)
			if target[0] not in Constants.CHANNEL_PREFIXES:
				#If it's a PM, bypass the message queue
				self.sendLineToServer(line)
			else:
				self.queueLineToSend(line)
			self.messageLogger.log(logtext.format(user=self.nickname, message=messageText), target)
			#Make sure any non-empty extra lines get sent too
			if extraMessages:
				for extraMessage in extraMessages:
					if extraMessage:
						self.sendMessage(target, extraMessage, messageType)

	def sendLengthLimitedMessage(self, target, messageTextToShorten, suffix=None, messageType=MessageTypes.SAY):
		"""
		Send a message to the provided target, limited to the maximum length allowed for a message to that target
		:param target: The user or channel to send the message to
		:param messageTextToShorten: The main message text that will be shortened if it exceeds the maximum message length, taking the suffix into account
		:param suffix: An optional string to add to the end of the messageTextToShorten. This suffix will not be shortened, and its length will be taken into account when shortening the messageText
		:type suffix: str
		:param messageType: The type of the message to send, or a normal text message if not provided
		"""
		maxMessageLength = Constants.MAX_LINE_LENGTH - self.calculateMessagePrefixLength(target, messageType)
		if self.settings.get('textDecoration', 'irc') != 'irc':
			messageTextToShorten = IrcFormattingUtil.removeFormatting(messageTextToShorten)
		shortenedMessageText = StringUtil.limitStringLength(messageTextToShorten, maxMessageLength, suffixes=suffix)
		self.sendMessage(target, shortenedMessageText, messageType)

	def calculateMessagePrefixLength(self, target, messageType):
		# Format of a server-side message (to send our message to everybody in a channel) is ':[nick,32]![username,12]@[hostmask,64] PRIVMSG [target,64] :[messagetext]'
		# Assume the maximum length for realname and hostname since we don't know if those are set properly or changed server-side
		prefixLength = len(target) + len(messageType) + 83  # +12 (realname), +64 (hostname), +7 (colons, spaces, etc), = 83
		if self.nickname:
			prefixLength += len(self.nickname)
		else:
			prefixLength += 32  # No nick set (yet), assume max length
		# Action messages are normal text messages plus an extra CTCP part
		if messageType == MessageTypes.ACTION:
			# +1 because 'PRIVMSG' is one character longer than 'ACTION', +6 for the length of 'ACTION' since it gets added a second time, +2 for the CTCP delimiters, +1 for an extra space = +10
			prefixLength += 10
		return prefixLength

	def getCommandAllowAndBlockLists(self, channel: str = None) -> Tuple[Union[None, List[str]], Union[None, List[str]]]:
		"""
		Get the command allow and block lists for this bot, optionally for the specified channel. Can be useful if you'ree going to iterate over commands and check permissions, so you don't have to keep getting the allow and/or block lists
		:param channel: Optionally, the channel to get the allow and block lists for. If omitted, or if the specified channel doesn't have a channel-specific list, the server allow and block lists are returned
		:return: The command allow and block lists, optionally for the specified channel. If an allow list is set, the block list is None
		"""
		allowlist = self.settings.get('commandAllowlist', None, channel)
		if allowlist:
			blocklist = None
		else:
			blocklist = self.settings.get('commandBlocklist', None, channel)
		return (allowlist, blocklist)

	def getCommandPrefix(self, channel: str = None):
		return self.settings.get("commandPrefix", "!", channel)

	#USER LIST CHECKING FUNCTIONS
	def isUserAdmin(self, user, userNick=None, userAddress=None):
		return self._isUserInList(self.settings['admins'], user, userNick, userAddress)

	def shouldUserBeIgnored(self, user, userNick=None, userAddress=None):
		return self._isUserInList(self.settings['userIgnoreList'], user, userNick, userAddress)

	def doesUserHavePermission(self, permissionLevel: PermissionLevel.PermissionLevel, user: str, userNick: str, userAddress: str, channel: str = None) -> bool:
		if permissionLevel <= PermissionLevel.BASIC:
			return True
		if permissionLevel <= PermissionLevel.BOT and self._isUserInList(self.settings['admins'], user, userNick, userAddress):
			return True
		elif permissionLevel <= PermissionLevel.SERVER and self._isUserInList(self.settings.get('serverAdmins', []), user, userNick, userAddress):
			return True
		elif permissionLevel <= PermissionLevel.CHANNEL and self._isUserInList(self.settings.get('channelAdmins', [], channel), user, userNick, userAddress):
			return True
		return False

	def getUserPermissionLevel(self, user: str, userNick: str, userAddress: str, channel: str = None):
		if self._isUserInList(self.settings['admins'], user, userNick, userAddress):
			return PermissionLevel.BOT
		elif self._isUserInList(self.settings.get('serverAdmins', []), user, userNick, userAddress):
			return PermissionLevel.SERVER
		elif self._isUserInList(self.settings.get('channelAdmins', [], channel), user, userNick, userAddress):
			return PermissionLevel.CHANNEL
		return PermissionLevel.BASIC

	@staticmethod
	def _isUserInList(userlist, user, userNick=None, userAddress=None) -> bool:
		if user is None:
			return False
		if user in userlist or user.lower() in userlist:
			return True
		#If a usernick is provided, use that, otherwise split the full user address ourselves (if possible)
		if userNick is None or userAddress is None:
			if '!' in user:
				userNick, userAddress = user.split('!', 1)
			else:
				return False
		if userNick in userlist or userNick.lower() in userlist or userAddress in userlist or userAddress.lower() in userlist:
			return True
		return False
