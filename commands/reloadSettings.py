from CommandTemplate import CommandTemplate
import GlobalStore

class Command(CommandTemplate):
	triggers = ['reloadsettings']
	helptext = "Reloads the settings from disk. Only rarely useful"
	adminOnly = True

	def execute(self, bot, user, target, triggerInMsg, msg, msgWithoutFirstWord, msgParts, msgPartsLength):
		for serverfolder, botfactory in GlobalStore.bothandler.botfactories.iteritems():
			botfactory.updateSettings()
		bot.say(target, "Reloaded all settings")