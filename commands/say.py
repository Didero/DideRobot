from CommandTemplate import CommandTemplate
from IrcMessage import IrcMessage


class Command(CommandTemplate):
	triggers = ['say', 'do', 'notice']
	helptext = "Makes the bot say the provided text in the provided channel  (format 'say [channel/user] text')"
	adminOnly = True
	showInCommandList = False

	def execute(self, message):
		"""
		:type message: IrcMessage
		"""
		if message.messagePartsLength < 2:
			message.bot.say(message.source, u"Please provide both a channel or user name to say something to, and the text to say")
		#Check if we're in the channel we have to say something to
		elif not message.isPrivateMessage and message.messageParts[0] not in message.bot.channelsUserList:
			message.bot.say(message.source, u"I'm not in that channel, so I can't say anything in there, sorry.")
		#Nothing's stopping us now! Say it!
		else:
			messageToSay = u" ".join(message.messageParts[1:])
			messageType = u'say'
			if message.trigger == u'do':
				messageType = u'action'
			elif message.trigger == u'notice':
				messageType = u'notice'

			message.bot.sendMessage(message.messageParts[0], messageToSay, messageType)
