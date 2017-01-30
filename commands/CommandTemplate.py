import logging

from twisted.internet import task


class CommandTemplate(object):
	triggers = []
	helptext = "This help text has not yet been filled in. Oops"
	showInCommandList = True
	stopAfterThisCommand = False  #Some modules might affect the command list, which leads to errors. If this is set to true and the command fires, no further commands are executed
	adminOnly = False
	scheduledFunctionTime = None  #Float, in seconds. Or None if you don't want a scheduled function
	callInThread = False
	allowedMessageTypes = ['say']
	
	def __init__(self):
		self.onLoad()  #Put this before starting the scheduled function because it may rely on loaded data
		if self.scheduledFunctionTime:
			self.logInfo("Executing looping function every {} seconds".format(self.scheduledFunctionTime))
			self.scheduledFunctionTimer = task.LoopingCall(self.executeScheduledFunction)
			self.scheduledFunctionTimer.start(self.scheduledFunctionTime)

	def onLoad(self):
		pass

	def unload(self):
		if self.scheduledFunctionTime:
			self.logInfo("Stopping looping function")
			self.scheduledFunctionTimer.stop()
			self.scheduledFunctionTimer = None
		self.onUnload()

	def onUnload(self):
		pass

	def getHelp(self, message):
		return self.helptext.format(commandPrefix=message.bot.factory.commandPrefix)
		
	def shouldExecute(self, message):
		#Check if we need to respond, ordered from cheapest to most expensive check
		#  (the allowedMessageTypes list is usually short, most likely shorter than the triggers list)
		if message.trigger and message.messageType in self.allowedMessageTypes and message.trigger in self.triggers:
			return True
		return False

	def execute(self, message):
		pass
	
	def executeScheduledFunction(self):
		pass

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
