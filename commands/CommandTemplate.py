import logging

import gevent

import MessageTypes

class CommandTemplate(object):
	"""
	The base class for Commands. If you make your own command, it should inherit from this class
	"""

	#Each command has certain settings. These are the default values, but you can override them in your command
	triggers = []  #A list of trigger words that the command should react to. These should all be lowercase, since the CommandHandler makes triggers in incoming messages lowercase too, to speed up checking
	helptext = "This help text has not yet been filled in. Oops"  #This text will get shown when users call '!help [trigger]', and should explain how the command works. Use '{commandPrefix}' in the help text to have the current command prefix filled in
	allowedMessageTypes = [MessageTypes.SAY]  #The message type(s) this command should react to. See the 'MessageTypeEnum' class for the available message types

	adminOnly = False  #If this is set to True, only users in the admin list for this server can call this command
	callInThread = False  #If you think your command will be slow, set this to True to make it run in a separate 'thread', meaning the bot won't be blocked while the command is running
	showInCommandList = True  #If this is set to False, this command won't be shown in the '!help' list of all commands
	stopAfterThisCommand = False  #Some commands might affect the list of loaded commands, which leads to errors if all commands get called. If this is set to True and the command executes, no further commands are asked if they should execute
	scheduledFunctionTime = None  #The command's 'executeScheduledFunction' method gets called periodically, with a wait of the number of seconds specified here between each call. Set to None if you don't want to run a scheduled method

	#These are for internal use and shouldn't be overwritten in your command
	scheduledFunctionGreenlet = None  #The greenlet that manages the scheduled function, or None if there isn't one
	scheduledFunctionIsExecuting = False  #Is set to True if the scheduled function is running, so we know when we can kill the scheduler greenlet. Can be read in your 'execute' method but shouldn't be changed there


	def __init__(self):
		"""
		Initialization of the command
		Don't override this in your command, use the 'onLoad' method if you want to do something during command initialization
		"""
		self.onLoad()  #Put this before starting the scheduled function because it may rely on loaded data
		if self.scheduledFunctionTime:
			self.scheduledFunctionGreenlet = gevent.spawn(self.keepRunningScheduledFunction)

	def onLoad(self):
		"""
		This method is called when a module is loaded
		If you need to initialize some data, override this method and add your data loading code here
		"""
		pass

	def unload(self):
		"""
		This method handles unloading of the module
		Don't override this in your command, use the 'onUnload' method if you need to do something when your command gets unloaded
		"""
		if self.scheduledFunctionTime:
			#We need to shut down the looping greenlet that calls the scheduled function
			# If it's not currently executing, we can stop it right now
			if not self.scheduledFunctionIsExecuting:
				self.scheduledFunctionGreenlet.kill()
			else:
				#If we set the scheduled function time to 'None', it'll stop looping, so the greenlet will exit once the scheduled function completes
				self.logInfo("Telling scheduled function to quit after finishing the current run")
				self.scheduledFunctionTime = None
		self.onUnload()

	def onUnload(self):
		"""
		This method gets called when a command is unloaded
		If you need to save some data before that happens, override this method and add your saving code here
		"""
		pass

	def getHelp(self, message):
		"""
		This method returns the help string for this command, with some added info like admin-only status and the command triggers
		Don't override this
		:param message: The IrcMessage object that is the source of the 'help' call
		:return: The formatted help text of this command
		"""
		#Will be formatted like '!help, !helpfull'
		if self.triggers:
			replytext = "{commandPrefix}" + ", {commandPrefix}".join(self.triggers)
		else:
			replytext = "(no command trigger)"
		#Some commands can only be used by people in the admins list. Inform users of that
		if self.adminOnly:
			replytext += " [admin-only]"
		replytext += ": " + self.helptext
		# Since some modules have '{commandPrefix}' in their helptext, turn that into the actual command prefix
		replytext = replytext.format(commandPrefix=message.bot.commandPrefix)
		return replytext

	def shouldExecute(self, message):
		"""
		This method checks whether this command should execute based on the provided IrcMessage
		It's usually not necessary to override this method, unless you want something more than a basic check on whether the message type matches and one of this command's triggers was used
		:param message: The IrcMessage object that represents an IRC message recieved by the bot
		:return: True if this message should cause the 'execute' method to be called, False if not
		"""
		#Check if we need to respond, ordered from cheapest to most expensive check
		#  (the allowedMessageTypes list is usually short, most likely shorter than the triggers list)
		if message.trigger and message.messageType in self.allowedMessageTypes and message.trigger in self.triggers:
			return True
		return False

	def execute(self, message):
		"""
		This method should be overridden in commands, since it gets called if this command should react to an incoming IrcMessage, determined by the 'shouldExecute' method
		Usually this is done by parsing the message and by the bot saying a message of its own (by using the 'message.reply' method), but sending a reply isn't mandatory
		:param message: The IrcMessage object that represents the received IRC message this command needs to handle
		"""
		pass

	def keepRunningScheduledFunction(self):
		"""
		This method takes makes sure the scheduled function gets called on schedule
		This method shouldn't be overridden, if you want to set the sheduled function, override 'executeScheduledFunction'
		"""
		self.logInfo("Executing looping function every {} seconds".format(self.scheduledFunctionTime))
		try:
			while self.scheduledFunctionTime and self.scheduledFunctionTime > 0:
				self.scheduledFunctionIsExecuting = True
				try:
					self.executeScheduledFunction()
				except Exception as e:
					logmessage = "{} exception occurred during a scheduled function: {}".format(type(e).__name__, str(e))
					logging.getLogger("DideRobot").exception(logmessage, exc_info=e)
				self.scheduledFunctionIsExecuting = False
				gevent.sleep(self.scheduledFunctionTime)
		except gevent.GreenletExit:
			self.logInfo("Scheduled function loop got killed")
		else:
			#While-loop ended normally
			self.logInfo("Scheduled function loop finished current run and was asked to stop afterwards")

	def resetScheduledFunctionGreenlet(self):
		"""
		Call this method if you want to reset when the scheduled function is next called to the period set by the 'scheduledFunctionTime' variable
		There's no need to override this method, just calling it in your command if you need it is sufficient
		"""
		if not self.scheduledFunctionIsExecuting:
			if self.scheduledFunctionGreenlet:
				self.scheduledFunctionGreenlet.kill()
			self.scheduledFunctionGreenlet = gevent.spawn(self.keepRunningScheduledFunction)

	def executeScheduledFunction(self):
		"""
		This method gets called periodically, with a period set by the 'scheduledFunctionTime' variable
		Override this with what you want to run on a schedule. If your command doesn't need to run code periodically, set 'scheduledFunctionTime' to None and ignore this method
		"""
		pass

	#Some convenience logging methods, no need to override these. You can call a 'log[level]' method in your command if you want to log something
	# The log message gets written to file and standard output if the log level in the settings is set to the same or a lower logging level as the logging command
	@staticmethod
	def log(level, message, *args, **kwargs):
		logging.getLogger('DideRobot').log(level, message, *args, **kwargs)

	@staticmethod
	def logDebug(message, *args, **kwargs):
		CommandTemplate.log(logging.DEBUG, message, *args, **kwargs)

	@staticmethod
	def logInfo(message, *args, **kwargs):
		CommandTemplate.log(logging.INFO, message, *args, **kwargs)

	@staticmethod
	def logWarning(message, *args, **kwargs):
		CommandTemplate.log(logging.WARNING, message, *args, **kwargs)

	@staticmethod
	def logError(message, *args, **kwargs):
		CommandTemplate.log(logging.ERROR, message, *args, **kwargs)

	@staticmethod
	def logCritical(message, *args, **kwargs):
		CommandTemplate.log(logging.CRITICAL, message, *args, **kwargs)
