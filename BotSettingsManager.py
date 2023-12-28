import logging, json, os
from typing import Any

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
			with open(os.path.join(GlobalStore.scriptfolder, 'serverSettings', "globalsettings.json"), 'r', encoding='utf-8') as globalSettingsFile:
				self.settings = json.load(globalSettingsFile)
			#Then update the defaults with the server-specific ones
			with open(self._settingsPath, encoding='utf-8') as serverSettingsFile:
				self.settings.update(json.load(serverSettingsFile))
		except ValueError as e:
			self._logger.critical("|SettingsManager {}| Error while trying to load settings file: {}".format(self.serverfolder, e))
			return False
		else:
			return True

	def verifySettings(self):
		"""
		Checks whether some required settings exist and are filled in, and changes deprecated key names to their new names
		:return: None
		:raise SettingException: Raised when a required setting is missing or isn't filled in
		"""
		for settingToEnsure in ("server", "port", "nickname", "keepSystemLogs", "keepChannelLogs", "keepPrivateLogs", "commandPrefix", "admins"):
			if settingToEnsure not in self.settings:
				raise SettingException("Required option '{}' not found in settings.json file for server '{}'".format(settingToEnsure, self.serverfolder))
			elif isinstance(self.settings[settingToEnsure], (list, str)) and len(self.settings[settingToEnsure]) == 0:
				raise SettingException("Option '{}' in settings.json for server '{}' is empty when it shouldn't be".format(settingToEnsure, self.serverfolder))
		for keyToRename, keyNewName in {'commandBlacklist': 'commandBlocklist', 'commandWhitelist': 'commandAllowlist'}.items():
			if keyToRename in self.settings:
				if keyNewName in self.settings and self.settings[keyNewName]:
					self._logger.warning(f"|SettingsManager {self.serverfolder}| Deprecated key name '{keyToRename}' and the new name '{keyNewName}' both exist, removing old key")
					del self.settings[keyToRename]
				else:
					self._logger.warning(f"|SettingsManager {self.serverfolder}| Renaming deprecated key '{keyToRename}' to '{keyNewName}'")
					self.settings[keyNewName] = self.settings.pop(keyToRename)
		# Since we need to check for channel-specific settings often, making sure the 'channelSettings' key always exists saves a check
		if 'channelSettings' not in self.settings:
			self.settings['channelSettings'] = {}

	def saveSettings(self):
		#First get only the keys that are different from the globalsettings
		settingsToSave = {}
		with open(os.path.join(GlobalStore.scriptfolder, 'serverSettings', 'globalsettings.json'), 'r', encoding='utf-8') as globalSettingsFile:
			globalsettings = json.load(globalSettingsFile)
		for key, value in self.settings.items():
			if key not in globalsettings or value != globalsettings[key]:
				settingsToSave[key] = value

		#Make sure there's no name collision
		if os.path.exists(self._settingsPath + '.new'):
			os.remove(self._settingsPath + '.new')
		#Save the data to a new file, so we don't end up without a settings file if something goes wrong
		with open(self._settingsPath + '.new', 'w', encoding='utf-8') as f:
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

	def get(self, keyname: str, defaultValue: Any = None, channel: str = None):
		"""
		Convenience function to get at the underlying settings easier, taking channel overrides into account if a 'channel' value is passed
		:param keyname: The name of the settings key to retrieve the value of
		:param defaultValue: The value to return if the settings key doesn't exist
		:param channel: If provided, check if that channel has an override for the provided value. If not passed or no override value exists, the non-channel-specific value is used
		:return: The value of the setting specified by the keyname, optionally taking the channel override into account, or the 'defaultValue' value if that key does not exist
		"""
		if channel and self.settings and channel in self.settings['channelSettings'] and keyname in self.settings['channelSettings'][channel]:
			return self.settings['channelSettings'][channel][keyname]
		return self.settings.get(keyname, defaultValue)

	def has_key(self, keyname):
		return keyname in self.settings

	def keys(self):
		return self.settings.keys()
