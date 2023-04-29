import argparse, logging, os, sys
import logging.handlers

import gevent
import gevent.monkey

import GlobalStore
from CommandHandler import CommandHandler
from BotHandler import BotHandler


if __name__ == '__main__':
	#First make sure everything is gevent-compatible
	gevent.monkey.patch_all()

	#Set up fancy argument parsing
	argparser = argparse.ArgumentParser()
	argparser.add_argument("serverlist", help="The comma-separated list of folders in serverSettings that you want to load the config from and start")
	args = argparser.parse_args()

	#Store where in the filesystem we are for future reference
	GlobalStore.scriptfolder = os.path.dirname(os.path.abspath(__file__))

	#Set up error and debug logging
	logger = logging.getLogger('DideRobot')
	logger.setLevel(logging.DEBUG)
	loggingFormatter = logging.Formatter('%(asctime)s (%(levelname)s) %(message)s', datefmt="%Y-%m-%d %H:%M:%S")

	#Log everything to a file. New file each day, keep 2 days
	loggingFileHandler = logging.handlers.TimedRotatingFileHandler(os.path.join(GlobalStore.scriptfolder, 'Program.log'), when='midnight', backupCount=2, delay=True, utc=True, encoding='utf-8')
	loggingFileHandler.setLevel(logging.DEBUG)
	loggingFileHandler.setFormatter(loggingFormatter)
	logger.addHandler(loggingFileHandler)

	#Also print everything to the console
	loggingStreamHandler = logging.StreamHandler(sys.stdout)
	loggingStreamHandler.setLevel(logging.DEBUG)
	loggingStreamHandler.setFormatter(loggingFormatter)
	logger.addHandler(loggingStreamHandler)

	#Start up the CommandHandler and have it load in all the modules
	GlobalStore.commandhandler = CommandHandler()
	GlobalStore.commandhandler.loadCommands()

	#Get the config files we need to load from the argument parser
	serverfolderList = args.serverlist.split(',')
	#Start up the bots
	bothandler = BotHandler(serverfolderList)

	#Only quit once every bot and command finishes running
	gevent.wait()
	logger.info("All bots quit and all commands unloaded, exiting")
