#Based on:
# http://newcoder.io/~drafts/networks/intro/
# https://github.com/MatthewCox/PyMoronBot

import os, time
from ConfigParser import ConfigParser

from twisted.internet import protocol
from twisted.words.protocols import irc

import GlobalStore
import Logger
from IrcMessage import IrcMessage


class DideRobot(irc.IRCClient):

	def __init__(self, factory):
		self.factory = factory
		self.channelsUserList = {}
		self.connectedAt = 0.0
		self.isMuted = False
		if self.factory.settings.has_option("connection", "minSecondsBetweenMessages"):
			self.lineRate = self.factory.settings.getfloat("connection", "minSecondsBetweenMessages")
			if self.lineRate <= 0.0:
				self.lineRate = None
	
	def connectionMade(self):
		"""Called when a connection is made."""
		self.nickname = self.factory.settings.get("connection", "nickname")
		self.realname = self.factory.settings.get("connection", "realname")
		irc.IRCClient.connectionMade(self)
		
		self.factory.logger.log("Connection to server made")
		#Let the factory know we've connected, needed because it's a reconnecting factory
		self.factory.resetDelay()

	def connectionLost(self, reason):
		"""Called when a connection is lost."""
		#self.factory.logger.log("Connection lost ({0})".format(reason))
		irc.IRCClient.connectionLost(self, reason)
		
	def signedOn(self):
		"""Called when bot has successfully signed on to server."""
		self.factory.logger.log("Signed on to server as {}".format(self.username))
		self.connectedAt = time.time()
		#Check if we have the nickname we should
		if self.nickname != self.factory.settings.get("connection", "nickname"):
			self.factory.logger.log("Nickname wasn't available, using nick '{0}'".format(self.nickname))
		#Join channels
		if not self.factory.settings.has_option('connection', 'joinChannels'):
			print "|{}| No join channels specified, idling".format(self.factory.serverfolder)
		else:
			joinChannels = self.factory.settings.get("connection", "joinChannels")
			if len(joinChannels) > 0:
				for channel in joinChannels.split(","):
					self.join(channel)
	
	def irc_JOIN(self, prefix, params):
		"""Called when a user or the bot joins a channel"""
		#'prefix' is the user, 'params' is a list with apparently just one entry, the channel
		self.factory.logger.log("User {} joined".format(prefix), params[0])
		#If we just joined a channel, or if don't have a record of this channel yet, get all the users in it
		if prefix.split("!", 1)[0] == self.nickname or params[0] not in self.channelsUserList:
			self.retrieveChannelUsers(params[0])
		#If we don't know this user yet, add it to our list
		elif prefix not in self.channelsUserList[params[0]]:
			self.channelsUserList[params[0]].append(prefix)
		
	def irc_PART(self, prefix, params):
		"""Called when a user or the bot leaves a channel"""
		#'prefix' is the user, 'params' is a list with only the channel
		self.factory.logger.log("User {} left".format(prefix), params[0])
		#Keep track of the channels we're in
		if prefix.split("!", 1)[0] == self.nickname:
			self.channelsUserList.pop(params[0])
		#Keep track of channel users
		elif prefix in self.channelsUserList[params[0]]:
				self.channelsUserList[params[0]].remove(prefix)

	def irc_QUIT(self, prefix, params):
		"""Called when a user quits"""
		#'prefix' is the user address, 'params' is a single-item list with the quit messages
		#log for every channel the user was in that they quit
		for channel, userlist in self.channelsUserList.iteritems():
			if prefix in userlist:
				self.factory.logger.log("User {} quit: {}".format(prefix, params[0]), channel)
				userlist.remove(prefix)

	def irc_KICK(self, prefix, params):
		"""Called when a user is kicked"""
		#'prefix' is the kicker, params[0] is the channel, params[1] is the kicked, params[-1] is the message
		self.factory.logger.log("{} kicked {}, reason: {}".format(prefix, params[1], params[-1]), params[0])
		#Keep track of the channels we're in
		if params[1].split("!", 1)[0] == self.nickname:
			if params[0] in self.channelsUserList:
				self.channelsUserList.pop(params[0])
				#If we were kicked, rejoin
				self.join(params[0])
		elif params[1] in self.channelsUserList[params[0]]:
				self.channelsUserList[params[0]].remove(params[1])

	def irc_NICK(self, prefix, params):
		"""Called when a user or me change their nickname"""
		#'prefix' is the full user address with the old nickname, params[0] is the new nickname
		#Update the userlists for all channels this user is in
		oldnick = prefix.split("!", 1)[0]
		newnick = params[0]
		newaddress = newnick + "!" + prefix.split("!",1)[1]
		for channel, userlist in self.channelsUserList.iteritems():
			if prefix in userlist:
				#New nick plus old address
				userlist.append(newaddress)
				userlist.remove(prefix)
				self.factory.logger.log("{} changed their nick from {} to {}".format(prefix, oldnick, newnick), channel)
		irc.IRCClient.irc_NICK(self, prefix, params)

	#Misc. logging
	#def topicUpdated(self, user, channel, newTopic):
	#	self.factory.logger.log("Channel topic: '{}' (Set by {})".format(newTopic, user), channel)
	def irc_TOPIC(self, prefix, params):
		print "irc_TOPIC called, prefix is '{}', params is '{}'".format(prefix, params)

	def irc_RPL_TOPIC(self, prefix, params):
		print "irc_RPL_TOPIC called, prefix is '{}', params is '{}'".format(prefix, params)
	def irc_RPL_NOTOPIC(self, prefix, params):
		print "irc_RPL_NOTOPIC called, prefix is '{}', params is '{}'".format(prefix, params)

	def irc_unknown(self, prefix, command, params):
		commandsToIgnore = ['PONG', 'RPL_NAMREPLY', 'RPL_ENDOFNAMES']
		#265 is rpl_localusers, 266 is globalusers. The last parameter is a string text saying how many users there are and the max.
		#  Sometimes previous parameters are these numbers separately
		if command == '265':
			print "|{}| rpl_localusers: '{}'".format(self.factory.serverfolder, params[-1])
		elif command == '266':
			print "|{}| rpl_globalusers: '{}'".format(self.factory.serverfolder, params[-1])
		#Sometimes there's no Message Of The Day
		elif command == 'ERR_NOMOTD':
			print "|{}| No MOTD".format(self.factory.serverfolder)
		elif command not in commandsToIgnore:
			print "|{}| UNKNOWN COMMAND (command is '{}', prefix is '{}', params are '{}'".format(self.factory.serverfolder, command, prefix, params)


	def receivedMOTD(self, motd):
		#Since the Message Of The Day can consist of multiple lines, print them all
		self.factory.logger.log("Server message of the day:\n {}".format("\n ".join(motd)))


	#Create a list of user addresses per channel
	def retrieveChannelUsers(self, channel):
		#Make sure we don't get duplicate data
		if channel in self.channelsUserList:
			self.channelsUserList.pop(channel)
		self.sendLine("WHO {}".format(channel))

	def irc_RPL_WHOREPLY(self, prefix, params):
		#'prefix' is the server, 'params' is a list, with meaning [own_nick, channel, other_username, other_address, other_server, other_nick, flags, hops realname]
		# Flags can be H for active or G for away, and a * for oper, + for voiced
		#print "WHOREPLY on '{}'. Prefix: '{}'. Params: '{}'".format(self.factory.serverfolder, prefix, params)
		if params[1] not in self.channelsUserList:
			self.channelsUserList[params[1]] = []
		#print "[{}] adding user {} to userlist".format(self.factory.serverfolder, params[5])
		self.channelsUserList[params[1]].append("{nick}!{username}@{address}".format(nick=params[5], username=params[2], address=params[3]))

	def irc_RPL_ENDOFWHO(self, prefix, params):
		#print "END WHOREPLY. Prefix: '{}'. Params: '{}'".format(prefix, params)
		print "End of WHO. User list for {}, have users for channels {}".format(self.factory.serverfolder, ", ".join(self.channelsUserList.keys()))
		#print self.channelsUserList


	def privmsg(self, user, channel, msg):
		"""Bot received a message in a channel or directly from another user"""
		self.factory.logger.log("{0}: {1}".format(user, msg), channel)
		self.handleMessage(user, channel, msg, 'say')

	#Incoming action
	def action(self, user, channel, msg):
		self.factory.logger.log("*{0} {1}".format(user, msg), channel)
		self.handleMessage(user, channel, msg, 'action')

	def noticed(self, user, channel, msg):
		self.factory.logger.log("[notice] {0}: {1}".format(user, msg), channel)
		#Don't send this to 'handleMessage', since you're not supposed to respond to notices

	def handleMessage(self, user, channel, msgText, type='say'):
		"""Called when the bot receives a message, which can be either in a channel or in a private message, as text or an action."""

		message = IrcMessage(irc.stripFormatting(msgText), self, type, user, channel)
		#Let the CommandHandler see if something needs to be said
		GlobalStore.commandhandler.fireCommand(message)

	def sendMessage(self, target, msg, messageType='say'):
		#Only say something if we're not muted, or if it's a private message or a notice
		if not self.isMuted or not target.startswith('#') or messageType == 'notice':
			try:
				msg = msg.encode(encoding='utf-8', errors='replace')
			except (UnicodeDecodeError, UnicodeEncodeError):
				print "Error encoding message to string (is now type '{}'): '{}'".format(type(msg), msg)
			if messageType == 'say':
				self.factory.logger.log("{0}: {1}".format(self.nickname, msg), target)
				self.msg(target, msg)
			elif messageType == 'action':
				self.factory.logger.log("*{0} {1}".format(self.nickname, msg), target)
				self.describe(target, msg)
			elif messageType == 'notice':
				self.factory.logger.log("[notice] {0}: {1}".format(self.nickname, msg), target)
				self.notice(target, msg)			

	def say(self, target, msg):
		self.sendMessage(target, msg, 'say')

	def doAction(self, target, action):
		self.sendMessage(target, action, 'action')

	def sendNotice(self, target, msg):
		self.sendMessage(target, msg, 'notice')
			
			
class DideRobotFactory(protocol.ReconnectingClientFactory):
	"""The factory creates the connection, that the bot itself handles and uses"""
	
	#Set the connection handler
	protocol = DideRobot

	def __init__(self, serverfolder):
		print "New botfactory for server '{}' started".format(serverfolder)
		self.serverfolder = serverfolder

		#Initialize some variables (in init() instead of outside it to prevent object sharing between instances)
		self.bot = None
		self.logger = None
		#Bot settings, with a few lifted out because they're frequently needed
		self.settings = None
		self.commandPrefix = u""
		self.commandPrefixLength = 0
		self.userIgnoreList = []
		self.admins = []
		self.commandWhitelist = None
		self.commandBlacklist = None

		self.shouldReconnect = True
		self.maxRetries = 5


		if not self.updateSettings(False):
			print "ERROR while loading settings for bot '{}', aborting launch!".format(self.serverfolder)
			GlobalStore.reactor.callLater(2.0, GlobalStore.bothandler.unregisterFactory, serverfolder)
		else:
			self.logger = Logger.Logger(self)
			GlobalStore.reactor.connectTCP(self.settings.get("connection", "server"), self.settings.getint("connection", "port"), self)				
		
	def buildProtocol(self, addr):
		self.bot = DideRobot(self)
		return self.bot

	def startedConnecting(self, connector):
		self.logger.log("Started connecting, attempt {} (Max is {})".format(self.retries, self.maxRetries))
		
	def clientConnectionLost(self, connector, reason):
		self.logger.log("Client connection lost (Reason: '{0}')".format(reason))
		if self.shouldReconnect:
			self.logger.log(" Restarting")
			protocol.ReconnectingClientFactory.clientConnectionLost(self, connector, reason)
		else:
			self.logger.log(" Quitting")
			self.logger.closelogs()
			GlobalStore.bothandler.unregisterFactory(self.serverfolder)

	def clientConnectionFailed(self, connector, reason):
		self.logger.log("Client connection failed (Reason: '{}')".format(reason))
		protocol.ReconnectingClientFactory.clientConnectionFailed(self, connector, reason)
		if self.retries > self.maxRetries:
			self.logger.log("Max amount of connection retries reached, removing bot factory")
			self.logger.closelogs()
			self.stopTrying()
			GlobalStore.bothandler.unregisterFactory(self.serverfolder)

		
	def updateSettings(self, updateLogger=True):
		self.settings = ConfigParser()
		if not os.path.exists(os.path.join(GlobalStore.scriptfolder, "serverSettings", "globalsettings.ini")):
			print "ERROR: globalsettings.ini not found!"
			return False
		if not os.path.exists(os.path.join(GlobalStore.scriptfolder, "serverSettings", self.serverfolder, "settings.ini")):
			print "ERROR: no settings.ini file in '{}' server folder!".format(self.serverfolder)
			return False

		self.settings.read([os.path.join(GlobalStore.scriptfolder, 'serverSettings', "globalsettings.ini"), os.path.join(GlobalStore.scriptfolder, 'serverSettings', self.serverfolder, "settings.ini")])
		#First make sure the required settings are in there
		settingsToEnsure = {"connection": ["server", "port", "nickname", "realname"], "scripts": ["commandPrefix", "admins", "keepSystemLogs", "keepChannelLogs", "keepPrivateLogs"]}
		for section, optionlist in settingsToEnsure.iteritems():
			if not self.settings.has_section(section):
				print "ERROR: Required section '{}' not found in settings.ini file for server '{}'".format(section, self.serverfolder)
				return False
			for optionToEnsure in optionlist:
				if not self.settings.has_option(section, optionToEnsure):
					print "ERROR: Required option '{}' not found in section '{}' of settings.ini file for server '{}'".format(optionToEnsure, section, self.serverfolder)
					return False

		#If we reached this far, then all required options have to be in there
		#Put some commonly-used settings in variables, for easy access
		self.commandPrefix = self.settings.get("scripts", "commandPrefix")
		self.commandPrefixLength = len(self.commandPrefix)
		self.admins = self.settings.get('scripts', 'admins').split(',')

		if self.settings.has_option('scripts', 'userIgnoreList'):
			self.userIgnoreList = self.settings.get("scripts", "userIgnoreList").split(',')
		if self.settings.has_option('scripts', 'commandWhitelist'):
			self.commandWhitelist = self.settings.get('scripts', 'commandWhitelist').split(',')
		elif self.settings.has_option('scripts', 'commandBlacklist'):
			self.commandBlacklist = self.settings.get('scripts', 'commandBlacklist').split(',')

		if updateLogger:
			self.logger.updateLogSettings()
		return True

	def isUserAdmin(self, user):
		if user in self.admins or user.split('!', 1)[0] in self.admins:
			return True
		return False
