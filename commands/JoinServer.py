from commands.CommandTemplate import CommandTemplate
import GlobalStore, PermissionLevel
from IrcMessage import IrcMessage


class Command(CommandTemplate):
	triggers = ['joinserver']
	helptext = "Makes me join a server, if it's preconfigured."
	minPermissionLevel = PermissionLevel.BOT

	def execute(self, message):
		"""
		:type message: IrcMessage
		"""
		replytext = ""
		if message.messagePartsLength == 0:
			replytext = "Please provide a server name to join"
		#One word was provided, assume it's a preconfigured server folder
		elif message.messagePartsLength == 1:
			success = GlobalStore.bothandler.startBot(message.message)
			if success:
				replytext = "Successfully created new bot instance for server '{}'".format(message.message)
			else:
				replytext = "Something went wrong with trying to create a bot instance for server '{}'. Most likely a typo in the name, or maybe no settings exist yet for that server".format(message.message)
		else:
			replytext = "Just supply a single server name for me to join, I don't know what to do with spaces"

		message.reply(replytext)
