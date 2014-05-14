from CommandTemplate import CommandTemplate
from IrcMessage import IrcMessage


class Command(CommandTemplate):
	triggers = ['source']
	helptext = "Provides a link to my GitHub repository"

	def execute(self, message):
		"""
		:type message: IrcMessage
		"""
		message.bot.say(message.source, "You wanna know how I work? I'm flattered! Here you go: https://github.com/Didero/DideRobot")