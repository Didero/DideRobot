import os, sys
import traceback
from ConfigParser import ConfigParser

import GlobalStore

class CommandHandler:
	commands = {}
	apikeys = ConfigParser()
	
	def __init__(self):
		self.loadApiKeys()


	def loadApiKeys(self):
		self.apikeys = ConfigParser()
		if not os.path.exists(os.path.join('data', 'apikeys.ini')):
			print "ERROR: API key file not found!"
		else:
			self.apikeys.read(os.path.join('data', 'apikeys.ini'))

	def saveApiKeys(self):
		with open(os.path.join('data', 'apikeys.ini'), 'w') as apifile:
			self.apikeys.write(apifile)

	
	def fireCommand(self, bot, user, target, msg):
		username = user.split("!", 1)[0]
		if username not in bot.factory.userIgnoreList and user not in bot.factory.userIgnoreList:
			msgParts = msg.split(" ")
			msgPartsLength = len(msgParts)

			triggerInMsg = ""
			if msg.startswith(bot.factory.commandPrefix):
				triggerInMsg = msgParts[0][bot.factory.commandPrefixLength:].lower()
			#Check if message started with something like "DideRobot:". Interpret it as the same as a command prefix
			elif msg.startswith(bot.nickname) and len(msgParts[0]) == len(bot.nickname) + 1:
				#Remove the nickname part, otherwise all the modules need to have extra checks to handle this exception
				if msgPartsLength > 1:
					msgParts = msgParts[1:]
					msgPartsLength -= 1
					triggerInMsg = msgParts[0].lower()
					if triggerInMsg.startswith(bot.factory.commandPrefix):
						triggerInMsg = triggerInMsg[bot.factory.commandPrefixLength:]

			msgWithoutFirstWord = ""
			if msgPartsLength > 1:
				msgWithoutFirstWord = " ".join(msgParts[1:])

			commandExecutionClaimed = False
			for commandname, command in self.commands.iteritems():
				if not self.isCommandAllowedForBot(bot, commandname):
					continue

				if command.shouldExecute(bot, commandExecutionClaimed, triggerInMsg, msg, msgParts):
					if command.adminOnly and username not in bot.factory.admins and user not in bot.factory.admins:
						bot.say(target, "Sorry, this command is admin-only")
					else:
						try:
							if command.callInThread:
								print "Calling '{}' in thread".format(command.triggers[0])
								GlobalStore.reactor.callInThread(command.execute, bot, user, target, triggerInMsg, msg, msgWithoutFirstWord, msgParts, msgPartsLength)
							else:
								command.execute(bot, user, target, triggerInMsg, msg, msgWithoutFirstWord, msgParts, msgPartsLength)
						except Exception as e:
							bot.factory.logger.log("ERROR executing '{}': {}".format(commandname, str(e)), target)
							traceback.print_exc()
							bot.say(target, "Sorry, an error occured while executing this command. It has been logged, and if you tell my owner(s), they could probably fix it")
						finally:
							if command.claimCommandExecution:
								commandExecutionClaimed = True

	def isCommandAllowedForBot(self, bot, commandname):
		if bot.factory.commandWhitelist is not None and commandname not in bot.factory.commandWhitelist:
			return False
		elif bot.factory.commandBlacklist is not None and commandname in bot.factory.commandBlacklist:
			return False
		return True
	
	def loadCommands(self, folder='commands'):
		modulesToIgnore = ['__init__.py', 'CommandTemplate.py']
		#modulesToIgnore.extend(GlobalStore.settings.get("scripts", "moduleIgnoreList").split(","))
		print "module ignore list: " + ", ".join(modulesToIgnore)
		
		commandFolder = os.path.join(GlobalStore.scriptfolder, folder)
		
		success = True
		for commandFile in os.listdir(commandFolder):
			print("Loading commandfile '" + commandFile + "'")
			if (not commandFile.endswith(".py")):
				print(" Skipping " + commandFile + ", not a Python file")
				continue
			if (commandFile in modulesToIgnore or commandFile[:-3] in modulesToIgnore):
				print(" Skipping " + commandFile + " since it's in the ignore list")
				continue
			#GlobalStore.logger.log("Loading module '{}'".format(commandFile))
			
			if self.loadCommand(commandFile[:-3], folder) == False:
				success = False
				#break
				
		print "commands loaded from '{}' folder: {}".format(folder, ", ".join(self.commands))
		#print "registered modules: {}".format(", ".join(sys.modules))
		return success
		
	def loadCommand(self, name, folder='commands'):
		print "Loading command '{}.{}".format(folder, name)
		
		commandFilename = os.path.join(GlobalStore.scriptfolder, folder, name + '.py')
		if not os.path.exists(commandFilename):
			print " File '{}' does not exist, aborting".format(commandFilename)
			return False

		try:
			module = __import__(folder + '.' + name, globals(), locals(), [])
			reload(module)
		
			#'module' now has two modules, the command filename and 'py'. Only use the first one
			module = getattr(module, name)
		
			command = module.Command()
			print " commands: '{}'".format(", ".join(command.triggers))
			#for trigger in command.triggers:
			#	print("Connecting command word '" + trigger + "' to " + name)
			#	self.commands[trigger] = command
			self.commands[name] = command
			return True
		except:
			print "An error occured loading command ''".format(name)
			traceback.print_exc()
			return False

			
	def unloadCommand(self, name, folder='commands'):
		print "[unload command] scriptpath='{}'  folder='{}'  name='{}'".format(GlobalStore.scriptfolder, folder, name)
		try:
			fullname = "{}.{}".format(folder, name)
			filename = os.path.join(GlobalStore.scriptfolder, folder, name + '.py')
			print "[unload command] full filename: {}".format(filename)
			if name in self.commands:
				print "[unload command] Removing '{}' from sys.modules".format(fullname)
				if fullname in sys.modules:
					del sys.modules[fullname]
				else:
					print "[unload command] '{}' not in sys.modules".format(fullname)
				#Remove the compiled Python file
				if os.path.exists(filename + 'c'):
					os.remove(filename + 'c')
				del self.commands[name]
				print "[unload command] Finished unloading module '{}'".format(fullname)
				return True
			else:
				print "Module '{}' not in command list".format(name)
			return False
		except:
			print "[unload command] An error occured trying to unload '{}'".format(name)
			traceback.print_exc()
			return False
			
		
	def reloadCommand(self, name, folder='commands'):
		if name in self.commands:
			success = True
			if self.unloadCommand(name, folder) == False:
				success = False
			if self.loadCommand(name, folder) == False:
				success = False
			return success
		else:
			print "{} not in command list: {}".format(name, ", ".join(self.commands))
			return False
