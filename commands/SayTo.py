import Constants, PermissionLevel
from commands.CommandTemplate import CommandTemplate
from IrcMessage import IrcMessage
import MessageTypes


class Command(CommandTemplate):
	triggers = ['sayto', 'doto', 'noticeto', 'saydef', 'dodef', 'noticedef']
	helptext = "Makes the bot say the provided text in the provided channel  (format 'sayto [channel/user] [text]'). " \
			   "Set a default with 'sayto setdefault [default]', and use 'saydef [text]' to use that default to save on typing"
	minPermissionLevel = PermissionLevel.SERVER
	showInCommandList = False

	defaultTargets = {}

	def execute(self, message):
		"""
		:type message: IrcMessage
		"""

		if message.messagePartsLength == 0:
			message.bot.sendMessage(message.source, "Say what? To whom? So many questions, you'd better just provide some more parameters")
			return

		#Everything's fine, let's do some actual work
		command = message.messageParts[0].lower()
		messageText = ""
		messageTarget = message.source
		messageType = MessageTypes.SAY
		#Check if it's to set the default channel instead of to actually say something
		if command == 'setdefault':
			if message.messagePartsLength == 1:
				messageText = "Set the default to what?"
			else:
				defaultTarget = message.messageParts[1]
				if defaultTarget[0] in Constants.CHANNEL_PREFIXES and defaultTarget not in message.bot.channelsUserList:
					messageText = "I'm sorry, I'm not in that channel, so I can't set that as the default"
				else:
					self.defaultTargets[message.bot.serverfolder] = defaultTarget
					if defaultTarget[0] in Constants.CHANNEL_PREFIXES:
						messageText = "Sure, all future Say messages will be sent to the channel '{}'".format(defaultTarget)
					else:
						messageText = "Ok, if you want to keep pestering user '{}' easily, I'll allow it, but I hope you know what you're doing".format(defaultTarget)
		#Allow the default to be cleared
		elif command == 'cleardefault':
			if message.bot.serverfolder in self.defaultTargets:
				messageText = "Ok, default Say target '{}' cleared".format(self.defaultTargets[message.bot.serverfolder])
				del self.defaultTargets[message.bot.serverfolder]
			else:
				messageText = "There's no default set for this server yet, so there's nothing to clear"
		#Check if there is a default set, and if so, what it is
		elif command == 'getdefault':
			messageText = "The default Say target is " + self.defaultTargets.get(message.bot.serverfolder, "not set")
		#Nothing's stopping us now! Say it!
		else:
			#Set the target properly
			if message.trigger.startswith('do'):
				messageType = MessageTypes.ACTION
			elif message.trigger.startswith('notice'):
				messageType = MessageTypes.NOTICE

			#'def' and non-'def' commands have to be treated a little differently
			if message.trigger.endswith('def'):
				#Should send to default, but no default set. Warn about that
				if message.bot.serverfolder not in self.defaultTargets:
					messageText = "There's no default set, so I don't know where to send the message. Use 'say setdefault [default]' to set a default"
					messageType = MessageTypes.SAY
				#There is a default set, so send the whole message there
				else:
					messageText = message.message
					messageTarget = self.defaultTargets[message.bot.serverfolder]
			#Don't use the default, so we need both a target and a message
			elif message.messagePartsLength == 1:
				messageText = "Tell '{}' what? I'm not gonna make anything up, add some text to send".format(message.messageParts[0])
				messageType = MessageTypes.SAY
			#Everything seems fine, go ahead
			else:
				messageTarget = message.messageParts[0]
				messageText = " ".join(message.messageParts[1:])

			#If we should end up having to say something in a channel we're not in, tell the original source that we can't do that
			if messageTarget[0] in Constants.CHANNEL_PREFIXES and messageTarget not in message.bot.channelsUserList:
				messageText = "I'm not in channel '{}', so I can't say anything there. Sorry".format(messageTarget)
				messageTarget = message.source
				messageType = MessageTypes.SAY

		message.bot.sendMessage(messageTarget, messageText, messageType)
