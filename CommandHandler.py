import importlib, json, logging, os, traceback

import GlobalStore
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
			self.logger.error("API key file at not found! It should be in the 'data' subfolder and called 'apikeys.json'")
		else:
			try:
				with open(os.path.join(GlobalStore.scriptfolder, 'data', 'apikeys.json')) as apikeysFile:
					self.apikeys = json.load(apikeysFile)
			except ValueError:
				self.logger.error("API key file is invalid JSON!")

	def saveApiKeys(self):
		with open(os.path.join(GlobalStore.scriptfolder, 'data', 'apikeys.json'), 'w') as apifile:
			apifile.write(json.dumps(self.apikeys, sort_keys=True, indent=4))

	def addCommandFunction(self, module, name, function):
		if name in self.commandFunctions:
			self.logger.warning("Trying to add a commandFuction called '{}' but it already exists".format(name))
			return False
		self.logger.info("Adding command function '{}' from module '{}'".format(name, os.path.basename(module).split('.')[0]))
		self.commandFunctions[name.lower()] = {'module': os.path.basename(module).split('.')[0], 'function': function}
		return True

	def addCommandFunctions(self, module, *args):
		"""
		Convenience function for adding multiple actions in one go, through an argument list (name, function)
		"""
		success = True
		#Assuming the provided arguments are in 'name, function' format, cycle through them
		for i in xrange(0, len(args), 2):
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
		name = name.lower()
		if name not in self.commandFunctions:
			self.logger.warning("Unknown commandFunction '{}' called".format(name))
			return defaultValue
		return self.commandFunctions[name]['function'](*args, **kwargs)

	def fireCommand(self, message):
		"""
		:type message: IrcMessage
		"""
		if not message.bot.factory.shouldUserBeIgnored(message.user, message.userNickname, message.userAddress):
			for commandname, command in self.commands.iteritems():
				if not self.isCommandAllowedForBot(message.bot, commandname):
					continue

				if command.shouldExecute(message):
					if command.adminOnly and not message.bot.factory.isUserAdmin(message.user, message.userNickname, message.userAddress):
						message.bot.say(message.source, "Sorry, this command is admin-only")
					else:
						if command.callInThread:
							#print "Calling '{}' in thread".format(command.triggers[0])
							GlobalStore.reactor.callInThread(self.executeCommand, commandname, message)
						else:
							self.executeCommand(commandname, message)
						if command.stopAfterThisCommand:
							break

	def executeCommand(self, commandname, message):
		try:
			self.commands[commandname].execute(message)
		except Exception as e:
			message.bot.say(message.source, "Sorry, an error occurred while executing this command. It has been logged, and if you tell my owner(s), they could probably fix it")
			message.bot.factory.messageLogger.log("ERROR executing '{}': {}".format(commandname, str(e)), message.source)
			self.logger.error("Exception thrown while handling command '{}' and message '{}'".format(commandname, message.rawText), exc_info=True)
			traceback.print_exc()

	@staticmethod
	def isCommandAllowedForBot(bot, commandname):
		if bot.factory.settings['commandWhitelist'] is not None and commandname not in bot.factory.settings['commandWhitelist']:
			return False
		elif bot.factory.settings['commandBlacklist'] is not None and commandname in bot.factory.settings['commandBlacklist']:
			return False
		return True
	
	def loadCommands(self, folder='commands'):
		modulesToIgnore = ('__init__.py', 'CommandTemplate.py')
		success = True
		errors = []
		self.logger.info("Loading commands from subfolder '{}'".format(folder))
		for commandFile in os.listdir(os.path.join(GlobalStore.scriptfolder, folder)):
			if not commandFile.endswith(".py"):
				continue
			if commandFile in modulesToIgnore or commandFile[:-3] in modulesToIgnore:
				continue
			loadResult = self.loadCommand(commandFile[:-3], folder)
			if not loadResult[0]:
				success = False
				errors.append(loadResult[1])
		return (success, errors)
		
	def loadCommand(self, name, folder='commands'):
		self.logger.info("Loading command '{}.{}".format(folder, name))
		commandFilename = os.path.join(GlobalStore.scriptfolder, folder, name + '.py')
		if not os.path.exists(commandFilename):
			self.logger.warning("File '{}' does not exist, aborting".format(commandFilename))
			return (False, "File '{}' does not exist".format(name))
		try:
			module = importlib.import_module(folder + '.' + name)
			#Since the module may already have been loaded in the past, make sure we have the latest version
			reload(module)
			command = module.Command()
			self.commands[name] = command
			return (True, "Successfully loaded file '{}'".format(name))
		except Exception as e:
			self.logger.error("An error occurred while trying to load command '{}'".format(name), exc_info=True)
			traceback.print_exc()
			return (False, e)

	def unloadCommand(self, name, folder='commands'):
		fullname = "{}.{}".format(folder, name)
		self.logger.info("Unloading module '{}'".format(fullname))
		if name not in self.commands:
			self.logger.warning("Asked to unload module '{}', but it was not found in command list".format(fullname))
			return (False, "Module '{}' not in command list".format(name))
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
			return (True, "Module '{}' successfully unloaded".format(name))
		except Exception as e:
			self.logger.error("An error occurred while trying to unload '{}'".format(name), exc_info=True)
			traceback.print_exc()
			return (False, e)

	def unloadAllCommands(self):
		self.logger.info("Unloading all commands")
		#Take the keys instead of iteritems() to prevent size change errors
		for commandname in self.commands.keys():
			self.unloadCommand(commandname)
		
	def reloadCommand(self, name, folder='commands'):
		if name in self.commands:
			result = self.unloadCommand(name, folder)
			if not result[0]:
				return (False, result[1])
			result = self.loadCommand(name, folder)
			if not result[0]:
				return (False, result[1])
			return (True, "Successfully reloaded command '{}'".format(name))
		else:
			self.logger.warning("Told to reload '{}' but it's not in command list".format(name))
			return (False, "Unknown command '{}'".format(name))
