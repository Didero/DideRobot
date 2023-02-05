import codecs, os

import Constants, GlobalStore
from CommandTemplate import CommandTemplate
from IrcMessage import IrcMessage
from util import StringUtil


class Command(CommandTemplate):
	triggers = ['errorreport']
	helptext = "Looks through the bot's logs and reports any errors it finds. Admin-only, and only works in private messages to prevent spam"

	def execute(self, message):
		"""
		:type message: IrcMessage
		"""

		if not message.bot.isUserAdmin(message.user, message.userNickname, message.userAddress):
			return message.reply("Sorry, this command is admin-only")
		if not message.isPrivateMessage:
			return message.reply("Sorry, this command only works in private messages, to prevent spam and possibly showing private information")

		# Go through all the Program.log files to look for errors
		# Start with any Program.log.[date] files, and then Program.log itself, to keep things chronological
		errors = []
		for fn in os.listdir(GlobalStore.scriptfolder):
			if fn.startswith('Program.log.'):
				errors.extend(self.findErrorsInLogFile(os.path.join(GlobalStore.scriptfolder, fn)))
		if os.path.isfile(os.path.join(GlobalStore.scriptfolder, 'Program.log')):
			errors.extend(self.findErrorsInLogFile(os.path.join(GlobalStore.scriptfolder, 'Program.log')))

		if not errors:
			message.reply("Hurray, no errors were found. That's because I'm programmed incredibly wlel", 'say')  # The typo in 'wlel' is intentional, it's a joke
		else:
			message.reply("Found {:,} error{}:".format(len(errors), '' if len(errors) == 1 else 's'))
			for error in errors:
				message.reply(StringUtil.limitStringLength(error, Constants.MAX_MESSAGE_LENGTH), 'say')

	def findErrorsInLogFile(self, logFilePath):
		errors = []
		with codecs.open(logFilePath, 'r', 'utf-8') as logFile:
			for line in logFile:
				if '(ERROR)' in line:
					# Check if it is an actual error entry and not just a line that happens to have '(ERROR)' somewhere in it
					lineParts = line.split(' ', 3)
					if len(lineParts) > 3 and lineParts[2] == '(ERROR)':
						errors.append(line)
		return errors
