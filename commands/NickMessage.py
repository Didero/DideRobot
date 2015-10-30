import json, os, time

from CommandTemplate import CommandTemplate
import GlobalStore
import SharedFunctions


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
			with open(nickmessagesFilepath) as nickmessagesFile:
				nickmessages = json.load(nickmessagesFile)

		#Let's create a slightly shorter way to reference this, shall we
		serverfolder = message.bot.factory.serverfolder

		if message.trigger == 'nickmessage':
			#Search if we know the provided nick (or use the user's nick if there's none provided)
			nickToSearchFor = message.messageParts[0].lower() if message.messagePartsLength > 0 else message.userNickname.lower()

			if serverfolder not in nickmessages or nickToSearchFor not in nickmessages[serverfolder]:
				message.reply(u"I don't have a nick message stored for '{}'".format(nickToSearchFor))
			else:
				nickmessage = nickmessages[serverfolder][nickToSearchFor]
				message.reply(u"Nick message for {}: {} (Set {} ago)".format(nickToSearchFor, nickmessage[0], SharedFunctions.durationSecondsToText(time.time() - nickmessage[1], 's')))
		elif message.trigger == 'setnickmessage':
			if message.messagePartsLength == 0:
				message.reply(u"Please provide some text to set as your nick message")
			else:
				if serverfolder not in nickmessages:
					nickmessages[serverfolder] = {}
				nickmessages[serverfolder][message.userNickname.lower()] = (message.message, time.time())
				with open(nickmessagesFilepath, 'w') as nickmessagesFile:
					nickmessagesFile.write(json.dumps(nickmessages))
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