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
		rollValues = []
		total = 0.0

		rollLimit = 1000
		displayRollsLimit = 20

		if message.messagePartsLength == 0:
			replytext = u"You want the classic six-sided die, I assume? Rolling... And it lands on a... {}!".format(random.randint(1,6))
		else:
			#No '1d12' or anything, just numbers
			if message.message.count('d') == 0:

				#assuming '^dice [sides] [rolls]
				if message.messagePartsLength > 0:
					try:
						sides = int(message.messageParts[0])
					except ValueError:
						sides = 6
						replytext += u"(I don't think '{}' is a valid number of sides, assuming {} sides) ".format(message.messageParts[0], sides)
				if message.messagePartsLength > 1:
					try:
						rollcount = int(message.messageParts[1])
					except ValueError:
						replytext += u"(I don't know how to roll '{}' times, I'm just gonna roll once) ".format(message.messageParts[1])
						rollcount = 1

			else:
				#There's a 'd' in the message, so it's probably something like '1d12
				diceroll = message.message.lower().split("d")
				print "Diceroll in parts: {}".format(", ".join(diceroll))

				#Verify that the number of sides was entered correctly
				if len(diceroll) == 1 or len(diceroll[1]) == 0:
					sides = 20
					replytext += u"(I think you forgot to add the number of sides, I'll just assume you want {}) ".format(sides)
				else:
					try:
						sides = int(diceroll[1])
					except ValueError:
						sides = 20
						replytext += u"(I don't know what to do with '{}', assuming {} sides) ".format(diceroll[1], sides)

				#Do the same check for the number of dice rolls
				if len(diceroll) == 0 or len(diceroll[0]) == 0:
					replytext += u"(Did you forget the number of rolls? I'll just roll once then) "
					rollcount = 1
				else:
					try:
						rollcount = int(diceroll[0])
					except ValueError:
						rollcount = 1
						replytext += u"(I don't know what to do with '{}', assuming {} roll) ".format(diceroll[0], rollcount)

			#Preventing negative numbers
			if rollcount <= 0:
				replytext += u"(I can't roll {} times, so I'm gonna assume you want a single roll) ".format(rollcount)
				rollcount = 1
			if sides <= 0:
				sides = 6
				replytext += u"(A die with {} sides is a bit weird, I'll just use this one with 6 sides) ".format(sides)

			keepRollValues = False
			if rollcount <= displayRollsLimit:
				keepRollValues = True
			if rollcount <= rollLimit:
				#On to the actual rolling!
				for roll in range(rollcount):
					rollValue = random.randint(1, sides)
					if keepRollValues:
						rollValues.append(str(rollValue))
					total += rollValue
			else:
				#Far too much rolls, estimate expected value
				sidesFloat = float(sides)
				rollcountFloat = float(rollcount)
				total = (sidesFloat + 1) * (sidesFloat / 2) * (rollcountFloat / sidesFloat)

			#Clean up any trailing decimal zeroes if necessary
			if int(total) == total:
				print "Turned 'total' from float to int, since {} is equal to {}".format(total, int(total))
				total = int(total)
			
			print u"{} rolls, {} sides, total = {}".format(rollcount, sides, total)
			if rollcount == 1:
				replytext += u"A {}-sided die roll! Rolling, rolling... and it's a... {}!".format(sides, total)
			elif rollcount <= displayRollsLimit:
				replytext += u"{} rolls with {}-sided dice: {} = {}".format(rollcount, sides, u" + ".join(rollValues), total)
			elif rollcount <= rollLimit:
				replytext += u"{} rolls with {}-sided dice. Wow, that's a lot. Good thing I'm fast with these. Your total is... hang on... {}!".format(rollcount, sides, total)
			else:
				replytext += u"{} is a LOT of rolls, even I would spend ages on that. I'll just give you the expected value, that'll be close enough. And that is... {}!".format(rollcount, total)

		message.bot.say(message.source, replytext)

