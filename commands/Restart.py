import os, sys

import gevent

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

			if message.messagePartsLength == 0:
				#restart this bot
				serverfolder = message.bot.serverfolder
			elif message.message in GlobalStore.bothandler.bots:
				#Restart other bot
				serverfolder = message.message
			else:
				message.reply("I'm not familiar with that server, sorry", "say")
				return

			if message.isPrivateMessage:
				#Private message, let the other person know the command was received
				message.reply("All right, restarting, I'll be back in a bit if everything goes well", "say")

			#Restart the bot
			GlobalStore.bothandler.stopBot(serverfolder, "Restarting...")
			GlobalStore.bothandler.startBot(serverfolder)
		elif message.trigger == 'restartfull':
			if message.isPrivateMessage:
				message.reply("Fully restarting bot, hopefully I'll be back in a couple of seconds", "say")
			#Idea from PyMoronBot (as usual)
			self.logInfo("[Restart] Setting '{}' as the commandline arguments".format(*sys.argv))
			# Replace the running process, in a separate Greenlet so this process won't quit until it's called
			gevent.spawn(self.startNewbotProcess)
			#First shut down all bots to make sure the logs are saved properly
			GlobalStore.bothandler.shutdown(quitmessage)

	def startNewbotProcess(self):
		try:
			gevent.sleep(10.0)  #Give everything plenty of time to shut down
			os.execl(sys.executable, sys.executable, *sys.argv)
		except gevent.GreenletExit:
			self.logInfo("[Restart] Bot process creation greenlet killed")
