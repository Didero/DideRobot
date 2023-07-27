import subprocess, sys

import Constants, PermissionLevel
from commands.CommandTemplate import CommandTemplate
from IrcMessage import IrcMessage


class Command(CommandTemplate):
	triggers = ['update', 'updatelibraries']
	helptext = "Gets the latest files from the GitHub repository, if there are any. Use '{commandPrefix}updatelibraries' to update the libraries I need to run"
	minPermissionLevel = PermissionLevel.BOT

	lastCommitHash = ""
	MAX_UPDATES_TO_DISPLAY = 5

	def onLoad(self):
		#Set the stored hash to the latest local one
		output = subprocess.check_output(['git', 'show', '--format=oneline', '--no-patch'])
		self.lastCommitHash = output.split(b" ", 1)[0]
	
	def execute(self, message):
		"""
		:type message: IrcMessage
		"""

		if message.trigger == 'update':
			#First just get anything new, if there is any
			subprocess.check_output(['git', 'pull'])
			#Check if any new updates were pulled in
			outputLines = subprocess.check_output(['git', 'log', '--format=oneline']).splitlines()
			commitMessages = []
			linecount = 0
			for line in outputLines:
				lineparts = line.split(b" ", 1)
				#If we've reached a commit we've already mentioned, stop the whole thing
				if lineparts[0] == self.lastCommitHash:
					break
				linecount += 1
				#Only show the last few commit messages, but keep counting lines regardless
				if len(commitMessages) < self.MAX_UPDATES_TO_DISPLAY :
					commitMessages.append(lineparts[1].decode('utf-8'))
			if linecount == 0:
				replytext = u"No updates found, seems I'm up-to-date. I feel so hip!"
			elif linecount == 1:
				replytext = u"One new commit: {}".format(commitMessages[0])
			else:
				commitMessages.reverse()  #Otherwise the messages are ordered new to old
				replytext = u"{:,} new commits: {}".format(linecount, Constants.GREY_SEPARATOR.join(commitMessages))
				if linecount > self.MAX_UPDATES_TO_DISPLAY:
					replytext += u"; {:,} older ones".format(linecount - self.MAX_UPDATES_TO_DISPLAY)
			#Set the last mentioned hash to the newest one
			self.lastCommitHash = outputLines[0].split(b" ", 1)[0]
		else:
			# Update libraries
			# First update PIP itself
			outputLines = subprocess.check_output([sys.executable, '-m', 'pip', 'install', '--upgrade', 'pip'])
			replyParts = []
			if b'Successfully installed pip-' in outputLines:
				updateLine = outputLines.splitlines()[-1]
				replyParts.append(updateLine.decode('utf-8'))

			# Then update all our libraries
			outputLines = subprocess.check_output([sys.executable, '-m', 'pip', 'install', '--upgrade', '-r', 'requirements.txt'])
			for outputLine in outputLines.splitlines():
				if outputLine.startswith(b'Successfully installed'):
					replyParts.append(outputLine.decode('utf-8'))

			if replyParts:
				replytext = ". ".join(replyParts)
			else:
				replytext = "All my libraries seem up to date, great!"

		message.reply(replytext)
