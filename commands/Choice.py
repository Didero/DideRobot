import random

from commands.CommandTemplate import CommandTemplate


class Command(CommandTemplate):
	triggers = ['choice', 'choose']
	helptext = "Helps you make a choice between options in a comma-separated list"

	possibleReplies = ["Hmm, I'd go with {}", "Out of those, {} sounds the least bad", "{}, obviously",
					   "Let's go with... {}. No wait! No, yeah, that one", "I don't know! *rolls dice* Seems you should go for {}",
					   "Pick {0}, pick {0}!", "Eh, {} will do", "Why not {}?", "The first one! The last one! {}!", "Just pick {}"]

	def pickRandomReply(self):
		#Based on a suggestion by ekimekim
		while True:
			#Shuffle the list initially
			random.shuffle(self.possibleReplies)
			#Then just feed a reply every time one is requested. Once we run out, the list is reshuffled, ready to start again
			for reply in self.possibleReplies:
				yield reply

	def execute(self, message):
		"""
		:type message: IrcMessage.IrcMessage
		"""
		replytext = None
		if message.messagePartsLength == 0:
			replytext = "My choice would be to provide me with some choices, preferably separated by commas"
		else:
			if ';' in message.message:
				choices = message.message.split(';')
			elif ',' in message.message:
				choices = message.message.split(',')
			else:
				choices = message.messageParts
			#Remove all the empty choices from the list
			choices = filter(bool, choices)
			if len(choices) == 0:
				replytext = "That's just an empty list of choices... I'll pick nothing then"
			elif len(choices) == 1:
				replytext = "Ooh, that's a tough one. I'd go with the first option, seeing as there is only one"
			else:
				#Make a new random generator with the choices as seed, so every time you ask the bot to make a choice from the same list, it picks the same outcome
				choice = random.Random(tuple(sorted(choices))).choice(choices).strip()
				#Pick a random reply sentence, and then add in the previously picked choice, enclosed in quotes
				replytext = self.pickRandomReply().next().format('"' + choice + '"')
		message.bot.sendMessage(message.source, replytext)