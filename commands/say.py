from CommandTemplate import CommandTemplate

class Command(CommandTemplate):
	triggers = ['say', 'do', 'notice']
	helptext = "Makes the bot say the provided text in the provided channel  (format 'say [channel/user] text')"
	adminOnly = True
	showInCommandList = False

	def execute(self, bot, user, target, triggerInMsg, msg, msgWithoutFirstWord, msgParts, msgPartsLength):
		if msgPartsLength < 3:
			bot.say(target, "Please provide both a channel or user name to say something to, and the text to say")
		#Check if we're in the channel we have to say something to
		elif msgParts[1].startswith('#') and msgParts[1] not in bot.channelsUserList:
			bot.say(target, "I'm not in that channel, so I can't say anything in there, sorry.")
		#Nothing's stopping us now! Say it!
		else:
			messageToSay = " ".join(msgParts[2:])
			messageType = 'say'
			if triggerInMsg == 'do':
				messageType = 'action'
			elif triggerInMsg == 'notice':
				messageType = 'notice'

			bot.sendMessage(msgParts[1], messageToSay, messageType)
