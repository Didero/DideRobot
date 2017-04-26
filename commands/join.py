from CommandTemplate import CommandTemplate
from IrcMessage import IrcMessage


class Command(CommandTemplate):
	triggers = ['join']
	helptext = "Makes me join another channel, if I'm allowed to at least"
	
	def execute(self, message):
		"""
		:type message: IrcMessage
		"""

		if message.messagePartsLength < 1:
			replytext = "Please provide a channel for me to join"
		else:
			channel = message.messageParts[0].lower()
			#Strip all possible channel prefixes
			channelWithoutPrefix = channel.lstrip("#&!+.~")

			if channel in message.bot.channelsUserList or '#' + channelWithoutPrefix in message.bot.channelsUserList:
				replytext = "I'm already there, waiting for you. You're welcome!"
			elif channelWithoutPrefix not in message.bot.factory.settings['allowedChannels'] and not message.bot.factory.isUserAdmin(message.user, message.userNickname, message.userAddress):
				replytext = "I'm sorry, I'm not allowed to go there. Please ask my admin(s) for permission"
			else:
				replytext = "All right, I'll go to '{}'. See you there!".format(channel)
				message.bot.join(channel)

		message.reply(replytext, "say")
