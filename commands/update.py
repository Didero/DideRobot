import subprocess

from CommandTemplate import CommandTemplate
from IrcMessage import IrcMessage


class Command(CommandTemplate):
	triggers = ['update']
	helptext = "Gets the latest files from the GitHub repository, if there are any"
	adminOnly = True

	lastCommitHash = ""

	def onLoad(self):
		#Set the stored hash to the latest local one
		output = subprocess.check_output(['git', 'log', '@{1}..', '--format=oneline'])
		self.lastCommitHash = output.split(" ", 1)[0]
	
	def execute(self, message):
		"""
		:type message: IrcMessage
		"""

		replytext = u""
		#First just get anything new, if there is any
		output = subprocess.check_output(['git', 'pull'])
		if output.startswith("Already up-to-date."):
			replytext = u"No new updates"
		else:
			maxUpdatesToDisplay = 15
			#New files, new updates! Check what they are
			output = subprocess.check_output(['git', 'log', '--format=oneline'])
			outputLines = output.splitlines()
			commitMessages = []
			linecount = 0
			for line in outputLines:
				lineparts = line.split(" ", 1)
				#If we've reached a commit we've already mentioned, stop the whole thing
				if lineparts[0] == self.lastCommitHash:
					break
				linecount += 1
				#Only show the last few commit messages, but keep counting lines regardless
				if len(commitMessages) < maxUpdatesToDisplay:
					commitMessages.append(lineparts[1])
			if linecount == 1:
				replytext = u"One new commit: {}".format(commitMessages[0])
			else:
				commitMessages.reverse()  #Otherwise the messages are ordered new to old
				replytext = u"{:,} new commits: {}".format(linecount, u" | ".join(commitMessages))
				if linecount > maxUpdatesToDisplay:
					replytext += u"; {:,} older ones".format(linecount - maxUpdatesToDisplay)
			#Set the last mentioned hash to the newest one
			self.lastCommitHash = outputLines[0].split(" ", 1)[0]

		message.bot.say(message.source, replytext)
