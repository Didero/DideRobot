import logging, json, os

import GlobalStore
from CustomExceptions import SettingException


class BotSettingsManager(object):
	def __init__(self, serverfolder):
		#Define in init to prevent object sharing between instances
		self._logger = logging.getLogger("DideRobot")
		self.settings = {}
		self.loadedSuccessfully = False

		self.serverfolder = serverfolder
		self._settingsPath = os.path.join(GlobalStore.scriptfolder, "serverSettings", self.serverfolder, "settings.json")
		self.reloadSettings(False)

	def reloadSettings(self, restorePreviousSettingsOnError=True):
		previousSettings = self.settings
		previousSettingsLoadSuccess = self.loadedSuccessfully
		self.loadedSuccessfully = False
		if not os.path.isfile(self._settingsPath):
			self._logger.critical("|SettingsManager {}| Settings file wasn't found!".format(self.serverfolder))
		elif not self.loadSettings():
			self._logger.critical("|SettingsManager {}| Error while loading the settings file".format(self.serverfolder))
		else:
			try:
				self.verifySettings()
			except SettingException as se:
				self._logger.error("|{}| Error in settings file: {}".format(self.serverfolder, se.displayMessage))
				#Clear the incomplete settings file
				self.settings = {}
			else:
				self.parseSettings()
				self.loadedSuccessfully = True

		#Don't keep a possibly broken settings file around
		if not self.loadedSuccessfully:
			if restorePreviousSettingsOnError:
				self.settings = previousSettings
				self.loadedSuccessfully = previousSettingsLoadSuccess
			else:
				self.settings = {}

	def loadSettings(self):
		try:
			#First load in the default settings
			with open(os.path.join(GlobalStore.scriptfolder, 'serverSettings', "globalsettings.json"), 'r') as globalSettingsFile:
				self.settings = json.load(globalSettingsFile)
			#Then update the defaults with the server-specific ones
			with open(self._settingsPath) as serverSettingsFile:
				self.settings.update(json.load(serverSettingsFile))
		except ValueError as e:
			self._logger.critical("|SettingsManager {}| Error while trying to load settings file: {}".format(self.serverfolder, e.message))
			return False
		else:
			return True

	def verifySettings(self):
		"""
		Checks whether some required settings exist and are filled in
		:return: None
		:raise SettingException: Raised when a required setting is missing or isn't filled in
		"""
		for settingToEnsure in ("server", "port", "nickname", "keepSystemLogs", "keepChannelLogs", "keepPrivateLogs", "commandPrefix", "admins"):
			if settingToEnsure not in self.settings:
				raise SettingException("Required option '{}' not found in settings.json file for server '{}'".format(settingToEnsure, self.serverfolder))
			elif isinstance(self.settings[settingToEnsure], (list, unicode)) and len(self.settings[settingToEnsure]) == 0:
				raise SettingException("Option '{}' in settings.json for server '{}' is empty when it shouldn't be".format(settingToEnsure, self.serverfolder))

	def parseSettings(self):
		#All the strings should be strings and not unicode, which makes it a lot easier to use later
		for key, value in self.settings.iteritems():
			if isinstance(value, unicode):
				self.settings[key] = value.encode('utf-8')

	def saveSettings(self):
		#First get only the keys that are different from the globalsettings
		settingsToSave = {}
		with open(os.path.join(GlobalStore.scriptfolder, 'serverSettings', 'globalsettings.json'), 'r') as globalSettingsFile:
			globalsettings = json.load(globalSettingsFile)
		for key, value in self.settings.iteritems():
			if key not in globalsettings or value != globalsettings[key]:
				settingsToSave[key] = value

		#Make sure there's no name collision
		if os.path.exists(self._settingsPath + '.new'):
			os.remove(self._settingsPath + '.new')
		#Save the data to a new file, so we don't end up without a settings file if something goes wrong
		with open(self._settingsPath + '.new', 'w') as f:
			f.write(json.dumps(settingsToSave, indent=2))
		#Remove the previous backup file
		if os.path.exists(self._settingsPath + '.old'):
			os.remove(self._settingsPath + '.old')
		#Keep the old settings file around, just in case we need to put it back
		os.rename(self._settingsPath, self._settingsPath + '.old')
		#Set the new settings file as the in-use one
		os.rename(self._settingsPath + '.new', self._settingsPath)

	def __getitem__(self, key):
		"""Allows access to setting values like mySettingsManager['commandPrefix'], makes getting values easier"""
		if key not in self.settings:
			raise KeyError("Key '{}' does not exist".format(key))
		return self.settings[key]

	def __setitem__(self, key, value):
		self.settings[key] = value

	def __delitem__(self, key):
		if key not in self.settings:
			raise KeyError("Key '{}' does not exist".format(key))
		del self.settings[key]

	def __nonzero__(self):
		"""Makes it possible to do 'if mySettingsManager' to see if loading went successfully"""
		if self.settings:
			return True
		else:
			return False

	def __contains__(self, key):
		return key in self.settings

	def get(self, keyname, defaultValue=None):
		#Convenience function to get at the underlying settings easier
		return self.settings.get(keyname, defaultValue)

	def has_key(self, keyname):
		return keyname in self.settings

	def keys(self):
		return self.settings.keys()
