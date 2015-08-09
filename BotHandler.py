import logging, os

from DideRobotFactory import DideRobotFactory
import GlobalStore


class BotHandler:
	botfactories = {}

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
				self.startBotfactory(serverfolder)

	def startBotfactory(self, serverfolder):
		if serverfolder in self.botfactories:
			self.logger.warning("BotHandler got command to join server which I'm already on, '{}'".format(serverfolder))
			return False
		if not os.path.exists(os.path.join(GlobalStore.scriptfolder, 'serverSettings', serverfolder)):
			self.logger.error("BotHandler got command to join server '{}', which I don't have settings for".format(serverfolder))
			return False
		#Start the bot, woo!
		botfactory = DideRobotFactory(serverfolder)
		self.botfactories[serverfolder] = botfactory
		return True

	def stopBotfactory(self, serverfolder, quitmessage="Quitting...", isRestarting=False):
		quitmessage = quitmessage.encode('utf-8')
		if serverfolder not in self.botfactories:
			self.logger.warning("Asked to stop unknown botfactory '{}'!".format(serverfolder))
			return False
		else:
			self.botfactories[serverfolder].shouldReconnect = False
			self.botfactories[serverfolder].bot.quit(quitmessage)
			self.unregisterFactory(serverfolder, isRestarting)
			return True

	def shutdown(self, quitmessage='Shutting down...'):
		#Give all modules a chance to close properly
		GlobalStore.commandhandler.unloadAllCommands()
		#Give all bots the same quit message
		quitmessage = quitmessage.encode('utf-8')
		for serverfolder, botfactory in self.botfactories.iteritems():
			if botfactory.bot:
				botfactory.shouldReconnect = False
				botfactory.bot.quit(quitmessage)
		self.botfactories = {}
		#Give all bots a little time to shut down
		GlobalStore.reactor.callLater(4.0, GlobalStore.reactor.stop)

	def unregisterFactory(self, serverfolder, isRestarting=False):
		if serverfolder in self.botfactories:
			del self.botfactories[serverfolder]
			#If there's no more bots running, there's no need to hang about
			if len(self.botfactories) == 0:
				if isRestarting:
					self.logger.info("Last bot unregistered, not shutting down because restart expected")
				else:
					self.logger.info("Out of bots, shutting down!")
					GlobalStore.reactor.callLater(2.0, GlobalStore.reactor.stop)
			else:
				self.logger.info("Successfully unregistered bot '{}', {} bots left: {}".format(serverfolder, len(self.botfactories), "; ".join(self.botfactories.keys())))
