from CommandTemplate import CommandTemplate
import GlobalStore
from IrcMessage import IrcMessage


class Command(CommandTemplate):
	triggers = ['load', 'unload', 'reload']
	helptext = "(Re)loads a module from disk, updating it with any changes, or unloads one"
	adminOnly = True
	showInCommandList = False
	stopAfterThisCommand = True
	
	def execute(self, message):
		"""
		:type message: IrcMessage
		"""

		if message.messagePartsLength == 0:
			message.reply(u"Please provide the name of a module to {}".format(message.trigger))
			return

		#Check if the module name is valid, but only if we're not trying to load a module since of course an unloaded module isn't stored yet
		if message.trigger == 'load' or message.messageParts[0] in GlobalStore.commandhandler.commands:
			modulename = message.messageParts[0]
		else:
			modulename = None
			#Maybe the parameter provided isn't a module name, but a trigger word. Try to find the module it belongs to
			for commandname, command in GlobalStore.commandhandler.commands.iteritems():
				if message.messageParts[0] in command.triggers:
					modulename = commandname
					break

		if not modulename:
			reply = u"That is not a module I'm familiar with, sorry"
		else:
			if message.trigger == 'load':
				result = GlobalStore.commandhandler.loadCommand(modulename)
			elif message.trigger == 'unload':
				result = GlobalStore.commandhandler.unloadCommand(modulename)
			#Only 'reload' is left as a possibility
			else:
				result = GlobalStore.commandhandler.reloadCommand(modulename)

			if not result[0]:
				reply = u"There was an error {}ing module '{}': {}".format(message.trigger, modulename, result[1])
			else:
				reply = u"Module '{}' successfully {}ed".format(modulename, message.trigger)

		message.reply(reply, "say")
