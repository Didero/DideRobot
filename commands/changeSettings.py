from CommandTemplate import CommandTemplate
import GlobalStore
from IrcMessage import IrcMessage


class Command(CommandTemplate):
	triggers = ['setting', 'reloadsettings', 'reloadkeys']
	helptext = "Used to view or change bot settings. See all keys with the parameter 'list', or use 'get' to see a single value. " \
			   "Use 'set' to change a value or 'delete' to delete it. Use 'add' and 'remove' to add to or remove from a list, " \
			   "and 'setlist' to change the entire list (';' as separator). The 'reload' triggers reload the setting and key files from disk"
	adminOnly = True

	def execute(self, message):
		"""
		:type message: IrcMessage
		"""
		replytext = u""
		if message.trigger == 'setting':
			if message.messagePartsLength == 0:
				return message.reply(u"Please add what I need to do to the config")

			param = message.messageParts[0].lower()

			#Check for a valid parameter
			if param not in ('list', 'get', 'delete', 'set', 'setlist', 'add', 'remove'):
				return message.reply(u"I don't know what to do with the parameter '{}', please check your spelling or read the help for this module".format(param))

			settings = message.bot.factory.settings
			if param == 'list':
				return message.reply(u"Keys in config file: {}".format('; '.join(sorted(settings.keys()))))

			#All other parameters need a key name
			if message.messagePartsLength == 1:
				return message.reply(u"'{}' what? Please add a config key")

			settingsKey = message.messageParts[1]  #Can't make this lower(), because some keys are camelCase
			if param == 'get':
				if settingsKey in settings:
					if isinstance(settings[settingsKey], list):
						return message.reply(u"List for '{}: {}".format(settingsKey, u"; ".join(settings[settingsKey])))
					else:
						return message.reply(u"Value for '{}': {}".format(settingsKey, settings[settingsKey]))
				else:
					return message.reply(u"The settings key '{}' does not exist".format(settingsKey))
			elif param == 'delete':
				if settingsKey not in settings:
					return message.reply(u"The key '{}' does not exist".format(settingsKey))
				del settings[settingsKey]
				if message.bot.factory.verifySettings():
					message.bot.factory.saveSettings()
					message.bot.factory.parseSettings()
					return message.reply(u"Successfully removed setting '{}'".format(settingsKey))
				else:
					return message.reply(u"Something went wrong with parsing the settings file after deletion. Please check the logs")

			#All other commands require a third parameter, the new value
			if message.messagePartsLength == 2:
				return message.reply(u"Please add a new value to change '{}' to".format(message.messageParts[1]))

			newSettingValue = " ".join(message.messageParts[2:])

			if param == 'set' or param == 'setlist':
				if param == 'set' and settingsKey in settings and isinstance(settings[settingsKey], list):
					return message.reply(u"The '{}' setting is a list. Use 'add', 'remove', or 'setlist' to alter it".format(settingsKey))
				elif param == 'setlist' and settingsKey in settings and settings[settingsKey] is not None and not isinstance(settings[settingsKey], list):
					return message.reply(u"The '{}' setting is not a list. Use 'set' to change it".format(settingsKey))
				if param == 'setlist':
					newSettingValue = newSettingValue.split('; ')
				#Make sure that keys that should be a number are actually stored as a number
				if settingsKey in settings and isinstance(settings[settingsKey], (int, float)):
					try:
						if isinstance(settings[settingsKey], int):
							newSettingValue = int(newSettingValue)
						else:
							newSettingValue = float(newSettingValue)
					except ValueError:
						return message.reply(u"'{}' is not a valid number, while the '{}' setting requires a numerical value".format(newSettingValue, settingsKey))
				settings[settingsKey] = newSettingValue
				if message.bot.factory.verifySettings():
					message.bot.factory.saveSettings()
					message.bot.factory.parseSettings()
					return message.reply(u"Successfully changed the value for '{}' to '{}'".format(settingsKey, settings[settingsKey]))
				else:
					return message.reply(u"Something went wrong when parsing the change of the value for '{}' to '{}'. Please check the logs".format(settingsKey, settings[settingsKey]))
			elif param == 'add' or param == 'remove':
				if settingsKey not in settings:
					return message.reply(u"The setting '{}' does not exist. Check your spelling or use 'setlist' to create the list")
				if not isinstance(settings[settingsKey], list):
					return message.reply(u"The setting '{}' is not a list. Use 'set' to change it".format(settingsKey))
				if param == 'add':
					settings[settingsKey].append(newSettingValue)
				elif param == 'remove':
					if newSettingValue not in settings[settingsKey]:
						return message.reply(u"The setting '{}' does not contain the value '{}', so I cannot remove it".format(settingsKey, newSettingValue))
					settings[settingsKey].remove(newSettingValue)
				if message.bot.factory.verifySettings():
					message.bot.factory.saveSettings()
					message.bot.factory.parseSettings()
					return message.reply(u"Successfully updated the '{}' list".format(settingsKey))
				else:
					return message.reply(u"Something went wrong when parsing the new settings. Please check the log for errors")

		elif message.trigger == 'reloadsettings':
			#If the keyword 'all' was provided, reload the settings of all bots
			if message.message.lower() == "all":
				serversWithReloadFault = []
				for serverfolder, botfactory in GlobalStore.bothandler.botfactories.iteritems():
					if not botfactory.loadSettings():
						serversWithReloadFault.append(serverfolder)
				replytext = u"Reloaded all settings"
				if len(serversWithReloadFault) > 0:
					replytext += u" (error reloading settings for {})".format("; ".join(serversWithReloadFault))
			#Otherwise, just reload the settings of this bot
			else:
				if message.bot.factory.loadSettings():
					replytext = u"Successfully reloaded settings for this bot"
				else:
					replytext = u"An error occurred while trying to reload the settings for this bot, check the debug output for the cause"
		elif message.trigger == 'reloadkeys':
			#Reload the api keys
			GlobalStore.commandhandler.loadApiKeys()
			replytext = u"API keys file reloaded"

		message.reply(replytext)