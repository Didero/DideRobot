from CommandTemplate import CommandTemplate
import GlobalStore

class Command(CommandTemplate):
	triggers = ['restart']
	helptext = "Restarts the bot"
	adminOnly = True

	def execute(self, bot, user, target, triggerInMsg, msg, msgWithoutFirstWord, msgParts, msgPartsLength):
		quitmessage = u"Don't worry, I'll be right back!"
		if msgPartsLength > 1:
			quitmessage = msgWithoutFirstWord
		serverfolder = bot.factory.serverfolder
		GlobalStore.bothandler.stopBotfactory(serverfolder, quitmessage)
		GlobalStore.reactor.callLater(5.0, GlobalStore.bothandler.startBotfactory, serverfolder)