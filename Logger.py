import datetime, os

import GlobalStore

class Logger(object):
	logfiles = {}
	currentDay = 0
	logfolder = None
	botfactory = None
	shouldKeepSystemLogs = True
	shouldKeepChannelLogs = True
	shouldKeepPrivateLogs = True
	
	def __init__(self, botfactory):
		self.botfactory = botfactory
		self.logfolder = os.path.join(GlobalStore.scriptfolder, 'serverSettings', botfactory.serverfolder, 'logs')
		print "Creating new logger for '{}', using logfolder '{}'".format(self.botfactory.serverfolder, self.logfolder)
		if not os.path.exists(self.logfolder):
				os.makedirs(self.logfolder)
		self.updateLogSettings()
		self.currentDay = datetime.datetime.now().day

	def updateLogSettings(self):
		print "[Logger] |{}| Reloading settings".format(self.botfactory.serverfolder)
		#Set local boolean values only to 'True' if they're 'true' in the ini file
		self.shouldKeepSystemLogs = self.botfactory.settings["connection"]["keepSystemLogs"]
		self.shouldKeepChannelLogs = self.botfactory.settings["connection"]["keepChannelLogs"]
		self.shouldKeepPrivateLogs = self.botfactory.settings["connection"]["keepPrivateLogs"]
		#Let's not let any file handlers linger about, in case logging settings were changed
		self.closelogs()

	def log(self, msg, source="system"):
		#First check if we're even supposed to log
		if source == "system" and not self.shouldKeepSystemLogs:
			return
		elif source.startswith('#') and not self.shouldKeepChannelLogs:
			return
		#Private messages don't start with a #
		elif not source.startswith('#') and not self.shouldKeepPrivateLogs:
			return

		now = datetime.datetime.now()
		#If we're at a new day, close all the logs, since they're daily
		if now.day != self.currentDay:
			print "[Logger] NEW DAY, NEW LOGS"
			self.closelogs()
			self.currentDay = datetime.datetime.now().day

		timestamp = now.strftime("%H:%M:%S")
		print "[Logger] |{0}| {1} [{2}] {3}".format(self.botfactory.serverfolder, source, timestamp, msg)

		#If no file has been opened for this source, open it
		if source not in self.logfiles:
			logfilename = "{}-{}.log".format(source, now.strftime("%Y-%m-%d"))
			self.logfiles[source] = open(os.path.join(self.logfolder, logfilename), 'a')
		self.logfiles[source].write("[{0}] {1}\n".format(timestamp, msg))
		self.logfiles[source].flush()

	def closelog(self, source):
		if source in self.logfiles:
			print "[Logger] |{}| closing log '{}'".format(self.botfactory.serverfolder, source)
			self.logfiles[source].close()
			del self.logfiles[source]
			return True
		return False
			
	def closelogs(self):
		print "[Logger] |{}| Closing ALL logs".format(self.botfactory.serverfolder)
		for source, logfile in self.logfiles.iteritems():
			logfile.close()
		self.logfiles = {}
		return True
