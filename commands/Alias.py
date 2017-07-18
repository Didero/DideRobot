import json, os, random, re

from CommandTemplate import CommandTemplate
from IrcMessage import IrcMessage
import GlobalStore


class Command(CommandTemplate):
	triggers = ['alias']
	helptext = "Allows you to make shortcut commands, called aliases. Parameters are 'list' to see which are available, 'show' to see a specific one, " \
			   "'serveradd' to add a serverwide alias or 'channeladd' for channel-specific, or 'remove' to remove. " \
			   "Special in-alias values are '$CP' for the command prefix, '$0' for all provided parameters, or '$n' for the nth parameter. " \
			   "'$random(low,high)' returns a random number between 'low' (inclusive) and 'high' (exclusive)"

	aliases = {}  #Key is either "[server]" or "[server] [channel]", value is a dictionary of "aliasname: aliascommand"
	aliasNameList = []  #A list of just the alias names, to speed up lookup

	def onLoad(self):
		filepath = os.path.join(GlobalStore.scriptfolder, "data", "Aliases.json")
		if os.path.isfile(filepath):
			with open(filepath, "r") as f:
				self.aliases = json.load(f)
			#Build the quick-lookup aliasname list
			for aliasTarget, aliasDict in self.aliases.iteritems():
				for aliasName in aliasDict:
					if aliasName not in self.aliasNameList:
						self.aliasNameList.append(aliasName)

	def shouldExecute(self, message):
		#Check if we need to respond, ordered from cheapest to most expensive check
		#  (the allowedMessageTypes list is usually short, most likely shorter than the triggers list)
		return message.trigger and message.messageType in self.allowedMessageTypes and (message.trigger in self.triggers or message.trigger in self.aliasNameList)

	def execute(self, message):
		"""
		:type message: IrcMessage
		"""

		#key in alias dict is either the server or a server-channel string
		server = message.bot.serverfolder
		serverChannelString = "{} {}".format(server, message.source)

		if message.trigger in self.aliasNameList:
			self.parseAndSendAlias(server, serverChannelString, message)
			return

		if message.messagePartsLength == 0:
			message.reply(self.helptext)
			return

		parameter = message.messageParts[0].lower()

		if parameter == "list":
			aliasNames = []
			if server in self.aliases:
				aliasNames.extend(self.aliases[server].keys())
			if serverChannelString in self.aliases:
				aliasNames.extend(self.aliases[serverChannelString].keys())
			if len(aliasNames) == 0:
				message.reply("No aliases stored yet. You could be the first to add one!", "say")
			else:
				message.reply(u"{:,} alias(es): {}".format(len(aliasNames), u", ".join(aliasNames)), "say")

		elif parameter == "show":
			if message.messagePartsLength == 1:
				message.reply("Show what? Please provide an alias name. Use 'list' to see all stored alias names", "say")
				return
			aliasname = message.messageParts[1].lower()
			alias = None
			#First check if it's stored and where
			if server in self.aliases and aliasname in self.aliases[server]:
				alias = self.aliases[server][aliasname]
			elif serverChannelString in self.aliases and aliasname in self.aliases[serverChannelString]:
				alias = self.aliases[serverChannelString][aliasname]

			#If we've found it, report it, otherwise say we haven't found it
			if alias:
				message.reply(u"{}: {}".format(aliasname, alias))
			else:
				message.reply(u"I'm sorry, I don't know the alias '{}'. Did you make a typo?".format(aliasname), "say")

		elif parameter == "serveradd" or parameter == "channeladd" or parameter == "add":
			#Restrict alias creation to bot admins for now
			if not message.bot.isUserAdmin(message.user, message.userNickname, message.userAddress):
				message.reply("Alias creation is limited to bot admins only for now, sorry! Poke them if you want an alias created", "say")
				return

			if parameter != "serveradd" and message.isPrivateMessage:
				message.reply("Channel aliases aren't allowed in private messages, sorry", "say")
				return
			elif message.messagePartsLength == 1:
				message.reply("Add what? Please add an alias name and a command for that alias", "say")
				return
			elif message.messagePartsLength == 2:
				message.reply("While I love running random code as much as the next bot, please add an actual command to store as an alias", "say")
				return

			aliasname = message.messageParts[1].lower()
			#Prevent an alias for 'alias' to prevent breakage
			if aliasname == "alias":
				message.reply("Leeeeet's not break this whole module, shall we? Better use a different name for this alias", "say")
				return

			#Check if an alias with the same name doesn't exist already
			if (server in self.aliases and aliasname in self.aliases[server]) or (serverChannelString in self.aliases and aliasname in self.aliases[serverChannelString]):
				message.reply(u"'{}' already is an alias! Looks like you weren't the only one with this presumably great idea!".format(aliasname), "say")
				return

			if parameter == "serveradd" and server not in self.aliases:
				self.aliases[server] = {}
			elif (parameter == "channeladd" or parameter == "add") and serverChannelString not in self.aliases:
				self.aliases[serverChannelString] = {}
			self.aliases[server if parameter == "serveradd" else serverChannelString][aliasname] = u" ".join(message.messageParts[2:])
			self.saveAliases()
			if aliasname not in self.aliasNameList:
				self.aliasNameList.append(aliasname)
			message.reply(u"Stored the alias '{}' for this {}!".format(aliasname, "server" if parameter == "serveradd" else "channel"), "say")

		elif parameter == "remove":
			#Restrict alias removal to bot admins as well
			if not message.bot.isUserAdmin(message.user, message.userNickname, message.userAddress):
				message.reply("Alias removal is limited to bot admins only for now, sorry! Poke them if you think an alias should be removed", "say")
				return

			if message.messagePartsLength == 1:
				message.reply("Please provide an alias name to remove, because I'm not just going to throw everything out")
				return
			aliasname = message.messageParts[1].lower()
			aliasKey = None
			if server in self.aliases and aliasname in self.aliases[server]:
				aliasKey = server
			elif serverChannelString in self.aliases and aliasname in self.aliases[serverChannelString]:
				aliasKey = serverChannelString

			if not aliasKey:
				message.reply(u"I don't know the alias '{}', so removal mission accomplished I guess?".format(aliasname), "say")
			else:
				del self.aliases[aliasKey][aliasname]
				#If no other aliases are stored for this server/channel, remove the entire key
				if len(self.aliases[aliasKey]) == 0:
					del self.aliases[aliasKey]
				self.saveAliases()
				message.reply(u"Ok, successfully removed the alias '{}'".format(aliasname), "say")

		else:
			message.reply("I don't know what to do with the parameter '{}'. Please (re)read the help text for info on how to use this module, or poke my owner(s) if you have questions")

	def parseAndSendAlias(self, server, serverChannelString, message):
		# Alias called, create a new IrcMessage and send it to the CommandHandler
		# First retrieve the actual alias
		if server in self.aliases and message.trigger in self.aliases[server]:
			aliasText = self.aliases[server][message.trigger]
		elif serverChannelString in self.aliases and message.trigger in self.aliases[serverChannelString]:
			aliasText = self.aliases[serverChannelString][message.trigger]
		else:
			self.logWarning("[Alias] Asked to parse alias in message '{}' but that alias doesn't exist".format(message.rawText))
			return

		# Fill in the special values
		newMessageText = aliasText
		# Modules won't expect incoming messages to be unicode, and the regex module doesn't like it. Best convert it
		if isinstance(newMessageText, unicode):
			newMessageText = newMessageText.encode('utf-8', errors='replace')

		# $0 is the whole provided message,
		newMessageText = re.sub(r"(?<!\\)\$0", message.message, newMessageText)

		# $n is a specific message part (so $1 is the first index, so messageParts[0])
		# $n+ would fill in everything starting at $n and all the parts after it ($2+ is messageParts[1:])
		# $n- is for everything until $n (so $3- is messageParts[:2])
		def fillInNumberedMessageParts(regexMatchObject):
			# group(0) is the whole match, group(1) is the first bracketed match, so the \d+
			index = int(regexMatchObject.group(1)) - 1
			if index >= message.messagePartsLength:
				# If there aren't enough message parts, just leave text as-is
				return regexMatchObject.group(0)
			# If there's a second group, a '+' or '-' was added after the number
			# '+' means all args starting with the index, '-' is all args until the index
			if regexMatchObject.group(2):
				if regexMatchObject.group(2) == "+":
					return " ".join(message.messageParts[index:])
				else:
					# If it's not +, it's -
					return " ".join(message.messageParts[:index])
			return message.messageParts[index]

		newMessageText = re.sub(r"(?<!\\)\$(\d+)(\+|-)?", fillInNumberedMessageParts, newMessageText)
		# The replacements may have left some trailing spaces if they couldn't fill in the parameters. Remove those
		newMessageText = newMessageText.rstrip()

		#Replace '$nick' with the nickname of the person calling the alias
		newMessageText = re.sub(r"(?<!\\)\$nick", message.userNickname, newMessageText)

		# Parse all possible alias commands
		def executeAliasCommand(regexMatchObject):
			command = regexMatchObject.group(1).lower()
			args = re.split(r", *", regexMatchObject.group(2))
			if command == "random":
				#'$random(lowerbound,higherbound)' returns a random integer between the lower bound (inclusive) and the upper bound (exclusive)
				try:
					lowerbound = int(args[0])
					upperbound = int(args[1])
				except ValueError:
					return "ERROR: 'random' only accepts number"
				except IndexError:
					return "ERROR: 'random' needs 2 arguments"
				#Flip bounds if lowerbound is larger than upperbound, to prevent errors and weird behaviour
				if lowerbound > upperbound:
					temp = lowerbound
					lowerbound = upperbound
					upperbound = temp
				try:
					return str(random.randrange(lowerbound, upperbound))
				except ValueError:
					return "ERROR: Invalid values for 'random'"
			elif command == "choose" or command == "choice":
				return random.choice(args)
			else:
				return "ERROR: Unknown command '{}'".format(command)
		changeCount = 1
		while changeCount != 0:
			#Substitute the right-most command:	No escaped $'s	get command		get args, if present	Not followed by other commands
			newMessageText, changeCount = re.subn(r"(?<!\\)\$(?P<command>\w+?)\((?P<args>[\w,% ]*?)\)(?=[^$]*$)", executeAliasCommand, newMessageText)

		# $cp is the command prefix
		newMessageText = re.sub(r"(?<!\\)\$CP", message.bot.commandPrefix, newMessageText, flags=re.IGNORECASE)
		#Since all commands (so far) only fire if the message starts with the command prefix, add it if it's not there
		if not newMessageText.startswith(message.bot.commandPrefix):
			newMessageText = message.bot.commandPrefix + newMessageText

		#Turn escaped dollar signs into normal ones, since we're done replacing
		newMessageText = newMessageText.replace("\\$", "$")

		# Allow for newlines in aliases, each a new message
		for newMessageLine in newMessageText.split("\\n"):
			#Done! Send the new message to the Commandhandler
			newMessage = IrcMessage(message.messageType, message.bot, message.user, message.source, newMessageLine)
			GlobalStore.commandhandler.handleMessage(newMessage)


	def saveAliases(self):
		with open(os.path.join(GlobalStore.scriptfolder, "data", "Aliases.json"), "w") as aliasFile:
			aliasFile.write(json.dumps(self.aliases))
