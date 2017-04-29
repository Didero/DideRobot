import logging

import gevent


class CommandTemplate(object):
	triggers = []
	helptext = "This help text has not yet been filled in. Oops"
	allowedMessageTypes = ['say']

	adminOnly = False
	callInThread = False
	showInCommandList = True
	stopAfterThisCommand = False  #Some modules might affect the command list, which leads to errors. If this is set to true and the command fires, no further commands are executed

	scheduledFunctionTime = None  #Float, in seconds. Or None if you don't want a scheduled function
	scheduledFunctionGreenlet = None  #The greenlet that manages the scheduled function, or None if there isn't one
	scheduledFunctionIsExecuting = False  #Set to True if the scheduled function is running, so we know when we can kill the scheduler greenlet


	def __init__(self):
		self.onLoad()  #Put this before starting the scheduled function because it may rely on loaded data
		if self.scheduledFunctionTime:
			self.scheduledFunctionGreenlet = gevent.spawn(self.keepRunningScheduledFunction)

	def onLoad(self):
		pass

	def unload(self):
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
		pass

	def getHelp(self, message):
		return self.helptext.format(commandPrefix=message.bot.commandPrefix)
		
	def shouldExecute(self, message):
		#Check if we need to respond, ordered from cheapest to most expensive check
		#  (the allowedMessageTypes list is usually short, most likely shorter than the triggers list)
		if message.trigger and message.messageType in self.allowedMessageTypes and message.trigger in self.triggers:
			return True
		return False

	def execute(self, message):
		pass

	def keepRunningScheduledFunction(self):
		self.logInfo("Executing looping function every {} seconds".format(self.scheduledFunctionTime))
		try:
			while self.scheduledFunctionTime and self.scheduledFunctionTime > 0:
				self.scheduledFunctionIsExecuting = True
				self.executeScheduledFunction()
				self.scheduledFunctionIsExecuting = False
				gevent.sleep(self.scheduledFunctionTime)
		except gevent.GreenletExit:
			self.logInfo("Scheduled function loop got killed")
		else:
			#While-loop ended normally
			self.logInfo("Scheduled function loop finished current run and was asked to stop afterwards")

	def resetScheduledFunctionGreenlet(self):
		if not self.scheduledFunctionIsExecuting:
			self.scheduledFunctionGreenlet.kill()
			self.scheduledFunctionGreenlet = gevent.spawn(self.keepRunningScheduledFunction)

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
