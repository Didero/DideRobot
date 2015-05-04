import os
from ConfigParser import ConfigParser

from twisted.internet import protocol

import GlobalStore
import Logger
from DideRobot import DideRobot


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
		self.logger.log("Started connecting, attempt {} (Max is {})".format(self.retries, self.maxRetries if self.maxRetries else "not set"))

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
		#If there is a maximum number of retries set, and that maximum is exceeded, stop trying
		if self.maxRetries and self.retries > self.maxRetries:
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
		self.admins = self.settings.get('scripts', 'admins').lower().split(',')

		if self.settings.has_option('scripts', 'userIgnoreList'):
			self.userIgnoreList = self.settings.get("scripts", "userIgnoreList").lower().split(',')
		else:
			self.userIgnoreList = []

		self.commandWhitelist = None
		self.commandBlacklist = None
		if self.settings.has_option('scripts', 'commandWhitelist'):
			self.commandWhitelist = self.settings.get('scripts', 'commandWhitelist').lower().split(',')
		elif self.settings.has_option('scripts', 'commandBlacklist'):
			self.commandBlacklist = self.settings.get('scripts', 'commandBlacklist').lower().split(',')

		#Load in the maximum connection settings to try, if there is any
		if not self.settings.has_option('connection', 'maxConnectionRetries'):
			self.maxRetries = None
		else:
			try:
				self.maxRetries = self.settings.getint('connection', 'maxConnectionRetries')
			except ValueError:
				print "|{}| Invalid value in settings file for 'maxConnectionRetries'. Expected integer, got '{}'".format(self.serverfolder, self.settings.get("connection", "maxConnectionRetries"))
				self.maxRetries = None
			#Assume values smaller than zero mean endless retries
			else:
				if self.maxRetries < 0:
					self.maxRetries = None

		if updateLogger:
			self.logger.updateLogSettings()
		return True

	def isUserAdmin(self, user, usernick=None):
		return self.isUserInList(self.admins, user, usernick)

	def shouldUserBeIgnored(self, user, usernick=None):
		return self.isUserInList(self.userIgnoreList, user, usernick)

	@staticmethod
	def isUserInList(userlist, user, usernick=None):
		if user in userlist or user.lower() in userlist:
			return True
		if usernick is None:
			usernick = user.split('!', 1)[0]
		#If a usernick is provided, use that, otherwise split the full user address ourselves
		elif usernick in userlist or usernick.lower() in userlist:
			return True
		return False
