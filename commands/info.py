from CommandTemplate import CommandTemplate
from IrcMessage import IrcMessage


class Command(CommandTemplate):
	triggers = ['info']
	helptext = "Gives some basic info about the bot"
	
	def execute(self, message):
		"""
		:type message: IrcMessage
		"""

		replytext = u"Hi {nick}, my name is {mynick}. I'm not very old, and my skills include whatever modules I've currently got loaded."
		replytext += u" I'm not sure what else to tell you, really. I probably have a {commandprefix}help module if you want to know what I'm capable of!"
		replytext = replytext.format(nick=message.userNickname, mynick=message.bot.nickname, commandprefix=message.bot.factory.commandPrefix)
		message.reply(replytext, "say")