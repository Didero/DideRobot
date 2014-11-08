import os, json
from datetime import datetime

from CommandTemplate import CommandTemplate
import GlobalStore
import SharedFunctions
from IrcMessage import IrcMessage


class Command(CommandTemplate):
	triggers = ['tell']
	helptext = "Stores messages you want to send to other users, and says them to that user when they speak. Add a tell in a PM to me, and I'll tell it privately. Usage: {commandPrefix}tell [username] [message]"

	tellsFileLocation = os.path.join(GlobalStore.scriptfolder, "data", "tells.json")
	storedTells = {}
	maxTellsAtATime = 4

	def onLoad(self):
		if os.path.exists(self.tellsFileLocation):
			with open(self.tellsFileLocation, 'r') as tellsfile:
				self.storedTells = json.load(tellsfile)

	def shouldExecute(self, message):
		#Moved to the 'execute' function, since we have to check on every message if there's a tell for that person
		return message.messageType in self.allowedMessageTypes

	def execute(self, message):
		"""
		:type message: IrcMessage
		"""

		#The tell file consists of a couple of nested dictionaries
		#The main dictionary has serverfolders as keys, and a list of users as items
		#Each user dictionary has a list of channels, and an item '_private', for messages that should be send through PM or notice
		#Each channel dict has a list of tells for that person
		#storedTells[serverfolder][username][channel] = [tellMessage1, tellMessag2, ...]

		serverfolder = message.bot.factory.serverfolder

		#Check if the person that said something has tells waiting for them
		usernick = message.userNickname.lower()
		if serverfolder in self.storedTells and usernick in self.storedTells[serverfolder]:
			publicTells = self.retrieveTells(serverfolder, usernick, message.source)
			sentTell = False
			for tell in publicTells:
				message.bot.sendMessage(message.source, self.formatTell(message.userNickname, tell))
				sentTell = True
			#If we haven't spammed the user enough, send them their private tells as well
			if len(publicTells) < self.maxTellsAtATime:
				for tell in self.retrieveTells(serverfolder, usernick, u"_private", self.maxTellsAtATime - len(publicTells)):
					message.bot.sendMessage(message.userNickname, self.formatTell(message.userNickname, tell), 'notice')
					sentTell = True
			if sentTell:
				if len(self.storedTells[serverfolder][usernick]) == 0:
					self.storedTells[serverfolder].pop(usernick)
				if len(self.storedTells[serverfolder]) == 0:
					self.storedTells.pop(serverfolder)
				self.saveTellsToFile()

		#Check if we need to add a new tell
		if CommandTemplate.shouldExecute(self, message, False):
			replytext = u""
			if message.messagePartsLength == 0:
				replytext = u"Add a username and a message as arguments, then we'll tell-I mean talk"
			elif message.messagePartsLength == 1:
				replytext = u"What do you want me to tell {}? Add that as an argument too, otherwise I'm just gonna stare at them and we'll all be uncomfortable".format(message.messageParts[0])
			elif message.messageParts[0].lower() == message.bot.nickname.lower():
				replytext = u"All right, I'll tell myself to tell myself that. Hey {}, what {} said! There, done".format(message.bot.nickname, message.userNickname)
			else:
				#Store that tell!
				messageTarget = u"_private" if message.isPrivateMessage else message.source

				targetnicks = message.messageParts[0].lower().split(u'&')
				for targetnick in targetnicks:
					#Make sure all the nested dictionaries exist
					if serverfolder not in self.storedTells:
						self.storedTells[serverfolder] = {}
					if targetnick not in self.storedTells[serverfolder]:
						self.storedTells[serverfolder][targetnick] = {}
					if messageTarget not in self.storedTells[serverfolder][targetnick]:
						self.storedTells[serverfolder][targetnick][messageTarget] = []

					self.storedTells[serverfolder][targetnick][messageTarget].append(self.createTell(message))
				self.saveTellsToFile()

				targetnick = u"them" if len(targetnicks) > 1 else message.messageParts[0]
				replytext = u"Ok, I'll tell {} that when they show a sign of life".format(targetnick)

			message.bot.say(message.source, replytext)

	@staticmethod
	def createTell(message):
		#		round to remove the milliseconds for nicer display
		tell = {u"sentAt": round(message.createdAt), u"sender": message.userNickname, u"text": u" ".join(message.messageParts[1:])}
		return tell

	def retrieveTells(self, serverfolder, usernick, field, tellLimit=None):
		if not tellLimit:
			tellLimit = self.maxTellsAtATime
		tells = []
		if field in self.storedTells[serverfolder][usernick]:
			for tell in self.storedTells[serverfolder][usernick][field][:tellLimit]:
				tells.append(tell)
			self.storedTells[serverfolder][usernick][field] = self.storedTells[serverfolder][usernick][field][tellLimit:]
			if len(self.storedTells[serverfolder][usernick][field]) == 0:
				self.storedTells[serverfolder][usernick].pop(field)
		return tells

	@staticmethod
	def formatTell(targetNick, tell):
		timeSent = datetime.utcfromtimestamp(tell[u"sentAt"])
		timeSinceTell = SharedFunctions.durationSecondsToText((datetime.utcnow() - timeSent).seconds)

		return u"{recipient}: {message} (sent by {sender} on {timeSent} UTC; {timeSinceTell} ago)"\
			.format(recipient=targetNick, message=tell[u"text"], sender=tell[u"sender"], timeSent=timeSent.isoformat(' '), timeSinceTell=timeSinceTell)

	def saveTellsToFile(self):
		with open(self.tellsFileLocation, 'w') as tellsfile:
			tellsfile.write(json.dumps(self.storedTells)) #Faster than 'json.dump(self.storedTells, tellsfile)'