import glob, inspect, json, os, random, re

from CommandTemplate import CommandTemplate
from IrcMessage import IrcMessage
import SharedFunctions
import GlobalStore


fieldCommandPrefix = u"$"
argumentIsVariablePrefix = u"%"
postProcessorPrefix = u"&"


class Command(CommandTemplate):
	triggers = ['generate', 'gen']
	helptext = "Generate random stories or words. Call a specific generator with '{commandPrefix}generate [genName]'. Enter 'random' to let me pick, or choose from: "
	callInThread = True

	generators = {}
	filesLocation = os.path.join(GlobalStore.scriptfolder, "data", "generators")

	def onLoad(self):
		#First fill the generators dict with a few built-in generators
		self.generators = {self.generateName: 'name', self.generateVideogame: ('game', 'videogame'), self.generateWord: 'word', self.generateWord2: 'word2'}
		#Go through all available .grammar files and store their 'triggers'
		for grammarFilename in glob.iglob(os.path.join(self.filesLocation, '*.grammar')):
			with open(grammarFilename, 'r') as grammarFile:
				try:
					grammarJson = json.load(grammarFile)
				except ValueError as e:
					self.logError("[Generators] Error parsing grammar file '{}', invalid JSON: {}".format(grammarFilename, e.message))
				else:
					if '_triggers' not in grammarJson:
						self.logError("[Gen] Grammar file '{}' is missing a '_triggers' field so it can't be called".format(os.path.basename(grammarFilename)))
					elif isinstance(grammarJson['_triggers'], basestring):
						self.generators[grammarFilename] = grammarJson['_triggers'].lower()
					else:
						#Make sure all the triggers are lower-case, to make matching them easier when this module is called
						triggers = [trigger.lower() for trigger in grammarJson['_triggers']]
						#Store them so we know which grammar file to parse for which trigger(s)
						self.generators[grammarFilename] = tuple(triggers)
		#Add all the available triggers to the module's helptext
		self.helptext += ", ".join(self.getAvailableTriggers())
		self.logDebug("[Generators] Loaded {:,} generators".format(len(self.generators)))

		#Make the grammar parsing function available to other modules
		GlobalStore.commandhandler.addCommandFunction(__file__, 'parseGrammarDict', self.parseGrammarDict)

	def getHelp(self, message):
		#If there's no parameters provided, just show the generic module help text
		if message.messagePartsLength <= 1:
			return CommandTemplate.getHelp(self, message)
		#Check if the parameter matches one of our generator triggers
		requestedTrigger = message.messageParts[1].lower()
		for generator, triggers in self.generators.iteritems():
			#If the triggers is a single string check if it's identical, otherwise check if it's in the list
			if (isinstance(triggers, basestring) and requestedTrigger == triggers) or requestedTrigger in triggers:
				#Trigger match! If the match is a grammar file, retrieve its description
				if isinstance(generator, basestring):
					with open(os.path.join(self.filesLocation, generator), 'r') as grammarFile:
						grammarDict = json.load(grammarFile)
						if '_description' in grammarDict:
							return u"{}{} {}: {}".format(message.bot.commandPrefix, message.messageParts[0], requestedTrigger, grammarDict['_description'])
						else:
							return "The '{}' generator file didn't specify a help text, sorry!".format(requestedTrigger)
				#Match is one of the built-in functions
				else:
					#Show the function's docstring, if it has one, otherwise show an error
					helptext = "No helptext was set for this generator, sorry"
					if generator.__doc__:
						#Get the docstring, with the newlines and tabs removed
						helptext = inspect.cleandoc(generator.__doc__).replace('\n', ' ')
					return "{}{} {}: {}".format(message.bot.commandPrefix, message.messageParts[0], requestedTrigger, helptext)
		#No matching generator trigger was found
		return "I'm not familiar with the '{}' generator, though if you think it would make a good one, feel free to inform my owner(s), maybe they'll create it!".format(requestedTrigger)

	def execute(self, message):
		"""
		:type message: IrcMessage
		"""

		if message.messagePartsLength == 0 or message.messageParts[0].lower() == 'help':
			return message.reply(self.getHelp(message))

		if len(self.generators) == 0:
			return message.reply("That's weird, I don't seem to have any generators loaded, sorry. Try updating, reloading this module, or writing your own generator!", "say")

		wantedGeneratorName = message.messageParts[0].lower()
		wantedGenerator = None

		if wantedGeneratorName == 'random':
			wantedGenerator = random.choice(self.generators.keys())
		else:
			#Check to see if it's a registered generator
			for generator, triggerEntry in self.generators.iteritems():
				#Triggers are either a single string, or a list of strings
				# So if the trigger is a string AND is equal to the wanted generator, return that
				if isinstance(triggerEntry, basestring) and wantedGeneratorName == triggerEntry:
					wantedGenerator = generator
					break
				# Otherwise the trigger entry is a list(-alike), check if the wanted name is in that list
				elif isinstance(triggerEntry, (list,tuple)) and wantedGeneratorName in triggerEntry:
					wantedGenerator = generator
					break

		if wantedGenerator is None:
			#No suitable generator found, list the available ones
			message.reply("That is not a valid generator name. Use 'random' to let me pick, or choose from: {}".format(", ".join(self.getAvailableTriggers())))
		else:
			parameters = message.messageParts[1:]
			#The generator can either be a module function, or a string pointing to a grammar file. Check which it is
			if isinstance(wantedGenerator, basestring):
				path = os.path.join(self.filesLocation, wantedGenerator)
				#Grammar file! First check if it still exists
				if not os.path.isfile(path):
					message.reply("Huh, that generator did exist last time I looked, but now it's... gone, for some reason. Please don't rename my files without telling me", "say")
					return
				#It exists! Send it to the parser
				with open(path, "r") as grammarfile:
					grammarDict = json.load(grammarfile)
					message.reply(self.parseGrammarDict(grammarDict, parameters=parameters))
			else:
				#Function! Just call it, with the message so it can figure it out from there itself
				message.reply(wantedGenerator(parameters))

	def getAvailableTriggers(self):
		availableTriggers = []
		for generator, triggers in self.generators.iteritems():
			if isinstance(triggers, basestring):
				availableTriggers.append(triggers)
			else:
				availableTriggers.extend(triggers)
		return sorted(availableTriggers)

	@staticmethod
	def getRandomLine(filename, filelocation=None):
		if not filelocation:
			filelocation = Command.filesLocation
		elif not filelocation.startswith(GlobalStore.scriptfolder):
			filelocation = os.path.join(GlobalStore.scriptfolder, filelocation)
		filepath = os.path.abspath(os.path.join(filelocation, filename))
		#Check if the provided file is in our 'generator' folder
		if not filepath.startswith(Command.filesLocation):
			#Trying to get out of the 'generators' folder
			Command.logWarning("[Gen] User is trying to access files outside the 'generators' folder with filename '{}'".format(filename))
			return "[Access error]"
		line = SharedFunctions.getRandomLineFromFile(filepath)
		if not line:
			#The line function encountered an error, so it returned None
			# Since we expect a string, provide an empty one
			return "[File error]"
		return line

	@staticmethod
	def numberToText(number):
		baseNumberNames = ("zero", "one", "two", "three", "four", "five", "six", "seven", "eight", "nine", "ten", "eleven", "twelve", "thirteen", "fourteen", "fifteen", "sixteen", "seventeen", "eighteen", "nineteen")
		tensNames = ("twenty", "thirty", "forty", "fifty", "sixty", "seventy", "eighty", "ninety")
		numberTextParts = []

		#Handle negative numbers too
		if number < 0:
			number *= -1
			numberTextParts.append("minus")

		#Easiest case if the number is small enough to be in the base number list
		if number < 20:
			numberTextParts.append(baseNumberNames[number])
			return " ".join(numberTextParts)

		#We only handle up to a hundred trillion (trillion is 10 to the 12th, so hundred trillion is 10 to the 14th)
		if number >= 10 ** 14:
			return "[Number too large]"

		#Now we have to split up the number into groups of three (called 'periods' apparently), so we can parse each in turn
		numberPeriods = []
		while number > 0:
			numberPeriods.append(number % 1000)
			number /= 1000

		#Since the number was parsed from right to left, we need to reverse it, since in text numbers are written left to right ( twelve thousand fifty, not fifty twelve thousand)
		numberPeriods.reverse()

		#And now we can add the proper name to each of these groups
		periodNames = ("", "thousand", "million", "billion", "trillion")

		numberPeriodsCount = len(numberPeriods)
		for periodIndex, periodValue in enumerate(numberPeriods):
			#Ignore empty periods (So 12,000 doesn't turn into 'twelve thousand zero')
			if periodValue == 0:
				continue

			#If the number period is larger than 100, we need to mention the first number separately (204,000 is 'two hundred and four thousand')
			if periodValue >= 100:
				numberTextParts.append(baseNumberNames[periodValue / 100])
				numberTextParts.append('hundred')
				periodValue %= 100

			#If the number period is smaller than 20, it's in the base list
			# Skip zero though, otherwise 100 becomes 'one hundred zero'
			if periodValue < 20 and periodValue > 0:
				numberTextParts.append(baseNumberNames[periodValue])
			#Otherwise we need to split it up a bit more
			else:
				tensValue = periodValue / 10
				if tensValue > 0:
					numberTextParts.append(tensNames[tensValue - 2])  # -2 because lists are zero-indexed, and the list starts at twenty, not ten
				#Make sure it doesn't turn 20 into 'twenty zero'
				onesValue = periodValue % 10
				if onesValue > 0:
					numberTextParts.append(baseNumberNames[onesValue])

			#Since we're parsing left to right, and the period names are sorted small to large, we need to get the distance between the start
			# of the periods and the current period to get the name, minus one because the index starts at 0 but the names at 'thousand'
			periodName = periodNames[numberPeriodsCount - periodIndex - 1]
			if len(periodName) > 0:
				numberTextParts.append(periodName)

		#Done! Stick the parts together
		return " ".join(numberTextParts)

	@staticmethod
	def getBasicOrSpecialLetter(vowelOrConsonant, basicLetterChance):
		if isinstance(vowelOrConsonant, int):
			#Assume the provided argument is a chance percentage of vowel
			if random.randint(1, 100) <= vowelOrConsonant:
				vowelOrConsonant = "vowel"
			else:
				vowelOrConsonant = "consonant"

		if vowelOrConsonant == "vowel":
			basicLetters = ('a', 'e', 'i', 'o', 'u')
			specialLetters = ('y',)
		else:
			basicLetters = ('b', 'c', 'd', 'f', 'g', 'h', 'k', 'l', 'm', 'n', 'p', 'r', 's', 't')
			specialLetters = ('j', 'q', 'v', 'w', 'x', 'z')

		if random.randint(1, 100) <= basicLetterChance:
			return random.choice(basicLetters)
		else:
			return random.choice(specialLetters)


	@staticmethod
	def isGenderParameter(arg):
		return arg.lower() in ("f", "female", "woman", "girl", "m", "male", "man", "boy", "misc", "other", "queer")

	@staticmethod
	def getGenderWords(genderString, allowUnspecified=True):
		if genderString is not None:
			genderString = genderString.lower()

		if genderString in ("f", "female", "woman", "girl"):
			gender = "f"
		elif genderString in ("m", "male", "man", "boy"):
			gender = "m"
		elif allowUnspecified and genderString in ("misc", "other", "queer"):
			gender = "misc"
		else:
			# No gender specified, pick one on our own
			roll = random.randint(1, 100)
			if allowUnspecified and roll <= 45 or roll <= 50:
				gender = "f"
			elif allowUnspecified and roll <= 90 or roll <= 100:
				gender = "m"
			else:
				gender = "misc"

		#Set some verb variables, so using both 'they' and 'he/his' in sentences is easier
		#For instance in grammar files you can do '<_var|they> <_var|isAre>' or '<_var|they> make<_var|verbS>'
		#First set them ot the 'he' and 'she' values, since then we only have to change them in one case
		genderDict = {"isAre": "is", "wasWere": "was", "verbS": "s", "verbEs": "es"}
		#Then set the pronouns
		if gender == "f":
			genderDict.update({"gender": "f", "genderNoun": "Woman", "genderNounYoung": "Girl", "pronoun": "she", "possessivePronoun": "her", "personalPronoun": "her",
							   "they": "she", "their": "her", "them": "her"})
		elif gender == "m":
			genderDict.update({"gender": "m", "genderNoun": "Man", "genderNounYoung": "Boy", "pronoun": "he", "possessivePronoun": "his", "personalPronoun": "him",
							   "they": "he", "their": "his", "them": "him"})
		else:
			#Since the pronoun is 'they', verbs need other forms, so set them too here
			genderDict.update({"gender": "misc", "genderNoun": "Person", "genderNounYoung": "Kid", "pronoun": "they", "possessivePronoun": "their", "personalPronoun": "them",
							   "they": "they", "their": "their", "them": "them",
							   "isAre": "are", "wasWere": "were", "verbS": "", "verbEs": ""})
		return genderDict

	def parseGrammarDict(self, grammarDict, parameters=None, variableDict=None):
		if variableDict is None:
			variableDict = {}

		#First check if the starting field exists
		if u'start' in grammarDict:
			startString = u"<start>"
		elif u'_start' in grammarDict:
			#Force the old '_start' into 'start' to prevent 'unknown command' errors
			grammarDict[u'start'] = grammarDict[u'_start']
			del grammarDict[u'_start']
			startString = u"<start>"
		else:
			self.logWarning(u"[Gen] Missing 'start' or '_start' field in grammar '{}'".format(grammarDict.get(u'_name', u'[noname]')))
			return u"Error: No 'start' field found!"

		#Parse any options specified
		if u'_options' in grammarDict:
			# Parse arguments
			if u'parseGender' in grammarDict[u'_options']:
				gender = None
				if parameters:
					for param in parameters:
						if self.isGenderParameter(param):
							gender = param
				variableDict.update(self.getGenderWords(gender))  #If no gender was provided, 'getGenderWords' will pick a random one
			if u'generateName' in grammarDict[u'_options']:
				#If a gender was provided or requested, use that to generate a name, otherwise make the function pick a gender
				variableDict[u'name'] = self.generateName(variableDict.get(u'gender', None))
				#Make first and last names separately accessible
				nameparts = variableDict[u'name'].split(' ')
				variableDict[u'firstname'] = nameparts[0]
				variableDict[u'lastname'] = nameparts[-1] #Use -1 because names

		#Since chance dictionaries ('{"20": "20% of this text", "80": "60% (80-20) of this text", "100: "20% chance"}') have to have string keys to be valid JSON,
		# the keys need to be converted to integers for correct sorting (so "100" doesn't come before "20"). We'll do that as we encounter them, so we need to
		# keep track of which dictionaries we've converted and which we haven't yet. We do that by storing references to them in a list, in the variableDict
		variableDict['_convertedChanceDicts'] = []

		#Start the parsing!
		return self.parseGrammarString(startString, grammarDict, parameters, variableDict)

	def parseGrammarString(self, grammarString, grammar, parameters=None, variableDict=None):
		if variableDict is None:
			variableDict = {}

		#Parse the parameters as a string (if there are any) in such a way that users don't have access to special fields
		# This to prevent abuse like infinite loops or creating heavy load
		#Store that string inside the variableDict under the key '_params', makes lookup and checking easier
		if parameters:
			variableDict[u'_params'] = " ".join(parameters).decode("utf-8", errors="replace")
			variableDict[u'_params'] = variableDict[u'_params'].replace(u"/", u"//").replace(u"<", u"/<")

		#Make sure the input string is Unicode, since that's what we expect
		if not isinstance(grammarString, unicode):
			grammarString = grammarString.decode("utf-8", errors="replace")

		outputString = grammarString
		loopcount = 0
		startIndex = 0
		while loopcount < 150:
			loopcount += 1

			nestedBracketLevel = 0
			characterIsEscaped = False
			grammarParts = [u""]
			#Go through the string to find the first bracketed section
			for index in xrange(startIndex, len(outputString)):
				character = outputString[index]

				#Handle character escaping first, since that overrides everything else
				if characterIsEscaped or character == u"/":
					characterIsEscaped = not characterIsEscaped  #Only escape one character, so flip it back. Or it's the escape character, so flip to True
					if nestedBracketLevel > 0:
						grammarParts[-1] += character
					continue

				if nestedBracketLevel == 0 and character == u"<":
					#Store this position for the next loop, so we don't needlessly check bracket-less text multiple times
					startIndex = index
					#And go up a level
					nestedBracketLevel = 1
				elif nestedBracketLevel == 1 and character == u"|":
					#Start a new gramamr part
					grammarParts.append(u"")
				elif nestedBracketLevel == 1 and character == u">":
					#We found the end of the grammar block. Have it parsed
					success, parsedGrammarBlock = self.parseGrammarBlock(grammarParts, grammar, variableDict)
					if not success:
						#If something went wrong, it returned an error message. Stop parsing and report that error
						return u"Error: " + parsedGrammarBlock
					#Everything went fine, replace the grammar block with the output
					outputString = outputString[:startIndex] + parsedGrammarBlock + outputString[index + 1:]
					#Done with this parsing loop, start a new one! (break out of the for-loop to start a new while-loop iteration)
					break
				#Don't append characters if we're not inside a grammar block
				elif nestedBracketLevel > 0:
					#We always want to append the character now
					grammarParts[-1] += character
					#Keep track of how many levels deep we are
					if character == u"<":
						nestedBracketLevel += 1
					elif character == u">":
						nestedBracketLevel -= 1
			else:
				#We reached the end of the output string. If we're not at top level, the gramamr block isn't closed
				if nestedBracketLevel > 0:
					self.logWarning(u"[Gen] Grammar '{}' is missing a closing bracket in line '{}'".format(grammar.get(u"_name", u"[noname]"), outputString))
					return u"Error: Missing closing bracket"
				#Otherwise, we're done! Break out of the while-loop
				break
		else:
			#We reached the loop limit, so there's probably an infinite loop. Report that
			self.logWarning(u"[Gen] Grammar '{}' has an infinite loop in line '{}'".format(grammar.get(u"_name", u"[noname]"), outputString))
			return u"Error: Loop limit reached, there's probably an infinite loop in the grammar file"

		#Unescape escaped characters so they display properly
		outputString = re.sub(ur"/(.)", ur"\1", outputString)
		#Done!
		return outputString

	def parseGrammarBlock(self, grammarBlockParts, grammar, variableDict=None):
		fieldKey = grammarBlockParts.pop(0)
		replacement = u""

		#If the last field starts with '&', it specifies special options, like making text bold.
		# Multiple options are separated by commas. Retrieve those options
		extraOptions = []
		if grammarBlockParts and grammarBlockParts[-1].startswith(postProcessorPrefix):
			extraOptions = grammarBlockParts.pop()[1:].split(u',')

		# Grammar commands start with an underscore, check if this block is a grammar command
		if fieldKey.startswith(fieldCommandPrefix):
			#Have the GrammarCommands class try and execute the provided command name
			isSuccess, replacement = GrammarCommands.runCommand(fieldKey[len(fieldCommandPrefix):], grammarBlockParts, grammar, variableDict)
			# If something went wrong, stop now. The replacement string should be an error message, pass that along too
			if not isSuccess:
				return (False, replacement)
			#Otherwise everything went fine, and the replacement string is set properly
		# No command, so check if it's a valid key
		elif fieldKey not in grammar:
			return (False, u"Field '{}' not found in grammar file!".format(fieldKey))
		# All's well, fill it in
		else:
			if isinstance(grammar[fieldKey], list):
				# It's a list! Just pick a random entry
				replacement = random.choice(grammar[fieldKey])
			elif isinstance(grammar[fieldKey], dict):
				# Dictionary! The keys are chance percentages, the values are the replacement strings

				#JSON requires keys to be strings, but we want them to be numbers. Check to see if we need to convert them
				if grammar[fieldKey] not in variableDict['_convertedChanceDicts']:
					for chanceDictKey in grammar[fieldKey].keys():
						value = grammar[fieldKey][chanceDictKey]
						#Remove the string key, and add in the integer key if the conversion succeeded
						del grammar[fieldKey][chanceDictKey]
						try:
							chanceDictKeyAsInt = int(chanceDictKey, 10)
							#Check if the number is in the correct range of 0 - 100
							if chanceDictKeyAsInt < 0 or chanceDictKeyAsInt > 100:
								self.logWarning(u"[Gen] Grammar '{}' chance dictionary field '{}' contains invalid key '{}'. Chance dictionary keys should be between 0 and 100. Ignoring it".format(
									grammar.get('_name', "[unknown]"), fieldKey, chanceDictKey))
							else:
								grammar[fieldKey][chanceDictKeyAsInt] = value
						except ValueError as e:
							#Show a warning about a non-int key in a chance dict. Not an error, since we can just ignore it and move on
							self.logWarning(u"[Gen] Grammar '{}' chance dictionary field '{}' contains non-numeric key '{}', which isn't supported. Ignoring it".format(grammar.get('_name', "[unknown]"), fieldKey, chanceDictKey))
					#Store that we converted the chance dict
					variableDict['_convertedChanceDicts'].append(grammar[fieldKey])

				#Now find the lowest chance dict key that's larger than our roll
				# So in a dict '{20: "first", 100: "second"}', a roll of 18 would return 'first', and a roll of 73 would return 'second'
				roll = random.randint(1, 100)
				for chance in sorted(grammar[fieldKey].keys()):
					if roll <= chance:
						replacement = grammar[fieldKey][chance]
						break
			elif isinstance(grammar[fieldKey], basestring):
				# If it's a string (either the string class or the unicode class), just dump it in
				replacement = grammar[fieldKey]
			else:
				return (False, u"No handling defined for type '{}' found in field '{}'".format(type(grammar[fieldKey]), fieldKey))

		# Process the possible extra options that can be provided, in the specified order
		for option in extraOptions:
			if option == u'lowercase':
				replacement = replacement.lower()
			elif option == u'uppercase':
				replacement = replacement.upper()
			elif option == u'camelcase' or option == u'titlecase':
				replacement = replacement.title()
			elif option == u'firstletteruppercase':
				if len(replacement) > 1:
					replacement = replacement[0].upper() + replacement[1:]
				else:
					replacement = replacement.upper()
			elif option == u'bold':
				replacement = SharedFunctions.makeTextBold(replacement)
			elif option.startswith(u'storeas'):
				#Store the replacement under the provided variable name
				# (format 'storeas:[varname]')
				if u':' not in option:
					return (False, u"Invalid 'storeas' argument for field '<{}|{}|&{}>', should be 'storeas:[varname]'".format(fieldKey, u"|".join(grammarBlockParts), u",".join(extraOptions)))
				varname = option.split(u':', 1)[1]
				variableDict[varname] = replacement
			elif option == u'numbertotext':
				#Convert an actual number to text, like '4' to 'four'
				try:
					replacement = Command.numberToText(int(replacement))
				except ValueError:
					return (False, u"Asked to convert '{}' to a number with 'numberasword' option, but it isn't one")
			elif option == u"hide":
				#Completely hides the replacement text. Useful in combination with 'storeas', if you don't want to store but not display the output
				replacement = u""

		# Sometimes decorations need to be passed on (like if we replace '<sentence|titlecase>' with '<word1> <word2>', 'word1' won't be titlecase)
		if len(extraOptions) > 0 and not fieldKey.startswith(u'_') and replacement.startswith(u'<'):
			closingBracketIndex = replacement.find(u'>')
			if closingBracketIndex > -1:
				# Only pass on the case changes
				optionsToPassOn = []
				for option in extraOptions:
					if option.endswith(u'case'):
						optionsToPassOn.append(option)
				orgReplacement = replacement
				replacement = replacement[:closingBracketIndex] + u"|&" + u",".join(optionsToPassOn) + replacement[closingBracketIndex:]
				self.logDebug(u"[Gen] Passed on case option, replaced '{}' with '{}'".format(orgReplacement, replacement))

		#The parser expects unicode, so make sure our replacement is unicode
		if not isinstance(replacement, unicode):
			replacement = replacement.decode("utf-8", errors="replace")

		#Done!
		return (True, replacement)

	def generateName(self, parameters=None):
		"""
		Generates a random first and last name. You can provide a parameter to specify the gender
		"""
		genderDict = None
		namecount = 1
		#Determine if a specific gender name and/or number of names was requested
		if parameters:
			#Make sure parameters is a list, so we don't iterate over each letter in a string accidentally
			if not isinstance(parameters, (tuple, list)):
				parameters = [parameters]
			#Go through all parameters to see if they're either a gender specifier or a name count number
			for param in parameters:
				if self.isGenderParameter(param):
					genderDict = self.getGenderWords(param, False)
				else:
					try:
						namecount = int(param)
						# Limit the number of names
						namecount = max(namecount, 1)
						namecount = min(namecount, 10)
					except ValueError:
						pass

		#If no gender parameter was passed, pick a random one
		if not genderDict:
			genderDict = self.getGenderWords(None, False)

		names = []
		for i in xrange(namecount):
			# First get a last name
			lastName = self.getRandomLine("LastNames.txt")
			#Get the right name for the provided gender
			if genderDict['gender'] == 'f':
				firstName = self.getRandomLine("FirstNamesFemale.txt")
			else:
				firstName = self.getRandomLine("FirstNamesMale.txt")

			#with a chance add a middle letter:
			if (parameters and "addletter" in parameters) or random.randint(1, 100) <= 15:
				names.append(u"{} {}. {}".format(firstName, self.getBasicOrSpecialLetter(50, 75).upper(), lastName))
			else:
				names.append(u"{} {}".format(firstName, lastName))

		return SharedFunctions.joinWithSeparator(names)


	def generateWord(self, parameters=None):
		"""
		Generates a word by putting letters together in semi-random order. Provide a number to generate that many words
		"""
		# Initial set-up
		vowels = ['a', 'e', 'i', 'o', 'u']
		specialVowels = ['y']

		consonants = ['b', 'c', 'd', 'f', 'g', 'h', 'k', 'l', 'm', 'n', 'p', 'r', 's', 't']
		specialConsonants = ['j', 'q', 'v', 'w', 'x', 'z']

		newLetterFraction = 5
		vowelChance = 50  #percent

		#Determine how many words we're going to have to generate
		repeats = 1
		if parameters and len(parameters) > 0:
			repeats = SharedFunctions.parseInt(parameters[0], 1, 1, 25)

		words = []
		for i in xrange(0, repeats):
			word = u""
			currentVowelChance = vowelChance
			currentNewLetterFraction = newLetterFraction
			consonantCount = 0
			while random.randint(0, currentNewLetterFraction) <= 6:
				if random.randint(1, 100) <= currentVowelChance:
					consonantCount = 0
					#vowel. Check if we're going to add a special or normal vowel
					if random.randint(1, 100) <= 10:
						word += random.choice(specialVowels)
						currentVowelChance -= 30
					else:
						word += random.choice(vowels)
						currentVowelChance -= 20
				else:
					consonantCount += 1
					#consonant, same deal
					if random.randint(1, 100) <= 25:
						word += random.choice(specialConsonants)
						currentVowelChance += 30
					else:
						word += random.choice(consonants)
						currentVowelChance += 20
					if consonantCount > 3:
						currentVowelChance = 100
				currentNewLetterFraction += 1

			#Enough letters added. Finish up
			word = word[0].upper() + word[1:]
			words.append(word)

		#Enough words generated, let's return the result
		return u", ".join(words)

	def generateWord2(self, parameters=None):
		"""
		Another method to generate a word. Tries to generate pronounceable syllables and puts them together. Provide a number to generate that many words
		"""

		##Initial set-up
		#A syllable consists of an optional onset, a nucleus, and an optional coda
		#Sources:
		# http://en.wikipedia.org/wiki/English_phonology#Phonotactics
		# http://en.wiktionary.org/wiki/Appendix:English_pronunciation
		onsets = ["ch", "pl", "bl", "cl", "gl", "pr", "br", "tr", "dr", "cr", "gr", "tw", "dw", "qu", "pu",
				  "fl", "sl", "fr", "thr", "shr", "wh", "sw",
				  "sp", "st", "sk", "sm", "sn", "sph", "spl", "spr", "str", "scr", "squ", "sm"]  #Plus the normal consonants
		nuclei = ["ai", "ay", "ea", "ee", "y", "oa", "au", "oi", "oo", "ou"]  #Plus the normal vowels
		codas = ["ch", "lp", "lb", "lt", "ld", "lch", "lg", "lk", "rp", "rb", "rt", "rd", "rch", "rk", "lf", "lth",
				 "lsh", "rf", "rth", "rs", "rsh", "lm", "ln", "rm", "rn", "rl", "mp", "nt", "nd", "nch", "nk", "mph",
				 "mth", "nth", "ngth", "ft", "sp", "st", "sk", "fth", "pt", "ct", "kt", "pth", "ghth", "tz", "dth",
				 "ks", "lpt", "lfth", "ltz", "lst", "lct", "lx","rmth", "rpt", "rtz", "rst", "rct","mpt", "dth",
				 "nct", "nx", "xth", "xt"]  #Plus normal consonants

		simpleLetterChance = 65  #percent, whether a single letter is chosen instead of an onset/nucleus/coda
		basicLetterChance = 75  #percent, whether a simple consonant/vowel is chosen over  a more rare one

		#Prevent unnecessary and ugly code repetition

		#Start the word
		repeats = 1
		if parameters and len(parameters) > 0:
			repeats = SharedFunctions.parseInt(parameters[0], 1, 1, 25)

		words = []
		for i in xrange(0, repeats):
			syllableCount = 2
			if random.randint(1, 100) <= 50:
				syllableCount -= 1
			if random.randint(1, 100) <= 35:
				syllableCount += 1

			word = u""
			for j in range(0, syllableCount):
				#In most cases, add an onset
				if random.randint(1, 100) <= 75:
					if random.randint(1, 100) <= simpleLetterChance:
						word += self.getBasicOrSpecialLetter("consonant", basicLetterChance)
					else:
						word += random.choice(onsets)

				#Nucleus!
				if random.randint(1, 100) <= simpleLetterChance:
					word += self.getBasicOrSpecialLetter("vowel", basicLetterChance)
				else:
					word += random.choice(nuclei)

				#Add a coda in most cases (Always add it if this is the last syllable of the word and it'd be too short otherwise)
				if (j == syllableCount - 1 and len(word) < 3) or random.randint(1, 100) <= 75:
					if random.randint(1, 100) <= simpleLetterChance:
						word += self.getBasicOrSpecialLetter("consonant", basicLetterChance)
					else:
						word += random.choice(codas)

			word = word[0].upper() + word[1:]
			words.append(word)

		return u", ".join(words)

	def generateVideogame(self, parameters=None):
		"""
		Generates random video game names. Optionally provide a number to make it generate that many game names,
		and replacement words that will get inserted into the generated name
		"""
		repeats = 1
		replacementText = None
		if parameters and len(parameters) > 0:
			#Accepted parameters are either a number, which would be the game name repeats, or a word, which will replace a generated word later
			try:
				repeats = int(parameters[0])
				replacementWords = parameters[1:]
			except ValueError:
				replacementWords = parameters

			#Make the replacement text titlecase (But not with .title() because that also capitalizes "'s" at the end of words)
			replacementText = ""
			for word in replacementWords:
				if len(word) > 1:
					replacementText += word[0].upper() + word[1:] + " "
				else:
					replacementText += word.upper() + " "
			replacementText = replacementText.rstrip()
			#Game names are unicode, best make this unicode too
			replacementText = replacementText.decode("utf-8", errors="replace")

			#Clamp the repeats to a max of 5
			repeats = min(repeats, 5)
			repeats = max(repeats, 1)

		#Both data and functioning completely stolen from http://videogamena.me/
		gamenames = []
		for r in xrange(0, repeats):
			subjectsPicked = []
			gamenameparts = []
			for partFilename in ("FirstPart", "SecondPart", "ThirdPart"):
				repeatedSubjectFound = True
				while repeatedSubjectFound:
					repeatedSubjectFound = False
					word = SharedFunctions.getRandomLineFromFile(os.path.join(self.filesLocation, "VideogameName{}.txt".format(partFilename)))
					#Some words are followed by a subject list, to prevent repeats
					subjects = []
					if '^' in word:
						parts = word.split('^')
						word = parts[0]
						subjects = parts[1].split('|')
					#Check if the word has appeared in the name already, or is too similar in subject to an already picked word
					if word in gamenameparts or word in subjectsPicked:
						repeatedSubjectFound = True
						continue
					elif len(subjects) > 0:
						for subject in subjects:
							if subject in subjectsPicked:
								repeatedSubjectFound = True
								continue
						#If it's not a repeated subject, add the current subjects to the list
						subjectsPicked.extend(subjects)
					gamenameparts.append(word)

			gamename = u" ".join(gamenameparts)
			if replacementText and len(replacementText) > 0:
				#Replace a word with the provided replacement text
				#  (but not words like 'of' and 'the', so only words that start with upper-case)
				if replacementText.endswith("'s"):
					#Possessive, try to match it with an existing possessive
					words = re.findall(r"\w+'s?(?= )", gamename)
					if len(words) == 0:
						#No possessive words in the gamename, pick other words (but not the last one)
						words = re.findall(r"[A-Z]\w+(?= )", gamename)
				else:
					words = re.findall(r"[A-Z]\w+", gamename)
				gamename = gamename.replace(random.choice(words), replacementText, 1)
			gamenames.append(gamename)

		return SharedFunctions.joinWithSeparator(gamenames)


#Store some data about grammar commands, so we can do some initial argument verification. Keeps the actual commands nice and short
grammarCommandOptions = {}

def validateArguments(argumentCount=0, numericArgumentIndexes=None):
	"""
	A decorator to store options on how grammar commands should be executed and how the input should be checked
	:param argumentCount: The minimum number of arguments this grammar command needs. An error is thrown if the command is called with fewer arguments
	:param numericArgumentIndexes: A tuple or list of the argument indexes that should be turned from strings into numbers (indexes start at 0).
			If an index specified here is larger than 'count', it's considered an optional arg
	"""
	def wrapperFunction(functionToWrap):
		grammarCommandOptions[functionToWrap] = (argumentCount, numericArgumentIndexes)
		return functionToWrap
	return wrapperFunction


class GrammarCommands(object):
	"""
	A class to hold all the commands that can be called from grammar files
	Each function should have the same name as it has in the grammar file, including case
	If that name is a reserved Python keyword, append 'Command' to it
	Each function should have a docstring. The first line of the docstring should be a usage string. Subsequent lines should be a description of what the command does
	The parameters a function accepts should always be the same:
	-argumentList, which is a list of the arguments provided to the function
	-grammarDict, the entire grammar dictionary, in case a field from that is needed. Should not be changed
	-variableDict, the dictionary with variables set during grammar parsing. Functions are allowed to change this
	Each function should return a tuple. The first value should be a boolean, set to True if executing the command succeeded, or to False if it failed
	The second value should be a unicode string. If command execution succeeded, it should be the string that should be put in the grammar output string
	 instead of this command block. If execution failed, it should be the reason why it failed
	"""

	@staticmethod
	def runCommand(commandName, argumentList, grammarDict, variableDict):
		"""
		This method calls a grammar command method if it exists, and optionally does some sanity checks beforehand, depending on their decorator
		:param commandName: The name of the grammar command that should be executed (without the preceding underscore from the grammar file)
		:param argumentList: A list of arguments to pass along to the command. Is optionally checked for length before the command is called, depending on decorator settings
		:param grammarDict: The grammar dictionary that's currently being parsed. Is only passed on to the command
		:param variableDict: The variable dictionary that's being used during the parsing. If the command enabled first-argument-variable checking, this dictionary is checked
			to contain a variable named the same as the first argument
		:return: A tuple, with the first entry a boolean indicating success, and the second entry a string. If something went wrong, either with the preliminary checks
			or during the grammar command execution, this is False, and the string is the error message. If everything went right, the boolean is True and the string is
			the outcome of the grammar command, ready to be substituted into the grammar string in place of the command
		"""
		command = getattr(GrammarCommands, 'command_' + commandName.lower(), None)
		#First check if the requested command exists
		if not command:
			return (False, u"Unknown command '{}' called".format(commandName))
		#Get the settings for the method
		requiredArgumentCount, numericArgIndexes = grammarCommandOptions.get(command, (0, None))
		#Check if enough arguments were passed, if not, return an error
		if len(argumentList) < requiredArgumentCount:
			return (False, GrammarCommands._constructNotEnoughParametersErrorMessage(command, requiredArgumentCount, len(argumentList)))
		#Check each arg for certain settings
		for argIndex in xrange(len(argumentList)):
			#Check if the arg start with the variables prefix, in which case it should be replaced by that variable's value
			if argumentList[argIndex].startswith(argumentIsVariablePrefix):
				varname = argumentList[argIndex][len(argumentIsVariablePrefix):]
				argumentSuffix = u''
				#Commands like $switch have arguments with a colon in them, to split the case and the value. Check for that too
				if u':' in varname:
					varname, argumentSuffix = varname.split(u':', 1)
					argumentSuffix = u':' + argumentSuffix
				if varname not in variableDict:
					return (False, u"Field '{}' references variable name '{}', but that isn't set".format(commandName, varname))
				argumentList[argIndex] = variableDict[varname] + argumentSuffix
			#If the arg is in the 'numericalArg' list, (try to) convert it to a number
			if numericArgIndexes and argIndex in numericArgIndexes:
				try:
					argumentList[argIndex] = int(argumentList[argIndex], 10)
				except ValueError as e:
					return (False, u"Argument '{}' (index {}) of command '{}' should be numeric, but couldn't get properly converted to a number".format(argumentList[argIndex], argIndex, commandName))
		#All checks passed, call the command
		try:
			return command(argumentList, grammarDict, variableDict)
		except Exception as e:
			return (False, u"Something went wrong when executing the '{}' command ({})".format(commandName, e.message))

	#Shared internal methods
	@staticmethod
	def _constructNotEnoughParametersErrorMessage(command, requiredNumber, foundNumber):
		#Each method should have a usage string as the first line of its docstring
		usageString = inspect.cleandoc(command.__doc__).splitlines()[0]
		#Display that no parameters were provided in a grammatically correct and sensible way
		if foundNumber == 0:
			foundNumberString = u"none were provided"
		else:
			foundNumberString = u"only found {}".format(foundNumber)
		#Return the results, formatted nicely
		return u"'{}' call needs at least {} parameter{}, but {}. Command usage: {}".format(command.__name__, requiredNumber, u's' if requiredNumber > 1 else u'',
																						   foundNumberString, usageString)


	#Saving and loading variables
	@staticmethod
	@validateArguments(argumentCount=2)
	def command_setvar(argumentList, grammarDict, variableDict):
		"""
		<$setvar|varname|value>
		Stores a value under the provided name, for future use
		"""
		variableDict[argumentList[0]] = argumentList[1]
		return (True, u"")

	@staticmethod
	@validateArguments(argumentCount=2)
	def command_setvarrandom(argumentList, grammarDict, variableDict):
		"""
		<$setvarrandom|varname|value1|value2|value3>
		Picks one of the provided values at random, and stores it under the provided name, for future use
		"""
		variableDict[argumentList[0]] = random.choice(argumentList[1:])
		return (True, u"")

	@staticmethod
	@validateArguments(argumentCount=3)
	def command_hasvar(argumentList, grammarDict, variableDict):
		"""
		<$hasvar|varname|stringIfVarnameExists|stringIfVarnameDoesntExist>
		Checks if the variable with the provided name exists. Returns the first string if it does, and the second one if it doesn't
		"""
		if argumentList[0] in variableDict:
			return (True, argumentList[1])
		else:
			return (True, argumentList[2])

	@staticmethod
	@validateArguments(argumentCount=1)
	def command_var(argumentList, grammarDict, variableDict):
		"""
		<$var|varname|[valueIfVarNotSet]>
		Returns the value stored under the provided variable name. The second argument is optional, and if set will be returned if the variable isn't stored
		"""
		# Check if the named variable was stored
		if argumentList[0] in variableDict:
			return (True, variableDict[argumentList[0]])
		else:
			# If a second parameter was passed, use it as a fallback value
			if len(argumentList) > 1:
				return (True, argumentList[1])
			# Otherwise, throw an error
			else:
				return (False, u"Referenced undefined variable '{}' in 'var' call".format(argumentList[0]))

	@staticmethod
	@validateArguments(argumentCount=1)
	def command_remvar(argumentList, grammarDict, variableDict):
		"""
		<$remvar|varname>
		Removes the value stored under this variable name. Does nothing if the variable doesn't exist
		"""
		if argumentList[0] in variableDict:
			del variableDict[argumentList[0]]
		return (True, u"")

	@staticmethod
	@validateArguments(argumentCount=1)
	def command_removevar(argumentList, grammarDict, variableDict):
		"""
		<$removevar|varname>
		Alias for 'remvar', removes the stored variable
		"""
		return GrammarCommands.command_remvar(argumentList, grammarDict, variableDict)


	#Variable checking
	@staticmethod
	@validateArguments(argumentCount=4)
	def command_ifequals(argumentList, grammarDict, variableDict):
		"""
		<$ifequals|firstStringToMatch|secondStringToMatch|resultIfIdentical|resultIfNotIdentical>
		Checks if the first string is identical to the second string. Returns the 'IfIdentical' result if they're identical, and the 'IfNotIdentical' result otherwise
		"""
		#Check if the variable exists and is set to the requested value
		if argumentList[0] == argumentList[1]:
			return (True, argumentList[2])
		else:
			return (True, argumentList[3])

	@staticmethod
	@validateArguments(argumentCount=4)
	def command_if(argumentList, grammarDict, variableDict):
		"""
		<$if|varname|stringToMatch|stringIfIdentical|stringIfNotIdentical>
		Alias for 'ifequals' left in for backwards compatibility. Functionality could change in the future, use 'ifequals' instead
		"""
		return GrammarCommands.command_ifequals(argumentList, grammarDict, variableDict)

	@staticmethod
	@validateArguments(argumentCount=4)
	def command_ifcontains(argumentList, grammarDict, variableDict):
		"""
		<$ifcontains|string|substringToCheckFor|resultIfSubstringInString|resultIfSubstringNotInString>
		Checks if the provided string contains the provided substring. Returns the 'InString' result if it is, and the 'NotInString' result otherwise
		"""
		#Check if the provided variable exists and if it contains the provided string
		if argumentList[1] in argumentList[0]:
			return (True, argumentList[2])
		else:
			return (True, argumentList[3])

	@staticmethod
	@validateArguments(argumentCount=4)
	def command_ifmatch(argumentList, grammarDict, variableDict):
		"""
		<$ifmatch|string|regexToMatch|resultIfMatch|resultIfNoMatch>
		Checks if the provided regular expression matches the provided string
		"""
		#Make sure we un-escape the regex, so it can use characters like < and | without messing up our parsing
		regex = re.compile(re.sub(r"/(.)", r"\1", argumentList[1]), flags=re.DOTALL)  # DOTALL so it can handle newlines in messages properly
		try:
			if re.search(regex, argumentList[0]):
				return (True, argumentList[2])
			else:
				return (True, argumentList[3])
		except re.error as e:
			return (False, u"Invalid regex '{}' in 'ifmatch' call ({})".format(argumentList[1], e.message))

	@staticmethod
	@validateArguments(argumentCount=4, numericArgumentIndexes=(0, 1))
	def command_ifsmaller(argumentList, grammarDict, variableDict):
		"""
		<$ifsmaller|firstValue|secondValue|resultIfFirstValueIsSmaller|resultIfFirstValueIsNotSmaller>
		Returns the first result if the first value is smaller than the second value, and the second result if the first value is equal to or larger than the second value
		"""
		if argumentList[0] < argumentList[1]:
			return (True, argumentList[2])
		else:
			return (True, argumentList[3])

	@staticmethod
	@validateArguments(argumentCount=4, numericArgumentIndexes=(0, 1))
	def command_ifsmallerorequal(argumentList, grammarDict, variableDict):
		"""
		<$ifsmallerorequal|firstValue|secondValue|resultIfFirstValueIsSmallerOrEqual|resulOtherwise>
		Returns the first result if the first value is smaller than or equal to the second value, and the second result if the first value is larger than the second value
		"""
		if argumentList[0] <= argumentList[1]:
			return (True, argumentList[2])
		else:
			return (True, argumentList[3])

	@staticmethod
	@validateArguments(argumentCount=2)
	def command_switch(argumentList, grammarDict, variableDict):
		"""
		<$switch|stringToCheck|case1:stringIfCase1|case2:stringIfCase2|...|[_default:stringIfNoCaseMatch]>
		Checks which provided case matches the string to check. The '_default' field is not mandatory, but if it's missing and no suitable case can be found, an error is returned
		"""
		#First construct the comparison dict
		caseDict = {}
		for caseString in argumentList[1:]:
			if u":" not in caseString:
				return (False, u"Missing colon in parameter '{}' to 'switch' command".format(caseString))
			case, stringIfCase = caseString.split(u':', 1)
			caseDict[case] = stringIfCase
		#Then see if we can find a matching case
		if argumentList[0] in caseDict:
			return (True, caseDict[argumentList[0]])
		elif u'_default' in caseDict:
			return (True, caseDict[u'_default'])
		else:
			return (False, u"'switch' command contains no case for '{}', and no '_default' fallback case".format(argumentList[0]))

	#Parameter functions
	@staticmethod
	@validateArguments(argumentCount=2)
	def command_hasparams(argumentList, grammarDict, variableDict):
		"""
		<$hasparams|stringIfHasParams|stringIfDoesntHaveParams>
		Checks if there are any parameters provided. Returns the first string if any parameters exist, and the second one if not
		"""
		if u'_params' in variableDict:
			return (True, argumentList[0])
		else:
			return (True, argumentList[1])

	@staticmethod
	@validateArguments(argumentCount=3)
	def command_hasparameter(argumentList, grammarDict, variableDict):
		"""
		<$hasparameter|paramToCheck|stringIfHasParam|stringIfDoesntHaveParam>
		Checks if the the provided parameter string is equal to a string. Returns the first string if it matches, and the second one if it doesn't.
		If no parameter string was provided, the 'doesn't match' string is returned
		"""
		if u'_params' in variableDict and argumentList[0] == variableDict[u'_params']:
			return (True, argumentList[1])
		else:
			return (True, argumentList[2])

	@staticmethod
	@validateArguments(argumentCount=3)
	def command_hasparam(argumentList, grammarDict, variableDict):
		"""
		<$hasparam|paramToCheck|stringIfHasParam|stringIfDoesntHaveParam>
		Checks if the the provided parameters are equal to a string. Returns the first string if it matches, and the second one if it doesn't.
		If no parameter string was provided, the 'doesn't match' string is returned
		"""
		return GrammarCommands.command_hasparameter(argumentList, grammarDict, variableDict)

	@staticmethod
	@validateArguments(argumentCount=0)
	def command_params(argumentList, grammarDict, variableDict):
		"""
		<$params>
		Returns the user-provided parameter string, or an empty string if no parameter string was provided
		"""
		# Fill in the provided parameter(s) in this field
		return (True, variableDict.get(u'_params', u""))

	#Random choices
	@staticmethod
	@validateArguments(argumentCount=2, numericArgumentIndexes=(0, 1))
	def command_randint(argumentList, grammarDict, variableDict):
		"""
		<$randint|lowerBound|higherBound>
		Returns a number between the lower and upper bound, inclusive on both sides
		"""
		if argumentList[1] < argumentList[0]:
			value = random.randint(argumentList[1], argumentList[0])
		else:
			value = random.randint(argumentList[0], argumentList[1])
		return (True, unicode(str(value), 'utf-8'))

	@staticmethod
	@validateArguments(argumentCount=1)
	def command_choose(argumentList, grammarDict, variableDict):
		"""
		<$choose|option1|option2|...>
		Chooses a random option from the ones provided. Useful if the options are short and it'd feel like a waste to make a separate field for each of them
		"""
		return (True, random.choice(argumentList))

	@staticmethod
	@validateArguments(argumentCount=1)
	def command_file(argumentList, grammarDict, variableDict):
		"""
		<$file|filename>
		Load a sentence from the specified file. Useful for not cluttering up the grammar file with a lot of options
		The file has to exists in the same directory the grammar file is in
		"""
		return (True, Command.getRandomLine(argumentList[0]))


	#Miscellaneous
	@staticmethod
	@validateArguments(argumentCount=3, numericArgumentIndexes=(3,))
	def command_replace(argumentList, grammarDict, variableDict):
		"""
		<$replace|stringToReplaceIn|whatToReplace|whatToReplaceItWith[|replacementCount]>
		Returns the provided string but with part of it replaced. The substring 'whatToReplace' is replaced by 'whatToReplaceItBy'
		If 'replacementCount' is set to a number, only that many replacements are made
		"""
		replacementCount = -1  #Negative count means no replacement limit
		#Check if a count parameter was given, and if so, if it's valid
		if len(argumentList) >= 4:
			replacementCount = argumentList[3]
			if replacementCount <= 0:
				return (False, u"Invalid optional replacement count value '{}' passed to 'replace' call".format(argumentList[3]))
		#Now replace what we need to replace
		return (True, argumentList[0].replace(argumentList[1], argumentList[2], replacementCount))

	@staticmethod
	@validateArguments(argumentCount=3, numericArgumentIndexes=(3,))
	def command_regexreplace(argumentList, grammarDict, variableDict):
		"""
		<$regexreplace|stringToReplaceIn|regexOfWhatToReplace|whatToReplaceItWith[|replacementCount]>
		Returns the provided string with part of it replaced. The part to replace is determined with the provided regular expression
		If 'replacementCount' is set to a number, only that many replacements are made
		"""
		replacementCount = 0  #0 means no replacement limit
		#Check if a replacement count parameter was given, and if so, if it's valid
		if len(argumentList) >= 4:
			replacementCount = argumentList[3]
			if replacementCount <= 0:
				return (False, u"Invalid optional replacement count value '{}' passed to 'regexreplace' call".format(argumentList[3]))
		try:
			# Unescape any characters inside the regex (like < and |)
			regex = re.compile(re.sub(r"/(.)", r"\1", argumentList[1]), flags=re.DOTALL)  # DOTALL so it can handle newlines in messages properly
			return (True, re.sub(regex, argumentList[2], argumentList[0], count=replacementCount))
		except re.error as e:
			return (False, u"Unable to parse regular expression '{}' in 'regexreplace' call ({})".format(argumentList[1], e.message))

	@staticmethod
	@validateArguments(argumentCount=1)
	def command_modulecommand(argumentList, grammarDict, variableDict):
		"""
		<$modulecommand|commandName[|argument1|argument2|key1=value1|key2=value2|...]>
		Runs a shared command in another bot module. The first parameter is the name of that command, the rest are unnamed and named parameters to pass on, and are all optional
		"""
		if not GlobalStore.commandhandler.hasCommandFunction(argumentList[0]):
			return (False, u"Unknown module command '{}'".format(argumentList[0]))
		# Turn the arguments into something we can call a function with
		commandArguments = []
		keywordCommandArguments = {}
		for argument in argumentList[1:]:
			# Make sure they're all converted from unicode to string, since that's what functions will expect
			argument = argument.encode('utf-8', errors='replace')
			# Remove any character escaping (so arguments can contain '<' without messing up)
			argument = re.sub(r"/(.)", r"\1", argument)
			if '=' not in argument:
				commandArguments.append(argument)
			else:
				key, value = argument.split('=', 1)
				keywordCommandArguments[key] = value
		# Call the module function!
		moduleCommandResult = GlobalStore.commandhandler.runCommandFunction(argumentList[0], u"", *commandArguments, **keywordCommandArguments)
		# Make sure the replacement is a unicode string
		if isinstance(moduleCommandResult, basestring):
			moduleCommandResult = moduleCommandResult.decode('utf-8', errors='replace')
		elif isinstance(moduleCommandResult, (list, tuple)):
			moduleCommandResult = u", ".join(moduleCommandResult)
		elif isinstance(moduleCommandResult, dict):
			SharedFunctions.dictToString(moduleCommandResult)
		else:
			return (False, u"Module command '{}' returned non-text object".format(argumentList[0]))
		#Everything parsed and converted fine
		return (True, moduleCommandResult)
