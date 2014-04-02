from twisted.internet import task

class CommandTemplate(object):
	triggers = []
	helptext = "This has not yet been filled in. Oops"
	showInCommandList = True
	claimCommandExecution = True #If set to to 'True' it will stop other commands with it also set to True from running if this command is executed
	adminOnly = False
	scheduledFunctionTime = -1.0
	callInThread = False
	
	def __init__(self):
		self.onStart()
		if self.scheduledFunctionTime > 0.0:
			print "Executing looping function every {} seconds".format(self.scheduledFunctionTime)
			self.scheduledFunctionTimer = task.LoopingCall(self.executeScheduledFunction)
			self.scheduledFunctionTimer.start(self.scheduledFunctionTime)

	def onStart(self):
		pass
		
	def shouldExecute(self, bot, commandExecutionClaimed, triggerInMsg, msg, msgParts):
		#If another command already claimed sole execution rights, and this one wants it too, don't run this command at all
		if commandExecutionClaimed and self.claimCommandExecution:
			return False
		if triggerInMsg in self.triggers:
			return True
		return False
	
	def execute(self, bot, user, target, triggerInMsg, msg, msgWithoutFirstWord, msgParts, msgPartsLength):
		pass
	
	def executeScheduledFunction(self):
		pass
