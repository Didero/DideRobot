import random

from CommandTemplate import CommandTemplate
from IrcMessage import IrcMessage


class Command(CommandTemplate):
	triggers = ['dice', 'roll']
	helptext = "Roll dice. Simple. Format is either <sides> [<rolls>], or <rolls>d<sides> like in those nerdy tabletop games"

	def execute(self, message):
		"""
		:type message: IrcMessage
		"""
		replytext = u""
		rollcount = 1
		sides = -1
		total = 0.0

		rollLimit = 1000
		displayRollsLimit = 20  #If there's more than this many rolls, don't list individual rolls
		displaySidesLimit = 999999999  #1 billion -1, if there's more than this many sides, don't list all the rolls

		if message.messagePartsLength == 0:
			replytext = u"You want the classic six-sided die, I assume? Rolling... And it lands on a... {}!".format(random.randint(1, 6))
		else:
			#No '1d12' or anything, just numbers
			if 'd' not in message.messageParts[0].lower():
				#assuming '!dice [sides] [rolls]'
				try:
					sides = int(message.messageParts[0])
				except ValueError:
					sides = 6
					replytext += u"(I don't think '{}' is a valid number of sides, I'll just use {} sides) ".format(message.messageParts[0], sides)
				if message.messagePartsLength > 1:
					try:
						rollcount = int(message.messageParts[1])
					except ValueError:
						replytext += u"(I don't know how to roll '{}' times, so I'm just gonna roll once) ".format(message.messageParts[1])
						rollcount = 1

			else:
				#There's a 'd' in the message, so it's probably something like '1d12
				diceroll = message.messageParts[0].lower().split("d")

				#Verify that the number of sides was entered correctly
				if len(diceroll) == 1 or len(diceroll[1]) == 0:
					sides = 20
					replytext += u"(I think you forgot to add the number of sides, I'll just assume you want {}) ".format(sides)
				else:
					try:
						sides = int(diceroll[1])
					except ValueError:
						sides = 20
						replytext += u"(I don't know what to do with '{}', I'll just use {}-sided dice) ".format(diceroll[1], sides)

				#Do the same check for the number of dice rolls
				if len(diceroll) == 0 or len(diceroll[0]) == 0:
					replytext += u"(Did you forget the number of rolls? I'll just roll once then) "
					rollcount = 1
				else:
					try:
						rollcount = int(diceroll[0])
					except ValueError:
						rollcount = 1
						replytext += u"(I don't know how many rolls '{}' is, so I'll just roll once) ".format(diceroll[0])

			#Preventing negative numbers
			if rollcount <= 0:
				replytext += u"(I can't roll {} times, so I'm gonna assume you want a single roll) ".format(rollcount)
				rollcount = 1
			if sides <= 0:
				replytext += u"(A die with {} sides is a bit weird, I'll just use this one with 6 sides) ".format(sides)
				sides = 6
			elif sides == 1:
				replytext += u"(A single side? But that... Fine, I'll just roll with it) "
			elif sides == 2:
				replytext += u"(I'd suggest flipping a coin, but this'll work too) "

			#Only keep the actual rolls if there's not too many
			keepRollValues = (rollcount <= displayRollsLimit and sides <= displaySidesLimit)

			rollValues = []
			#On to the actual rolling!
			if rollcount <= rollLimit:
				for roll in xrange(rollcount):
					rollValue = random.randint(1, sides)
					if keepRollValues:
						rollValues.append("{:,}".format(rollValue))  #Use format to get thousands-separators
					total += rollValue
			else:
				#Far too much rolls, estimate expected value. With floats to allow for decimals
				sidesFloat = float(sides)
				total = (sidesFloat + 1) * (sidesFloat / 2) * (float(rollcount) / sidesFloat)

			#Clean up any trailing decimal zeroes if necessary
			if int(total) == total:
				total = int(total)
			
			average = float(total) / float(rollcount)
			if rollcount == 1:
				replytext += u"A single {:,}-sided die roll, I can do that. Rolling, rolling... and it lands on... {:,}!".format(sides, total)
			elif rollcount <= displayRollsLimit:
				if sides <= displaySidesLimit:
					replytext += u"{:,} rolls with {:,}-sided dice: {} = {:,}, average of {:,}".format(rollcount, sides, u" + ".join(rollValues), total, average)
				else:
					replytext += u"{:,} rolls with {:,}-sided dice. That's a lot of sides, I hope you don't mind that I don't show them all. " \
								 u"Your total is... (oof, clumsy large dice)... {:,}, with an average of {:,}".format(rollcount, sides, total, average)
			elif rollcount <= rollLimit:
				replytext += u"{} rolls with {:,}-sided dice. That's a quite a few rolls, but luckily I'm pretty fast. Your total is... hang on... {:,}, " \
							 u"with an average roll of {:,}".format(rollcount, sides, total, average)
			else:
				replytext += u"{:,} is a LOT of rolls, even I would spend ages on that. I'll just give you the expected value, that'll be close enough. " \
							 u"And that is... {:,}!".format(rollcount, total)

		message.reply(replytext)

