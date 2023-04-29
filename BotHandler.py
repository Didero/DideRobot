import logging, os

import gevent

from DideRobot import DideRobot
import GlobalStore


class BotHandler:
	bots = {}  #Keys are serverfolder names, value is the bot instance for that serverfolder

	def __init__(self, serverfolderList):
		self.logger = logging.getLogger('DideRobot')
		GlobalStore.bothandler = self

		#Since a lot of modules save stuff to the 'data' subfolder, make sure it exists to save all of them some checking time
		if not os.path.exists(os.path.join(GlobalStore.scriptfolder, 'data')):
			os.mkdir(os.path.join(GlobalStore.scriptfolder, 'data'))

		if not os.path.exists(os.path.join(GlobalStore.scriptfolder, 'serverSettings', 'globalsettings.json')):
			self.logger.critical("'globalsettings.json' file not found in 'serverSettings' folder! Shutting down")
			self.shutdown()
		else:		
			for serverfolder in serverfolderList:
				gevent.spawn(self.startBot, serverfolder)

	def startBot(self, serverfolder):
		if serverfolder in self.bots:
			self.logger.warning("BotHandler got command to join server which I'm already on, '{}'".format(serverfolder))
			return False
		if not os.path.exists(os.path.join(GlobalStore.scriptfolder, 'serverSettings', serverfolder)):
			self.logger.error("BotHandler got command to join server '{}', which I don't have settings for".format(serverfolder))
			return False
		#Start the bot, woo!
		self.bots[serverfolder] = DideRobot(serverfolder)
		return True

	def stopBot(self, serverfolder, quitmessage="Quitting..."):
		if serverfolder not in self.bots:
			self.logger.warning("Asked to stop unknown bot '{}'!".format(serverfolder))
			return False
		self.bots[serverfolder].quit(quitmessage)
		return True

	def unregisterBot(self, serverfolder):
		if serverfolder not in self.bots:
			self.logger.warning("Asked to unregister non-registered bot '{}'".format(serverfolder))
		else:
			del self.bots[serverfolder]
			self.logger.info("Successfully unregistered bot '{}'".format(serverfolder))
		#If there's no more bots running, there's no need to hang about
		if len(self.bots) == 0:
			self.logger.info("Out of bots, shutting down!")
			#Unload all commands. This will mean there won't be any greenlets left running, so the main loop will quit
			GlobalStore.commandhandler.unloadAllCommands()

	def shutdown(self, quitmessage='Shutting down...'):
		#Give all bots the same quit message
		for serverfolder in self.bots.keys():
			self.stopBot(serverfolder, quitmessage)
