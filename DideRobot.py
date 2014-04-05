#Based on:
# http://newcoder.io/~drafts/networks/intro/
# https://github.com/MatthewCox/PyMoronBot

import os, time
import argparse
from ConfigParser import ConfigParser

from twisted.internet import protocol#, reactor
from twisted.python import log
from twisted.python.logfile import DailyLogFile
from twisted.words.protocols import irc

import Logger
import GlobalStore
from CommandHandler import CommandHandler
#import TwitterFunctions

class DideRobot(irc.IRCClient):
	channelsUserList = {}
	connectedAt = 0.0
	isMuted = False
	
	def connectionMade(self):
		"""Called when a connection is made."""
		self.nickname = self.factory.nickname
		self.realname = self.factory.realname
		irc.IRCClient.connectionMade(self)
		
		self.factory.logger.log("Connection to server made")

	def connectionLost(self, reason):
		"""Called when a connection is lost."""
		#self.factory.logger.log("Connection lost ({0})".format(reason))
		irc.IRCClient.connectionLost(self, reason)
		
	def signedOn(self):
		"""Called when bot has successfully signed on to server."""
		self.factory.logger.log("Signed on to server as {}".format(self.username))
		self.connectedAt = time.time()
		#Check if we have the nickname we should
		if self.nickname != self.factory.nickname:
			self.factory.logger.log("Nickname wasn't available, using nick '{0}'".format(self.nickname))
		#Join channels
		if self.factory.settings.has_option('connection', 'joinChannels'):
			joinChannels = self.factory.settings.get("connection", "joinChannels")
			if len(joinChannels) > 0:
				for channel in joinChannels.split(","):
					self.join(channel)
	
	def irc_JOIN(self, prefix, params):
		"""Called when a user or the bot joins a channel"""
		#'prefix' is the user, 'params' is a list with apparently just one entry, the channel
		self.factory.logger.log("User {} joined".format(prefix), params[0])
		#Keep track of the channels we're in
		if prefix.split("!", 1)[0] == self.nickname:
			if params[0] not in self.channelsUserList:
				#self.channelsUserList[params[0]] = [prefix]
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
		elif params[1] in self.channelsUserList[params[0]]:
				self.channelsUserList[params[0]].remove(params[1])


	#Create a list of user addresses per channel
	def retrieveChannelUsers(self, channel):
		self.sendLine("WHO {}".format(channel))

	def irc_RPL_WHOREPLY(self, prefix, params):
		#'prefix' is the server, 'params' is a list, with meaning [own_nick, channel, other_username, other_address, other_server, other_nick, flags, hops realname]
		# Flags can be H for active or G for away, and a * for oper, + for voiced
		print "WHOREPLY on '{}'. Prefix: '{}'. Params: '{}'".format(self.factory.serverfolder, prefix, params)
		if params[1] not in self.channelsUserList:
			self.channelsUserList[params[1]] = []
		#print "[{}] adding user {} to userlist".format(self.factory.serverfolder, params[5])
		self.channelsUserList[params[1]].append("{nick}!{username}@{address}".format(nick=params[5], username=params[2], address=params[3]))

	def irc_RPL_ENDOFWHO(self, prefix, params):
		#print "END WHOREPLY. Prefix: '{}'. Params: '{}'".format(prefix, params)
		print "End of WHO. User list for {}:".format(self.factory.serverfolder)
		print self.channelsUserList
		#pass


	def privmsg(self, user, channel, msg):
		"""Bot received a message in a channel or directly from another user"""
		#For private messages, the source is the user that sent it, while on channels it's the channel name
		# This is different for private messages that the bot sends, since there the target is actually the target
		source = channel
		if not channel.startswith("#") and user != self.nickname:
			source = user.split("!", 1)[0]

		self.factory.logger.log("{0}: {1}".format(user, msg), source)
		#Check if a command needs to be executed
		self.handleMessage(user, channel, msg)

	def action(self, user, channel, msg):
		self.factory.logger.log("{0} {1}".format(user, msg), channel)
		self.handleMessage(user, channel, msg)

	def handleMessage(self, user, channel, msg):
		"""Called when the bot receives a message, which can be either in a channel, a private message, or an action."""
		
		isPrivateMessage = False
		if not channel.startswith('#'):
			isPrivateMessage = True
		
		target = channel
		if isPrivateMessage:
			target = user.split("!", 1)[0]
			
		#Let the CommandHandler see if something needs to be said
		GlobalStore.commandhandler.fireCommand(self, user, target, msg)
			

	def say(self, target, msg):
		if  not self.isMuted or not target.startswith('#'):
			try:
				msg = msg.encode(encoding='utf-8', errors='replace')
			except:
				msg = msg
			#print "Logging '{}' to '{}'".format(msg, target)
			self.factory.logger.logmsg(msg, target, self.nickname)
			print "Saying '{0}' to '{1}'".format(msg, target)
			self.msg(target, msg)
			
			
class DideRobotFactory(protocol.ClientFactory):
	"""The factory creates the connection, that the bot itself handles and uses"""
	
	#Set the connection handler
	protocol=DideRobot
	bot = None
	serverfolder = ""
	logger = None

	#Bot settings, with a few lifted out because they're frequently needed
	settings = None
	commandPrefix = u""
	commandPrefixLength = 0
	userIgnoreList = []
	admins = []
	commandWhitelist = None
	commandBlacklist = None


	def __init__(self, serverfolder):
		print "New botfactory for server '{}' started".format(serverfolder)
		self.serverfolder = serverfolder
		self.updateSettings(False)
		self.logger = Logger.Logger(self)
		#self.logger.updateLogSettings() #already done in logger__init__()
		
		self.nickname = self.settings.get("connection", "nickname")
		self.realname = self.settings.get("connection", "realname")

		GlobalStore.reactor.connectTCP(self.settings.get("connection", "server"), self.settings.getint("connection", "port"), self)
				
		
	def buildProtocol(self, addr):
		self.bot = DideRobot()
		self.bot.factory = self
		return self.bot
		
	def clientConnectionLost(self, connector, reason):
		self.logger.log("Client connection lost (Reason: '{0}'); Quitting".format(reason))
		self.logger.closelogs()
		GlobalStore.bothandler.unregisterFactory(self.serverfolder)
		
	def updateSettings(self, updateLogger=True):
		self.settings = ConfigParser()
		self.settings.read([os.path.join('serverSettings', "globalsettings.ini"), os.path.join('serverSettings', self.serverfolder, "settings.ini")])
		#Put some commonly-used settings in variables, for easy access
		self.commandPrefix = self.settings.get("scripts", "commandPrefix")
		self.commandPrefixLength = len(self.commandPrefix)
		self.userIgnoreList = self.settings.get("scripts", "userIgnoreList").split(',')
		self.admins = self.settings.get('scripts', 'admins').split(',')
		if self.settings.has_option('scripts', 'commandWhitelist'):
			self.commandWhitelist = self.settings.get('scripts', 'commandWhitelist').split(',')
		elif self.settings.has_option('scripts', 'commandBlacklist'):
			self.commandBlacklist = self.settings.get('scripts', 'commandBlacklist').split(',')

		if updateLogger == True:
			self.logger.updateLogSettings()

	def isUserAdmin(self, user):
		if user in self.admins or user.split('!', 1)[0] in self.admins:
			return True
		return False
