import base64, codecs, json, logging, os, random, re

import requests

import Constants, GlobalStore

logger = logging.getLogger('DideRobot')


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

def downloadFile(url, targetFilename, timeout=30.0):
	try:
		r = requests.get(url, headers={'user-agent': 'DideRobot (http://github.com/Didero/DideRobot)'}, timeout=timeout)
		with open(targetFilename, 'wb') as f:
			for chunk in r.iter_content(4096):
				f.write(chunk)
		return (True, targetFilename)
	except Exception as e:
		return (False, e)



