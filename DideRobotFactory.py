import json
import os

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
		self.settings = {}
		self.commandPrefix = ""
		self.commandPrefixLength = 0

		#This is toggled to 'False' on a Quit command, to bypass automatic reconnection
		self.shouldReconnect = True

		#If something goes wrong with updating the settings, it returns False. Don't continue then
		#Also don't update the logger settings, since we don't have a logger yet
		if not self.updateSettings(False):
			print "ERROR while loading settings for bot '{}', aborting launch!".format(self.serverfolder)
			GlobalStore.reactor.callLater(2.0, GlobalStore.bothandler.unregisterFactory, serverfolder)
		else:
			self.logger = Logger.Logger(self)
			GlobalStore.reactor.connectTCP(self.settings["server"], self.settings["port"], self)

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
		if not os.path.exists(os.path.join(GlobalStore.scriptfolder, "serverSettings", "globalsettings.json")):
			print "ERROR: globalsettings.json not found!"
			return False
		if not os.path.exists(os.path.join(GlobalStore.scriptfolder, "serverSettings", self.serverfolder, "settings.json")):
			print "ERROR: no settings.json file in '{}' server folder!".format(self.serverfolder)
			return False

		#First load in the default settings
		with open(os.path.join(GlobalStore.scriptfolder, 'serverSettings', "globalsettings.json"), 'r') as globalSettingsFile:
			self.settings = json.load(globalSettingsFile)
		#Then update the defaults with the server-specific ones
		with open(os.path.join(GlobalStore.scriptfolder, 'serverSettings', self.serverfolder, "settings.json"), 'r') as serverSettingsFile:
			serverSettings = json.load(serverSettingsFile)
			self.settings.update(serverSettings)

		#First make sure the required settings are in there
		settingsToEnsure = ["server", "port", "nickname", "realname", "keepSystemLogs", "keepChannelLogs", "keepPrivateLogs", "commandPrefix", "admins"]
		for settingToEnsure in settingsToEnsure:
			if settingToEnsure not in self.settings:
				print "ERROR: Required option '{}' not found in settings.json file for server '{}'".format(settingToEnsure, self.serverfolder)
				return False
			elif isinstance(self.settings[settingToEnsure], (list, unicode)) and len(self.settings[settingToEnsure]) == 0:
				print "ERROR: Option '{}' in settings.json for server '{}' is empty when it shouldn't be".format(settingToEnsure, self.serverfolder)
				return False

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
		self.maxRetries = self.settings.get('maxConnectionRetries', -1)
		#Assume values smaller than zero mean endless retries
		if self.maxRetries < 0:
			self.maxRetries = None

		if updateLogger:
			self.logger.updateLogSettings()
		return True

	def isUserAdmin(self, user, userNick=None, userAddress=None):
		return self.isUserInList(self.settings['admins'], user, userNick, userAddress)

	def shouldUserBeIgnored(self, user, userNick=None, userAddress=None):
		return self.isUserInList(self.settings['userIgnoreList'], user, userNick, userAddress)

	@staticmethod
	def isUserInList(userlist, user, userNick=None, userAddress=None):
		if user in userlist or user.lower() in userlist:
			return True
		#If a usernick is provided, use that, otherwise split the full user address ourselves
		if userNick is None or userAddress is None:
			userNick, userAddress = user.split('!', 1)
		if userNick in userlist or userNick.lower() in userlist or userAddress in userlist or userAddress.lower() in userlist:
			return True
		return False
