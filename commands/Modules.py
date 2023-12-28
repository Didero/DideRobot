from commands.CommandTemplate import CommandTemplate
import GlobalStore
from IrcMessage import IrcMessage


class Command(CommandTemplate):
	triggers = ['module', 'modules']
	helptext = "Shows a list of the modules loaded. This is different from the list of commands, since this is just the filenames. Not really useful, except when an admin forgets a module name"
	
	def execute(self, message):
		"""
		:type message: IrcMessage
		"""
		replytext = ""
		modulename = ""
		if message.messagePartsLength > 0:
			modulename = message.messageParts[0]
		
		if modulename in GlobalStore.commandhandler.commands and GlobalStore.commandhandler.isCommandAllowedForBot(message.bot, modulename, message.source):
			module = GlobalStore.commandhandler.commands[modulename]
			replytext = "Module '{0}' has triggers: {1}; Helptext: {2}".format(modulename, ", ".join(module.triggers), module.helptext.format(commandPrefix=message.bot.getCommandPrefix(message.source)))
		else:
			if modulename != "":
				replytext = "Unknown module. "
			moduleNames = []
			for loadedModuleName, loadedModule in GlobalStore.commandhandler.getCommandsIterator(message.bot, message.source):
					moduleNames.append(loadedModuleName)
			moduleNames = sorted(moduleNames, key=lambda s: s.lower())  #The key=lambda part is so the sort ignores case

			replytext += "Modules loaded: {}".format(", ".join(moduleNames))
			
		message.reply(replytext)