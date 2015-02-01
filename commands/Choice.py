import random

from CommandTemplate import CommandTemplate


class Command(CommandTemplate):
	triggers = ['choice', 'choose']
	helptext = "Helps you make a choice between options in a comma-separated list"

	def execute(self, message):
		"""
		:type message: IrcMessage.IrcMessage
		"""
		replytext = None
		if message.messagePartsLength == 0:
			replytext = "My choice would be to provide me with some choices, preferably separated by commas"
		else:
			choices = []
			if ',' in message.message:
				choices = message.message.split(',')
			else:
				choices = message.messageParts
			if len(choices) == 1:
				replytext = "Ooh, that's a tough one. I'd go with the first option, seeing as there is only one"
			else:
				possibleReplies = ["{}", "Hmm, I'd go with {}", "Out of those, {} sounds the least bad", "{}, obviously",
								   "Let's go with... {}. No wait! No, yeah, that one", "I don't know! *rolls dice* Seems you should go for {}",
								   "Pick {0}, pick {0}!", "Eh, {} will do", "Why not {}?", "The first one! The last one! {}!"]
				#Pick a random reply sentence, and then add in a random choice from the provided list, enclosed in quotes
				replytext = random.choice(possibleReplies).format("'" + random.choice(choices).strip() + "'")
		message.bot.sendMessage(message.source, replytext)