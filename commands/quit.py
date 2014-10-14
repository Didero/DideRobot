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
			message.bot.factory.logger.log("{0} told me to quit in channel {1}, obliging".format(message.user, message.source))
		

			quitmessage = "{0} told me to quit, so here I go..."
			if message.message and message.message != u"":
				quitmessage = message.message

			#You don't see quit messages in PMs, inform the user anyway
			if message.isPrivateMessage:
				message.bot.say(message.source, quitmessage)

			#Replace the first argument with the caller's name, for fun possibilities
			quitmessage = quitmessage.format(message.userNickname)
			GlobalStore.bothandler.stopBotfactory(message.bot.factory.serverfolder, quitmessage)

		elif message.trigger == 'shutdown':
			#SHUT DOWN EVERYTHING
			quitmessage = "Total shutdown initiated. Bye..."
			if message.message and message.message != u"":
				quitmessage = message.message.format(message.userNickname)

			if message.isPrivateMessage:
				#If we've been told to shut down in a PM, inform the user that we're complying
				message.bot.say(message.source, quitmessage)
			GlobalStore.bothandler.shutdown(quitmessage)