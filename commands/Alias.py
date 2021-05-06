import json, os

from CommandTemplate import CommandTemplate
from IrcMessage import IrcMessage
import GlobalStore


class Command(CommandTemplate):
	triggers = ['alias']
	helptext = "Allows you to make shortcut commands, called aliases. Parameters are 'list' to see which are available, 'show' to see a specific one, " \
			   "'serveradd' to add a serverwide alias or 'channeladd' for channel-specific, or 'remove' to remove.\n" \
			   "Uses the same format as Generate's grammar files. Use '<CP>' for the command prefix, '<0>' for the whole message, '<n>' for the nth message part," \
			   "and '<nick>' for alias caller's nickname. The rest of the Generate module's grammar commands are also available."

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
				message.reply(u"{:,} alias{}: {}".format(len(aliasNames), u"es" if len(aliasNames) > 1 else u"", u", ".join(sorted(aliasNames))), "say")

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

			#Check if there is a module that already has the trigger that we want to set for this alias
			for modulename, module in GlobalStore.commandhandler.commands.iteritems():
				#Also check if the module is enabled for this server, because if, say, the help module is disabled, creating a 'help' alias isn't a problem
				if aliasname in module.triggers and GlobalStore.commandhandler.isCommandAllowedForBot(message.bot, modulename):
					message.reply(u"'{}' is already a trigger for the {} module, so using it as an alias would just get confusing. I'm sure you can think of another name though!".format(aliasname, modulename))
					return

			if parameter == "serveradd" and server not in self.aliases:
				self.aliases[server] = {}
			elif (parameter == "channeladd" or parameter == "add") and serverChannelString not in self.aliases:
				self.aliases[serverChannelString] = {}
			#Make sure it's unicode, since that's what the Generator module expects
			aliasToAdd = unicode(" ".join(message.messageParts[2:]), 'utf-8', 'replace')
			self.aliases[server if parameter == "serveradd" else serverChannelString][aliasname] = aliasToAdd
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
			message.reply("I don't know what to do with the parameter '{}'. Please (re)read the help text for info on how to use this module, or poke my owner(s) if you have questions".format(parameter))

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

		#Create a grammar dictionary out of the alias text
		aliasDict = {u'start': aliasText}
		#Numbered fields refer to message parts.
		# Use '<0>' to refer to the whole message (grammar also accepts '<_params>' but this is for completion's sake
		aliasDict[u'0'] = message.message if message.messagePartsLength > 0 else u""
		#  Fill in enough fields for aliases that use numbered fields not to error out
		for i in xrange(0, 11):
			aliasDict[str(i+1)] = message.messageParts[i] if i < message.messagePartsLength else u""
		aliasDict[u'nick'] = message.userNickname
		aliasDict[u'CP'] = message.bot.commandPrefix
		# Pass along the last message so the alias can use it
		lastMessage = GlobalStore.commandhandler.runCommandFunction('getLastMessage', '', server, message.source, '')
		# Generator module expects all text to be unicode
		if not isinstance(lastMessage, unicode):
			lastMessage = unicode(lastMessage, 'utf-8', errors='replace')
		# Escape any special grammar characters in the message, otherwise stuff like URLs get parsed wrong because of the /
		lastMessage = GlobalStore.commandhandler.runCommandFunction('escapeGrammarString', lastMessage, lastMessage)
		# Pass it along as a variable to the alias
		variableDict = {u'lastMessage': lastMessage}
		#Always send along parameters
		parameters = message.messageParts if message.messagePartsLength > 0 else None
		newMessageText = GlobalStore.commandhandler.runCommandFunction('parseGrammarDict', None, aliasDict, message.trigger,
																	   parameters=parameters, variableDict=variableDict)
		#Check if the parsing went well
		if newMessageText.startswith(u"Error: "):
			message.reply(u"Something went wrong with executing the alias: " + newMessageText.split(': ', 1)[1])
			return
		#Aliases that use parameters can end with whitespace at the end. Remove that
		newMessageText = newMessageText.rstrip()

		# Modules won't expect incoming messages to be unicode. Best convert it
		if isinstance(newMessageText, unicode):
			newMessageText = newMessageText.encode('utf-8', errors='replace')

		# Allow for newlines in aliases, each a new message
		for newMessageLine in newMessageText.split("\\n"):
			#Done! Send the new message to the Commandhandler
			newMessage = IrcMessage(message.messageType, message.bot, message.user, message.source, newMessageLine)
			GlobalStore.commandhandler.handleMessage(newMessage)


	def saveAliases(self):
		with open(os.path.join(GlobalStore.scriptfolder, "data", "Aliases.json"), "w") as aliasFile:
			aliasFile.write(json.dumps(self.aliases))
