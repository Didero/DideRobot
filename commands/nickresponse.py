"""A module that responds with basic info when just the bot's name is said"""
from CommandTemplate import CommandTemplate

class Command(CommandTemplate):
	helptext = "SAY MY NAME AGAIN- I mean, if you just say my name, I'll give you some basic info about myself"

	def shouldExecute(self, bot, commandExecutionClaimed, triggerInMsg, msg, msgParts):
		if msg.lower() == bot.nickname.lower() or msg[:-1].lower() == bot.nickname.lower():
			return True
		return False

	def execute(self, bot, user, target, triggerInMsg, msg, msgWithoutFirstWord, msgParts, msgPartsLength):
		bot.say(target, "Hi {}! My command prefix is {}".format(user.split("!", 1)[0], bot.factory.commandPrefix))