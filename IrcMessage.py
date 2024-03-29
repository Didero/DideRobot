import re
import time
import typing
if typing.TYPE_CHECKING:
	from DideRobot import DideRobot

import Constants
import MessageTypes
from StringWithSuffix import StringWithSuffix
from PermissionLevel import PermissionLevel


class IrcMessage(object):
	"""Parses incoming messages into usable parts like the command trigger"""

	def __init__(self, messageType, bot: 'DideRobot', user=None, source=None, rawText=""):
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
			commandPrefix = bot.settings.get("commandPrefix", None, self.source)
			if commandPrefix and self.rawText.startswith(commandPrefix):
				#Get the part from the end of the command prefix to the first space (the 'help' part of '!help say')
				self.trigger = self.rawText[len(commandPrefix):].split(" ", 1)[0].lower()
				self.message = self.rawText[len(commandPrefix) + len(self.trigger):].lstrip()
			# Check if the text starts with the nick of the bot, and then something that could be a command trigger, for instance 'DideRobot help', '@DideRobot generate random', or 'DideRobot: source'
			elif bot.nickname and bot.nickname in self.rawText and re.match(f"@?{bot.nickname}:? ", self.rawText):
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

	def _determineReplyMessageType(self):
		# Reply with a notice to a user's notice (not a channel one, that spams everybody!), and with a normal message to anything else
		return MessageTypes.NOTICE if self.isPrivateMessage and self.messageType == MessageTypes.NOTICE else MessageTypes.SAY

	def reply(self, replytext, messagetype=None):
		"""
		Reply to this message with the provided replytext
		:param replytext: The text to send to the source of this message, be it a user or a channel
		:param messagetype: The type of the message to respond with. Leave empty to reply to a private notice with a notice and to everything else with a normal text message
		:return: None
		"""
		if not messagetype:
			messagetype = self._determineReplyMessageType()
		self.bot.sendMessage(self.source, replytext, messagetype)

	def replyWithLengthLimit(self, reply, messagetype=None):
		"""
		Reply to this message with the provided string with optional suffix, with the main text shortened to the maximum message length that fits in a message to this source
		:param reply: The string or stringWithSuffix object that contains the text to reply with
		:type reply: str or StringWithSuffix
		:param messagetype: The type of the message to respond with. Leave empty to reply to a private notice with a notice and to everything else with a normal text message
		:return: None
		"""
		if not messagetype:
			messagetype = self._determineReplyMessageType()
		if isinstance(reply, StringWithSuffix):
			mainReply = reply.mainString
			suffix = reply.suffix
		else:
			mainReply = reply
			suffix = None
		self.bot.sendLengthLimitedMessage(self.source, mainReply, suffix, messagetype)

	def doesSenderHavePermission(self, permissionLevel: PermissionLevel) -> bool:
		"""
		Checks whether the user that sent this message has at least the provided permission level
		:param permissionLevel: The minimum permission level the user that sent this message should have
		:return: True if the user that sent this message has the provided permission level or a higher one, False otherwise
		"""
		return self.bot.doesUserHavePermission(permissionLevel, self.user, self.userNickname, self.userAddress, self.source)
