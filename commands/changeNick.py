from CommandTemplate import CommandTemplate
import GlobalStore

class Command(CommandTemplate):
	triggers = ['nick', 'nickname']
	helptext = "Changes my nick to the provided new one, assuming it's not taken. If no argument is provided, try to change back to the default as set in the server settings"
	adminOnly = True
	
	def execute(self, bot, user, target, triggerInMsg, msg, msgWithoutFirstWord, msgParts, msgPartsLength):
		if msgPartsLength == 1:
			#Change nick back to the default
			bot.setNick(bot.factory.settings.get("connection", "nickname"))
		else:
			bot.setNick(msgParts[1])