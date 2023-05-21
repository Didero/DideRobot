import logging

import requests

from CustomExceptions import WebRequestException
import GlobalStore


def downloadFile(url, targetFilename, timeout=30.0):
	try:
		r = requests.get(url, headers={'user-agent': 'DideRobot (http://github.com/Didero/DideRobot)'}, timeout=timeout)
		with open(targetFilename, 'wb') as f:
			for chunk in r.iter_content(4096):
				f.write(chunk)
		return targetFilename
	except Exception as e:
		exceptionName = e.__class__.__name__
		logging.getLogger('DideRobot').error("{} Exception while downloading '{}' to '{}': {}".format(exceptionName, url, targetFilename, e))
		raise WebRequestException("Downloading the file failed, sorry ({}). Check the logs to see what exactly went wrong".format(exceptionName))

def uploadText(textToUpload, uploadDescription="Text Upload", expireInSeconds=600):
	"""
	Upload the provided text to Paste.ee, and returns the link to the upload
	:param textToUpload: The text to upload to Paste.ee
	:param uploadDescription: An optional description to add to the text upload
	:param expireInSeconds: In how many seconds the text upload should be removed from Paste.ee
	:return: The link to the uploaded text on Paste.ee
	:raise WebRequestException: Raised when something went wrong with uploading the text
	"""
	apiKey = GlobalStore.commandhandler.getApiKey('paste.ee')
	if not apiKey:
		raise WebRequestException("API key for Paste.ee is missing")
	# Send the actual request ('expire' is documented on https://paste.ee/wiki/API:Basics as being in minute, but it's in seconds)
	apiReply = None
	try:
		apiReply = requests.post("https://paste.ee/api", data={"key": apiKey, "description": uploadDescription, "paste": textToUpload, "expire": expireInSeconds, "format": "json"}, timeout=30)
		apiReplyData = apiReply.json()
	except requests.exceptions.Timeout:
		raise WebRequestException("Paste.ee took too long to respond")
	except ValueError as ve:
		raise WebRequestException("Paste.ee API reply couldn't be parsed as JSON, API reply: {}".format(apiReply.text if apiReply else '[missing]'))
	if apiReply.status_code != requests.codes.ok or 'error' in apiReplyData or 'paste' not in apiReplyData or 'link' not in apiReplyData['paste']:
		raise WebRequestException("Something went wrong while trying to upload the log. (HTTP code {}, API reply: {})".format(apiReply.status_code, apiReplyData))
	return apiReplyData['paste']['link']
