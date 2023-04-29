import time

from commands.CommandTemplate import CommandTemplate
from IrcMessage import IrcMessage
from util import DateTimeUtil


class Command(CommandTemplate):
	triggers = ['uptime']
	helptext = "Simply shows how long the bot has been online"
	
	def execute(self, message):
		"""
		:type message: IrcMessage
		"""
		uptime = round(time.time() - message.bot.connectedAt)
		message.reply("I have been running for {}".format(DateTimeUtil.durationSecondsToText(uptime, numberOfParts=0)))
