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
	dictstring = u""
	for key, value in dictionary.iteritems():
		dictstring += u"{}: {}, ".format(key, forceToUnicode(value))
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

def removeNewlines(string):
	if '\n' not in string:
		return string
	return re.sub(r"( ?\n+ ?)+", " ", string)

def forceToUnicode(varToForceToUnicode):
	if isinstance(varToForceToUnicode, unicode):
		return varToForceToUnicode
	if isinstance(varToForceToUnicode, dict):
		return dictToString(varToForceToUnicode)
	if not isinstance(varToForceToUnicode, basestring):
		varToForceToUnicode = str(varToForceToUnicode)
	return unicode(varToForceToUnicode, encoding='utf-8', errors='replace')

def limitStringLength(stringToShorten, maxLength=Constants.MAX_MESSAGE_LENGTH, suffixes=None, shortenIndicator='[...]'):
	suffixesLength = 0
	if suffixes:
		for suffix in suffixes:
			suffixesLength += len(suffix)
	stringLength = len(stringToShorten)
	if stringLength + suffixesLength <= maxLength:
		shortenedString = stringToShorten
	else:
		shortenedString = stringToShorten[:maxLength - suffixesLength - len(shortenIndicator)] + shortenIndicator
	if suffixes:
		for suffix in suffixes:
			shortenedString += suffix
	return shortenedString
