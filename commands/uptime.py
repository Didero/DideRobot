import datetime, time

from CommandTemplate import CommandTemplate
import SharedFunctions

class Command(CommandTemplate):
	triggers = ['uptime']
	helptext = "Simply shows how long the bot has been online"
	
	def execute(self, bot, user, target, triggerInMsg, msg, msgWithoutFirstWord, msgParts, msgPartsLength):

		uptime = round(time.time() - bot.connectedAt)
		replytext = u"I have been running for {}".format(SharedFunctions.durationSecondsToText(uptime))

		bot.say(target, replytext)

