import os

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

		reply = u""
		success = False

		if message.messagePartsLength < 1:
			reply = u"Please provide the name of a module to {}".format(message.trigger)
		else:
			modulename = message.messageParts[0]

			#Check if the module name is valid, but only if we're not trying to load a module since of course an unloaded module isn't stored yet
			if message.trigger != 'load' and not modulename in GlobalStore.commandhandler.commands:
				modulename = u""
				#Maybe the parameter provided isn't a module name, but a trigger word. Try to find the module it belongs to
				for commandname, command in GlobalStore.commandhandler.commands.iteritems():
					if message.messageParts[0] in command.triggers:
						modulename = commandname
						break
		
			if modulename == "":
				reply = u"That is not a module I'm familiar with, sorry"
			else:
				#Check if we're not trying to do unload the module loader or reload it since that errors out
				if modulename + '.py' == os.path.basename(__file__):
					reply = "Yeah, let's not mess with the module loader, shall we? It's probably gonna break, and then we don't have a module loader to fix it"
				else:				
					if message.trigger == 'unload':
						success = GlobalStore.commandhandler.unloadCommand(modulename)
					elif message.trigger == 'reload':
						success = GlobalStore.commandhandler.reloadCommand(modulename)
					elif message.trigger == 'load':
						success = GlobalStore.commandhandler.loadCommand(modulename)
					else:
						print "Unknown command '{}' given to moduleLoader module".format(message.trigger)

					if (success):
						reply = u"Module '{}' successfully {}ed".format(modulename, message.trigger)
					else:
						reply = u"There was an error {}ing module '{}'. There's probably something about it in the log".format(message.trigger, modulename)
			
		message.bot.say(message.source, reply)