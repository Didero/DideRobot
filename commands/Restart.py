import os, sys

import gevent

from CommandTemplate import CommandTemplate
import GlobalStore
from IrcMessage import IrcMessage
from CustomExceptions import CommandInputException


class Command(CommandTemplate):
	triggers = ['restart', 'restartother', 'restartfull']
	helptext = "Restarts the bot instance or the whole program"
	adminOnly = True
	stopAfterThisCommand = True

	def execute(self, message):
		"""
		:type message: IrcMessage
		"""
		quitmessage = u"Don't worry, I'll be right back!"

		if message.trigger == 'restart':
			if message.isPrivateMessage:
				#Private message, let the other person know the command was received
				message.reply("All right, restarting, I'll be back in a bit if everything goes well")

			#Restart the bot
			if message.messagePartsLength > 0:
				quitmessage = message.message
			GlobalStore.bothandler.stopBot(message.bot.serverfolder, quitmessage)
			GlobalStore.bothandler.startBot(message.bot.serverfolder)

		elif message.trigger == 'restartother':
			if message.messagePartsLength == 0:
				raise CommandInputException("Please provide the name of the server where I should restart the bot")
			if message.messageParts[0] not in GlobalStore.bothandler.bots:
				raise CommandInputException("I'm not familiar with a server called '{}', sorry. Maybe you made a typo?".format(message.messageParts[0]))
			servername = message.messageParts[0]

			message.reply("Ok, restarting the '{}' bot".format(servername))
			if message.messagePartsLength > 1:
				quitmessage = " ".join(message.messageParts[1:])
			GlobalStore.bothandler.stopBot(servername, quitmessage)
			GlobalStore.bothandler.startBot(servername)

		elif message.trigger == 'restartfull':
			if message.isPrivateMessage:
				message.reply("Fully restarting bot, hopefully I'll be back in a couple of seconds")
			self.logInfo("[Restart] Setting '{}' as the commandline arguments".format(*sys.argv))
			# Replace the running process, in a separate Greenlet so this process won't quit until it's called
			gevent.spawn(self.startNewbotProcess)
			# Shut down all bots to make sure the logs are saved properly
			if message.messagePartsLength > 0:
				quitmessage = message.message
			GlobalStore.bothandler.shutdown(quitmessage)

	def startNewbotProcess(self):
		try:
			gevent.sleep(10.0)  #Give everything plenty of time to shut down
			os.execl(sys.executable, sys.executable, *sys.argv)
		except gevent.GreenletExit:
			self.logInfo("[Restart] Bot process creation greenlet killed")
