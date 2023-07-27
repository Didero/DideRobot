from commands.CommandTemplate import CommandTemplate
from IrcMessage import IrcMessage
import PermissionLevel


class Command(CommandTemplate):
	triggers = ['leave']
	helptext = "Makes me leave the current channel, if you're sure you no longer want me around..."
	
	def execute(self, message):
		"""
		:type message: IrcMessage
		"""
		if message.isPrivateMessage:
			if message.messagePartsLength >= 1:
				if not message.doesSenderHavePermission(PermissionLevel.SERVER):
					return message.reply("Only server admins can make me leave a channel remotely, sorry")
				message.reply("All right, I'll leave '{}' if I'm there")
				if message.messagePartsLength > 1:
					message.bot.leaveChannel(message.messageParts[0], " ".join(message.messagePartsLength[1:]))
				else:
					message.bot.leaveChannel(message.messageParts[0])
			else:
				message.reply("This isn't a channel, this is a private conversation. YOU leave")
		elif not message.doesSenderHavePermission(PermissionLevel.CHANNEL):
			return message.reply("Only channel admins can make me leave, sorry. Tell one of them you don't want me around anymore, maybe they also don't like me...")
		else:
			message.reply("All right, I'll go... Call me back in when you want me around again!")
			message.bot.leaveChannel(message.source)
