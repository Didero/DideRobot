import codecs, os

import GlobalStore
from commands.CommandTemplate import CommandTemplate
from IrcMessage import IrcMessage


class Command(CommandTemplate):
	triggers = ['errorreport', 'warningreport']
	helptext = "Looks through the bot's logs and reports any errors or warnings (depending on the trigger) it finds. Admin-only, and only works in private messages to prevent spam"

	def execute(self, message):
		"""
		:type message: IrcMessage
		"""

		if not message.bot.isUserAdmin(message.user, message.userNickname, message.userAddress):
			return message.reply("Sorry, this command is admin-only")
		if not message.isPrivateMessage:
			return message.reply("Sorry, this command only works in private messages, to prevent spam and possibly showing private information")

		logLevel = 'error' if message.trigger == 'errorreport' else 'warning'

		# Go through all the Program.log files to look for lines with the requested loglevel
		# Start with any Program.log.[date] files, and then Program.log itself, to keep things chronological
		matchingLines = []
		numberOfFilesChecked = 0
		for fn in os.listdir(GlobalStore.scriptfolder):
			if fn.startswith('Program.log.'):
				matchingLines.extend(self.findLogLevelLinesInLogfile(os.path.join(GlobalStore.scriptfolder, fn), logLevel))
				numberOfFilesChecked += 1
		if os.path.isfile(os.path.join(GlobalStore.scriptfolder, 'Program.log')):
			matchingLines.extend(self.findLogLevelLinesInLogfile(os.path.join(GlobalStore.scriptfolder, 'Program.log'), logLevel))
			numberOfFilesChecked += 1

		if not matchingLines:
			message.reply("Hurray, no {}s were found in the {:,} logfiles I checked. That's because I'm programmed incredibly wlel"  # The typo in 'wlel' is intentional, it's a joke
						  .format(logLevel, numberOfFilesChecked))
		else:
			message.reply("Found {:,} {}{} in {:,} logfile{}:".format(len(matchingLines), logLevel, '' if len(matchingLines) == 1 else 's', numberOfFilesChecked, '' if numberOfFilesChecked == 1 else 's'))
			for line in matchingLines[-4:]:
				message.replyWithLengthLimit(line)

	def findLogLevelLinesInLogfile(self, logFilePath, logLevelString):
		matchingLines = []
		logLevelStringToFind = '({})'.format(logLevelString.upper())
		with codecs.open(logFilePath, 'r', 'utf-8') as logFile:
			for line in logFile:
				if logLevelStringToFind in line:
					# Check if it is an actual matching entry and not just a line that happens to have the log level text somewhere in it
					lineParts = line.split(' ', 3)
					if len(lineParts) > 3 and lineParts[2] == logLevelStringToFind:
						matchingLines.append(line)
		return matchingLines
