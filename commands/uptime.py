import time

from CommandTemplate import CommandTemplate

class Command(CommandTemplate):
	triggers = ['uptime']
	helptext = "Simply shows how long the bot has been online"
	
	def execute(self, bot, user, target, triggerInMsg, msg, msgWithoutFirstWord, msgParts, msgPartsLength):

		uptime = time.time() - bot.connectedAt

		replytext = u"I have been running for {:,} seconds".format(round(uptime, 1))
		bot.say(target, replytext)

