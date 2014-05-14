from CommandTemplate import CommandTemplate
from IrcMessage import IrcMessage


class Command(CommandTemplate):
	triggers = ['join']
	helptext = "Makes me join another channel, if I'm allowed to at least"
	
	def execute(self, message):
		"""
		:type message: IrcMessage
		"""

		replytext = u""
		if message.messagePartsLength < 1:
			replytext = u"Please provide a channel for me to join"
		else:
			allowedChannels = message.bot.factory.settings.get('connection', 'allowedChannels').split(',')
			
			channel = message.messageParts[0]
			if channel.startswith('#'):
				channel = channel[1:]
			if channel not in allowedChannels and not message.bot.factory.isUserAdmin(message.user):
				replytext = u"I'm sorry, I'm not allowed to go there. Please ask my admin(s) for permission"
			else:
				channel = '#' + channel
				replytext = u"All right, I'll go to {}. See you there!".format(channel)
				message.bot.join(channel)
				
		message.bot.say(message.source, replytext)