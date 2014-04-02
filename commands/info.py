import os

from CommandTemplate import CommandTemplate

class Command(CommandTemplate):
	triggers = ['info']
	helptext = "Gives some info about the bot. Mainly used for debugging now"
	
	def execute(self, bot, user, target, triggerInMsg, msg, msgWithoutFirstWord, msgParts, msgPartsLength):

		replytext = u"Hi {nick}, my name is {mynick}. I'm not very old, and my skills include whatever modules I've currently got loaded."
		replytext += u" I'm not sure what else to tell you, really. I probably have a {commandprefix}help module if you want to know what I'm capable of!"
		replytext = replytext.format(nick=user.split("!", 1)[0], mynick=bot.nickname, commandprefix=bot.factory.commandPrefix)
		bot.say(target, replytext)