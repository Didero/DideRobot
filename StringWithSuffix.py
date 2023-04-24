class StringWithSuffix(object):
	"""
	This object can be used if you need a string with a main part that's allowed to be shortened and a suffix that needs to be added at the end un-shortened
	"""
	def __init__(self, mainString, suffix=None):
		self.mainString = mainString
		self.suffix = suffix
		if isinstance(self.suffix, list) or isinstance(self.suffix, tuple):
			self.suffix = "".join(self.suffix)
