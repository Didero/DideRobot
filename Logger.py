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
		if not os.path.exists(self.logfolder):
				os.makedirs(self.logfolder)
		print "Creating new logger for '{}', using logfolder '{}'".format(self.botfactory.serverfolder, self.logfolder)

		self.updateLogSettings()
		
		self.currentDay = datetime.datetime.now().day

	def updateLogSettings(self):
		print "[Logger] |{}| Reloading settings".format(self.botfactory.serverfolder)
		#Set local boolean values only to 'True' if they're 'true' in the ini file
		self.shouldKeepSystemLogs = self.botfactory.settings.get("scripts", "keepSystemLogs").lower() == "true"
		self.shouldKeepChannelLogs = self.botfactory.settings.get("scripts", "keepChannelLogs").lower() == "true"
		self.shouldKeepPrivateLogs = self.botfactory.settings.get("scripts", "keepPrivateLogs").lower() == "true"

		#Let's not let any file handlers linger about
		self.closelogs()

		
	def logmsg(self, msg, source, user):
		#For private messages, the source is the user that sent it, while on channels it's the channel name
		# This is different for private messages that the bot sends, since there the target is actually the target
		if not source.startswith("#") and user != self.botfactory.bot.nickname:
			source = user.split("!", 1)[0]
			
		#Write that message down!
		return self.log("{0}: {1}".format(user, msg), source)
		

	def log(self, msg, source="system", addTimestamp=True):		
		#First check if we're even supposed to log
		if source == "system" and not self.shouldKeepSystemLogs:
			#print 'Not keeping system logs, not writing "{}" to "system" log'.format(msg) 
			return
		elif source.startswith("#") and not self.shouldKeepChannelLogs:
			#print 'Not keeping channel logs, not writing "{}" to "{}" log'.format(msg, source)
			return
		#Private messages
		elif not self.shouldKeepPrivateLogs:
			#print 'Not keeping private logs, not writing "{}" to "{}" log'.format(msg, source)
			return


		now = datetime.datetime.now()
		#If we're at a new day, close all the logs, since they're daily
		if now.day != self.currentDay:
			print "NEW DAY, NEW LOGS"
			self.closelogs()
			self.currentDay = datetime.datetime.now().day

		timestamp = now.strftime("%H:%M:%S")
		print "[Logger] |{0}| {1} [{2}] {3}".format(self.botfactory.serverfolder, source, timestamp, msg)
		#print "[Logger] |{}| {} open logfiles: ".format(self.botfactory.serverfolder, len(self.logfiles))
		#for key, value in self.logfiles.iteritems():
		#	print "  {}: {}".format(key, value)

		#If no file has been opened for this source, open it
		if source not in self.logfiles:
			#print "[Logger] |{}|: NONEXISTANT LOG '{}', opening".format(self.botfactory.serverfolder, source)
			logfilename = "{}-{}.log".format(source, now.strftime("%Y-%m-%d"))
			self.logfiles[source] = open(os.path.join(self.logfolder, logfilename), 'a')
		
		#print '[Logger] Writing "{0}" to "{1}"'.format(msg, source) 
		self.logfiles[source].write("[{0}] {1}\n".format(timestamp, msg))
		self.logfiles[source].flush()
		#os.fsync(self.logfiles[source].fileno())
		return True
			
		
	def closelog(self, source):
		print "[Logger] |{}| closing log '{}'".format(self.botfactory.serverfolder, source)
		if source in self.logfiles:
			#self.logfiles[source].flush()
			self.logfiles[source].close()
			#del self.logfiles[source]
			self.logfiles.pop(source, None)
			return True
		return False
			
	def closelogs(self):
		print "[Logger] |{}| Closing ALL logs".format(self.botfactory.serverfolder)
		for source, logfile in self.logfiles.iteritems():
			#print "[Logger] |{}| Closing log '{}' while closing all logs".format(self.botfactory.serverfolder, source)
			#logfile.flush()
			logfile.close()
		self.logfiles = {}
		return True
			