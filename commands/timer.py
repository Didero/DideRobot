import GlobalStore
from CommandTemplate import CommandTemplate

class Command(CommandTemplate):
	triggers = ['timer', 'remind']
	helptext = "Set a timer to remind you of something later. parameters are [time in seconds] ([message])"

	def execute(self, bot, user, target, triggerInMsg, msg, msgWithoutFirstWord, msgParts, msgPartsLength):
		replytext = u""
		if msgPartsLength == 1:
			replytext = u"Please add a time (in seconds) and optionally a reminder message"
		else:
			nick = user.split("!", 1)[0]

			waittime = -1.0
			try:
				waittime = float(msgParts[1])
			except:
				replytext = u"'{}' is not a valid number".format(msgParts[1])

			#Only continue if no error message has already been set
			if replytext == u"":
				if waittime < 0.0:
					replytext = u"Your timer of {} seconds ago is already up, since it's negative".format(waittime)
				elif waittime <= 10.0:
					replytext = u"Surely you don't forget stuff that quickly? Try a delay of more than 10 seconds"
				elif waittime > 86400.0: #Longer than a day
					replytext = u"That's a bit too long of a wait time, sorry. Try less than a day"
				else:
					if msgPartsLength > 2:
						timerMsg = "{}: {}".format(nick, " ".join(msgParts[2:]))
						GlobalStore.reactor.callLater(waittime, bot.say, target, timerMsg)
					else:
						GlobalStore.reactor.callLater(waittime, bot.say, target, "{}: Your timer is up".format(nick))

					replytext = u"{}: Your timer will fire in {} seconds".format(nick, waittime)

		bot.say(target, replytext)
