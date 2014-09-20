import base64, json, os, random, re, sys
from ConfigParser import ConfigParser

import requests

import GlobalStore


#First some Twitter functions
def updateTwitterToken():
	if not GlobalStore.commandhandler.apikeys.has_section('twitter') or not GlobalStore.commandhandler.apikeys.has_option('twitter', 'key') or not GlobalStore.commandhandler.apikeys.has_option('twitter', 'secret'):
		print "No Twitter API key and/or secret found !"
		return False

	credentials = base64.b64encode("{}:{}".format(GlobalStore.commandhandler.apikeys.get('twitter', 'key'), GlobalStore.commandhandler.apikeys.get('twitter', 'secret')))
	headers = {"Authorization": "Basic {}".format(credentials), "Content-Type": "application/x-www-form-urlencoded;charset=UTF-8"}
	data = "grant_type=client_credentials"

	req = requests.post("https://api.twitter.com/oauth2/token", data=data, headers=headers)
	#print req.text
	reply = json.loads(req.text)
	if 'access_token' not in reply:
		print "ERROR while retrieving token: " + json.dumps(reply)
		return False

	if not GlobalStore.commandhandler.apikeys.has_section('twitter'):
		GlobalStore.commandhandler.apikeys.add_section('twitter')
	GlobalStore.commandhandler.apikeys.set('twitter', 'token', reply['access_token'])
	GlobalStore.commandhandler.apikeys.set('twitter', 'tokentype', reply['token_type'])

	GlobalStore.commandhandler.saveApiKeys()

	return True

def downloadTweets(username, downloadNewerThanId=-1, downloadOlderThanId=999999999999999999):
	highestIdDownloaded = 0
	storedInfo = ConfigParser()
	storedInfo.optionxform = str  #Makes sure options preserve their case. Prolly breaks something down the line, but CASE!
	twitterInfoFilename = os.path.join(GlobalStore.scriptfolder, 'data', 'TwitterInfo.dat')
	if os.path.exists(twitterInfoFilename):
		storedInfo.read(twitterInfoFilename)
	if not storedInfo.has_section(username):
		storedInfo.add_section(username)
	if storedInfo.has_option(username, "highestIdDownloaded"):
		highestIdDownloaded = int(storedInfo.get(username, "highestIdDownloaded"))

	headers = {"Authorization": "{} {}".format(GlobalStore.commandhandler.apikeys.get('twitter', 'tokentype'), GlobalStore.commandhandler.apikeys.get('twitter', 'token'))}
	params = {"screen_name": username, "count": "200", "trim_user": "true", "exclude_replies": "true", "include_rts": "false"}
	if downloadNewerThanId > -1:
		params["since_id"] = downloadNewerThanId

	tweets = {}
	lowestIdFound = downloadOlderThanId
	newTweetsFound = True

	while newTweetsFound:
		params["max_id"] = lowestIdFound

		req = requests.get("https://api.twitter.com/1.1/statuses/user_timeline.json", headers=headers, params=params)
		apireply = json.loads(req.text)

		newTweetsFound = False
		for tweet in apireply:
			tweettext = tweet["text"].replace("\n", " ").encode(encoding="utf-8", errors="replace")
			#print "Tweet {}: {}".format(tweet["id"], tweettext)
			if tweet["id"] not in tweets:
				#print "  storing tweet"
				newTweetsFound = True
				tweets[tweet["id"]] = tweettext

				tweetId = int(tweet["id"])
				lowestIdFound = min(lowestIdFound, tweetId-1)
				highestIdDownloaded = max(highestIdDownloaded, tweetId)
			#else:
			#	print "  skipping duplicate tweet"

	#All tweets downloaded. Time to process them
	tweetfile = open(os.path.join(GlobalStore.scriptfolder, 'data', "tweets-{}.txt".format(username)), "a")
	#Sort the keys before saving, so we're writing from oldest to newest, so in the same order as the Twitter timeline (Not absolutely necessary, but it IS neat and tidy)
	for id in sorted(tweets.keys()):
		tweetfile.write(tweets[id] + "\n")
	tweetfile.close()

	storedInfo.set(username, "highestIdDownloaded", highestIdDownloaded)
	linecount = 0
	if storedInfo.has_option(username, "linecount"):
		linecount = storedInfo.getint(username, "linecount")
	linecount += len(tweets)
	storedInfo.set(username, "linecount", linecount)

	storedInfoFile = open(twitterInfoFilename, "w")
	storedInfo.write(storedInfoFile)
	storedInfoFile.close()
	return True

def downloadNewTweets(username):
	highestIdDownloaded = -1
	twitterInfoFilename = os.path.join(GlobalStore.scriptfolder, 'data', 'TwitterInfo.dat')
	if os.path.exists(twitterInfoFilename):
		storedInfo = ConfigParser()
		storedInfo.read(twitterInfoFilename)
		if storedInfo.has_section(username) and storedInfo.has_option(username, "highestIdDownloaded"):
			highestIdDownloaded = storedInfo.get(username, "highestIdDownloaded")

	return downloadTweets(username, highestIdDownloaded)

def getLineFromTweetFile(username, linenumber):
	linenumber = linenumber -1 #iteration function starts at 0

	twitterInfoFilename = os.path.join(GlobalStore.scriptfolder, 'data', 'TwitterInfo.dat')
	if not os.path.exists(twitterInfoFilename):
		return "ERROR: No data file found!"
	
	storedInfo = ConfigParser()
	storedInfo.read(twitterInfoFilename)
	if not storedInfo.has_section(username):
		return "ERROR: No info on '{}' found!".format(username)
	if not storedInfo.has_option(username, "linecount"):
		return "ERROR: Number of lines not stored!"
	
	if not os.path.exists(os.path.join(GlobalStore.scriptfolder, 'data', "tweets-{}.txt".format(username))):
		return "ERROR: No tweets for '{}' stored!".format(username)

	if linenumber > storedInfo.getint(username, 'linecount'):
		return "ERROR: Requested line number {} while there are only {} lines".format(linenumber+1, storedInfo.getint(username, 'linecount'))

	#print "Picking line {} out of {}".format(linenumber+1, storedInfo.getint(username, "linecount"))
	with open(os.path.join(GlobalStore.scriptfolder, 'data', "tweets-{}.txt".format(username))) as linefile:
		for filelinenumber, line in enumerate(linefile):
			if filelinenumber == linenumber:
				return unicode(line.replace("\n", ""))

	return "That's weird, no line was found. That shouldn't happen (Tried to load line {} of {})".format(linenumber, storedInfo.getint(username, "linecount"))

def getRandomLineFromTweetFile(username):
	storedInfo = ConfigParser()
	storedInfo.read(os.path.join(GlobalStore.scriptfolder, 'data', 'TwitterInfo.dat'))
	if not storedInfo.has_section(username):
		return "ERROR: No info on '{}' found!".format(username)
	if not storedInfo.has_option(username, "linecount"):
		return "ERROR: Number of lines not stored!"
	
	randomlinenumber = random.randint(1, storedInfo.getint(username, "linecount"))
	return getLineFromTweetFile(username, randomlinenumber)


def getRandomLineFromFile(filename):
	lines = getAllLinesFromFile(filename)
	return random.choice(lines).strip()

def getAllLinesFromFile(filename):
	if not os.path.exists(filename):
		print u"LINE READ ERROR: File '{}' does not exist".format(filename)
		return None
	#Make sure it's an absolute filename
	if GlobalStore.scriptfolder not in filename:
		filename = os.path.join(GlobalStore.scriptfolder, filename)
	file = open(filename, 'r')
	lines = file.readlines()
	file.close()
	return lines


def parseIsoDate(isoString, formatstring=""):
	"""Turn an ISO 8601 formatted duration string like P1DT45M3S into something readable like "1 day, 45 minutes, 3 seconds"""

	durations = {"year": 0, "month": 0, "week": 0, "day": 0, "hour": 0, "minute": 0, "second": 0}

	regex = 'P(?:(?P<year>\d+)Y)?(?:(?P<month>\d+)M)?(?:(?P<week>\d+)W)?(?:(?P<day>\d+)D)?T?(?:(?P<hour>\d+)H)?(?:(?P<minute>\d+)M)?(?:(?P<second>\d+)S)?'
	result = re.search(regex, isoString)
	if result is None:
		print "No results found"
	else:
		for group, value in result.groupdict().iteritems():
			if value is not None:
				durations[group] = int(float(value))
		#print durations
	
	if formatstring != "":
		return formatstring.format(**durations)
	else:
		return durations

def parseInt(text, defaultValue=None, lowestValue=None, highestValue=None):
	try:
		integer = int(text)
		if lowestValue:
			integer = max(integer, lowestValue)
		if highestValue:
			integer = min(integer, highestValue)
		return integer
	except (TypeError, ValueError):
		return defaultValue


def durationSecondsToText(durationInSeconds):
	minutes, seconds = divmod(durationInSeconds, 60)
	hours, minutes = divmod(minutes, 60)
	days, hours = divmod(hours, 24)

	replytext = u""
	if days > 0:
		replytext += u"{:,.0f} days, ".format(days)
	if hours > 0:
		replytext += u"{:,.0f} hours, ".format(hours)
	if minutes > 0:
		replytext += u"{:,.0f} minutes, ".format(minutes)
	replytext += u"{:,.0f} seconds".format(seconds)
	return replytext


def dictToString(dictionary):
	dictstring = u""
	for key, value in dictionary.iteritems():
		dictstring += u"{}: {}, ".format(key, value)
	if len(dictstring) > 2:
		dictstring = dictstring[:-2]
	return dictstring


def stringToDict(string, removeStartAndEndQuotes=True):
	if string.startswith('{') and string.endswith('}'):
		string = string[1:-1]

	dictionary = {}
	#Split the string on commas that aren't followed by any other commas before encountering a colon
	#  This makes sure that it doesn't trip on commas in dictionary items
	keyValuePairs = re.split(r",(?=[^,]+:)", string)

	for pair in keyValuePairs:
		parts = pair.split(':')
		if len(parts) != 2:
			print "ERROR in stringToDict when trying to parse pair '{}'. Expected 2 parts, found {}".format(pair, len(parts))
			continue
		key = parts[0].strip()
		item = parts[1].strip()
		if removeStartAndEndQuotes:
			key = removeCharactersFromStringEnds(key, '"', "'").strip()
			item = removeCharactersFromStringEnds(item, '"', "'").strip()
		dictionary[key] = item
	return dictionary


def removeCharactersFromStringEnds(string, *chars):
	charRemoved = True
	#Keep removing characters until there's nothing left to remove
	while charRemoved:
		charRemoved = False
		for char in chars:
			charLength = len(char)
			while string.startswith(char):
				charRemoved = True
				string = string[charLength:]
			while string.endswith(char):
				charRemoved = True
				string = string[:-charLength]
	return string
