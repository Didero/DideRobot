import datetime, time

from CommandTemplate import CommandTemplate
import SharedFunctions
from IrcMessage import IrcMessage


class Command(CommandTemplate):
	triggers = ['uptime']
	helptext = "Simply shows how long the bot has been online"
	
	def execute(self, message):
		"""
		:type message: IrcMessage
		"""
		uptime = round(time.time() - message.bot.connectedAt)
		message.reply(u"I have been running for {}".format(SharedFunctions.durationSecondsToText(uptime)), "say")
