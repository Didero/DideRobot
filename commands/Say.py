from commands.CommandTemplate import CommandTemplate
from IrcMessage import IrcMessage
import MessageTypes


class Command(CommandTemplate):
	triggers = ['say', 'do']
	helptext = "Makes the bot say or do the provided text"

	def execute(self, message):
		"""
		:type message: IrcMessage
		"""

		if message.messagePartsLength == 0:
			message.reply("I'm not going to make up something, you have to tell me what to {}!".format(message.trigger))
		else:
			message.reply(message.message, MessageTypes.SAY if message.trigger == 'say' else MessageTypes.ACTION)
