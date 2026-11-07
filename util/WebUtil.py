import logging
from enum import StrEnum

import requests

from CustomExceptions import WebRequestException
import GlobalStore


USER_AGENT = "DideRobot (https://github.com/Didero/DideRobot)"

class UPLOAD_TEXT_EXPIRATION(StrEnum):
	NEVER = "N",
	TEN_MINUTES = "10M"
	HOUR = "1H",
	DAY = "1D"
	WEEK = "1W"
	MONTH = "1M"
	HALF_YEAR = "6M"
	YEAR = "1Y"


def downloadFile(url, targetFilename, timeout=30.0):
	try:
		r = requests.get(url, headers={'user-agent': USER_AGENT}, timeout=timeout)
		with open(targetFilename, 'wb') as f:
			for chunk in r.iter_content(4096):
				f.write(chunk)
		return targetFilename
	except Exception as e:
		exceptionName = e.__class__.__name__
		logging.getLogger('DideRobot').error("{} Exception while downloading '{}' to '{}': {}".format(exceptionName, url, targetFilename, e))
		raise WebRequestException("Downloading the file failed, sorry ({}). Check the logs to see what exactly went wrong".format(exceptionName))

def uploadText(textToUpload, uploadDescription="Text Upload", expiration: UPLOAD_TEXT_EXPIRATION = UPLOAD_TEXT_EXPIRATION.TEN_MINUTES):
	"""
	Upload the provided text, and returns the link to the upload
	:param textToUpload: The text to upload
	:param uploadDescription: An optional description to add to the text upload
	:param expiration: One of the provided enum values that determines how long the uploaded text will stay available
	:return: The link to the uploaded text
	:raise WebRequestException: Raised when something went wrong with uploading the text
	"""
	apiKey = GlobalStore.commandhandler.getApiKey('pastebin')
	if not apiKey:
		raise WebRequestException("API key for Pastebin.com is missing")
	try:
		apiReply = requests.post("https://pastebin.com/api/api_post.php", data={"api_dev_key": apiKey, "api_option": "paste", "api_paste_code": textToUpload, "api_paste_name": uploadDescription,
																				"api_paste_private": 1, "api_paste_expire_date": expiration}, timeout=30)
	except requests.exceptions.Timeout:
		raise WebRequestException("Pastebin took too long to respond")
	if apiReply.status_code != requests.codes.ok or not apiReply.text.startswith("https"):
		raise WebRequestException("Something went wrong while trying to upload text. (HTTP code {}, API reply: {})".format(apiReply.status_code, apiReply.text))
	return apiReply.text
