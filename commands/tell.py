import os, json
import time
from datetime import datetime, timedelta

from CommandTemplate import CommandTemplate

class Command(CommandTemplate):
	triggers = ['tell']
	helptext = "Stores messages you want to send to other users, and says them to that user when they speak"
	claimCommandExecution = False

	storedTells = {}

	def onStart(self):
		if os.path.exists("tells.json"):
			with open("tells.json", 'r') as tellsfile:
				self.storedTells = json.load(tellsfile)

	def shouldExecute(self, bot, commandExecutionClaimed, triggerInMsg, msg, msgParts):
		#Moved to the 'execute' function, since we have to check on every message if there's a tell for that person
		return True
	
	def execute(self, bot, user, target, triggerInMsg, msg, msgWithoutFirstWord, msgParts, msgPartsLength):
		nick = user.split("!", 1)[0]
		tells = []
		#Load in the tell data for the person if needed, and delete them
		if user in self.storedTells:
			tells = self.storedTells[user]
			self.storedTells.pop(user, None)
		elif nick in self.storedTells:
			tells = self.storedTells[nick]
			self.storedTells.pop(nick, None)

		if len(tells) > 0:
			for tell in tells:
				if tell["sentInChannel"] == target:
					timeSent = datetime.utcfromtimestamp(tell['sentAt'])
					timeSinceTell = datetime.utcnow() - timeSent
					#Since the timedelta class doesn't have a nice strftime() method, let's make one ourselves. Yay, this is not ugly at all!
					hoursSinceTell, remainder = divmod(timeSinceTell.seconds, 3600)
					minutesSinceTell, secondsSinceTell = divmod(remainder, 60)
					timeSinceTellFormattedList = []
					if timeSinceTell.days > 0:
						timeSinceTellFormattedList.append("{} days".format(timeSinceTell.days))
					if hoursSinceTell > 0:
					    timeSinceTellFormattedList.append("{} hours".format(hoursSinceTell))
					if minutesSinceTell > 0:
						timeSinceTellFormattedList.append("{} minutes".format(minutesSinceTell))
					if secondsSinceTell > 0:
						timeSinceTellFormattedList.append("{} seconds".format(secondsSinceTell))
					timeSinceTellFormatted = ", ".join(timeSinceTellFormattedList)

					bot.say(target, u"{recipient}: {message} (sent by {sender} on {timeSent}, {timeSinceTell} ago)".format(
											recipient=nick, message=tell["message"], sender=tell["sender"], timeSent=timeSent.isoformat(' '), timeSinceTell=timeSinceTellFormatted))
			#Store the changed tells to disk
			self.saveTellsToFile()

		#Done here instead of in 'shouldExecute', because it should execute every time to check if there is a tell for that user
		if triggerInMsg in self.triggers:
			replytext = u""
			if msgPartsLength == 1:
				replytext = u"Add a username and a message as arguments, then we'll tell-I mean talk"
			elif msgPartsLength == 2:
				replytext = u"What do you want me to tell {}? Add that as an argument too, otherwise I'm just gonna stare at them and we'll all be uncomfortable".format(msgParts[1])
			else:
				tellRecipient = msgParts[1]
				#Prevent tells to us, in case that would ever come up
				if tellRecipient.lower() == bot.nickname.lower():
					replytext = "You can talk to me directly, I'm here for you now!"
				else:
					tellMessage = " ".join(msgParts[2:])
					if tellRecipient not in self.storedTells:
						self.storedTells[tellRecipient] = []

					tell = {"message": tellMessage, "sender": nick, "sentAt": round(time.time()), "sentInChannel": target}
					self.storedTells[tellRecipient].append(tell)

					print "storedTells: ", self.storedTells

					replytext = u"All right, I'll tell {} when they show a sign of life".format(tellRecipient)
					self.saveTellsToFile()

			bot.say(target, replytext)

	def saveTellsToFile(self):
		with open("tells.json", 'w') as tellsfile:
			tellsfile.write(json.dumps(self.storedTells)) #Faster than 'json.dump(self.storedTells, tellsfile)'