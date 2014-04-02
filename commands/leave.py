from CommandTemplate import CommandTemplate

class Command(CommandTemplate):
	triggers = ['leave']
	helptext = "Makes me leave the current channel, if you're sure you no longer want me around..."
	
	def execute(self, bot, user, target, triggerInMsg, msg, msgWithoutFirstWord, msgParts, msgPartsLength):

		if not target.startswith("#"):
			#Private conversation
			if msgPartsLength > 1:
				bot.say("All right, I'll leave '{}' if I'm there")
				if msgPartsLength > 2:
					bot.leave(msgParts[1], " ".join(msgParts[2:]))
				else:
					bot.leave(msgParts[1])
			else:
				bot.say("This isn't a channel, this is a private conversation. YOU leave")
		else:
			bot.say(target, "All right, I'll go... Call me back in when you want me around again!")
			bot.leave(target)