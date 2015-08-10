import datetime, time
import json
import os

import requests

from CommandTemplate import CommandTemplate
from IrcMessage import IrcMessage
import GlobalStore


class Command(CommandTemplate):
	triggers = ['log']
	helptext = u"Posts the log of the given day to Paste.ee. If you don't provide any parameters, it posts today's log." \
			   u" You can also provide a day in 'yyyy-mm-dd' format, or for instance '-1' to get yesterday's log"
	
	def execute(self, message):
		"""
		:type message: IrcMessage
		"""

		replytext = u""
		if 'paste.ee' not in GlobalStore.commandhandler.apikeys:
			replytext = u"The Paste.ee API key was not found. Please tell my owner so they can fix this"
		elif not message.source.startswith('#'):
			replytext = u"A log of a private conversation? That could lead to all kinds of privacy concerns..."
		elif not message.bot.factory.messageLogger.shouldKeepChannelLogs:
			replytext = u"I'm sorry, I was told not to keep logs for this channel"
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
					replytext = u"Invalid number entered, please type a negative number that indicates the amount of days you want to go back"
			elif message.messageParts[0].count('-') == 2 and len(message.messageParts[0]) > 2:
				#Date entry, like '2014-06-28'
				dateparts = message.messageParts[0].split('-')
				try:
					date = datetime.datetime(int(dateparts[0]), int(dateparts[1]), int(dateparts[2]))
				except ValueError:
					replytext = u"Date format entered in wrong format. Please provide it as 'yyyy-mm-dd'"
			else:
				#I don't know what argument was entered, but it's nothing we can use
				replytext = u"Unknown parameters provided. Please provide a date in 'yyyy-mm-dd' format, or the amount of days you want to go back (for instance '-1' for yesterday's log)"

			#If we have a datetime object, parse it to the text format we save logs as
			if date:
				logfilename = "{}-{}.log".format(message.source, date.strftime("%Y-%m-%d"))
				logfilename = os.path.join(GlobalStore.scriptfolder, "serverSettings", message.bot.factory.serverfolder, "logs", logfilename)
				#check if we've got a log for this channel and day
				if not os.path.exists(logfilename):
					replytext = u"Sorry, no log for that day was found"
				else:
					pasteData = {"key": GlobalStore.commandhandler.apikeys["paste.ee"],
								 "description": "Log for {} from {}".format(message.source, date.strftime("%Y-%m-%d")),
								 "format": "json", "paste": u"", "expire": 600}  #Expire value is in supposedly in minutes, but apparently it's in seconds

					#Add the actual log to the paste
					with open(logfilename, 'r') as logfile:
						for line in logfile:
							pasteData["paste"] += line.decode('utf-8')

					#Send the collected data to Paste.ee
					reply = requests.post("http://paste.ee/api", data=pasteData)
					if reply.status_code != requests.codes.ok:
						replytext = u"Something went wrong while trying to upload the log. (HTTP code {})".format(reply.status_code)
					else:
						replydata = json.loads(reply.text)
						if replydata['status'] != 'success':
							replytext = u"Something went wrong with uploading the log (Code {}: {})".format(replydata['errorcode'], replydata['error'])
						else:
							replytext = u"Log uploaded to Paste.ee: {} (Expires in {} minutes)".format(replydata['paste']['link'], pasteData['expire'] / 60)

		message.bot.sendMessage(message.source, replytext, 'say')