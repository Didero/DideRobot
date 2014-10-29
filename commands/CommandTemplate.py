from twisted.internet import task

from IrcMessage import IrcMessage


class CommandTemplate(object):
	triggers = []
	helptext = "This has not yet been filled in. Oops"
	showInCommandList = True
	claimCommandExecution = True  #If set to to 'True' it will stop other commands with it also set to True from running if this command is executed
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
		
	def shouldExecute(self, message, commandExecutionClaimed):
		"""
		:type message: IrcMessage
		"""
		#If another command already claimed sole execution rights, and this one wants it too, don't run this command at all
		if commandExecutionClaimed and self.claimCommandExecution:
			return False
		if message.messageType not in self.allowedMessageTypes:
			return False
		if message.trigger in self.triggers:
			return True
		return False
	
	def execute(self, message):
		"""
		:type message: IrcMessage
		"""
		pass
	
	def executeScheduledFunction(self):
		pass
