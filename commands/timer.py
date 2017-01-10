import GlobalStore
from CommandTemplate import CommandTemplate
from IrcMessage import IrcMessage


class Command(CommandTemplate):
	triggers = ['timer', 'remind']
	helptext = "Set a timer to remind you of something later. parameters are [time in seconds] ([message])"

	def execute(self, message):
		"""
		:type message: IrcMessage
		"""
		replytext = u""
		if message.messagePartsLength == 1:
			replytext = u"Please add a time (in seconds) and optionally a reminder message"
		else:
			waittime = -1.0
			try:
				waittime = float(message.messageParts[0])
			except ValueError:
				replytext = u"'{}' is not a valid number".format(message.messageParts[0])

			#Only continue if no error message has already been set
			if replytext == u"":
				if waittime < 0.0:
					replytext = u"Your timer of {} seconds ago is already up, since it's negative".format(waittime)
				elif waittime <= 10.0:
					replytext = u"Surely you don't forget stuff that quickly? Try a delay of more than 10 seconds"
				elif waittime > 86400.0:  #Longer than a day
					replytext = u"That's a bit too long of a wait time, sorry. Try less than a day"
				else:
					timerMsg = u"{}, your {}-second timer is up".format(message.userNickname, waittime)
					if message.messagePartsLength >= 2:
						timerMsg += u": {}".format(u" ".join(message.messageParts[1:]))

					GlobalStore.reactor.callLater(waittime, message.bot.sendMessage, message.source, timerMsg, "say")

					replytext = u"{}: Your timer will fire in {} seconds".format(message.userNickname, waittime)

		message.reply(replytext, "say")
