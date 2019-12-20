class CommandException(Exception):
	"""
	This custom exception can be thrown by commands when something goes wrong during execution.
	The parameter is a message sent to the source that called the command (a channel or a user)
	"""

	def __init__(self, displayMessage=None):
		"""
		Create a new CommandException, to be thrown when something goes wrong during Command execution
		:param displayMessage: An optional message to display to the IRC chat the bot is in
		"""
		self.displayMessage = displayMessage

	def __str__(self):
		return self.displayMessage
