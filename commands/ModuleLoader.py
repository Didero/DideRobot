from commands.CommandTemplate import CommandTemplate
import GlobalStore, PermissionLevel
from IrcMessage import IrcMessage
from CustomExceptions import CommandException, CommandInputException


class Command(CommandTemplate):
	triggers = ['load', 'unload', 'reload', 'reloadall']
	helptext = "(Re)loads one or more modules from disk, updating them with any changes, or unloads them. 'reloadall' unloads all modules and then loads all of them again"
	minPermissionLevel = PermissionLevel.BOT
	showInCommandList = False
	stopAfterThisCommand = True
	
	def execute(self, message):
		"""
		:type message: IrcMessage
		"""

		# 'reloadall' handling is different from the other triggers, so handle that separately
		if message.trigger == 'reloadall':
			moduleCountBeforeUnload = len(GlobalStore.commandhandler.commands)
			modulesWithUnloadErrors = GlobalStore.commandhandler.unloadAllCommands()
			modulesWithLoadErrors = GlobalStore.commandhandler.loadCommands()
			reply = "Unloaded {:,} commands, loaded {:,} commands".format(moduleCountBeforeUnload, len(GlobalStore.commandhandler.commands))
			if modulesWithUnloadErrors:
				reply += ". Modules with unload errors: {}".format(", ".format(modulesWithUnloadErrors))
			if modulesWithLoadErrors:
				reply += ". Modules with load errors: {}".format(", ".format(modulesWithLoadErrors))
			return message.reply(reply)

		if message.messagePartsLength == 0:
			message.reply("Please provide the name of one or more modules to {}".format(message.trigger))
			return

		#Check if the module names are valid, but only if we're not trying to load a module since of course an unloaded module isn't stored yet
		modulenames = []
		if message.trigger == 'load':
			modulenames = message.messageParts
		else:
			for messagePart in message.messageParts:
				triggerToLookFor = messagePart.lower()
				#Maybe the parameter provided isn't a module name, but a trigger word. Try to find the module it belongs to
				for commandname, command in GlobalStore.commandhandler.commands.items():
					if messagePart == commandname or messagePart in command.triggers or triggerToLookFor in command.triggers:
						modulenames.append(commandname)
						break
				else:
					raise CommandInputException("'{} is not a module I'm familiar with, sorry. Maybe you made a typo?".format(messagePart))

		modulesWithoutErrors = []
		modulesWithErrors = []
		for modulename in modulenames:
			try:
				if message.trigger == 'load':
					GlobalStore.commandhandler.loadCommand(modulename)
				elif message.trigger == 'unload':
					GlobalStore.commandhandler.unloadCommand(modulename)
				#Only 'reload' is left as a possibility
				else:
					GlobalStore.commandhandler.reloadCommand(modulename)
			except CommandException as ce:
				modulesWithErrors.append(modulename)
			else:
				modulesWithoutErrors.append(modulename)

		reply = ""
		if modulesWithoutErrors:
			reply += "Successfully {}ed {}. ".format(message.trigger, ", ".join(modulesWithoutErrors))
		if modulesWithErrors:
			reply += "Something went wrong when {}ing {}".format(message.trigger, ", ".join(modulesWithErrors))
		message.reply(reply)
