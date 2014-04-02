import os

from CommandTemplate import CommandTemplate

import GlobalStore

class Command(CommandTemplate):
	triggers = ['load', 'unload', 'reload']
	helptext = "(Re)loads a module from disk, updating it with any changes, or unloads one"
	adminOnly = True
	
	def execute(self, bot, user, target, triggerInMsg, msg, msgWithoutFirstWord, msgParts, msgPartsLength):

		reply = u""
		modulename = ""
		success = False

		if msgPartsLength <= 1:
			reply = u"Please provide the name of a module to {}".format(triggerInMsg)
		else:
			modulename = msgParts[1]


			#Check if the module name is valid, but only if we're not trying to load a module since of course an unloaded module isn't stored yet
			if triggerInMsg != 'load' and not modulename in GlobalStore.commandhandler.commands:
				modulename = ""
				#Maybe the parameter provided isn't a module name, but a trigger word. Try to find the module it belongs to
				for commandname, command in GlobalStore.commandhandler.commands.iteritems():
					if msgParts[1] in command.triggers:
						modulename = commandname
						break
		
			if modulename == "":
				reply = u"That is not a module I'm familiar with, sorry"
			else:
				#Check if we're not trying to do unload the module loader or reload it since that errors out
				if modulename + '.py' == os.path.basename(__file__):
					reply = "Yeah, let's not mess with the module loader, shall we? It's probably gonna break, and then we don't have a module loader to fix it"
				else:				
					if triggerInMsg == 'unload':
						success = GlobalStore.commandhandler.unloadCommand(modulename)
					elif triggerInMsg == 'reload':
						success = GlobalStore.commandhandler.reloadCommand(modulename)
					elif triggerInMsg == 'load':
						success = GlobalStore.commandhandler.loadCommand(modulename)
					else:
						print "Unknown command '{}' given to moduleLoader module".format(triggerInMsg)

					if (success):
						reply = u"Module '{}' successfully {}ed".format(modulename, triggerInMsg)
					else:
						reply = u"There was an error {}ing module '{}'. There's probably something about it in the log".format(triggerInMsg, modulename)
			
		bot.say(target, reply)