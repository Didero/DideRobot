import subprocess

from CommandTemplate import CommandTemplate
from IrcMessage import IrcMessage
import SharedFunctions


class Command(CommandTemplate):
	triggers = ['update']
	helptext = "Gets the latest files from the GitHub repository, if there are any"
	adminOnly = True

	lastCommitHash = ""
	MAX_UPDATES_TO_DISPLAY = 5

	def onLoad(self):
		#Set the stored hash to the latest local one
		output = subprocess.check_output(['git', 'show', '--format=oneline', '--no-patch'])
		self.lastCommitHash = output.split(" ", 1)[0]
	
	def execute(self, message):
		"""
		:type message: IrcMessage
		"""

		#First just get anything new, if there is any
		subprocess.check_output(['git', 'pull'])
		#Check if any new updates were pulled in
		outputLines = subprocess.check_output(['git', 'log', '--format=oneline']).splitlines()
		commitMessages = []
		linecount = 0
		for line in outputLines:
			lineparts = line.split(" ", 1)
			#If we've reached a commit we've already mentioned, stop the whole thing
			if lineparts[0] == self.lastCommitHash:
				break
			linecount += 1
			#Only show the last few commit messages, but keep counting lines regardless
			if len(commitMessages) < self.MAX_UPDATES_TO_DISPLAY :
				commitMessages.append(lineparts[1])
		if linecount == 0:
			replytext = u"No updates found, seems I'm up-to-date. I feel so hip!"
		elif linecount == 1:
			replytext = u"One new commit: {}".format(commitMessages[0])
		else:
			commitMessages.reverse()  #Otherwise the messages are ordered new to old
			replytext = u"{:,} new commits: {}".format(linecount, SharedFunctions.joinWithSeparator(commitMessages))
			if linecount > self.MAX_UPDATES_TO_DISPLAY:
				replytext += u"; {:,} older ones".format(linecount - self.MAX_UPDATES_TO_DISPLAY)
		#Set the last mentioned hash to the newest one
		self.lastCommitHash = outputLines[0].split(" ", 1)[0]

		message.reply(replytext, "say")
