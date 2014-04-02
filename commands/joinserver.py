from CommandTemplate import CommandTemplate
import GlobalStore

class Command(CommandTemplate):
	triggers = ['joinserver']
	helptext = "Makes me join a server, if it's preconfigured."
	adminOnly = True

	def execute(self, bot, user, target, triggerInMsg, msg, msgWithoutFirstWord, msgParts, msgPartsLength):
		replytext = u""
		if msgPartsLength == 1:
			replytext = u"Please provide a server name to join"
		else:
			success = GlobalStore.bothandler.startBotfactory(msgWithoutFirstWord)
			if success:
				replytext = u"Successfully created new bot instance for server '{}'".format(msgWithoutFirstWord)
			else:
				replytext = u"Something went wrong with trying to create a bot instance for server '{}'. Most likely a typo in the name, or maybe no settings exist yet for that server".format(msgWithoutFirstWord)

		bot.say(target, replytext)