import json, os

import GlobalStore, PermissionLevel
from commands.CommandTemplate import CommandTemplate
from IrcMessage import IrcMessage
from CustomExceptions import CommandInputException


class Command(CommandTemplate):
	triggers = ['alias']
	helptext = "Allows you to make shortcut commands, called aliases. Parameters are 'list' to see which are available, 'show' to see a specific one, " \
			   "'serveradd' to add a serverwide alias or 'channeladd' for channel-specific, or 'remove' to remove. 'sethelp' sets a helptext for an alias, 'help' shows that helptext" \
			   "Uses the same format as Generate's grammar files. Use '<CP>' for the command prefix, '<0>' for the whole message, '<n>' for the nth message part, " \
			   "and '<nick>' for alias caller's nickname. The rest of the Generate module's grammar commands are also available."

	aliases = {}  #Key is either "[server]" or "[server] [channel]", value is a dictionary of "aliasname: aliascommand"
	aliasNameList = []  #A list of just the alias names, to speed up lookup

	def onLoad(self):
		filepath = os.path.join(GlobalStore.scriptfolder, "data", "Aliases.json")
		if os.path.isfile(filepath):
			with open(filepath, 'r', encoding='utf-8') as f:
				self.aliases = json.load(f)
			#Build the quick-lookup aliasname list
			for aliasTarget, aliasDict in self.aliases.items():
				for aliasName in aliasDict:
					if aliasName not in self.aliasNameList:
						self.aliasNameList.append(aliasName)

	def shouldExecute(self, message):
		return message.trigger and message.messageType in self.allowedMessageTypes and (message.trigger in self.triggers or message.trigger in self.aliasNameList)

	def execute(self, message):
		"""
		:type message: IrcMessage
		"""

		if message.trigger in self.aliasNameList:
			self.parseAndSendAlias(message)
			return

		if message.messagePartsLength == 0:
			message.reply(self.helptext)
			return

		parameter = message.messageParts[0].lower()
		server = message.bot.serverfolder
		serverChannelString = self.createServerChannelString(message.bot.serverfolder, message.source)

		if parameter == "list":
			aliasNames = []
			if server in self.aliases:
				aliasNames.extend(self.aliases[server].keys())
			if serverChannelString in self.aliases:
				aliasNames.extend(self.aliases[serverChannelString].keys())
			if len(aliasNames) == 0:
				return message.reply("No aliases stored yet. You could be the first to add one!")
			else:
				return message.reply("{:,} alias{}: {}".format(len(aliasNames), "es" if len(aliasNames) > 1 else "", ", ".join(sorted(aliasNames))))

		# Check if an alias name has been provided and retrieve the alias if so, because all following subcommands need that information
		if message.messagePartsLength <= 1:
			raise CommandInputException("Please also provide an alias name. Use the 'list' subcommand to see which aliases exist")
		aliasname = message.messageParts[1]
		alias = self.retrieveAlias(message.bot.serverfolder, message.source, aliasname)

		if parameter == "serveradd" or parameter == "channeladd" or parameter == "add":
			#Restrict alias creation to admins for now
			if not message.doesSenderHavePermission(PermissionLevel.SERVER if parameter == "serveradd" else PermissionLevel.CHANNEL):
				raise CommandInputException("Only {0} admins can create {0} aliases, sorry! Poke one of them if you want an alias created")

			if parameter != "serveradd" and message.isPrivateMessage:
				message.reply("Channel aliases aren't allowed in private messages, sorry")
				return
			elif message.messagePartsLength <= 2:
				message.reply("While I love running random code as much as the next bot, please add an actual command to store as an alias")
				return

			#Prevent an alias for 'alias' to prevent breakage
			if aliasname == "alias":
				message.reply("Leeeeet's not break this whole module, shall we? Better use a different name for this alias")
				return

			#Check if an alias with the same name doesn't exist already
			if alias is not None:
				message.reply("'{}' already is an alias! Looks like you weren't the only one with this presumably great idea!".format(aliasname))
				return

			#Check if there is a module that already has the trigger that we want to set for this alias
			for modulename, module in GlobalStore.commandhandler.getCommandsIterator(message.bot, message.source):
				#Also check if the module is enabled for this server, because if, say, the help module is disabled, creating a 'help' alias isn't a problem
				if aliasname in module.triggers:
					message.reply("'{}' is already a trigger for the {} module, so using it as an alias would just get confusing. I'm sure you can think of another name though!".format(aliasname, modulename))
					return

			if parameter == "serveradd" and server not in self.aliases:
				self.aliases[server] = {}
			elif (parameter == "channeladd" or parameter == "add") and serverChannelString not in self.aliases:
				self.aliases[serverChannelString] = {}
			aliasToAdd = " ".join(message.messageParts[2:])
			self.aliases[server if parameter == "serveradd" else serverChannelString][aliasname] = aliasToAdd
			self.saveAliases()
			if aliasname not in self.aliasNameList:
				self.aliasNameList.append(aliasname)
			return message.reply("Stored the alias '{}' for this {}!".format(aliasname, "server" if parameter == "serveradd" else "channel"))

		# All of the following subcommands need an existing alias, so check if we have one
		if not alias:
			raise CommandInputException("I'm not familiar with the alias '{}', sorry. Either you made a typo, and you should use the 'list' subcommand to see how it should be spelled, "
								 "or it doesn't exist yet in which case you should ask an admin to create it".format(aliasname))

		if parameter == "show":
			return message.reply(u"{}: {}".format(aliasname, alias.command))

		elif parameter == "remove":
			#Restrict alias removal to bot admins as well
			if not message.doesSenderHavePermission(PermissionLevel.SERVER if alias.isServerAlias else PermissionLevel.CHANNEL):
				return message.reply("Removing {0} aliases is limited to {0} admins only for now, sorry! Poke them if you think an alias should be removed".format("server" if alias.isServerAlias else "channel"))
			aliasname = message.messageParts[1].lower()
			aliasKey = None
			if server in self.aliases and aliasname in self.aliases[server]:
				aliasKey = server
			elif serverChannelString in self.aliases and aliasname in self.aliases[serverChannelString]:
				aliasKey = serverChannelString

			if not aliasKey:
				return message.reply("I don't know the alias '{}', so removal mission accomplished I guess?".format(aliasname))
			else:
				del self.aliases[aliasKey][aliasname]
				#If no other aliases are stored for this server/channel, remove the entire key
				if len(self.aliases[aliasKey]) == 0:
					del self.aliases[aliasKey]
					self.aliasNameList.remove(aliasname)
				self.saveAliases()
				return message.reply("Ok, successfully removed the alias '{}'".format(aliasname))

		elif parameter == "help":
			if not alias.helptext:
				return message.reply("The alias '{0}' doesn't have any help text set, sorry. Either ask my admin(s) for an explanation, or try to parse it yourself by using '{1}alias show {0}'".format(aliasname, message.bot.commandPrefix))
			return message.reply("{}{}: {}".format(message.bot.commandPrefix, aliasname, alias.helptext))

		elif parameter == 'sethelp':
			if not message.doesSenderHavePermission(PermissionLevel.SERVER if alias.isServerAlias else PermissionLevel.CHANNEL):
				return message.reply("Only {0} admins are allowed to set or change a {0} alias's helptext, sorry! Tell one of them that you have an idea for an alias helptext!".format("server" if alias.isServerAlias else "channel"))
			if message.messagePartsLength <= 2:
				return message.reply("Please add the help text you want to set for the '{}' alias, because I sure can't explain how it works".format(message.messageParts[1]))
			self.aliases[alias.aliasKey][aliasname.lower()] = [alias.command, " ".join(message.messageParts[2:])]
			self.saveAliases()
			return message.reply("Ok, I set the help text for the '{}' alias, that should help people understand how it works".format(aliasname))

		else:
			message.reply("I don't know what to do with the parameter '{}'. Please (re)read the help text for info on how to use this module, or poke my owner(s) if you have questions".format(parameter))

	def retrieveAlias(self, server, channel, aliasname):
		loweredAliasName = aliasname.lower()
		aliasData = None
		aliasKey = None
		isServerAlias = False
		if server in self.aliases and loweredAliasName in self.aliases[server]:
			aliasData = self.aliases[server][loweredAliasName]
			aliasKey = server
			isServerAlias = True
		else:
			serverChannelString = self.createServerChannelString(server, channel)
			if serverChannelString in self.aliases and loweredAliasName in self.aliases[serverChannelString]:
				aliasData = self.aliases[serverChannelString][loweredAliasName]
				aliasKey = serverChannelString
		if not aliasData:
			return None
		aliasHelptext = None
		if isinstance(aliasData, list):
			aliasCommand, aliasHelptext = aliasData
		else:
			aliasCommand = aliasData
		return Alias(aliasname, aliasCommand, aliasKey, isServerAlias, aliasHelptext)

	def parseAndSendAlias(self, message):
		"""
		:type message: IrcMessage
		"""
		# Alias called, create a new IrcMessage and send it to the CommandHandler
		# First retrieve the actual alias
		server = message.bot.serverfolder
		alias = self.retrieveAlias(server, message.source, message.trigger)
		if not alias:
			# No alias found for the provided trigger on the message's server, abort
			return

		#Create a grammar dictionary out of the alias text
		aliasDict = {'start': alias.command}
		#Numbered fields refer to message parts.
		# Use '<0>' to refer to the whole message (grammar also accepts '<_params>' but this is for completion's sake
		aliasDict['0'] = message.message if message.messagePartsLength > 0 else ""
		#  Fill in enough fields for aliases that use numbered fields not to error out
		for i in range(0, 11):
			aliasDict[str(i+1)] = message.messageParts[i] if i < message.messagePartsLength else ""
		aliasDict['nick'] = message.userNickname
		aliasDict['CP'] = message.bot.commandPrefix
		# The grammar module stores some info from the message the grammar file is called from, fill that in here too because some grammar commands use it
		variableDict = {'_sourceserver': server, '_sourcechannel': message.source, '_sourcenick': message.userNickname}
		# Pass along the last message so the alias can use it, if needed
		if 'lastMessage' in alias.command:
			lastMessage = GlobalStore.commandhandler.runCommandFunction('getLastMessage', '', server, message.source, '')
			# Escape any special grammar characters in the message, otherwise stuff like URLs get parsed wrong because of the /
			lastMessage = GlobalStore.commandhandler.runCommandFunction('escapeGrammarString', lastMessage, lastMessage)
			# Pass it along as a variable to the alias
			variableDict['lastMessage'] = lastMessage
		#Always send along parameters
		parameters = message.messageParts if message.messagePartsLength > 0 else None
		newMessageText = GlobalStore.commandhandler.runCommandFunction('parseGrammarDict', None, aliasDict, message.trigger,
																	   parameters=parameters, variableDict=variableDict)
		#Check if the parsing went well
		if newMessageText.startswith("Error: "):
			message.reply("Something went wrong with executing the alias: " + newMessageText.split(': ', 1)[1])
			return
		#Aliases that use parameters can end with whitespace at the end. Remove that
		newMessageText = newMessageText.rstrip()

		# Allow for newlines in aliases, each a new message
		for newMessageLine in newMessageText.split("\\n"):
			#Done! Send the new message to the Commandhandler
			newMessage = IrcMessage(message.messageType, message.bot, message.user, message.source, newMessageLine)
			GlobalStore.commandhandler.handleMessage(newMessage)

	def saveAliases(self):
		with open(os.path.join(GlobalStore.scriptfolder, "data", "Aliases.json"), 'w', encoding='utf-8') as aliasFile:
			aliasFile.write(json.dumps(self.aliases))

	def createServerChannelString(self, server, channel):
		return "{} {}".format(server, channel)


class Alias(object):
	def __init__(self, name, command, aliasKey, isServerAlias, helptext=None):
		self.name = name
		self.command = command
		self.aliasKey = aliasKey
		self.isServerAlias = isServerAlias
		self.helptext = helptext
