from commands.CommandTemplate import CommandTemplate
from IrcMessage import IrcMessage
import GlobalStore, MessageTypes


class Command(CommandTemplate):
	triggers = ['lastmessage']
	helptext = "Stores the last message for each channel the bot is in, so other modules can retrieve it through a commandfunction"

	# Stores the last message. Key is the server name, value is a nested dict, which has the channel as key and the message as value
	lastMessagePerServer = {}

	def onLoad(self):
		GlobalStore.commandhandler.addCommandFunction(__file__, 'getLastMessage', self.getLastMessage)

	def getLastMessage(self, server, channel, defaultValue=""):
		"""
		Get the last message said in the provided channel on the provided server, or the default value if either of those isn't stored
		:param server: The server to check for the message
		:param channel: Which channel on the provided server to get the last message for
		:param defaultValue: The value to return if there's no message stored for the provided server and channel
		:return: The last message said in the provided channel on the provided server, or the default value if there's nothing stored
		"""
		if server in self.lastMessagePerServer and channel in self.lastMessagePerServer[server]:
			return self.lastMessagePerServer[server][channel]
		return defaultValue

	def shouldExecute(self, message):
		""":type message: IrcMessage"""
		# Ignore private messages
		if message.isPrivateMessage:
			return False
		# If the message is a bot command, don't register it
		if message.trigger:
			return False
		server = message.bot.serverfolder
		isBotEvent = message.userNickname == message.bot.nickname
		# If it's a normal message, store it as the last message for this channel
		if not isBotEvent and message.messageType == MessageTypes.SAY:
			self._storeMessage(server, message.source, message.message)
		elif isBotEvent:
			if message.messageType == 'part':
				# If we leave a channel, no need to store the last message for that channel anymore
				self._removeChannelMessage(server, message.source)
			elif message.messageType == 'quit':
				# If we quit a server, forget all the messages for all channels in that server
				self._removeServer(server)
		# Since we never need to execute anything, always return False
		return False

	def _storeMessage(self, server, channel, message):
		if server not in self.lastMessagePerServer:
			self.lastMessagePerServer[server] = {channel: message}
		else:
			self.lastMessagePerServer[server][channel] = message

	def _removeChannelMessage(self, server, channel):
		if server in self.lastMessagePerServer:
			if len(self.lastMessagePerServer[server]) == 1:
				self.lastMessagePerServer.pop(server, None)
			else:
				self.lastMessagePerServer[server].pop(channel, None)

	def _removeServer(self, server):
		self.lastMessagePerServer.pop(server, None)
