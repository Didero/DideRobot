import argparse, os, sys
#Make sure 'import' also searches inside the 'libraries' folder, so those libs don't clutter up the main directory
sys.path.append(os.path.join(os.path.dirname(os.path.abspath(__file__)), 'libraries'))

from twisted.internet import reactor

import GlobalStore
from CommandHandler import CommandHandler
from BotHandler import BotHandler


#Set up fancy argument parsing
argparser = argparse.ArgumentParser()
argparser.add_argument("serverlist", help="The comma-separated list of folders in serverSettings that you want to load the config from and start")
args = argparser.parse_args()

#Store where in the filesystem we are for future reference
GlobalStore.scriptfolder = os.path.dirname(os.path.abspath(__file__))

#Some commands need the reactor, register it already
GlobalStore.reactor = reactor

#Start up the CommandHandler and have it load in all the modules
GlobalStore.commandhandler = CommandHandler()
GlobalStore.commandhandler.loadCommands()

#Get the config files we need to load from the argument parser
serverfolderList = args.serverlist.split(',')
#Start up the bots
bothandler = BotHandler(serverfolderList)

#Finally, set the whole thing off
GlobalStore.reactor.run()
