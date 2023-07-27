from commands.CommandTemplate import CommandTemplate
from IrcMessage import IrcMessage
import PermissionLevel


class Command(CommandTemplate):
	triggers = ['nick', 'nickname']
	helptext = "Changes my nick to the provided new one, assuming it's not taken. If no argument is provided, try to change back to the default as set in the server settings"
	minPermissionLevel = PermissionLevel.SERVER
	
	def execute(self, message):
		"""
		:type message: IrcMessage
		"""
		if message.messagePartsLength == 0:
			#Change nick back to the default
			message.bot.setNick(message.bot.settings['nickname'])
		else:
			message.bot.setNick(message.messageParts[0])
