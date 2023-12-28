from commands.CommandTemplate import CommandTemplate

import GlobalStore
from IrcMessage import IrcMessage


class Command(CommandTemplate):	
	triggers = ['help', 'helpfull']
	helptext = "Shows the explanation of the provided command, or the list of commands if there aren't any arguments. {commandPrefix}helpfull shows all command aliases as well"
	
	def execute(self, message):
		"""
		:type message: IrcMessage
		"""
		#First get all the existing triggers, since we either need to list them or check if the provided one exists
		triggerlist = {}
		shortTriggerlist = {}
		userPermissionLevel = message.bot.getUserPermissionLevel(message.user, message.userNickname, message.userAddress, message.source)
		for commandname, command in GlobalStore.commandhandler.getCommandsIterator(message.bot, message.source):
			if command.showInCommandList and (not command.minPermissionLevel or userPermissionLevel >= command.minPermissionLevel) and len(command.triggers) > 0:
				shortTriggerlist[command.triggers[0]] = command
				for trigger in command.triggers:
					triggerlist[trigger] = command
				
		replytext = ""
		#Check if a command has been passed as argument
		command = None
		if message.messagePartsLength > 0:
			command = message.messageParts[0].lower()
			#Remove the command prefix if it's there, because the lookup doesn't have it
			commandPrefix = message.bot.getCommandPrefix(message.source)
			if command.startswith(commandPrefix):
					command = command[len(commandPrefix):]
		
		#check if the provided argument exists
		if command and command in triggerlist:
			replytext = triggerlist[command].getHelp(message)
		#If the provided command can't be found (either because of misspelling or because they didn't provide one),
		# show a list of available commands
		else:
			#If a command was provided but not found, apologize even though it's not our fault
			if command:
				replytext = "I don't know that command, sorry. "
			if message.trigger == 'helpfull':
				commandslist = ", ".join(sorted(triggerlist.keys()))
			else:
				commandslist = ", ".join(sorted(shortTriggerlist.keys()))
			replytext += "Commands loaded: {}. Type '{}help [commandname]' for info on how to use that command".format(commandslist, message.bot.getCommandPrefix(message.source))
		
		message.bot.sendMessage(message.source, replytext)
