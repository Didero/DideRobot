from CommandTemplate import CommandTemplate
import GlobalStore
from IrcMessage import IrcMessage


class Command(CommandTemplate):
	triggers = ['joinserver']
	helptext = "Makes me join a server, if it's preconfigured."
	adminOnly = True

	def execute(self, message):
		"""
		:type message: IrcMessage
		"""
		replytext = u""
		if message.messagePartsLength == 0:
			replytext = u"Please provide a server name to join"
		#One word was provided, assume it's a preconfigured server folder
		elif message.messagePartsLength == 1:
			success = GlobalStore.bothandler.startBot(message.message)
			if success:
				replytext = u"Successfully created new bot instance for server '{}'".format(message.message)
			else:
				replytext = u"Something went wrong with trying to create a bot instance for server '{}'. Most likely a typo in the name, or maybe no settings exist yet for that server".format(message.message)
		else:
			replytext = u"Just supply a single server name for me to join, I don't know what to do with spaces"

		message.reply(replytext)
