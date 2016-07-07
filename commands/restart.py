import os, sys

from CommandTemplate import CommandTemplate
import GlobalStore
from IrcMessage import IrcMessage


class Command(CommandTemplate):
	triggers = ['restart', 'restartfull']
	helptext = "Restarts the bot instance or the whole program"
	adminOnly = True
	stopAfterThisCommand = True

	def execute(self, message):
		"""
		:type message: IrcMessage
		"""
		quitmessage = u"Don't worry, I'll be right back!"
		if message.messagePartsLength > 0:
			quitmessage = message.message

		if message.trigger == 'restart':
			if message.isPrivateMessage:
				#Private message, let the other person know the command was received
				message.bot.say(message.source, "All right, restarting, I'll be back in a bit if everything goes well")

			serverfolder = u""
			if message.messagePartsLength == 0:
				#restart this bot
				serverfolder = message.bot.factory.serverfolder
			elif message.message in GlobalStore.bothandler.botfactories:
				#Restart other bot
				serverfolder = message.message
			else:
				message.bot.say(message.source, "I'm not familiar with that server, sorry")

			if serverfolder != u"":
				GlobalStore.bothandler.stopBotfactory(serverfolder, quitmessage, True)
				GlobalStore.reactor.callLater(5.0, GlobalStore.bothandler.startBotfactory, serverfolder)
		elif message.trigger == 'restartfull':
			if message.isPrivateMessage:
				message.bot.say(message.source, "Fully restarting bot, hopefully I'll be back in a couple of seconds")
			#Idea from PyMoronBot (as usual)
			#First shut down all bots to make sure the logs are saved properly
			GlobalStore.bothandler.shutdown(quitmessage)
			#Replace the running process
			self.logInfo("[Restart] Setting '{}' as the commandline arguments".format(*sys.argv))
			GlobalStore.reactor.callLater(2.0, os.execl, sys.executable, sys.executable, *sys.argv)