"""A module that responds with basic info when just the bot's name is said"""
from CommandTemplate import CommandTemplate

class Command(CommandTemplate):
	helptext = "SAY MY NAME- I mean, if you just say my name, I'll give you some basic info about myself"

	def shouldExecute(self, bot, commandExecutionClaimed, triggerInMsg, msg, msgParts):
		botnick = bot.nickname.lower()
		#If either the entire message is my nick, or something like 'DideRobot!'
		if msg.lower() == botnick or msg[:-1].lower() == botnick:
			return True
		return False

	def execute(self, bot, user, target, triggerInMsg, msg, msgWithoutFirstWord, msgParts, msgPartsLength):
		bot.say(target, "Hi {0}! My command prefix is {1}. I probably have a {1}help command, try it out!".format(user.split("!", 1)[0], bot.factory.commandPrefix))