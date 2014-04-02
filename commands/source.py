from CommandTemplate import CommandTemplate

class Command(CommandTemplate):
	triggers = ['source']
	helptext = "Provides a link to my GitHub repository"

	def execute(self, bot, user, target, triggerInMsg, msg, msgWithoutFirstWord, msgParts, msgPartsLength):
		bot.say(target, "You wanna know how I work? I'm flattered! Here you go: https://github.com/Didero/DideRobot")