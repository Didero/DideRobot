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
		for commandname, command in GlobalStore.commandhandler.commands.iteritems():
			if command.showInCommandList and GlobalStore.commandhandler.isCommandAllowedForBot(message.bot, commandname) and len(command.triggers) > 0:
				shortTriggerlist[command.triggers[0]] = command
				for trigger in command.triggers:
					triggerlist[trigger] = command
				
		replytext = u""
		#Check if a command has been passed as argument
		command = message.message.lower()
		#Remove the command prefix if it's there, because the lookup doesn't have it
		if command.startswith(message.bot.factory.commandPrefix):
				command = command[message.bot.factory.commandPrefixLength:]
		
		#check if the provided argument exists
		if command in triggerlist:
			#'!help, !helpfull: '
			replytext = u"{commandPrefix}{triggers}".format(triggers=", {commandPrefix}".join(triggerlist[command].triggers), commandPrefix="{commandPrefix}")
			#some commands can only be used by people in the admins list. Inform users of that
			if triggerlist[command].adminOnly:
				replytext += u" [admin-only]"			
			replytext += u": {helptext}".format(helptext=triggerlist[command].helptext)
		#If the provided command can't be found (either because of misspelling or because they didn't provide one),
		# show a list of available commands
		else:
			#If a command was provided but not found, apologize even though it's not our fault
			if command != u"":
				replytext = u"I don't know that command, sorry. "
			commandslist = ""
			if message.trigger == u'helpfull':
				commandslist = u", ".join(sorted(triggerlist.keys()))
			else:
				commandslist = ", ".join(sorted(shortTriggerlist.keys()))
			replytext += u"Commands loaded: {commandslist}. Type '{prefix}help [commandname]' for info on how to use that command"\
				.format(commandslist=commandslist, prefix=message.bot.factory.commandPrefix)
		
		replytext = replytext.format(commandPrefix=message.bot.factory.commandPrefix)
		message.bot.say(message.source, replytext)
		
