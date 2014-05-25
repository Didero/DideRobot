import subprocess

from CommandTemplate import CommandTemplate
from IrcMessage import IrcMessage


class Command(CommandTemplate):
	triggers = ['update']
	helptext = "Gets the latest files from the GitHub repository, if there are any"
	adminOnly = True

	lastCommitHash = ""
	
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
			#New files, new updates! Check what they are ('@{1}' returns the last commit)
			output = subprocess.check_output(['git', 'log', '--format=oneline'])
			outputLines = output.splitlines()
			replytext = u"Updated: Commit messages: "
			for line in outputLines:
				lineparts = line.split(" ", 1)
				#If we've reached a commit we've already mentioned, stop the whole thing
				if lineparts[0] == self.lastCommitHash:
					break
				replytext += u"'{}'; ".format(lineparts[1])
			replytext = replytext[:-2]
			#Set the last mentioned hash to the newest one
			self.lastCommitHash = outputLines[0].split(" ", 1)[0]

		message.bot.say(message.source, replytext)
