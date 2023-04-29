import logging, re

import Constants


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
	dictstring = ""
	for key, value in dictionary.items():
		dictstring += "{}: {}, ".format(key, forceToString(value))
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

def removeNewlines(string, replacementString=" "):
	"""
	Returns the provided string with newline characters removed
	:param string: The string to remove the newlines from
	:param replacementString: What to replace newlines with, a single space by default. Repeated newlines will only be replaced by a single replacementString ("\n\n\n" will be replaced by a single replacementString)
	:return: The provided string except with all newlines replaced with the replacementString (a single space by default)
	"""
	if '\n' not in string and '\r' not in string:
		return string
	return re.sub(r" *[\r\n]+ *", replacementString, string.rstrip('\r\n'))

def forceToString(varToForceToString):
	if isinstance(varToForceToString, str):
		return varToForceToString
	if isinstance(varToForceToString, dict):
		return dictToString(varToForceToString)
	if isinstance(varToForceToString, int):
		return '{}'.format(varToForceToString)
	if isinstance(varToForceToString, bytes):
		return varToForceToString.decode('utf-8', errors='replace')
	return str(varToForceToString)

def limitStringLength(stringToShorten, maxLength=Constants.MAX_MESSAGE_LENGTH, suffixes=None, shortenIndicator='[...]'):
	"""
	Shorten the provided string to the provided maximum length, optionally with the provided suffixes appended unshortened
	:param stringToShorten: The string to shorten if it plus the length of the suffixes is longer than the provided maximum length
	:param maxLength: The maximum length the returned string is allowed to be
	:param suffixes: Optional suffixes to add after the shortened string. These suffixes will be appended in order, as-is, and their length will be taken into account when shortening the string to shorten
	:param shortenIndicator: If the string has to be shortened, this indicator will be added to the end of the shortened string to show it's been shortened
	:return: The provided string optionally appended with the suffixes, with the stringToShorten shortened so that the whole result isn't longer than the maxLength
	"""
	suffixesLength = 0
	suffix = None
	if suffixes:
		if isinstance(suffixes, str):
			suffix = suffixes
		else:
			suffix = "".join(suffixes)
		suffixesLength = len(suffix)
	if len(stringToShorten) + suffixesLength <= maxLength:
		shortenedString = stringToShorten
	else:
		shortenedString = stringToShorten[:maxLength - suffixesLength - len(shortenIndicator)] + shortenIndicator
	if suffix:
		shortenedString += suffix
	return shortenedString
