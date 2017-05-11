import time

import Constants


class IrcMessage(object):
	"""Parses incoming messages into usable parts like the command trigger"""

	def __init__(self, messageType, bot, user=None, source=None, rawText=""):
		self.createdAt = time.time()
		#MessageType is what kind of message it is. A 'say', 'action' or 'quit', for instance
		self.messageType = messageType

		self.bot = bot

		#Info about the user that sent the message
		self.user = user
		if self.user and '!' in self.user:
			self.userNickname, self.userAddress = self.user.split("!", 1)
		else:
			self.userNickname = None
			self.userAddress = None

		#Info about the source the message came from, either a channel, or a PM from a user
		#If there is no source provided, or the source isn't a channel, assume it's a PM
		if not source or source[0] not in Constants.CHANNEL_PREFIXES:
			self.source = self.userNickname
			self.isPrivateMessage = True
		else:
			self.source = source
			self.isPrivateMessage = False

		#Handle the text component, including seeing if it starts with the bot's command character
		self.rawText = rawText.strip()
		#There isn't always text
		if self.rawText == "":
			self.trigger = None
			self.message = ""
			self.messageParts = []
			self.messagePartsLength = 0
		else:
			#Collect information about the possible command in this message
			if self.rawText.startswith(bot.commandPrefix):
				#Get the part from the end of the command prefix to the first space (the 'help' part of '!help say')
				self.trigger = self.rawText[bot.commandPrefixLength:].split(" ", 1)[0].lower()
				self.message = self.rawText[bot.commandPrefixLength + len(self.trigger):].lstrip()
			#Check if the text starts with the nick of the bot, 'DideRobot: help'
			elif bot.nickname and self.rawText.startswith(bot.nickname + ": ") and len(self.rawText) > len(bot.nickname) + 2:
				self.trigger = self.rawText.split(" ", 2)[1].strip().lower()
				self.message = self.rawText[len(bot.nickname) + len(self.trigger) + 3:].lstrip()  #+3 because of the colon and space
			#In private messages we should respond too if there's no command character, because there's no other reason to PM a bot
			elif self.isPrivateMessage:
				self.trigger = self.rawText.split(" ", 1)[0].lower()
				self.message = self.rawText[len(self.trigger)+1:]
			else:
				self.trigger = None
				self.message = self.rawText

			if self.message != "":
				self.messageParts = self.message.split(" ")
				self.messagePartsLength = len(self.messageParts)
			else:
				self.messageParts = []
				self.messagePartsLength = 0

	def reply(self, replytext, messagetype=None):
		if not messagetype:
			#Reply with a notice to a user's notice (not a channel one!), and with a 'say' to anything else
			messagetype = 'notice' if self.messageType == 'notice' and self.source[0] not in Constants.CHANNEL_PREFIXES else 'say'
		self.bot.sendMessage(self.source, replytext, messagetype)
