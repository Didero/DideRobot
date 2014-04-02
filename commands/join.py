from CommandTemplate import CommandTemplate

class Command(CommandTemplate):
	triggers = ['join']
	helptext = "Makes me join another channel, if I'm allowed to at least"
	
	def execute(self, bot, user, target, triggerInMsg, msg, msgWithoutFirstWord, msgParts, msgPartsLength):

		replytext = u""
		if msgPartsLength == 1:
			replytext = u"Please provide a channel for me to join"
		else:
			allowedChannels = bot.factory.settings.get('connection', 'allowedChannels').split(',')
			
			channel = msgParts[1]
			if channel.startswith('#'):
				channel = channel[1:]
			if channel not in allowedChannels and not bot.factory.isUserAdmin(user):
				replytext = u"I'm sorry, I'm not allowed to go there. Please ask my admin(s) for permission"
			else:
				channel = '#' + channel
				replytext = u"All right, I'll go to {}. See you there!".format(channel)
				bot.join(channel)
				
		bot.say(target, replytext)
		