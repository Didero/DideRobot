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
	# print durations

	if formatstring != "":
		return formatstring.format(**durations)
	else:
		return durations

def durationSecondsToText(durationInSeconds, precision='s'):
	minutes, seconds = divmod(durationInSeconds, 60)
	hours, minutes = divmod(minutes, 60)
	days, hours = divmod(hours, 24)

	replytext = u""
	if days > 0:
		replytext += u"{:,.0f} day{}, ".format(days, u's' if days > 1 else u'')
	if hours > 0:
		replytext += u"{:,.0f} hour{}".format(hours, u's' if hours > 1 else u'')
	if minutes > 0 and precision in ['s', 'm']:
		if hours > 0:
			replytext += u", "
		replytext += u"{:,.0f} minute{}".format(minutes, u's' if minutes > 1 else u'')
	if seconds > 0 and precision == 's':
		if hours > 0 or minutes > 0:
			replytext += u", "
		replytext += u"{:,.0f} second{}".format(seconds, u's' if seconds > 1 else u'')
	return replytext
