from CommandTemplate import CommandTemplate
import GlobalStore
from IrcMessage import IrcMessage


class Command(CommandTemplate):
	triggers = ['quit', 'shutdown']
	helptext = "Shuts down the bot. {commandPrefix}quit closes down just this bot, {commandPrefix}shutdown shuts down all instances of DideRobot on all servers it's connected to"
	adminOnly = True
	stopAfterThisCommand = True  #Since 'shutdown' unloads all the modules, prevent iteration errors, even though it shouldn't matter much
	
	def execute(self, message):
		"""
		:type message: IrcMessage
		"""
		if message.trigger == 'quit':
			#Just quit this server
			message.bot.factory.messageLogger.log("{0} told me to quit in channel {1}, obliging".format(message.user, message.source))
		

			quitmessage = "{0} told me to quit, so here I go..."
			if message.messagePartsLength > 0:
				quitmessage = message.message

			#Replace the first argument with the caller's name, for fun possibilities
			quitmessage = quitmessage.format(nick=message.userNickname)

			#You don't see quit messages in PMs, inform the user anyway
			if message.isPrivateMessage:
				message.reply("Quitting! Reason: " + quitmessage, "say")

			GlobalStore.bothandler.stopBotfactory(message.bot.factory.serverfolder, quitmessage)

		elif message.trigger == 'shutdown':
			#SHUT DOWN EVERYTHING
			quitmessage = "Total shutdown initiated. Bye..."
			if message.messagePartsLength > 0:
				quitmessage = message.message.format(nick=message.userNickname)

			if message.isPrivateMessage:
				#If we've been told to shut down in a PM, inform the user that we're complying
				message.reply("Shutting down! Reason: " + quitmessage, "say")
			GlobalStore.bothandler.shutdown(quitmessage)