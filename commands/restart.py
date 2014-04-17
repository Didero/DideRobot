import os, sys

from CommandTemplate import CommandTemplate
import GlobalStore

class Command(CommandTemplate):
	triggers = ['restart', 'restartfull']
	helptext = "Restarts the bot instance or the whole program"
	adminOnly = True

	def execute(self, bot, user, target, triggerInMsg, msg, msgWithoutFirstWord, msgParts, msgPartsLength):
		quitmessage = u"Don't worry, I'll be right back!"
		if msgPartsLength > 1:
			quitmessage = msgWithoutFirstWord

		if triggerInMsg == 'restart':
			serverfolder = bot.factory.serverfolder
			GlobalStore.bothandler.stopBotfactory(serverfolder, quitmessage, True)
			GlobalStore.reactor.callLater(5.0, GlobalStore.bothandler.startBotfactory, serverfolder)
		elif triggerInMsg == 'restartfull':
			#Idea from PyMoronBot (as usual)
			#First shut down all bots to make sure the logs are saved properly
			GlobalStore.bothandler.shutdown(quitmessage)
			#Replace the running process
			print "Setting '{}' as the commandline arguments".format(*sys.argv)
			GlobalStore.reactor.callLater(2.0, os.execl, sys.executable, sys.executable, *sys.argv)