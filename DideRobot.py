import logging
import time

from twisted.words.protocols import irc

import GlobalStore
from IrcMessage import IrcMessage


class DideRobot(irc.IRCClient):
	def __init__(self, factory):
		self.logger = logging.getLogger('DideRobot')
		self.factory = factory
		self.channelsUserList = {}
		self.isUpdatingChannelsUserList = False
		self.connectedAt = 0.0
		self.isMuted = False
		#Limit the speed at which we send messages, if necessary
		self.lineRate = self.factory.settings.get('minSecondsBetweenMessages', -1.0)
		if not isinstance(self.lineRate, float) or self.lineRate <= 0.0:
			self.lineRate = None
		self.nickname = self.factory.settings['nickname']
		self.realname = self.factory.settings['realname'] if 'realname' in self.factory.settings else 'DideRobot'
		if 'serverpassword' in self.factory.settings and len(self.factory.settings['serverpassword']) > 0:
			self.password = self.factory.settings['serverpassword']
	
	def connectionMade(self):
		"""Called when a connection is made."""
		irc.IRCClient.connectionMade(self)
		self.factory.messageLogger.log("Connection to server made")

	def connectionLost(self, reason):
		"""Called when a connection is lost."""
		irc.IRCClient.connectionLost(self, reason)
		
	def signedOn(self):
		"""Called when bot has successfully signed on to server."""
		self.factory.messageLogger.log("Signed on to server as {}".format(self.username))
		self.connectedAt = time.time()
		#Let the factory know we've connected, needed because it's a reconnecting factory
		self.factory.resetDelay()
		#Check if we have the nickname we should
		if self.nickname != self.factory.settings['nickname']:
			self.factory.messageLogger.log("Specified nickname '{}' wasn't available, using nick '{}'".format(self.factory.settings['nickname'], self.nickname))
		#Join channels
		if len(self.factory.settings['joinChannels']) == 0:
			self.logger.info("|{}| No join channels specified, idling".format(self.factory.serverfolder))
		else:
			for channel in self.factory.settings['joinChannels']:
				self.join(channel.encode('utf-8'))
	
	def irc_JOIN(self, prefix, params):
		"""Called when a user or the bot joins a channel"""
		#'prefix' is the user, 'params' is a list with apparently just one entry, the channel
		message = IrcMessage('join', self, prefix, params[0])
		self.factory.messageLogger.log("JOIN: {nick} ({address})".format(nick=message.userNickname, address=prefix), params[0])
		#If we just joined a channel, or if don't have a record of this channel yet, get all the users in it
		if message.userNickname == self.nickname or params[0] not in self.channelsUserList:
			self.retrieveChannelUsers(params[0])
		#If we don't know this user yet, add it to our list
		elif prefix not in self.channelsUserList[params[0]]:
			self.channelsUserList[params[0]].append(prefix)
		GlobalStore.commandhandler.fireCommand(message)

		
	def irc_PART(self, prefix, params):
		"""Called when a user or the bot leaves a channel"""
		#'prefix' is the user, 'params' is a list with only the channel
		message = IrcMessage('part', self, prefix, params[0])
		self.factory.messageLogger.log("PART: {nick} ({address})".format(nick=message.userNickname, address=prefix), params[0])
		#If a user parts before we have a proper channellist built, catch that error
		if params[0] not in self.channelsUserList:
			self.logger.warning("|{}| Unexpected PART, user '{}' parted from channel '{}' but we had no record of them".format(self.factory.serverfolder, prefix, params[0]))
			#Schedule a rebuild of the userlist
			if not self.isUpdatingChannelsUserList:
				self.retrieveChannelUsers(params[0])
			else:
				GlobalStore.reactor.callLater(3.0, self.retrieveChannelUsers, params[0])
		#Keep track of the channels we're in
		elif message.userNickname == self.nickname:
			self.channelsUserList.pop(params[0])
		#Keep track of channel users
		elif prefix in self.channelsUserList[params[0]]:
				self.channelsUserList[params[0]].remove(prefix)
		GlobalStore.commandhandler.fireCommand(message)

	def irc_QUIT(self, prefix, params):
		"""Called when a user quits"""
		#'prefix' is the user address, 'params' is a single-item list with the quit messages
		#log for every channel the user was in that they quit
		message = IrcMessage('quit', self, prefix, None, params[0])
		for channel, userlist in self.channelsUserList.iteritems():
			if prefix in userlist:
				self.factory.messageLogger.log("QUIT: {nick} ({address}): '{quitmessage}' ".format(nick=message.userNickname, address=prefix, quitmessage=params[0]), channel)
				userlist.remove(prefix)
		GlobalStore.commandhandler.fireCommand(message)

	def irc_KICK(self, prefix, params):
		"""Called when a user is kicked"""
		#'prefix' is the kicker, params[0] is the channel, params[1] is the user address of the kicked, params[-1] is the kick reason
		message = IrcMessage('kick', self, prefix, params[0], params[-1])
		kickedUserNick = params[1].split("!", 1)[0]
		self.factory.messageLogger.log("KICK: {} was kicked by {}, reason: '{}'".format(kickedUserNick, message.userNickname, params[-1]), params[0])
		#Keep track of the channels we're in
		if kickedUserNick == self.nickname:
			if params[0] in self.channelsUserList:
				self.channelsUserList.pop(params[0])
		elif params[1] in self.channelsUserList[params[0]]:
				self.channelsUserList[params[0]].remove(params[1])
		GlobalStore.commandhandler.fireCommand(message)

	def irc_NICK(self, prefix, params):
		"""Called when a user or me change their nickname"""
		#'prefix' is the full user address with the old nickname, params[0] is the new nickname
		#Update the userlists for all channels this user is in
		message = IrcMessage('nickchange', self, prefix, None, params[0])
		oldnick = message.userNickname
		newnick = params[0]
		newaddress = newnick + "!" + prefix.split("!", 1)[1]
		#If it's about us, apparently a nick change was successful
		if oldnick == self.nickname:
			self.nickname = newnick
		#Log the change in every channel where it's relevant
		for channel, userlist in self.channelsUserList.iteritems():
			if prefix in userlist:
				#New nick plus old address
				userlist.append(newaddress)
				userlist.remove(prefix)
				self.factory.messageLogger.log("NICK CHANGE: {oldnick} changed their nick to {newnick}".format(oldnick=oldnick, newnick=newnick), channel)
		GlobalStore.commandhandler.fireCommand(message)

	#Misc. logging
	def irc_TOPIC(self, prefix, params):
		self.logger.debug("irc_TOPIC called, prefix is '{}', params is '{}'".format(prefix, params))
	def irc_RPL_TOPIC(self, prefix, params):
		self.logger.debug("irc_RPL_TOPIC called, prefix is '{}', params is '{}'".format(prefix, params))
	def irc_RPL_NOTOPIC(self, prefix, params):
		self.logger.debug("irc_RPL_NOTOPIC called, prefix is '{}', params is '{}'".format(prefix, params))

	def irc_unknown(self, prefix, command, params):
		commandsToIgnore = ['PONG', 'RPL_NAMREPLY', 'RPL_ENDOFNAMES']
		#265 is rpl_localusers, 266 is globalusers. The last parameter is a string text saying how many users there are and the max.
		#  Sometimes previous parameters are these numbers separately
		if command == '265':
			self.logger.debug("|{}| rpl_localusers: '{}'".format(self.factory.serverfolder, params[-1]))
		elif command == '266':
			self.logger.debug("|{}| rpl_globalusers: '{}'".format(self.factory.serverfolder, params[-1]))
		#Sometimes there's no Message Of The Day
		elif command == 'ERR_NOMOTD':
			self.logger.debug("|{}| No MOTD".format(self.factory.serverfolder))
		elif command not in commandsToIgnore:
			self.logger.debug("|{}| UNKNOWN COMMAND (command is '{}', prefix is '{}', params are '{}'".format(self.factory.serverfolder, command, prefix, params))


	def receivedMOTD(self, motd):
		#Since the Message Of The Day can consist of multiple lines, print them all
		self.factory.messageLogger.log("Server message of the day:\n {}".format("\n ".join(motd)))

	#Create a list of user addresses per channel
	def retrieveChannelUsers(self, channel):
		self.isUpdatingChannelsUserList = True
		#Make sure we don't get duplicate data
		if channel in self.channelsUserList:
			self.channelsUserList.pop(channel)
		self.sendLine("WHO {}".format(channel))

	def irc_RPL_WHOREPLY(self, prefix, params):
		#'prefix' is the server, 'params' is a list, with meaning [own_nick, channel, other_username, other_address, other_server, other_nick, flags, hops realname]
		# Flags can be H for active or G for away, and a * for oper, + for voiced
		if params[1] not in self.channelsUserList:
			self.channelsUserList[params[1]] = []
		self.channelsUserList[params[1]].append("{nick}!{username}@{address}".format(nick=params[5], username=params[2], address=params[3]))

	def irc_RPL_ENDOFWHO(self, prefix, params):
		self.isUpdatingChannelsUserList = False
		self.logger.info("|{}| Userlist for channels {} collected".format(self.factory.serverfolder, ", ".join(self.channelsUserList.keys())))


	def privmsg(self, user, channel, msg):
		"""Bot received a message in a channel or directly from another user"""
		self.handleMessage(user, channel, msg, 'say')

	#Incoming action
	def action(self, user, channel, msg):
		self.handleMessage(user, channel, msg, 'action')

	def noticed(self, user, channel, msg):
		self.handleMessage(user, channel, msg, 'notice')

	def handleMessage(self, user, channel, messageText, messageType='say'):
		"""Called when the bot receives a message, which can be either in a channel or in a private message, as text or an action."""

		usernick = user.split("!", 1)[0]

		logsource = channel
		if channel == self.nickname or channel == '*':  #If a server wants to send a message to you before it knows your nick, it uses *
			logsource = usernick
		logtext = ""
		if messageType == 'say':
			logtext = "{user}: {message}"
		elif messageType == 'action':
			logtext = "*{user} {message}"
		elif messageType == 'notice':
			logtext = "[notice] {user}: {message}"

		self.factory.messageLogger.log(logtext.format(user=usernick, message=messageText), logsource)

		message = IrcMessage(messageType, self, user, channel, messageText)
		#Let the CommandHandler see if something needs to be said
		GlobalStore.commandhandler.fireCommand(message)

	def sendMessage(self, target, msg, messageType='say'):
		#Only say something if we're not muted, or if it's a private message or a notice
		if not self.isMuted or not target.startswith('#') or messageType == 'notice':
			#Twisted can only send str messages. Make sure we're not trying to send Unicode
			if isinstance(msg, unicode):
				try:
					msg = msg.encode(encoding='utf-8', errors='replace')
				except (UnicodeDecodeError, UnicodeEncodeError):
					self.logger.warning("[sendMessage] Error encoding message to string (is now type '{}'): '{}'".format(type(msg), msg))
			#It can't handle unicode message targets either
			if isinstance(target, unicode):
				target = target.encode('utf-8')
			logtext = ""
			if messageType == 'say':
				logtext = "{user}: {message}"
				self.msg(target, msg)
			elif messageType == 'action':
				logtext = "*{user} {message}"
				self.describe(target, msg)
			elif messageType == 'notice':
				logtext = "[notice] {user}: {message}"
				self.notice(target, msg)

			self.factory.messageLogger.log(logtext.format(user=self.nickname, message=msg), target)
