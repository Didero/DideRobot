import base64, json, os, random
from ConfigParser import ConfigParser

import requests

import GlobalStore

twitterFolder = 'TwitterData'
twitterInfoFilename = os.path.join(twitterFolder, 'TwitterInfo.dat')

if not os.path.exists(twitterFolder):
	os.makedirs(twitterFolder)

def updateToken():
	if not GlobalStore.commandhandler.apikeys.has_section('twitter') or not GlobalStore.commandhandler.apikeys.has_option('twitter', 'key') or not GlobalStore.commandhandler.apikeys.has_option('twitter', 'secret'):
		print "No Twitter API key and/or secret found !"
		return False

	credentials = base64.b64encode("{}:{}".format(GlobalStore.commandhandler.apikeys.get('twitter', 'key'), GlobalStore.commandhandler.apikeys.get('twitter', 'secret')))
	headers = {"Authorization": "Basic {}".format(credentials), "Content-Type": "application/x-www-form-urlencoded;charset=UTF-8"}
	data = "grant_type=client_credentials"

	req = requests.post("https://api.twitter.com/oauth2/token", data=data, headers=headers)
	#print req.text
	reply = json.loads(req.text)
	if ('access_token' not in reply):
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
	storedInfo.optionxform = str #Makes sure options preserve their case. Prolly breaks something down the line, but CASE!
	if (os.path.exists(twitterInfoFilename)):
		storedInfo.read(twitterInfoFilename)
	if (not storedInfo.has_section(username)):
		storedInfo.add_section(username)
	if (storedInfo.has_option(username, "highestIdDownloaded")):
		#print "Found stored highest id"
		highestIdDownloaded = int(storedInfo.get(username, "highestIdDownloaded"))

	headers = {"Authorization": "{} {}".format(GlobalStore.commandhandler.apikeys.get('twitter', 'tokentype'), GlobalStore.commandhandler.apikeys.get('twitter', 'token'))}
	params = {"screen_name": username, "count": "200", "trim_user": "true", "exclude_replies": "true", "include_rts": "false"}
	if (downloadNewerThanId > -1):
		params["since_id"] = downloadNewerThanId


	tweets = {}
	lowestIdFound = downloadOlderThanId
	newTweetsFound = True

	while newTweetsFound:
		params["max_id"] = lowestIdFound

		req = requests.get("https://api.twitter.com/1.1/statuses/user_timeline.json", headers=headers, params=params)
		apireply = json.loads(req.text)

		#print json.dumps(apireply, indent=2, separators=(",", ": "))
		#newTweetsFound = False

		newTweetsFound = False
		for tweet in apireply:
			tweettext = tweet["text"].replace("\n", " ").encode(encoding="utf-8", errors="replace")
			print "Tweet {}: {}".format(tweet["id"], tweettext)
			if (tweet["id"] not in tweets):
				print "  storing tweet"
				newTweetsFound = True
				tweets[tweet["id"]] = tweettext

				tweetId = int(tweet["id"])
				lowestIdFound = min(lowestIdFound, tweetId-1)
				highestIdDownloaded = max(highestIdDownloaded, tweetId)
			else:
				print "  skipping duplicate tweet"

	#All tweets downloaded. Time to process them
	print "Saving {} tweets to file".format(len(tweets))
	tweetfile = open(os.path.join(twitterFolder, "tweets-{}.txt".format(username)), "a")
	#Sort the keys before saving, so we're writing from oldest to newest, so in the same order as the Twitter timeline (Not absolutely necessary, but it IS neat and tidy)
	for id in sorted(tweets.keys()):
		#tweetfile.write("[{}] {}\n".format(str(id), tweets[id]))
		tweetfile.write(tweets[id] + "\n")
	tweetfile.close()
	print "Done saving tweets to file"

	storedInfo.set(username, "highestIdDownloaded", highestIdDownloaded)
	linecount = 0
	if (storedInfo.has_option(username, "linecount")):
		linecount = storedInfo.getint(username, "linecount")
	linecount += len(tweets)
	storedInfo.set(username, "linecount", linecount)

	storedInfoFile = open(twitterInfoFilename, "w")
	storedInfo.write(storedInfoFile)
	storedInfoFile.close()
	return True

def downloadNewTweets(username):
	highestIdDownloaded = -1
	if (os.path.exists(twitterInfoFilename)):
		storedInfo = ConfigParser()
		storedInfo.read(twitterInfoFilename)
		if (storedInfo.has_section(username) and storedInfo.has_option(username, "highestIdDownloaded")):
			highestIdDownloaded = storedInfo.get(username, "highestIdDownloaded")

	return downloadTweets(username, highestIdDownloaded)

def getLine(username, linenumber):
	linenumber = linenumber -1 #iteration function starts at 0

	if not os.path.exists(twitterInfoFilename):
		return "ERROR: No data file found!"
	
	storedInfo = ConfigParser()
	storedInfo.read(twitterInfoFilename)
	if not storedInfo.has_section(username):
		return "ERROR: No info on '{}' found!".format(username)
	if not storedInfo.has_option(username, "linecount"):
		return "ERROR: Number of lines not stored!"
	
	if not os.path.exists(os.path.join(twitterFolder, "tweets-{}.txt".format(username))):
		return "ERROR: No tweets for '{}' stored!".format(username)

	print "Picking line {} out of {}".format(linenumber+1, storedInfo.getint(username, "linecount"))
	with open(os.path.join(twitterFolder, "tweets-{}.txt".format(username))) as linefile:
		for filelinenumber, line in enumerate(linefile):
			#print "{}: {}".format(linenumber, line.replace("\n", ""))
			if filelinenumber == linenumber:
				return unicode(line.replace("\n", ""))

	return "That's weird, no line was found. That shouldn't happen (Tried to load line {} of {})".format(linenumber, storedInfo.getint(username, "linecount"))

def getRandomLine(username):
	storedInfo = ConfigParser()
	storedInfo.read(twitterInfoFilename)
	if not storedInfo.has_section(username):
		return "ERROR: No info on '{}' found!".format(username)
	if not storedInfo.has_option(username, "linecount"):
		return "ERROR: Number of lines not stored!"
	
	randomlinenumber = random.randint(1, storedInfo.getint(username, "linecount")) - 1 #minus one, because the iteration function starts at 0	
	return getLine(username, randomlinenumber)