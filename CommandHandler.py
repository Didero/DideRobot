import importlib, os, traceback
from ConfigParser import ConfigParser

import GlobalStore
from IrcMessage import IrcMessage


class CommandHandler:
	commands = {}
	commandFunctions = {}
	apikeys = ConfigParser()
	
	def __init__(self):
		GlobalStore.commandhandler = self
		self.loadApiKeys()

	def loadApiKeys(self):
		self.apikeys = ConfigParser()
		if not os.path.exists(os.path.join(GlobalStore.scriptfolder, 'data', 'apikeys.ini')):
			print "[CH] ERROR: API key file not found!"
		else:
			self.apikeys.read(os.path.join(GlobalStore.scriptfolder, 'data', 'apikeys.ini'))

	def saveApiKeys(self):
		with open(os.path.join(GlobalStore.scriptfolder, 'data', 'apikeys.ini'), 'w') as apifile:
			self.apikeys.write(apifile)

	def addCommandFunction(self, module, name, function):
		if name in self.commandFunctions:
			print "[CH] ERROR: Trying to add a commandFuction called '{}' but it already exists".format(name)
			return False
		print "[CH] Adding command function '{}' from module '{}'".format(name, os.path.basename(module).split('.')[0])
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
			print "[CH] ERROR: Trying to remove the commandFunction '{}' while it is not registered".format(name)
			return False
		print "[CH] Removing command function '{}' registered by module '{}'".format(name, self.commandFunctions[name]['module'])
		del self.commandFunctions[name]
		return True

	def hasCommandFunction(self, name):
		return name.lower() in self.commandFunctions

	def runCommandFunction(self, name, defaultValue=None, *args, **kwargs):
		name = name.lower()
		if name not in self.commandFunctions:
			print "[CH] ERROR: Unknown commandFunction '{}' called".format(name)
			return defaultValue
		return self.commandFunctions[name]['function'](*args, **kwargs)

	def fireCommand(self, message):
		"""
		:type message: IrcMessage
		"""
		if not message.bot.factory.shouldUserBeIgnored(message.user, message.userNickname):
			commandExecutionClaimed = False
			for commandname, command in self.commands.iteritems():
				if not self.isCommandAllowedForBot(message.bot, commandname):
					continue

				if command.shouldExecute(message, commandExecutionClaimed):
					if command.adminOnly and not message.bot.factory.isUserAdmin(message.user, message.userNickname):
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
			message.bot.factory.logger.log("ERROR executing '{}': {}".format(commandname, str(e)), message.source)
			traceback.print_exc()

	@staticmethod
	def isCommandAllowedForBot(bot, commandname):
		commandname = commandname.lower()
		if bot.factory.commandWhitelist is not None and commandname not in bot.factory.commandWhitelist:
			return False
		elif bot.factory.commandBlacklist is not None and commandname in bot.factory.commandBlacklist:
			return False
		return True
	
	def loadCommands(self, folder='commands'):
		modulesToIgnore = ['__init__.py', 'CommandTemplate.py']
		success = True
		print "[CH] Loading commands from subfolder '{}'".format(folder)
		for commandFile in os.listdir(os.path.join(GlobalStore.scriptfolder, folder)):
			if not commandFile.endswith(".py"):
				continue
			if commandFile in modulesToIgnore or commandFile[:-3] in modulesToIgnore:
				continue
			if not self.loadCommand(commandFile[:-3], folder):
				success = False
		return success
		
	def loadCommand(self, name, folder='commands'):
		print "[CH] Loading command '{}.{}".format(folder, name)
		commandFilename = os.path.join(GlobalStore.scriptfolder, folder, name + '.py')
		if not os.path.exists(commandFilename):
			print "[CH] File '{}' does not exist, aborting".format(commandFilename)
			return False
		try:
			module = importlib.import_module(folder + '.' + name)
			#Since the module may already have been loaded in the past, make sure we have the latest version
			reload(module)
			command = module.Command()
			self.commands[name] = command
			return True
		except:
			print "[CH] An error occurred while trying to load command '{}'".format(name)
			traceback.print_exc()
			return False

	def unloadCommand(self, name, folder='commands'):
		fullname = "{}.{}".format(folder, name)
		print "[CH] Unloading module '{}'".format(fullname)
		if name not in self.commands:
			print "[CH] Module '{}' not in command list".format(fullname)
			return False
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
				print "[CH] Removing {} registered command functions".format(len(functionsToRemove))
				for funcToRemove in functionsToRemove:
					del self.commandFunctions[funcToRemove]
			return True
		except:
			print "[CH] An error occurred trying to unload '{}'".format(name)
			traceback.print_exc()
			return False

	def unloadAllCommands(self):
		#Take the keys instead of iteritems() to prevent size change errors
		for commandname in self.commands.keys():
			self.unloadCommand(commandname)
		
	def reloadCommand(self, name, folder='commands'):
		if name in self.commands:
			success = True
			if not self.unloadCommand(name, folder):
				success = False
			if not self.loadCommand(name, folder):
				success = False
			return success
		else:
			print "[CH] Told to reload '{}' but it's not in command list: {}".format(name, ", ".join(self.commands))
			return False
