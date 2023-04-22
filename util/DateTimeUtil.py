import logging, re


logger = logging.getLogger('DideRobot')


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

	if formatstring != "":
		return formatstring.format(**durations)
	else:
		return durations

def durationSecondsToText(durationInSeconds, precision='s'):
	"""
	Convert a duration in seconds to a human-readable description, for instance 140 seconds into "2 minutes, 20 seconds"
	:param durationInSeconds: The number of seconds to convert to human-readable text
	:param precision: The lowest precision level to include. Should be 'm' to include minutes or 's' to include minutes and seconds, anything else will exclude minutes and seconds
	:return: The provided duration as human-readable text, to the provided level of precision, and with the provided number of parts
	"""
	minutes, seconds = divmod(durationInSeconds, 60)
	hours, minutes = divmod(minutes, 60)
	days, hours = divmod(hours, 24)

	durationTextParts = []
	if days > 0:
		durationTextParts.append("{:,.0f} day{}".format(days, 's' if days > 1 else ''))
	if hours > 0:
		durationTextParts.append("{:,.0f} hour{}".format(hours, 's' if hours > 1 else ''))
	if minutes > 0 and precision in ('s', 'm'):
		durationTextParts.append("{:,.0f} minute{}".format(minutes, 's' if minutes > 1 else ''))
	if seconds > 0 and precision == 's':
		durationTextParts.append("{:,.0f} second{}".format(seconds, 's' if seconds > 1 else ''))
	return ", ".join(durationTextParts)
