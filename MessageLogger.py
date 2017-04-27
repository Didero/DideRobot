import datetime, logging, os

import GlobalStore

class MessageLogger(object):
	logfiles = {}
	currentDay = 0
	logfolder = None
	bot = None
	shouldKeepSystemLogs = True
	shouldKeepChannelLogs = True
	shouldKeepPrivateLogs = True
	
	def __init__(self, bot):
		self.logger = logging.getLogger('DideRobot')
		self.bot = bot
		self.logfolder = os.path.join(GlobalStore.scriptfolder, 'serverSettings', bot.serverfolder, 'logs')
		self.logger.info("Creating new message logger for '{}', using logfolder '{}'".format(bot.serverfolder, self.logfolder))
		if not os.path.exists(self.logfolder):
				os.makedirs(self.logfolder)
		self.updateLogSettings()
		self.currentDay = datetime.datetime.now().day

	def updateLogSettings(self):
		self.logger.info("[MessageLogger] |{}| Reloading settings".format(self.bot.serverfolder))
		#Set local boolean values only to 'True' if they're 'true' in the ini file
		self.shouldKeepSystemLogs = self.bot.settings["keepSystemLogs"]
		self.shouldKeepChannelLogs = self.bot.settings["keepChannelLogs"]
		self.shouldKeepPrivateLogs = self.bot.settings["keepPrivateLogs"]
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
			self.logger.info("[MessageLogger] New day, new message logs")
			self.closelogs()
			self.currentDay = datetime.datetime.now().day

		timestamp = now.strftime("%H:%M:%S")
		print "[MessageLogger] |{0}| {1} [{2}] {3}".format(self.bot.serverfolder, source, timestamp, msg)

		#If no file has been opened for this source, open it
		if source not in self.logfiles:
			logfilename = "{}-{}.log".format(source, now.strftime("%Y-%m-%d"))
			try:
				self.logfiles[source] = open(os.path.join(self.logfolder, logfilename), 'a')
			except IOError as e:
				self.logger.error("[MessageLogger] Error while trying to open logfile '{}': {}".format(logfilename, e.message))
				return
		self.logfiles[source].write("[{0}] {1}\n".format(timestamp, msg))
		self.logfiles[source].flush()

	def closelog(self, source):
		if source in self.logfiles:
			self.logger.info("[MessageLogger] |{}| closing log '{}'".format(self.bot.serverfolder, source))
			self.logfiles[source].close()
			del self.logfiles[source]
			return True
		return False
			
	def closelogs(self):
		self.logger.info("[MessageLogger] |{}| Closing ALL logs".format(self.bot.serverfolder))
		for source, logfile in self.logfiles.iteritems():
			logfile.close()
		self.logfiles = {}
		return True
