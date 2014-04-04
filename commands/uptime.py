import datetime, time

from CommandTemplate import CommandTemplate

class Command(CommandTemplate):
	triggers = ['uptime']
	helptext = "Simply shows how long the bot has been online"
	
	def execute(self, bot, user, target, triggerInMsg, msg, msgWithoutFirstWord, msgParts, msgPartsLength):

		uptime = round(time.time() - bot.connectedAt)
		minutes, seconds = divmod(uptime, 60)
		hours, minutes = divmod(minutes, 60)
		days, hours = divmod(hours, 24)

		replytext = u"I have been running for "
		if days > 0:
			replytext += u"{:,.0f} days, ".format(days)
		if hours > 0:
			replytext += u"{:,.0f} hours, ".format(hours)
		if minutes > 0:
			replytext += u"{:,.0f} minutes, ".format(minutes)
		replytext += u"{:,.0f} seconds".format(seconds)

		bot.say(target, replytext)

