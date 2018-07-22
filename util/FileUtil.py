import codecs, logging, os, random

import GlobalStore


logger = logging.getLogger('DideRobot')

def isAllowedPath(path):
	#This function checks whether the provided path is inside the bot's data folder
	# To prevent people adding "../.." to some bot calls to have free access to the server's filesystem
	if not os.path.abspath(path).startswith(GlobalStore.scriptfolder):
		logger.warning("[SharedFunctions] Somebody is trying to leave the bot's file systems by calling filename '{}'".format(path))
		return False
	return True

def getLineCount(filename):
	#Set a default in case the file has no lines
	linecount = -1  #'-1' so with the +1 at the end it ends up a 0 for an empty file
	if not filename.startswith(GlobalStore.scriptfolder):
		filename = os.path.join(GlobalStore.scriptfolder, filename)
	if not os.path.isfile(filename):
		return -1
	with codecs.open(filename, 'r', 'utf-8') as f:
		for linecount, line in enumerate(f):
			continue
	return linecount + 1  #'enumerate()' starts at 0, so add one

def getLineFromFile(filename, wantedLineNumber):
	"""Returns the specified line number from the provided file (line number starts at 0)"""
	if not filename.startswith(GlobalStore.scriptfolder):
		filename = os.path.join(GlobalStore.scriptfolder, filename)
	#Check if it's an allowed path
	if not isAllowedPath(filename):
		return None
	if not os.path.isfile(filename):
		logger.error(u"Can't read line {} from file '{}'; file does not exist".format(wantedLineNumber, filename))
		return None
	with codecs.open(filename, 'r', 'utf-8') as f:
		for lineNumber, line in enumerate(f):
			if lineNumber == wantedLineNumber:
				return line.rstrip()
	return None

def getRandomLineFromFile(filename, linecount=None):
	if not filename.startswith(GlobalStore.scriptfolder):
		filename = os.path.join(GlobalStore.scriptfolder, filename)
	if not linecount:
		linecount = getLineCount(filename)
	if linecount <= 0:
		return None
	return getLineFromFile(filename, random.randrange(0, linecount))

def getAllLinesFromFile(filename):
	#Make sure it's an absolute filename
	if not filename.startswith(GlobalStore.scriptfolder):
		filename = os.path.join(GlobalStore.scriptfolder, filename)
	if not isAllowedPath(filename):
		return None
	if not os.path.exists(filename):
		logger.error(u"Can't read lines from file '{}'; it does not exist".format(filename))
		return None
	#Get all the lines!
	with codecs.open(filename, 'r', 'utf-8') as linesfile:
		return linesfile.readlines()