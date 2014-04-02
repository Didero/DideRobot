from CommandTemplate import CommandTemplate
import GlobalStore

class Command(CommandTemplate):
	triggers = ['quit', 'shutdown']
	helptext = "Shuts down the bot. {commandPrefix}quit closes down just this bot, {commandPrefix}shutdown shuts down all instances of DideRobot on all servers it's connected to"
	adminOnly = True
	
	def execute(self, bot, user, target, triggerInMsg, msg, msgWithoutFirstWord, msgParts, msgPartsLength):
		if triggerInMsg == 'quit':
			#Just quit this server
			bot.factory.logger.log("{0} told me to quit in channel {1}, obliging".format(user, target))
		
			#You don't see quit messages in PMs, inform the user anyway
			if not target.startswith("#"):
				bot.say(target, "All right, I'll quit then...")
			
			quitmessage = "{0} told me to quit, so here I go..."
			if (msgWithoutFirstWord != ""):
				quitmessage = msgWithoutFirstWord

			#Replace the first argument with the caller's name, for fun possibilities
			quitmessage = quitmessage.format(user.split("!", 1)[0])
			#bot.quit(quitmessage.format(user.split("!", 1)[0]))
			GlobalStore.bothandler.stopBotfactory(bot.factory.serverfolder, quitmessage)

		elif triggerInMsg == 'shutdown':
			#SHUT DOWN EVERYTHING
			quitmessage = "Total shutdown initiated. Bye..."
			if msgWithoutFirstWord != "":
				quitmessage = msgWithoutFirstWord.format(user.split("!",1)[0])

			if not target.startswith('#'):
				#If we've been told to shut down in a PM, inform the user that we're complying
				bot.say(target, quitmessage)
			GlobalStore.bothandler.shutdown(quitmessage)