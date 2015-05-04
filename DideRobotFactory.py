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
			GlobalStore.reactor.connectTCP(self.settings["connection"]["server"], self.settings["connection"]["port"], self)

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
			for section in ('connection', 'commands'):
				if section not in serverSettings:
					continue
				if section not in self.settings:
					self.settings[section] = serverSettings[section]
				else:
					self.settings[section].update(serverSettings[section])

		#First make sure the required settings are in there
		settingsToEnsure = {"connection": ["server", "port", "nickname", "realname", "keepSystemLogs", "keepChannelLogs", "keepPrivateLogs"], "commands": ["commandPrefix", "admins"]}
		for section, optionlist in settingsToEnsure.iteritems():
			if section not in self.settings:
				print "ERROR: Required section '{}' not found in settings.ini file for server '{}'".format(section, self.serverfolder)
				return False
			for optionToEnsure in optionlist:
				if optionToEnsure not in self.settings[section]:
					print "ERROR: Required option '{}' not found in section '{}' of settings.json file for server '{}'".format(optionToEnsure, section, self.serverfolder)
					return False
				elif isinstance(self.settings[section][optionToEnsure], (list, unicode)) and len(self.settings[section][optionToEnsure]) == 0:
					print "ERROR: Option '{}' in section '{}' in settings.json for server '{}' is empty".format(optionToEnsure, section, self.serverfolder)

		#All the strings should be strings and not unicode, which makes it a lot easier to use later
		for section in ('connection', 'commands'):
			for key, value in self.settings[section].iteritems():
				if isinstance(value, unicode):
					self.settings[section][key] = value.encode('utf-8')

		#The command prefix is going to be needed often, as will its length. Put that in an easy-to-reach place
		self.commandPrefix = self.settings['commands']['commandPrefix']
		self.commandPrefixLength = len(self.commandPrefix)

		# If the command whitelist or blacklist is empty, set that to 'None' so you can easily check if they're filled
		for l in ('commandWhitelist', 'commandBlacklist'):
			print "{} is set to {}".format(l, self.settings['commands'].get(l, 'nothing'))
			if self.settings['commands'][l] is not None and len(self.settings['commands'][l]) == 0:
				print "Setting {} to None".format(l)
				self.settings['commands'][l] = None
			else:
				print "Keeping {} as {}".format(l, self.settings['commands'][l])

		#Load in the maximum connection settings to try, if there is any
		self.maxRetries = self.settings['connection'].get('maxConnectionRetries', -1)
		#Assume values smaller than zero mean endless retries
		if self.maxRetries < 0:
			self.maxRetries = None

		if updateLogger:
			self.logger.updateLogSettings()
		return True

	def isUserAdmin(self, user, usernick=None):
		return self.isUserInList(self.settings['commands']['admins'], user, usernick)

	def shouldUserBeIgnored(self, user, usernick=None):
		return self.isUserInList(self.settings['commands']['userIgnoreList'], user, usernick)

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
