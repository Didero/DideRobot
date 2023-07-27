import os, re

from commands.CommandTemplate import CommandTemplate
import GlobalStore, PermissionLevel
from IrcMessage import IrcMessage
from CustomExceptions import SettingException


class Command(CommandTemplate):
	triggers = ['setting', 'reloadsettings', 'reloadkeys']
	helptext = "Used to view or change bot settings. See all keys with the parameter 'list', or use 'get' to see a single value. " \
			   "Use 'set' to change a value or 'delete' to delete it. Use 'add' and 'remove' to add to or remove from a list, " \
			   "and 'setlist' to change the entire list (';' as separator). The 'reload' triggers reload the setting and key files from disk"
	minPermissionLevel = PermissionLevel.BOT

	def execute(self, message):
		"""
		:type message: IrcMessage
		"""
		replytext = ""
		if message.trigger == 'setting':
			if message.messagePartsLength == 0:
				return message.reply("Please add what I need to do to the settings")

			param = message.messageParts[0].lower()

			#Check for a valid parameter
			if param not in ('list', 'get', 'delete', 'set', 'setlist', 'add', 'remove'):
				return message.reply("I don't know what to do with the parameter '{}', please check your spelling or read the help for this module".format(param))

			settings = message.bot.settings
			if param == 'list':
				return message.reply("Keys in config file: {}".format('; '.join(sorted(settings.keys()))))

			#All other parameters need a key name
			if message.messagePartsLength == 1:
				return message.reply("'{}' what? Please add a config key")

			settingsKey = message.messageParts[1]  #Can't make this lower(), because some keys are camelCase
			if param == 'get':
				if settingsKey in settings:
					if settings[settingsKey] is None:
						return message.reply("Setting '{}' is set to an empty value".format(settingsKey))
					elif isinstance(settings[settingsKey], list):
						if len(settings[settingsKey]) == 0:
							return message.reply("Setting '{}' is an empty list".format(settingsKey))
						else:
							return message.reply("List for setting '{}: {}".format(settingsKey, "; ".join(settings[settingsKey])))
					else:
						return message.reply("Value for setting '{}': {}".format(settingsKey, settings[settingsKey]))
				else:
					return message.reply("The setting '{}' does not exist".format(settingsKey))
			elif param == 'delete':
				if settingsKey not in settings:
					return message.reply("The key '{}' does not exist".format(settingsKey))
				#Store the value in case we need to add it back in
				value = settings[settingsKey]
				del settings[settingsKey]
				try:
					self.verifyAndParseSettings(message.bot, settingsKey, value)
				except SettingException as se:
					# Inform the user something went wrong
					self.logWarning("[changeSettings] Deleting key '{}' resulted in a failed verification: {}".format(settingsKey, se.displayMessage))
					return message.reply("Something went wrong with parsing the settings file after deletion. "
										 "The deleted key-value pair has been added back in. Please check the logs for the error that occurred")
				else:
					return message.reply("Successfully removed setting '{}'".format(settingsKey))

			#All other commands require a third parameter, the new value
			if message.messagePartsLength == 2:
				return message.reply("There seems to be a missing parameter. The format of this command is '{} [field name] [value]".format(param))

			newSettingValue = " ".join(message.messageParts[2:])

			if param == 'set' or param == 'setlist':
				if param == 'set' and settingsKey in settings and isinstance(settings[settingsKey], list):
					return message.reply("The '{}' setting is a list. Use 'add', 'remove', or 'setlist' to alter it".format(settingsKey))
				elif param == 'setlist' and settingsKey in settings and settings[settingsKey] is not None and not isinstance(settings[settingsKey], list):
					return message.reply("The '{}' setting is not a list. Use 'set' to change it".format(settingsKey))
				if param == 'setlist':
					newSettingValue = re.split(r"; ?", newSettingValue)
				#Make sure that keys that should be a number are actually stored as a number
				if settingsKey in settings and isinstance(settings[settingsKey], (int, float)):
					try:
						if isinstance(settings[settingsKey], int):
							newSettingValue = int(newSettingValue)
						else:
							newSettingValue = float(newSettingValue)
					except ValueError:
						return message.reply("'{}' is not a valid number, while the '{}' setting requires a numerical value".format(newSettingValue, settingsKey))
				oldValue = settings.get(settingsKey, None)
				settings[settingsKey] = newSettingValue
				try:
					self.verifyAndParseSettings(message.bot, settingsKey, oldValue)
				except SettingException as se:
					self.logWarning("[changeSettings] Changing setting '{}' from '{}' to '{}' resulted in failed verification: {}".format(settingsKey, oldValue, newSettingValue, se.displayMessage))
					return message.reply("Something went wrong when parsing the change of the value for '{}' to '{}'. Please check the logs".format(settingsKey, settings[settingsKey]))
				else:
					return message.reply("Successfully changed the value for '{}' to '{}'".format(settingsKey, settings[settingsKey]))
			elif param == 'add' or param == 'remove':
				if settingsKey not in settings:
					return message.reply("The setting '{}' does not exist. Check your spelling or use 'setlist' to create the list".format(settingsKey))
				if not isinstance(settings[settingsKey], list):
					return message.reply("The setting '{}' is not a list. Use 'set' to change it".format(settingsKey))
				oldValue = settings[settingsKey]
				if param == 'add':
					settings[settingsKey].append(newSettingValue)
				elif param == 'remove':
					if newSettingValue not in settings[settingsKey]:
						return message.reply("The setting '{}' does not contain the value '{}', so I cannot remove it".format(settingsKey, newSettingValue))
					settings[settingsKey].remove(newSettingValue)
				try:
					self.verifyAndParseSettings(message.bot, settingsKey, oldValue)
				except SettingException as se:
					self.logWarning("[changeSettings] Changing list setting '{}' from '{}' to '{}' resulted in failed verification: {}".format(settingsKey, oldValue, newSettingValue, se.displayMessage))
					return message.reply("Something went wrong when parsing the new settings. Please check the log for errors")
				else:
					return message.reply("Successfully updated the '{}' list".format(settingsKey))

		elif message.trigger == 'reloadsettings':
			argument = None
			if message.messagePartsLength > 0:
				argument = message.message.lower()
			#If the keyword 'all' was provided, reload the settings of all bots
			if argument == "all":
				serversWithReloadFault = []
				for serverfolder, bot in GlobalStore.bothandler.bots.items():
					if not bot.reloadSettings():
						serversWithReloadFault.append(serverfolder)
				replytext = "Reloaded all settings"
				if len(serversWithReloadFault) > 0:
					replytext += " (error reloading settings for {})".format("; ".join(serversWithReloadFault))
			#Load the backup settings
			elif argument == "old" or argument == "previous":
				settingsFilepath = os.path.join(GlobalStore.scriptfolder, "serverSettings", message.bot.serverfolder, "settings.json")
				if not os.path.exists(settingsFilepath + ".old"):
					return message.reply("I don't have a backup settings file, sorry")
				os.rename(settingsFilepath, settingsFilepath + ".new")
				os.rename(settingsFilepath + ".old", settingsFilepath)
				if message.bot.reloadSettings():
					replytext = "Old settings file successfully reloaded"
				else:
					#Loading went wrong, put the other file back
					os.rename(settingsFilepath, settingsFilepath + ".old")
					os.rename(settingsFilepath + ".new", settingsFilepath)
					#And have the bot reload the previous settings
					message.bot.reloadSettings()
					replytext = "Something went wrong when reloading the old settings file, check the log for errors. Original settings file has been reinstated"
			#Otherwise, just reload the settings of this bot
			else:
				if message.bot.reloadSettings():
					replytext = "Successfully reloaded settings for this bot"
				else:
					replytext = "An error occurred while trying to reload the settings for this bot, check the debug output for the cause"
		elif message.trigger == 'reloadkeys':
			#Reload the api keys
			GlobalStore.commandhandler.loadApiKeys()
			replytext = "API keys file reloaded"

		message.reply(replytext)

	def verifyAndParseSettings(self, bot, changedKey=None, oldValue=None):
		try:
			bot.settings.verifySettings()
		except SettingException as se:
			if changedKey is not None:
				bot.settings[changedKey] = oldValue
				self.verifyAndParseSettings(bot, None, None)
			raise se
		else:
			bot.settings.saveSettings()
			bot.parseSettings()
