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
		#Assume a non-preconfigured server is entered, in a JSON way, so 'server: irc.server.com'
		elif message.messagePartsLength > 1 or ":" in message.message:
			replytext = u"Oh, being fancy, are we? This'll be implemented in a bit, but good on you for trying!"
		#One word was provided, assume it's a preconfigured server folder
		elif message.messagePartsLength == 1:
			success = GlobalStore.bothandler.startBotfactory(message.message)
			if success:
				replytext = u"Successfully created new bot instance for server '{}'".format(message.message)
			else:
				replytext = u"Something went wrong with trying to create a bot instance for server '{}'. Most likely a typo in the name, or maybe no settings exist yet for that server".format(message.message)

		message.reply(replytext, "say")