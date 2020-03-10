import base64, json, logging

import requests

import GlobalStore


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
	params = {'screen_name': username, 'count': min(200, maxTweetCount), 'trim_user': 'true', 'tweet_mode': 'extended',
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
			logger.error("[TwitterUtil] Error occurred while retrieving tweets for {}. Parameters:".format(username))
			logger.error(params)
			logger.error("[TwitterUtil] Twitter API reply:")
			logger.error(apireply)
			errorMessages = '; '.join(e['message'] for e in apireply['errors'])
			return (False, "Error(s) occurred: {}".format(errorMessages), tweets)
		#Sometimes the API does not return a list of tweets for some reason. Catch that
		if not isinstance(apireply, list):
			logger.error("[TwitterUtil] Unexpected reply from Twitter API. Expected tweet list, got {}:".format(type(apireply)))
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

def downloadTweet(username, tweetId=None):
	"""
	Download a single tweet for the provided username
	:param username: The username to retrieve the tweet of
	:param tweetId: The tweetId to retrieve. If this is None or not provided, the latest tweet will be retrieved
	:return: A success-tuple, with the first value a success boolean and the second either the error message or the downloaded tweet
	"""
	downloadedTweet = downloadTweets(username, maxTweetCount=1,
									 downloadNewerThanId=tweetId-1 if tweetId else None,
									 downloadOlderThanId=tweetId+1 if tweetId else None)
	#If something went wrong, pass on the error
	if not downloadedTweet[0]:
		return downloadedTweet
	#Otherwise, make the single-item tweet list just the tweet
	return (True, downloadedTweet[1][0])
