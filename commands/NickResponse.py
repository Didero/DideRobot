from commands.CommandTemplate import CommandTemplate

from IrcMessage import IrcMessage
import MessageTypes


class Command(CommandTemplate):
	"""A module that responds with basic info when just the bot's name is said"""
	helptext = "SAY MY NAME- I mean, if you just say my name, I'll give you some basic info about myself"

	def shouldExecute(self, message):
		if message.messageType != MessageTypes.SAY:
			return False
		botnick = message.bot.nickname.lower()
		text = message.rawText.lower()
		#If either the entire message is my nick, or something like 'DideRobot!'
		if text == botnick or text[:-1] == botnick:
			return True
		return False

	def execute(self, message):
		"""
		:type message: IrcMessage
		"""
		message.reply("Hi {0}! My command prefix is {1}. I probably have a {1}help command, try it out!".format(message.userNickname, message.bot.getCommandPrefix(message.source)))
