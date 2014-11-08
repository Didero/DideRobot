from twisted.internet import task

from IrcMessage import IrcMessage


class CommandTemplate(object):
	triggers = []
	helptext = "This help text has not yet been filled in. Oops"
	showInCommandList = True
	stopAfterThisCommand = False  #Some modules might affect the command list, which leads to errors. If this is set to true and the command fires, no further commands are executed
	adminOnly = False
	scheduledFunctionTime = -1.0
	callInThread = False
	allowedMessageTypes = ['say']
	
	def __init__(self):
		if self.scheduledFunctionTime > 0.0:
			print "Executing looping function every {} seconds".format(self.scheduledFunctionTime)
			self.scheduledFunctionTimer = task.LoopingCall(self.executeScheduledFunction)
			self.scheduledFunctionTimer.start(self.scheduledFunctionTime)
		self.onLoad()

	def onLoad(self):
		pass

	def unload(self):
		if self.scheduledFunctionTime > 0.0:
			print "Stopping looping function"
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
