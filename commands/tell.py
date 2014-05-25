import os, json
import time
from datetime import datetime, timedelta

from CommandTemplate import CommandTemplate
import GlobalStore
import SharedFunctions
from IrcMessage import IrcMessage


class Command(CommandTemplate):
	triggers = ['tell']
	helptext = "Stores messages you want to send to other users, and says them to that user when they speak. Usage: {commandPrefix}tell [username] [message]"
	claimCommandExecution = False

	tellsFileLocation = os.path.join(GlobalStore.scriptfolder, "data", "tells.json")
	storedTells = {}
	maxTellsAtATime = 4

	def onStart(self):
		if os.path.exists(self.tellsFileLocation):
			with open(self.tellsFileLocation, 'r') as tellsfile:
				self.storedTells = json.load(tellsfile)

	def shouldExecute(self, message, commandExecutionClaimed):
		#Moved to the 'execute' function, since we have to check on every message if there's a tell for that person
		return True
	
	def execute(self, message):
		"""
		:type message: IrcMessage
		"""
		tells = []
		#Load in the tell data for the person if needed, and delete them
		if message.user in self.storedTells:
			tells.extend(self.storedTells[message.user])
			self.storedTells.pop(message.user)
		if message.userNickname in self.storedTells:
			tells.extend(self.storedTells[message.userNickname])
			self.storedTells.pop(message.userNickname)

		if len(tells) > 0:
			#Sort the stored tells by their send time
			sortedTells = sorted(tells, key=lambda k: k['sentAt'])
			#If there's too many tells for one time, store the rest for next time but keep the first few
			if len(sortedTells) > self.maxTellsAtATime:
				self.storedTells[message.user] = sortedTells[self.maxTellsAtATime:]
				sortedTells = sortedTells[:self.maxTellsAtATime]

			#Talkin' time!
			for tell in sortedTells:
				if tell["sentInChannel"] == message.source:
					timeSent = datetime.utcfromtimestamp(tell['sentAt'])
					timeSinceTell = (datetime.utcnow() - timeSent).seconds
					timeSinceTellFormatted = SharedFunctions.durationSecondsToText(timeSinceTell)

					message.bot.say(message.source, u"{recipient}: {message} (sent by {sender} on {timeSent}; {timeSinceTell} ago)"
						.format(recipient=message.userNickname, message=tell["message"], sender=tell["sender"], timeSent=timeSent.isoformat(' '), timeSinceTell=timeSinceTellFormatted))
			#Store the changed tells to disk
			self.saveTellsToFile()

		#Done here instead of in 'shouldExecute', because it should execute every time to check if there is a tell for that user
		if message.trigger in self.triggers:
			replytext = u""
			if message.messagePartsLength == 0:
				replytext = u"Add a username and a message as arguments, then we'll tell-I mean talk"
			elif message.messagePartsLength == 1:
				replytext = u"What do you want me to tell {}? Add that as an argument too, otherwise I'm just gonna stare at them and we'll all be uncomfortable".format(message.messageParts[0])
			else:
				tellRecipient = message.messageParts[0]
				#Prevent tells to us, in case that would ever come up
				if tellRecipient.lower() == message.bot.nickname.lower():
					replytext = "You can talk to me directly, I'm here for you now!"
				else:
					tellMessage = " ".join(message.messageParts[1:])
					if tellRecipient not in self.storedTells:
						self.storedTells[tellRecipient] = []

					tell = {"message": tellMessage, "sender": message.userNickname, "sentAt": round(time.time()), "sentInChannel": message.source}
					self.storedTells[tellRecipient].append(tell)

					print "storedTells: ", self.storedTells

					replytext = u"All right, I'll tell {} when they show a sign of life".format(tellRecipient)
					self.saveTellsToFile()

			message.bot.say(message.source, replytext)

	def saveTellsToFile(self):
		with open(self.tellsFileLocation, 'w') as tellsfile:
			tellsfile.write(json.dumps(self.storedTells)) #Faster than 'json.dump(self.storedTells, tellsfile)'