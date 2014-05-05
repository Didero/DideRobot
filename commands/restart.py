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
			if not target.startswith("#"):
				#Private message, let the other person know the command was received
				bot.say(target, "All right, restarting, I'll be back in a bit if everything goes well")

			serverfolder = u""
			if msgWithoutFirstWord == u"":
				#restart this bot
				serverfolder = bot.factory.serverfolder
			elif msgWithoutFirstWord in GlobalStore.bothandler.botfactories:
				#Restart other bot
				serverfolder = msgWithoutFirstWord
			else:
				bot.say(target, "I'm not familiar with that server, sorry")

			if serverfolder != u"":
				GlobalStore.bothandler.stopBotfactory(serverfolder, quitmessage, True)
				GlobalStore.reactor.callLater(5.0, GlobalStore.bothandler.startBotfactory, serverfolder)
		elif triggerInMsg == 'restartfull':
			if not target.startswith("#"):
				bot.say(target, "Fully restarting bot, hopefully I'll be back in a couple of seconds")
			#Idea from PyMoronBot (as usual)
			#First shut down all bots to make sure the logs are saved properly
			GlobalStore.bothandler.shutdown(quitmessage)
			#Replace the running process
			print "Setting '{}' as the commandline arguments".format(*sys.argv)
			GlobalStore.reactor.callLater(2.0, os.execl, sys.executable, sys.executable, *sys.argv)