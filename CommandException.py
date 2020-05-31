class CommandException(Exception):
	"""
	This custom exception can be thrown by commands when something goes wrong during execution.
	The parameter is a message sent to the source that called the command (a channel or a user)
	"""

	def __init__(self, displayMessage=None, shouldLogError=True):
		"""
		Create a new CommandException, to be thrown when something goes wrong during Command execution
		:param displayMessage: An optional message to display to the IRC chat the bot is in
		:param shouldLogError: Whether this exception should be logged to the program log. This is useful if it's a problem that needs to be solved, but can be set to False if it's a user input error
		"""
		self.displayMessage = displayMessage
		self.shouldLogError = shouldLogError

	def __str__(self):
		return self.displayMessage
