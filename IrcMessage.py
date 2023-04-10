import time

import Constants
import MessageTypes


class IrcMessage(object):
	"""Parses incoming messages into usable parts like the command trigger"""

	def __init__(self, messageType, bot, user=None, source=None, rawText=""):
		self.createdAt = time.time()
		#MessageType is what kind of message it is. A 'say', 'action' or 'quit', for instance. See the MessagesTypes class for all the message types
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
		if not self.rawText:
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
			# Check if the text starts with the nick of the bot, then a space, and then something that could be a command trigger, for instance 'DideRobot help' or 'DideRobot generate random'
			elif bot.nickname and self.rawText.startswith(bot.nickname) and self.rawText[len(bot.nickname)] == " ":
				messageParts = self.rawText.split(" ", 2)
				self.trigger = messageParts[1].lower()
				self.message = messageParts[2] if len(messageParts) > 2 else ""
			#In private messages we should respond too if there's no command character, because there's no other reason to PM a bot
			elif self.isPrivateMessage:
				self.trigger = self.rawText.split(" ", 1)[0].lower()
				self.message = self.rawText[len(self.trigger)+1:]
			else:
				self.trigger = None
				self.message = self.rawText

			if self.message:
				self.messageParts = self.message.split(" ")
				self.messagePartsLength = len(self.messageParts)
			else:
				self.messageParts = []
				self.messagePartsLength = 0

	def reply(self, replytext, messagetype=None):
		if not messagetype:
			#Reply with a notice to a user's notice (not a channel one, that spams everybody!), and with a normal message to anything else
			messagetype = MessageTypes.NOTICE if self.isPrivateMessage and self.messageType == MessageTypes.NOTICE else MessageTypes.SAY
		self.bot.sendMessage(self.source, replytext, messagetype)

	def isSenderAdmin(self):
		"""
		:return: True if the person that sent this message is a bot admin, False otherwise
		"""
		return self.bot.isUserAdmin(self.user, self.userNickname, self.userAddress)
