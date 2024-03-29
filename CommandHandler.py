import importlib, json, logging, os

import gevent

import GlobalStore
from CustomExceptions import CommandException
from IrcMessage import IrcMessage


class CommandHandler:
	commands = {}
	commandFunctions = {}
	apikeys = {}


	def __init__(self):
		self.logger = logging.getLogger("DideRobot")
		GlobalStore.commandhandler = self
		self.loadApiKeys()

	def loadApiKeys(self):
		self.apikeys = {}
		if not os.path.exists(os.path.join(GlobalStore.scriptfolder, 'data', 'apikeys.json')):
			self.logger.error("API key file not found, it should be in the 'data' subfolder and called 'apikeys.json'")
		else:
			try:
				with open(os.path.join(GlobalStore.scriptfolder, 'data', 'apikeys.json'), encoding='utf-8') as apikeysFile:
					self.apikeys = json.load(apikeysFile)
			except ValueError as e:
				self.logger.error(f"API key file is invalid JSON: {e}")

	def saveApiKeys(self):
		with open(os.path.join(GlobalStore.scriptfolder, 'data', 'apikeys.json'), 'w', encoding='utf-8') as apifile:
			apifile.write(json.dumps(self.apikeys, sort_keys=True, indent=4))

	def getApiKey(self, keyName, parentKey=None):
		"""
		Get the value of the provided api key name, optionally from inside a parent key
		:param keyName: The name of the key to get
		:param parentKey: If the key you want is nested inside a sub-dictionary, provide the parent key name
		:return: The value for the provided key name, or None if no key is stored or if it wasn't filled in
		"""
		apiKey = None
		if parentKey:
			if parentKey in self.apikeys and keyName in self.apikeys[parentKey]:
				apiKey = self.apikeys[parentKey][keyName]
		else:
			apiKey = self.apikeys.get(keyName, None)
		# The apikeys.json.example has a string for each key, something like "your [keyName] API key here" or "your secret token here". Ignore those values
		if isinstance(apiKey, str) and apiKey.startswith("your "):
			apiKey = None
		return apiKey

	def addCommandFunction(self, module, name, function):
		"""
		Add a global function available to all commands thorugh 'CommandHandler.runCommandFunction'
		Usually called in the 'onLoad' of a command
		The command function gets removed automatically when the command is unloaded, or it can be manually removed with 'removeCommandFunction'
		:param module: The name of the module, usually '__file__' in the command class. This is needed to automatically remove the command function when the command module gets unloaded
		:param name: The name of the command function. This is the string other command modules have to use with 'runCommandFunction'. Not case-sensitive
		:param function: The local function inside the command module that 'runCommandFunction' should call when the name is called
		:return: True if the adding succeeded, False otherwise (for instance if the name already exists)
		"""
		name = name.lower()
		if name in self.commandFunctions:
			self.logger.warning("Trying to add a commandFuction called '{}' but it already exists".format(name))
			return False
		self.commandFunctions[name] = {'module': os.path.basename(module).split('.', 1)[0], 'function': function}
		self.logger.info("Adding command function '{}' from module '{}'".format(name, self.commandFunctions[name]['module']))
		return True

	def addCommandFunctions(self, module, *args):
		"""
		Convenience function for adding multiple actions in one go, through an argument list (name, function)
		"""
		success = True
		#Assuming the provided arguments are in 'name, function' format, cycle through them
		for i in range(0, len(args), 2):
			if not self.addCommandFunction(module, args[i], args[i+1]):
				success = False
		return success

	def removeCommandFunction(self, name):
		name = name.lower()
		if name not in self.commandFunctions:
			self.logger.warning("Trying to remove the commandFunction '{}' while it is not registered".format(name))
			return False
		self.logger.info("Removing command function '{}' registered by module '{}'".format(name, self.commandFunctions[name]['module']))
		del self.commandFunctions[name]
		return True

	def hasCommandFunction(self, name):
		return name.lower() in self.commandFunctions

	def runCommandFunction(self, name, defaultValue=None, *args, **kwargs):
		"""
		Run a command function, which is a function another command module registered for global access
		:param name: The name of the command function to run. Not case sensitive
		:param defaultValue: The default value to return if the provided name isn't a registered command function
		:param args: The argument(s) to pass to the command function. Optional
		:param kwargs: The keyword argument(s) to pass to the command function. Optional
		:return: The result of the command function, or the default value if there is no command function with the provided name
		"""
		name = name.lower()
		if name not in self.commandFunctions:
			self.logger.warning("Unknown commandFunction '{}' called".format(name))
			return defaultValue
		return self.commandFunctions[name]['function'](*args, **kwargs)

	def handleMessage(self, message):
		"""
		:type message: IrcMessage
		"""
		#First check if this user is even allowed to call commands
		if message.bot.shouldUserBeIgnored(message.user, message.userNickname, message.userAddress):
			return

		#Then check whether any of our loaded commands need to react to this message
		settingSource = None if message.isPrivateMessage else message.source
		for commandname, command in self.getCommandsIterator(message.bot, settingSource):
			if command.shouldExecute(message):
				if command.minPermissionLevel and not message.doesSenderHavePermission(command.minPermissionLevel):
					message.reply("Sorry, this command can only be used by {}s".format(command.minPermissionLevel))
				else:
					if command.callInThread:
						gevent.spawn(self.executeCommand, commandname, message)
					else:
						self.executeCommand(commandname, message)
					if command.stopAfterThisCommand:
						break

	def executeCommand(self, commandname, message):
		try:
			self.commands[commandname].execute(message)
		except Exception as e:
			displayMessage = "Sorry, an error occurred while executing this command. It has been logged, and if you tell my owner(s), they could probably fix it"
			shouldLogError = True
			shouldLogStacktrace = True
			# Check if it's a special Command Exception, which should have a more specific display error
			# And It should have logged more extensive information if available, so we don't need a stacktrace here
			if isinstance(e, CommandException):
				shouldLogError = e.shouldLogError
				shouldLogStacktrace = False
				if e.displayMessage:
					displayMessage = e.displayMessage

			# Show the user the (custom or generic) error message, and log the error to the program log
			message.reply(displayMessage)
			if shouldLogError:
				self.logger.error("{} exception thrown while handling command '{}' and message '{}': {}".format(type(e).__name__, commandname, message.rawText, str(e)), exc_info=shouldLogStacktrace)

	@staticmethod
	def isCommandAllowedForBot(bot, commandname: str, channel: str = None, allowlist = None, blocklist = None):
		if allowlist is None and blocklist is None:
			allowlist, blocklist = bot.getCommandAllowAndBlockLists(channel)
		if allowlist and commandname not in allowlist:
			return False
		if blocklist and commandname in blocklist:
			return False
		return True
	
	def loadCommands(self, folder='commands'):
		modulesToIgnore = ('__init__.py', 'CommandTemplate.py')
		commandsWithErrors = []
		self.logger.info("Loading commands from subfolder '{}'".format(folder))
		for commandFile in os.listdir(os.path.join(GlobalStore.scriptfolder, folder)):
			if not commandFile.endswith(".py"):
				continue
			commandName = commandFile[:-3]
			if commandFile in modulesToIgnore or commandName in modulesToIgnore:
				continue
			try:
				self.loadCommand(commandName, folder)
			except CommandException:
				commandsWithErrors.append(commandName)
		return commandsWithErrors
		
	def loadCommand(self, name, folder='commands'):
		self.logger.info("Loading command '{}.{}".format(folder, name))
		commandFilename = os.path.join(GlobalStore.scriptfolder, folder, name + '.py')
		if not os.path.exists(commandFilename):
			self.logger.warning("File '{}' does not exist, aborting".format(commandFilename))
			raise CommandException("File '{}' does not exist".format(name))
		try:
			loadedModule = importlib.import_module(folder + '.' + name)
			#Since the module may already have been loaded in the past, make sure we have the latest version
			importlib.reload(loadedModule)
			command = loadedModule.Command()
			self.commands[name] = command
			return command
		except Exception as e:
			exceptionName = e.__class__.__name__
			self.logger.error("A {} error occurred while trying to load command '{}': {}".format(exceptionName, name, e), exc_info=True)
			raise CommandException("{} exception occurred while loading command '{}'".format(exceptionName, name))

	def unloadCommand(self, name, folder='commands'):
		fullname = "{}.{}".format(folder, name)
		self.logger.info("Unloading module '{}'".format(fullname))
		if name not in self.commands:
			self.logger.warning("Asked to unload module '{}', but it was not found in command list".format(fullname))
			raise CommandException("Module '{}' not in command list".format(name))
		try:
			#Inform the module it's being unloaded
			self.commands[name].unload()
			#And remove the reference to it
			del self.commands[name]
			#Check if any registered command functions belong to this module
			functionsToRemove = []
			for funcName in self.commandFunctions.keys():
				if name == self.commandFunctions[funcName]['module']:
					functionsToRemove.append(funcName)
			if len(functionsToRemove) > 0:
				self.logger.info("Removing {} registered command functions".format(len(functionsToRemove)))
				for funcToRemove in functionsToRemove:
					del self.commandFunctions[funcToRemove]
		except Exception as e:
			exceptionName = e.__class__.__name__
			self.logger.error("A {}error occurred while trying to unload '{}': {}".format(exceptionName, name, e), exc_info=True)
			raise CommandException("{} exception occurred while unloading command '{}'".format(exceptionName, name))

	def unloadAllCommands(self):
		self.logger.info("Unloading all commands")
		commandsWithErrors = []
		#Take the keys instead of just iterating over the dict, to prevent size change errors
		for commandname in list(self.commands.keys()):
			try:
				self.unloadCommand(commandname)
			except CommandException as e:
				self.logger.error(f"Error while unloading '{commandname}': {e}")
				commandsWithErrors.append(commandname)
		return commandsWithErrors
		
	def reloadCommand(self, name, folder='commands'):
		if name in self.commands:
			self.unloadCommand(name, folder)
			self.loadCommand(name, folder)
		else:
			raise CommandException("Told to reload '{}' but it's not in command list".format(name))

	def getCommandsIterator(self, bot, channel: str = None):
		"""
		Get an iterator over all the commands allowed for the provided bot and optionally for the provided channel
		:param bot: The bot instance to get the allowed commands for
		:param channel: The channel to get the allowed commands for. If omitted, or if no channel-specific allow- or blocklist is set for the provided channel, the commands allowed for the server are returned
		:return: An iterator returning commandname-commandobject pairs for the allowed commands for the bot and optionally the channel
		"""
		allowlist, blocklist = bot.getCommandAllowAndBlockLists(channel)
		for commandname, command in self.commands.items():
			if self.isCommandAllowedForBot(bot, commandname, allowlist=allowlist, blocklist=blocklist):
				yield commandname, command
