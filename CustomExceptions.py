class BaseCustomException(Exception):
	"""
	An abstract class that other custom exceptions should inherit from. Don't instantiate this directly
	"""
	def __init__(self, displayMessage):
		"""
		Create a new exception
		:param displayMessage: An optional user-facing message, that will also be used as the exception's string representation
		"""
		super(BaseCustomException, self).__init__(displayMessage)
		self.displayMessage = displayMessage

	def __str__(self):
		if self.displayMessage:
			return self.displayMessage
		return super(BaseCustomException, self).__str__()

	def __repr__(self):
		if self.displayMessage:
			return "<{}> {}".format(self.__class__.__name__, self.displayMessage)
		return super(BaseCustomException, self).__repr__()


class CommandException(BaseCustomException):
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
		super(CommandException, self).__init__(displayMessage)
		self.shouldLogError = shouldLogError


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
		super(CommandInputException, self).__init__(displayMessage, False)
