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


class CommandInputException(CommandException):
	"""
	This custom exception can be raised when the input to some module or command is invalid or can't be parsed.
	It is a more specific implementation of the CommandException, that doesn't log itself to the logfile
	"""

	def __init__(self, displayMessage):
		"""
		Create a new InputException. The display message will be shown to the user
		:param displayMessage: The message to show to the user that called the command. This message should explain how the input should be correctly formatted
		"""
		super(CommandException, self).__init__(displayMessage, False)
