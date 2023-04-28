import json, os, time

from CommandTemplate import CommandTemplate
import GlobalStore
from util import DateTimeUtil


class Command(CommandTemplate):
	triggers = ['nickmessage', 'setnickmessage', 'clearnickmessage']
	helptext = "Allows you to set a message that others can look up, or you can look up another person's message. " \
			   "Useful if you're going on vacation or something, and want to have a way to let people know. " \
			   "'{commandPrefix}nickmessage' shows your own message, or you can add a nickname to look up that person's message"

	def execute(self, message):
		"""
		:type message: IrcMessage.IrcMessage
		"""

		#We're always going to need the NickMessage file
		nickmessages = {}
		nickmessagesFilepath = os.path.join(GlobalStore.scriptfolder, 'data', 'NickMessages.json')
		if os.path.exists(nickmessagesFilepath):
			#If the file exists but is empty, an error is thrown. Prevent that error, even though an empty file should never exist
			try:
				with open(nickmessagesFilepath, 'r') as nickmessagesFile:
					nickmessages = json.load(nickmessagesFile)
			except ValueError:
				self.logError("[NickMessage] An error occurred while trying to load the NickMessages file. Something probably went wrong with storing the data")

		#Let's create a slightly shorter way to reference this, shall we
		serverfolder = message.bot.serverfolder

		if message.trigger == 'nickmessage':
			#Search if we know the provided nick (or use the user's nick if there's none provided)
			nickToSearchFor = message.messageParts[0].lower() if message.messagePartsLength > 0 else message.userNickname.lower()

			if serverfolder not in nickmessages or nickToSearchFor not in nickmessages[serverfolder]:
				message.reply(u"I don't have a nick message stored for '{}'".format(nickToSearchFor))
			else:
				nickmessage = nickmessages[serverfolder][nickToSearchFor]
				message.reply(u"Nick message for {}: {} (Set {} ago)".format(nickToSearchFor, nickmessage[0], DateTimeUtil.durationSecondsToText(time.time() - nickmessage[1])))
		elif message.trigger == 'setnickmessage':
			if message.messagePartsLength == 0:
				message.reply(u"Please provide some text to set as your nick message")
			else:
				if serverfolder not in nickmessages:
					nickmessages[serverfolder] = {}
				nickmessages[serverfolder][message.userNickname.lower()] = (message.message, time.time())
				#Only save the file if the message doesn't contain any weird Unicode characters that might trip up the JSON lib
				try:
					nickMessagesString = json.dumps(nickmessages)
				except UnicodeDecodeError:
					message.reply(u"I'm sorry, but there's a weird character in your message. I can't store it like this. Please remove any unusual characters, and try again")
				else:
					with open(nickmessagesFilepath, 'w') as nickmessagesFile:
						nickmessagesFile.write(nickMessagesString)
					message.reply(u"Your nick message was successfully set")
		elif message.trigger == 'clearnickmessage':
			if serverfolder not in nickmessages or message.userNickname.lower() not in nickmessages[serverfolder]:
				message.reply(u"There is no message stored for your nick")
			else:
				del nickmessages[serverfolder][message.userNickname.lower()]
				#Might as well clear the serverfolder entry if there's no messages in it
				if len(nickmessages[serverfolder]) == 0:
					del nickmessages[serverfolder]
				with open(nickmessagesFilepath, 'w') as nickmessagesFile:
					nickmessagesFile.write(json.dumps(nickmessages))
				message.reply(u"Your nick message was successfully cleared")
