from CommandTemplate import CommandTemplate

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
		isUserAdmin = message.bot.isUserAdmin(message.user, message.userNickname, message.userAddress)
		for commandname, command in GlobalStore.commandhandler.commands.iteritems():
			if command.showInCommandList and (isUserAdmin or not command.adminOnly) and len(command.triggers) > 0 and GlobalStore.commandhandler.isCommandAllowedForBot(message.bot, commandname):
				shortTriggerlist[command.triggers[0]] = command
				for trigger in command.triggers:
					triggerlist[trigger] = command
				
		replytext = u""
		#Check if a command has been passed as argument
		command = None
		if message.messagePartsLength > 0:
			command = message.messageParts[0].lower()
			#Remove the command prefix if it's there, because the lookup doesn't have it
			if command.startswith(message.bot.commandPrefix):
					command = command[message.bot.commandPrefixLength:]
		
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
			replytext += "Commands loaded: {}. Type '{}help [commandname]' for info on how to use that command".format(commandslist, message.bot.commandPrefix)
		
		message.bot.sendMessage(message.source, replytext)
