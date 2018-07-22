import logging

import requests

import GlobalStore


logger = logging.getLogger('DideRobot')

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
