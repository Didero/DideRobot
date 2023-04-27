import json, os

import GlobalStore
from CommandTemplate import CommandTemplate
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
			with open(filepath, "r") as f:
				self.aliases = json.load(f)
			#Build the quick-lookup aliasname list
			for aliasTarget, aliasDict in self.aliases.iteritems():
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
				return message.reply(u"{:,} alias{}: {}".format(len(aliasNames), u"es" if len(aliasNames) > 1 else u"", u", ".join(sorted(aliasNames))))

		# Check if an alias name has been provided and retrieve the alias if so, because all following subcommands need that information
		if message.messagePartsLength <= 1:
			raise CommandInputException("Please also provide an alias name. Use the 'list' subcommand to see which aliases exist")
		aliasname = message.messageParts[1]
		alias = self.retrieveAlias(message.bot.serverfolder, message.source, aliasname)

		if parameter == "serveradd" or parameter == "channeladd" or parameter == "add":
			#Restrict alias creation to bot admins for now
			if not message.bot.isUserAdmin(message.user, message.userNickname, message.userAddress):
				message.reply("Alias creation is limited to bot admins only for now, sorry! Poke them if you want an alias created")
				return

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
				message.reply(u"'{}' already is an alias! Looks like you weren't the only one with this presumably great idea!".format(aliasname))
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
			return message.reply(u"Stored the alias '{}' for this {}!".format(aliasname, "server" if parameter == "serveradd" else "channel"))

		# All of the following subcommands need an existing alias, so check if we have one
		if not alias:
			raise CommandInputException("I'm not familiar with the alias '{}', sorry. Either you made a typo, and you should use the 'list' subcommand to see how it should be spelled, "
								 "or it doesn't exist yet in which case you should ask an admin to create it".format(aliasname))

		if parameter == "show":
			return message.reply(u"{}: {}".format(aliasname, alias))

		elif parameter == "remove":
			#Restrict alias removal to bot admins as well
			if not message.bot.isUserAdmin(message.user, message.userNickname, message.userAddress):
				return message.reply("Alias removal is limited to bot admins only for now, sorry! Poke them if you think an alias should be removed")
			aliasname = message.messageParts[1].lower()
			aliasKey = None
			if server in self.aliases and aliasname in self.aliases[server]:
				aliasKey = server
			elif serverChannelString in self.aliases and aliasname in self.aliases[serverChannelString]:
				aliasKey = serverChannelString

			if not aliasKey:
				return message.reply(u"I don't know the alias '{}', so removal mission accomplished I guess?".format(aliasname))
			else:
				del self.aliases[aliasKey][aliasname]
				#If no other aliases are stored for this server/channel, remove the entire key
				if len(self.aliases[aliasKey]) == 0:
					del self.aliases[aliasKey]
					self.aliasNameList.remove(aliasname)
				self.saveAliases()
				return message.reply(u"Ok, successfully removed the alias '{}'".format(aliasname))

		elif parameter == "help":
			if not alias.helptext:
				return message.reply("The alias '{0}' doesn't have any help text set, sorry. Either ask my admin(s) for an explanation, or try to parse it yourself by using '{1}alias show {0}'".format(aliasName, message.bot.commandPrefix))
			return message.reply(u"{}{}: {}".format(message.bot.commandPrefix, aliasname, alias.helptext))

		elif parameter == 'sethelp':
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
		if server in self.aliases and loweredAliasName in self.aliases[server]:
			aliasData = self.aliases[server][loweredAliasName]
			aliasKey = server
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
		return Alias(aliasname, aliasCommand, aliasKey, aliasHelptext)

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
		aliasDict = {u'start': alias.command}
		#Numbered fields refer to message parts.
		# Use '<0>' to refer to the whole message (grammar also accepts '<_params>' but this is for completion's sake
		aliasDict[u'0'] = message.message if message.messagePartsLength > 0 else u""
		#  Fill in enough fields for aliases that use numbered fields not to error out
		for i in xrange(0, 11):
			aliasDict[unicode(i+1)] = message.messageParts[i] if i < message.messagePartsLength else u""
		aliasDict[u'nick'] = message.userNickname
		aliasDict[u'CP'] = message.bot.commandPrefix
		# The grammar module stores some info from the message the grammar file is called from, fill that in here too because some grammar commands use it
		variableDict = {u'_sourceserver': server, u'_sourcechannel': message.source, u'_sourcenick': message.userNickname}
		# Pass along the last message so the alias can use it, if needed
		if u'lastMessage' in alias.command:
			lastMessage = GlobalStore.commandhandler.runCommandFunction('getLastMessage', '', server, message.source, '')
			# Generator module expects all text to be unicode
			if not isinstance(lastMessage, unicode):
				lastMessage = unicode(lastMessage, 'utf-8', errors='replace')
			# Escape any special grammar characters in the message, otherwise stuff like URLs get parsed wrong because of the /
			lastMessage = GlobalStore.commandhandler.runCommandFunction('escapeGrammarString', lastMessage, lastMessage)
			# Pass it along as a variable to the alias
			variableDict[u'lastMessage'] = lastMessage
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

	def createServerChannelString(self, server, channel):
		return "{} {}".format(server, channel)


class Alias(object):
	def __init__(self, name, command, aliasKey, helptext=None):
		self.name = name
		self.command = command
		self.aliasKey = aliasKey
		self.helptext = helptext
