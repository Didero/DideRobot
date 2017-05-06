import base64, codecs, json, logging, os, random, re

import requests

import Constants, GlobalStore

logger = logging.getLogger('DideRobot')

#First some Twitter functions
def updateTwitterToken():
	apikeys = GlobalStore.commandhandler.apikeys
	if 'twitter' not in apikeys or 'key' not in apikeys['twitter']or 'secret' not in apikeys['twitter']:
		logger.error("No Twitter API key and/or secret found!")
		return False

	credentials = base64.b64encode("{}:{}".format(apikeys['twitter']['key'], apikeys['twitter']['secret']))
	headers = {"Authorization": "Basic {}".format(credentials), "Content-Type": "application/x-www-form-urlencoded;charset=UTF-8"}
	data = "grant_type=client_credentials"

	req = requests.post("https://api.twitter.com/oauth2/token", data=data, headers=headers)
	reply = json.loads(req.text)
	if 'access_token' not in reply:
		logger.error("An error occurred while retrieving Twitter token: " + json.dumps(reply))
		return False

	if 'twitter' not in apikeys:
		apikeys['twitter'] = {}
	apikeys['twitter']['token'] = reply['access_token']
	apikeys['twitter']['tokentype'] = reply['token_type']

	GlobalStore.commandhandler.saveApiKeys()
	return True

def downloadTweets(username, maxTweetCount=200, downloadNewerThanId=None, downloadOlderThanId=None, includeReplies=False, includeRetweets=False):
	#First check if we can even connect to the Twitter API
	if 'twitter' not in GlobalStore.commandhandler.apikeys or\
					'token' not in GlobalStore.commandhandler.apikeys['twitter'] or\
					'tokentype' not in GlobalStore.commandhandler.apikeys['twitter']:
		logger.warning("No twitter token found, retrieving a new one")
		tokenUpdateSuccess = updateTwitterToken()
		if not tokenUpdateSuccess:
			logger.error("Unable to retrieve a new Twitter token!")
			return (False, "Unable to retrieve Twitter authentication token!")

	#Now download tweets!
	headers = {'Authorization': "{} {}".format(GlobalStore.commandhandler.apikeys['twitter']['tokentype'], GlobalStore.commandhandler.apikeys['twitter']['token'])}
	params = {'screen_name': username, 'count': min(200, maxTweetCount), 'trim_user': 'true',
			  'exclude_replies': 'false' if includeReplies else 'true',
			  'include_rts': True}  #Always get retweets, remove them later if necessary. Needed because 'count' always includes retweets, even if you don't want them
	if downloadOlderThanId:
		params['max_id'] = downloadOlderThanId

	tweets = []
	if downloadNewerThanId:
		params['since_id'] = downloadNewerThanId
	while len(tweets) < maxTweetCount:
		params['count'] = maxTweetCount - len(tweets)  #Get as much tweets as we still need
		try:
			req = requests.get("https://api.twitter.com/1.1/statuses/user_timeline.json", headers=headers, params=params, timeout=20.0)
			apireply = json.loads(req.text)
		except requests.exceptions.Timeout:
			logger.error("Twitter API reply took too long to arrive")
			return (False, "Twitter took too long to respond", tweets)
		except ValueError:
			logger.error(u"Didn't get parsable JSON return from Twitter API: {}".format(req.text.replace('\n', '|')))
			return (False, "Unexpected data returned", tweets)
		except Exception as e:
			logger.error("Tweet download threw an unexpected error of type '{}': {}".format(type(e), str(e)))
			return (False, "Unknown error occurred", tweets)

		if len(apireply) == 0:
			#No more tweets to parse!
			break
		#Check for errors
		if isinstance(apireply, dict) and 'errors' in apireply:
			logger.error("[SharedFunctions] Error occurred while retrieving tweets for {}. Parameters:".format(username))
			logger.error(params)
			logger.error("[SharedFunctions] Twitter API reply:")
			logger.error(apireply)
			errorMessages = '; '.join(e['message'] for e in apireply['errors'])
			return (False, "Error(s) occurred: {}".format(errorMessages), tweets)
		#Sometimes the API does not return a list of tweets for some reason. Catch that
		if not isinstance(apireply, list):
			logger.error("[SharedFunctions] Unexpected reply from Twitter API. Expected tweet list, got {}:".format(type(apireply)))
			logger.error(apireply)
			return (False, "Unexpected API reply", tweets)
		#Tweets are sorted reverse-chronologically, so we can get the highest ID from the first tweet
		params['since_id'] = apireply[0]['id']
		#Remove retweets if necessary (done manually to make the 'count' variable be accurate)
		if not includeRetweets:
			apireply = [t for t in apireply if 'retweeted_status' not in t]
		#There are tweets, store those
		tweets.extend(apireply)
	return (True, tweets)

def downloadTweet(username, tweetId):
	downloadedTweet = downloadTweets(username, maxTweetCount=1, downloadNewerThanId=tweetId-1, downloadOlderThanId=tweetId+1)
	#If something went wrong, pass on the error
	if not downloadedTweet[0]:
		return downloadedTweet
	#Otherwise, make the single-item tweet list just the tweet
	return (True, downloadedTweet[1][0])

def getLineCount(filename):
	#Set a default in case the file has no lines
	linecount = -1  #'-1' so with the +1 at the end it ends up a 0 for an empty file
	if not filename.startswith(GlobalStore.scriptfolder):
		filename = os.path.join(GlobalStore.scriptfolder, filename)
	with codecs.open(filename, 'r', 'utf-8') as f:
		for linecount, line in enumerate(f):
			continue
	return linecount + 1  #'enumerate()' starts at 0, so add one

def getRandomLineFromFile(filename, linecount=None):
	if not filename.startswith(GlobalStore.scriptfolder):
		filename = os.path.join(GlobalStore.scriptfolder, filename)
	if not linecount:
		linecount = getLineCount(filename)
	chosenLineNumber = random.randrange(0, linecount)
	with codecs.open(filename, 'r', 'utf-8') as f:
		for lineNumber, line in enumerate(f):
			if lineNumber == chosenLineNumber:
				return line.rstrip()
	return ""

def getAllLinesFromFile(filename):
	if not os.path.exists(filename):
		logger.error(u"Can't read lines from file '{}'; it does not exist".format(filename))
		return None
	#Make sure it's an absolute filename
	if not filename.startswith(GlobalStore.scriptfolder):
		filename = os.path.join(GlobalStore.scriptfolder, filename)
	#Get all the lines!
	with codecs.open(filename, 'r', 'utf-8') as linesfile:
		return linesfile.readlines()


def parseIsoDate(isoString, formatstring=""):
	"""Turn an ISO 8601 formatted duration string like P1DT45M3S into something readable like "1 day, 45 minutes, 3 seconds"""

	durations = {"year": 0, "month": 0, "week": 0, "day": 0, "hour": 0, "minute": 0, "second": 0}

	regex = 'P(?:(?P<year>\d+)Y)?(?:(?P<month>\d+)M)?(?:(?P<week>\d+)W)?(?:(?P<day>\d+)D)?T?(?:(?P<hour>\d+)H)?(?:(?P<minute>\d+)M)?(?:(?P<second>\d+)S)?'
	result = re.search(regex, isoString)
	if result is None:
		logger.warning("No date results found")
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


def durationSecondsToText(durationInSeconds, precision='s'):
	minutes, seconds = divmod(durationInSeconds, 60)
	hours, minutes = divmod(minutes, 60)
	days, hours = divmod(hours, 24)

	replytext = u""
	if days > 0:
		replytext += u"{:,.0f} day{}, ".format(days, u's' if days > 1 else u'')
	if hours > 0:
		replytext += u"{:,.0f} hour{}".format(hours, u's' if hours > 1 else u'')
	if minutes > 0 and precision in ['s', 'm']:
		if hours > 0:
			replytext += u", "
		replytext += u"{:,.0f} minute{}".format(minutes, u's' if minutes > 1 else u'')
	if seconds > 0 and precision == 's':
		if hours > 0 or minutes > 0:
			replytext += u", "
		replytext += u"{:,.0f} second{}".format(seconds, u's' if seconds > 1 else u'')
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
			logger.error("ERROR in stringToDict when trying to parse pair '{}'. Expected 2 parts, found {}".format(pair, len(parts)))
			continue
		key = parts[0].strip()
		item = parts[1].strip()
		if removeStartAndEndQuotes:
			key = key.strip("'\" \t")
			item = item.strip("'\" \t")
		dictionary[key] = item
	return dictionary

def joinWithSeparator(listOfStrings, separator=None):
	if not separator:
		separator = Constants.GREY_SEPARATOR
	return separator.join(listOfStrings)

def makeTextBold(s):
	return '\x02' + s + '\x0f'  #\x02 is the 'bold' control character, '\x0f' cancels all decorations

def shortenUrl(longUrl):
	if 'google' not in GlobalStore.commandhandler.apikeys:
		logger.error("Url shortening requested but Google API key not found")
		return (False, longUrl, "No Google API key found")
	#The Google shortening API requires the url key in the POST message body for some reason, hence 'json' and not 'data'
	response = requests.post('https://www.googleapis.com/urlshortener/v1/url?key=' + GlobalStore.commandhandler.apikeys['google'],
				  json={'longUrl': longUrl})
	try:
		data = response.json()
	except ValueError:
		return (False, longUrl, "Reply was not JSON", response.text)
	else:
		if 'error' in data:
			return (False, longUrl, "An error occurred: {}", data)
		#If we reach here, everything is fine.
		# 'id' contains the shortened URL
		# 'longUrl' usually contains the original URL, but sometimes it is also the result of redirects or canonization
		return (True, data['id'], data['longUrl'])

def downloadFile(url, targetFilename):
	try:
		r = requests.get(url, headers={'user-agent': 'DideRobot (http://github.com/Didero/DideRobot)'})
		with open(targetFilename, 'wb') as f:
			for chunk in r.iter_content(4096):
				f.write(chunk)
		return (True, targetFilename)
	except Exception as e:
		return (False, e)



