import datetime, os, time

from commands.CommandTemplate import CommandTemplate
from IrcMessage import IrcMessage
import GlobalStore
from util import WebUtil
from CustomExceptions import WebRequestException


class Command(CommandTemplate):
	triggers = ['log']
	helptext = "Posts the log of the given day. If you don't provide any parameters, it posts today's log." \
			   " You can also provide a day in 'yyyy-mm-dd' format, or for instance '-1' to get yesterday's log"
	
	def execute(self, message):
		"""
		:type message: IrcMessage
		"""

		replytext = ""
		if message.isPrivateMessage:
			replytext = "A log of a private conversation? That could lead to all kinds of privacy concerns..."
		elif not message.bot.messageLogger.shouldKeepChannelLogs:
			replytext = "I'm sorry, I was told not to keep logs for this channel"
		else:
			date = None
			if message.messagePartsLength == 0:
				#No special parameters, post today's log
				date = datetime.datetime.now()
			elif message.messageParts[0].startswith('-') and len(message.messageParts[0]) > 1:
				#Assume it's a negative number
				try:
					daysBack = int(message.messageParts[0])
					secondsBack = daysBack * 86400  # 24 hours per day * 60 minutes per hour * 60 seconds per minute
					date = datetime.datetime.fromtimestamp(time.time() + secondsBack)  #Add secondsBack, since it's negative
				except ValueError:
					replytext = "Invalid number entered, please type a negative number that indicates the amount of days you want to go back"
			elif message.messageParts[0].count('-') == 2 and len(message.messageParts[0]) > 2:
				#Date entry, like '2014-06-28'
				dateparts = message.messageParts[0].split('-')
				try:
					date = datetime.datetime(int(dateparts[0]), int(dateparts[1]), int(dateparts[2]))
				except ValueError:
					replytext = "Date format entered in wrong format. Please provide it as 'yyyy-mm-dd'"
			else:
				#I don't know what argument was entered, but it's nothing we can use
				replytext = "Unknown parameters provided. Please provide a date in 'yyyy-mm-dd' format, or the amount of days you want to go back (for instance '-1' for yesterday's log)"

			#If we have a datetime object, parse it to the text format we save logs as
			if date:
				logfilename = "{}-{}.log".format(message.source, date.strftime("%Y-%m-%d"))
				logfilename = os.path.join(GlobalStore.scriptfolder, "serverSettings", message.bot.serverfolder, "logs", logfilename)
				#check if we've got a log for this channel and day
				if not os.path.exists(logfilename):
					replytext = "Sorry, no log for that day was found"
				else:
					logtext = ""
					with open(logfilename, 'r', encoding='utf-8') as logfile:
						for line in logfile:
							logtext += line
					try:
						pasteLink = WebUtil.uploadText(logtext, "Log for {} from {}".format(message.source, date.strftime("%Y-%m-%d")), 600)
					except WebRequestException as wre:
						self.logError("[LogPoster] Uploading log failed: {}".format(wre))
						replytext = "Something went wrong with uploading the log, sorry. Either try again in a bit, or tell my owner(s) so they can try to fix it"
					else:
						replytext = "Log uploaded to Paste.ee: {} (Expires in 10 minutes)".format(pasteLink)

		message.reply(replytext)
