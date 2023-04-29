from commands.CommandTemplate import CommandTemplate
from IrcMessage import IrcMessage
import GlobalStore


class Command(CommandTemplate):
	triggers = ['source']
	helptext = "Provides a link to my GitHub repository, or to a specific command module if a module name is provided as a parameter"

	def execute(self, message):
		"""
		:type message: IrcMessage
		"""
		# Check if there's an argument provided, and if it's a module name, link to that directly
		if message.messagePartsLength > 0:
			for commandName, command in GlobalStore.commandhandler.commands.items():
					if commandName == message.messageParts[0] or (command.triggers and message.messageParts[0] in command.triggers):
						# Found a matching module, link to that
						return message.reply("You want to peek behind the magic of the {0} command? Sure, that's what open-source means, here you go: https://github.com/Didero/DideRobot/blob/master/commands/{0}.py".format(commandName))
			else:
				return message.reply("Hmm, I don't have a module named '{0}'. Either you made a typo, or you should convince my owner(s) to create the '{0}' module so I can link it when it's done".format(message.messageParts[0]))
		# No argument provided, just link to the general repository
		message.reply("You wanna know how I work? I'm flattered! Here you go: https://github.com/Didero/DideRobot")
