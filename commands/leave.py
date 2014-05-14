from CommandTemplate import CommandTemplate
from IrcMessage import IrcMessage


class Command(CommandTemplate):
	triggers = ['leave']
	helptext = "Makes me leave the current channel, if you're sure you no longer want me around..."
	
	def execute(self, message):
		"""
		:type message: IrcMessage
		"""
		if message.isPrivateMessage:
			if message.messagePartsLength >= 1:
				message.bot.say("All right, I'll leave '{}' if I'm there")
				if message.messagePartsLength > 1:
					message.bot.leave(message.messageParts[0], " ".join(message.messagePartsLength[1:]))
				else:
					message.bot.leave(message.messageParts[0])
			else:
				message.bot.say("This isn't a channel, this is a private conversation. YOU leave")
		else:
			message.bot.say(message.source, "All right, I'll go... Call me back in when you want me around again!")
			message.bot.leave(message.source)