from CommandTemplate import CommandTemplate
import GlobalStore

class Command(CommandTemplate):
	triggers = ['debug']
	helptext = "Used in debugging. Only really useful to my owner"
	showInCommandList = False
	adminOnly = True

	def execute(self, bot, user, target, triggerInMsg, msg, msgWithoutFirstWord, msgParts, msgPartsLength):
		for serverfolder, botfactory in GlobalStore.bothandler.botfactories.iteritems():
			print "Channel and user list for {}:".format(botfactory.serverfolder)
			print botfactory.bot.channelsUserList