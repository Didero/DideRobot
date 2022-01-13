import logging

import requests

from CustomExceptions import WebRequestException


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
