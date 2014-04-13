import base64, json, os, random
from ConfigParser import ConfigParser

import requests

from CommandTemplate import CommandTemplate
import GlobalStore
import SharedFunctions

class Command(CommandTemplate):
	triggers = ['startrektip', 'sttip', 'startrektips']
	helptext = "Shows a randomly chosen tip from one of the Star Trek Tips accounts, or of a specific one if a name is provided"
	twitterUsernames = {'data': 'Data_Tips', 'guinan': 'GuinanTips', 'laforge': 'LaForgeTips', 'locutus': 'LocutusTips', 'picard': 'PicardTips', 'quark': 'QuarkTips', 'riker': 'RikerTips', 'worf': 'WorfTips'}
	scheduledFunctionTime = 18000.0 #Every 5 hours

	isUpdating = False

	def execute(self, bot, user, target, triggerInMsg, msg, msgWithoutFirstWord, msgParts, msgPartsLength):
		name = ""
		if msgPartsLength > 1:
			name = msgParts[1].lower()
		if name == 'random':
			name = random.choice(self.twitterUsernames.keys())

		replytext = ""
		if name in self.twitterUsernames:
			replytext = SharedFunctions.getRandomLineFromTwitterFile(self.twitterUsernames[name])
			if not replytext.lower().startswith(name):
				replytext = u"{} tip: {}".format(name[0:1].upper() + name[1:], replytext)
		else:
			if name != "":
				replytext = "I don't know anybody by the name of '{}', sorry. ".format(name)
			replytext += "Type '{}{} <name>' to hear one of <name>'s tips, or use 'random' to have me pick a name for you. ".format(bot.factory.commandPrefix, triggerInMsg)
			replytext += "Available tip-givers: {}".format(", ".join(sorted(self.twitterUsernames.keys())))

		replytext = replytext.encode('utf-8', 'replace')
		bot.say(target, replytext)


	def executeScheduledFunction(self):
		GlobalStore.reactor.callInThread(self.updateTwitterMessages)

	def updateTwitterMessages(self):
		self.isUpdating = True
		for name, username in self.twitterUsernames.iteritems():
			#print "Updating stored twitter messages for '{}'".format(username)
			SharedFunctions.downloadNewTweets(username)
		self.isUpdating = False
