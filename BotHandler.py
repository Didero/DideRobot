import os, sys
#Make sure 'import' also searches inside the 'libraries' folder, so it can find Twisted and the like without those libs cluttering up the main directory
sys.path.append(os.path.join(os.path.dirname(os.path.abspath(__file__)), 'libraries'))

from twisted.internet import reactor

from DideRobot import DideRobot, DideRobotFactory
import GlobalStore
from CommandHandler import CommandHandler


class BotHandler:
	botfactories = {}

	def __init__(self, serverfolderList):
		GlobalStore.bothandler = self
		GlobalStore.scriptfolder = os.path.dirname(os.path.abspath(__file__))

		#Since a lot of modules save stuff to the 'data' subfolder, make sure it exists to save all of them some checking time
		if not os.path.exists(os.path.join(GlobalStore.scriptfolder, 'data')):
			os.mkdir(os.path.join(GlobalStore.scriptfolder, 'data'))

		if not os.path.exists(os.path.join(GlobalStore.scriptfolder, 'serverSettings', 'globalsettings.ini')):
			print "ERROR: 'globalsettings.ini' file not found in 'serverSettings' folder! Shutting down"
			self.shutdown()
		else:		
			for serverfolder in serverfolderList:
				self.startBotfactory(serverfolder)

			GlobalStore.commandhandler = CommandHandler()
			GlobalStore.commandhandler.loadCommands()
			GlobalStore.reactor.run()

	def startBotfactory(self, serverfolder):
		if serverfolder in self.botfactories:
			print "BotHandler got command to join server which I'm already on, '{}'".format(serverfolder)
			return False

		if not os.path.exists(os.path.join(GlobalStore.scriptfolder, 'serverSettings', serverfolder)):
			print "BotHandler got command to join server '{}', which I don't have settings for".format(serverfolder)
			return False

		print "Launching bot for server '{}'!".format(serverfolder)

		#Start the bot, woo!
		botfactory = DideRobotFactory(serverfolder)
		self.botfactories[serverfolder] = botfactory
		return True

	def stopBotfactory(self, serverfolder, quitmessage="Quitting...", isRestarting=False):
		quitmessage = quitmessage.encode('utf-8')
		if serverfolder not in self.botfactories:
			print "ERROR: Asked to stop an unknown botfactory '{}'!".format(serverfolder)
			return False
		else:
			self.botfactories[serverfolder].shouldReconnect = False
			self.botfactories[serverfolder].bot.quit(quitmessage)
			self.unregisterFactory(serverfolder, isRestarting)
			return True

	def shutdown(self, quitmessage='Shutting down...'):
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
					print "Last bot unregistered, not shutting down because restart expected"
				else:
					print "Out of bots, shutting down!"
					GlobalStore.reactor.callLater(2.0, GlobalStore.reactor.stop)
			else:
				print "Successfully unregistered bot '{}', {} bots left: {}".format(serverfolder, len(self.botfactories), "; ".join(self.botfactories.keys()))

if __name__ == "__main__":
	GlobalStore.reactor = reactor
	#Get the settings location and log target location from the command line
	serverfolderList = sys.argv[1].split(',')
	print "First argument: '{}'; Server folder list: '{}'".format(sys.argv[1], serverfolderList)
	bothandler = BotHandler(serverfolderList)