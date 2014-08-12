import os, sys
#Make sure 'import' also searches inside the 'libraries' folder, so those libs don't clutter up the main directory
sys.path.append(os.path.join(os.path.dirname(os.path.abspath(__file__)), 'libraries'))

from twisted.internet import reactor

import GlobalStore
from CommandHandler import CommandHandler
from BotHandler import BotHandler


if __name__ == "__main__":
	#Store where in the filesystem we are for future reference
	GlobalStore.scriptfolder = os.path.dirname(os.path.abspath(__file__))

	#Some commands need the reactor, register it already
	GlobalStore.reactor = reactor

	#Start up the CommandHandler and have it load in all the modules
	GlobalStore.commandhandler = CommandHandler()
	GlobalStore.commandhandler.loadCommands()

	#Get the settings location and log target location from the command line
	serverfolderList = sys.argv[1].split(',')
	print "Server folder list: '{}'".format(sys.argv[1], serverfolderList)
	bothandler = BotHandler(serverfolderList)

	#Finally, start the whole thing
	GlobalStore.reactor.run()
