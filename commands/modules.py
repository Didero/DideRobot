from CommandTemplate import CommandTemplate

import GlobalStore

class Command(CommandTemplate):
	triggers = ['module', 'modules']
	helptext = "Shows a list of the modules loaded. This is different from the list of commands, since this is just the filenames. Not really useful, except when an admin forgets a module name"
	
	def execute(self, bot, user, target, triggerInMsg, msg, msgWithoutFirstWord, msgParts, msgPartsLength):

		replytext = ""
		
		modulename = ""
		if msgPartsLength > 1:
			modulename = msgParts[1]
		
		if modulename in GlobalStore.commandhandler.commands and GlobalStore.commandhandler.isCommandAllowedForBot(bot, modulename):
			module = GlobalStore.commandhandler.commands[modulename]
			replytext = "Module '{0}' has triggers: {1}; Helptext: {2}".format(modulename, ", ".join(module.triggers), module.helptext)
		else:
			if modulename != "":
				replytext = "Unknown module. "
			modules = []
			for loadedModuleName in GlobalStore.commandhandler.commands.keys():
				if GlobalStore.commandhandler.isCommandAllowedForBot(bot, loadedModuleName):
					modules.append(loadedModuleName)
			modules = sorted(modules, key=lambda s: s.lower())#The key=lambda part is so the sort ignores case

			replytext += "Modules loaded: {}".format(", ".join(modules)) 
			
		bot.say(target, replytext)