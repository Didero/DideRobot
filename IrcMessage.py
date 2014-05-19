class IrcMessage(object):
	"""Parses incoming messages into usable parts like the command trigger"""

	def __init__(self, rawText, bot, messageType='say', user=None, source=None):
		#First store the basic provided data
		self.rawText = rawText
		try:
			self.rawText = self.rawText.decode('utf-8')
		except (UnicodeDecodeError, UnicodeEncodeError):
			print "[IrcMessage] |{}| Unable to turn message (of type '{}') into unicode: '{}'".format(bot.factory.serverfolder, type(rawText), rawText)
		#print "type of rawText: '{}'; type of self.rawText: '{}'".format(type(rawText), type(self.rawText))
		self.bot = bot
		#MessageType is expected to be one of 'say', 'action', 'notice'
		self.messageType = messageType

		#Info about the user that sent the message
		self.user = user
		if self.user:
			self.userNickname = self.user.split("!", 1)[0]
		else:
			self.userNickname = None

		#Info about the source the message came from, either a channel, or a PM from a user
		#If there is no source provided, or the source isn't a channel, assume it's a PM
		if not source or not source.startswith(u'#'):
			self.source = self.userNickname
			self.isPrivateMessage = True
		else:
			self.source = source
			self.isPrivateMessage = False

		#Collect information about the possible command in this message
		if self.rawText.startswith(self.bot.factory.commandPrefix):
			#Get the part from the end of the command prefix to the first space (the 'help' part of '!help say')
			self.trigger = self.rawText[self.bot.factory.commandPrefixLength:].split(u" ")[0].strip()
			self.message = self.rawText[self.bot.factory.commandPrefixLength + len(self.trigger):].strip()
		#Check if the text doesn't start with the nick of the bot, 'DideRobot: help'
		elif self.rawText.startswith(self.bot.nickname + ": ") and len(self.rawText) > len(self.bot.nickname) + 2:
			self.trigger = self.rawText.split(u" ")[1].strip()
			self.message = self.rawText[len(self.bot.nickname) + len(self.trigger) + 3:].strip()
		else:
			self.trigger = None
			self.message = self.rawText.strip()
		
		#messageParts should never include the trigger, so we split the messageWithoutTrigger
		if self.message != u"":
			self.messageParts = self.message.split(u" ")
		else:
			self.messageParts = []
		self.messagePartsLength = len(self.messageParts)


