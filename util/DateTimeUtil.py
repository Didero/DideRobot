import re
from collections import OrderedDict

from CustomExceptions import CommandException



def parseIsoDuration(isoString, formatstring=""):
	"""Turn an ISO 8601 formatted duration string like P1DT45M3S into something readable like "1 day, 45 minutes, 3 seconds"""

	durations = {"year": 0, "month": 0, "week": 0, "day": 0, "hour": 0, "minute": 0, "second": 0}

	regex = 'P(?:(?P<year>\d+)Y)?(?:(?P<month>\d+)M)?(?:(?P<week>\d+)W)?(?:(?P<day>\d+)D)?T?(?:(?P<hour>\d+)H)?(?:(?P<minute>\d+)M)?(?:(?P<second>\d+)S)?'
	result = re.search(regex, isoString)
	if result is None:
		raise CommandException("No date results found in '{}'".format(isoString))
	else:
		for group, value in result.groupdict().iteritems():
			if value is not None:
				durations[group] = int(float(value))

	if formatstring != "":
		return formatstring.format(**durations)
	else:
		return durations

def durationSecondsToText(durationInSeconds, precision='s', numberOfParts=2):
	"""
	Convert a duration in seconds to a human-readable description, for instance 140 seconds into "2 minutes, 20 seconds"
	:param durationInSeconds: The number of seconds to convert to human-readable text
	:param precision: The lowest precision level to include. Should be 'm' to include minutes or 's' to include minutes and seconds, anything else will exclude minutes and seconds
	:param numberOfParts: The number of parts to include, or set to 0 to include all available ones. So for 3 hours, 20 minutes, and 14 seconds, even if the precision is 's', if numberOfParts is 2, the result will be "3 hours, 20 minutes"
	:return: The provided duration as human-readable text, to the provided level of precision, and with the provided number of parts
	"""
	timeParts = OrderedDict()
	timeParts['day'] = (durationInSeconds / 86400.0)
	timeParts['hour'] = (durationInSeconds / 3600.0) % 24
	if precision in ('m', 's'):
		timeParts['minute'] = (durationInSeconds / 60.0) % 60
		if precision == 's':
			timeParts['second'] = durationInSeconds % 60

	# Remove any part that is (or will be rounded to) zero
	for timePartName in timeParts.keys():
		if timeParts[timePartName] < 0.5:
			del timeParts[timePartName]

	# Limit the requested number of parts to the amount available
	if numberOfParts <= 0 or numberOfParts > len(timeParts):
		numberOfPartsLeft = len(timeParts)
	else:
		numberOfPartsLeft = numberOfParts

	durationTextParts = []
	for timePartName, timePartValue in timeParts.iteritems():
		if numberOfPartsLeft > 1:
			# There's another time part entry coming, so make sure rounding the value results in flooring it
			timePartValue = timePartValue - 0.5
		timePartValue = round(timePartValue)
		if timePartValue >= 1:
			durationTextParts.append("{:,.0f} {}{}".format(timePartValue, timePartName, 's' if timePartValue > 1 else ''))
		if numberOfPartsLeft == 1:
			break
		else:
			numberOfPartsLeft -= 1

	if durationTextParts:
		# We have a displayable result, return that
		return ", ".join(durationTextParts)
	else:
		# If duration is too short to list anything, return 0 for the lowest asked precision level
		if precision == 's':
			return "0 seconds"
		elif precision == 'm':
			return "0 minutes"
		return "0 hours"
