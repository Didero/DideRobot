import glob, inspect, json, os, random, re

from CommandTemplate import CommandTemplate
from IrcMessage import IrcMessage
from util import FileUtil
from util import IrcFormattingUtil
from util import StringUtil
import GlobalStore
from CommandException import CommandException


fieldCommandPrefix = u"$"
argumentIsVariablePrefix = u"%"
modifiersPrefix = u"&"


class Command(CommandTemplate):
	triggers = ['generate', 'gen']
	helptext = "Generate random stories or words. Reload generators with '{commandPrefix}generate reload'. Call a specific generator with '{commandPrefix}generate [genName]'. Enter 'random' to let me pick, or choose from: "
	callInThread = True

	generators = {}
	filesLocation = os.path.join(GlobalStore.scriptfolder, "data", "generators")
	MAX_LOOP_COUNT = 300

	def onLoad(self):
		#Make the grammar parsing function available to other modules
		GlobalStore.commandhandler.addCommandFunction(__file__, 'parseGrammarDict', Command.parseGrammarDict)
		Command.loadGenerators()

	@staticmethod
	def loadGenerators():
		#Make sure there aren't any lingering keys
		Command.generators.clear()
		#First fill the generators dict with a few built-in generators
		Command.generators.update({u'name': Command.generateName, u'word': Command.generateWord, u'word2': Command.generateWord2})
		#Go through all available .grammar files and store their 'triggers'
		for grammarFilePath in glob.iglob(os.path.join(Command.filesLocation, '*.grammar')):
			grammarFileName = os.path.basename(grammarFilePath)
			with open(grammarFilePath, 'r') as grammarFile:
				try:
					grammarJson = json.load(grammarFile)
				except ValueError as e:
					Command.logError("[Generators] Error parsing grammar file '{}', invalid JSON: {}".format(grammarFileName, e.message))
				else:
					if u'_triggers' not in grammarJson:
						Command.logError("[Gen] Grammar file '{}' is missing a '_triggers' field so it can't be called".format(os.path.basename(grammarFileName)))
					else:
						triggers = grammarJson[u'_triggers']
						if isinstance(triggers, basestring):
							#If there's only one trigger, make it a list anyway so we can loop as normal, saves duplicate code
							triggers = [triggers]
						for trigger in triggers:
							trigger = trigger.lower()
							#Check if the trigger isn't in there already
							if trigger in Command.generators:
								Command.logError(u"[Gen] Trigger '{}' is in multiple generators ('{}' and '{}')".format(trigger, grammarJson.get(u'_name', grammarFileName), Command.generators[trigger]))
							else:
								Command.generators[trigger] = grammarFileName
		Command.logDebug("[Generators] Loaded {:,} generators".format(len(Command.generators)))

	def getHelp(self, message):
		#If there's no parameters provided, just show the generic module help text
		if message.messagePartsLength <= 1:
			return CommandTemplate.getHelp(self, message) + ", ".join(Command.getAvailableTriggers())
		requestedTrigger = message.messageParts[1].lower()
		if requestedTrigger not in Command.generators:
			# No matching generator trigger was found
			return "I'm not familiar with the '{}' generator, though if you think it would make a good one, feel free to inform my owner(s), maybe they'll create it!".format(requestedTrigger)
		generator = Command.generators[requestedTrigger]
		if isinstance(generator, basestring):
			with open(os.path.join(Command.filesLocation, generator), 'r') as grammarFile:
				grammarDict = json.load(grammarFile)
				if u'_description' in grammarDict:
					helpstring = u"{}{} {}: {}".format(message.bot.commandPrefix, message.messageParts[0], requestedTrigger, grammarDict[u'_description'])
					if u'_version' in grammarDict:
						helpstring += u" [Version {}]".format(grammarDict[u'_version'])
					return helpstring
				else:
					return u"The '{}' generator file didn't specify a help text, sorry!".format(requestedTrigger)
		#Match is one of the built-in functions
		elif callable(generator):
			#Show the function's docstring, if it has one, otherwise show an error
			helptext = "No helptext was set for this generator, sorry"
			if generator.__doc__:
				#Get the docstring, with the newlines and tabs removed
				helptext = inspect.cleandoc(generator.__doc__).replace('\n', ' ')
			return "{}{} {}: {}".format(message.bot.commandPrefix, message.messageParts[0], requestedTrigger, helptext)
		else:
			self.logError("[Gen] Generator for trigger '{}' has type '{}', and we can't get the help from that".format(requestedTrigger, type(generator)))
			return "I'm not sure how to get help for '{}', sorry. Maybe just try it out and see what happens instead?".format(requestedTrigger)

	def execute(self, message):
		"""
		:type message: IrcMessage
		"""
		if message.messagePartsLength == 0 or message.messageParts[0].lower() == 'help':
			return message.reply(self.getHelp(message))

		if message.messageParts[0].lower() == 'reload':
			if 	not message.bot.isUserAdmin(message.user, message.userNickname, message.userAddress):
				return message.reply("I'm sorry, only admins are allowed to make me reload my generators. Try asking one if my admins. Sorry!")
			Command.loadGenerators()
			return message.reply(u"Ok, I reloaded all the generators from disk. I now have these {:,} generators loaded: {}".format(len(Command.generators), u", ".join(Command.getAvailableTriggers())))

		try:
			message.reply(Command.executeGrammarByTrigger(message.messageParts[0].lower(), message.messageParts[1:]))
		except GrammarException as e:
			raise CommandException(e.message)

	@staticmethod
	def getAvailableTriggers():
		return sorted(Command.generators.keys())

	@staticmethod
	def executeGrammarByTrigger(trigger, parameters=None, variableDict=None):
		"""
		Looks to see if there's a grammar that should fire on the provided trigger, and executes it if so.
		If the grammar can't be found, or if something goes wrong during execution, a GrammarException will be thrown
		:param trigger: The grammar trigger to execute
		:param parameters: A string with space-delimited parameters to pass on to the grammar
		:param variableDict: An optional dictionary with pre-set variables to use while parsing
		:return: A string with the grammar result
		:raises GrammarException if no generators are loaded, if there is no grammar that should fire on the provided trigger, or if something goes wrong during execution
		"""
		if not Command.generators:
			raise GrammarException(u"That's weird, I don't seem to have any generators loaded, sorry. Try updating, reloading this module, or writing your own generator!")

		trigger = StringUtil.forceToUnicode(trigger)
		if trigger == u'random':
			wantedGenerator = random.choice(Command.generators.values())
		elif trigger in Command.generators:
			wantedGenerator = Command.generators[trigger]
		else:
			#No suitable generator found, list the available ones
			raise GrammarException(u"'{}' is not a valid generator name. Use 'random' to let me pick, or choose from: {}".format(trigger, u", ".join(Command.getAvailableTriggers())))

		#The generator can either be a module function, or a string pointing to a grammar file. Check which it is
		if isinstance(wantedGenerator, basestring):
			path = os.path.join(Command.filesLocation, wantedGenerator)
			#Grammar file! First check if it still exists
			if not os.path.isfile(path):
				Command.loadGenerators()
				raise GrammarException(u"Huh, the '{}' generator did exist last time I looked, but now it's... gone, for some reason. Please don't rename my files without telling me. I'll just refresh my generator list".format(trigger))
			#It exists! Send it to the parser
			with open(path, "r") as grammarfile:
				try:
					grammarDict = json.load(grammarfile)
				except ValueError as e:
					Command.logError(u"[Gen] Grammar file '{}' is invalid JSON: {}".format(wantedGenerator, e))
					raise GrammarException(u"The grammar file for '{}' is broken, for some reason. Tell my owner(s), hopefully they can fix it".format(trigger))
				return Command.parseGrammarDict(grammarDict, trigger, parameters=parameters, variableDict=variableDict)
		else:
			#Function! Just call it, with the message so it can figure it out from there itself
			return wantedGenerator(parameters)

	@staticmethod
	def getLineFromFile(filename, filelocation=None, lineNumber=None):
		"""
		Gets a line from the provided file. If no line number is provided, a random line will be returned
		:param filename: The name of the file to get the line from
		:param filelocation: The path to the file. If it's empty or None, the default location will be prepended
		:param lineNumber: If provided, the specified line will be retrieved from the file (line counts start at 0). If not specified, a random line is returned
		:return: A line from the specified file, or an error message if the file is in an invalid location or doesn't exit
		"""
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
		if lineNumber and lineNumber >= 0:
			line = FileUtil.getLineFromFile(filepath, lineNumber)
		else:
			line = FileUtil.getRandomLineFromFile(filepath)
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
			if 0 < periodValue < 20:
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
		return arg.lower() in (u"f", u"female", u"woman", u"girl", u"m", u"male", u"man", u"boy", u"misc", u"other", u"queer")

	@staticmethod
	def getGenderWords(genderString, allowUnspecified=True):
		if genderString is not None:
			genderString = genderString.lower()

		if genderString in (u"f", u"female", u"woman", u"girl"):
			gender = u"f"
		elif genderString in (u"m", u"male", u"man", u"boy"):
			gender = u"m"
		elif allowUnspecified and genderString in (u"misc", u"other", u"queer"):
			gender = u"misc"
		else:
			# No gender specified, pick one on our own
			roll = random.randint(1, 100)
			if allowUnspecified and roll <= 45 or roll <= 50:
				gender = u"f"
			elif allowUnspecified and roll <= 90 or roll <= 100:
				gender = u"m"
			else:
				gender = u"misc"

		#Set some verb variables, so using both 'they' and 'he/his' in sentences is easier
		#For instance in grammar files you can do '<_var|they> <_var|isAre>' or '<_var|they> make<_var|verbS>'
		#First set them to the 'he' and 'she' values, since then we only have to change them in one case
		genderDict = {u"isAre": u"is", u"wasWere": u"was", u"verbS": u"s", u"verbEs": u"es"}
		#Then set the pronouns
		if gender == u"f":
			genderDict.update({u"gender": u"f", u"genderNoun": u"Woman", u"genderNounYoung": u"Girl", u"pronoun": u"she", u"possessivePronoun": u"her", u"personalPronoun": u"her",
							   u"they": u"she", u"their": u"her", u"them": u"her"})
		elif gender == u"m":
			genderDict.update({u"gender": u"m", u"genderNoun": u"Man", u"genderNounYoung": u"Boy", u"pronoun": u"he", u"possessivePronoun": u"his", u"personalPronoun": u"him",
							   u"they": u"he", u"their": u"his", u"them": u"him"})
		else:
			#Since the pronoun is 'they', verbs need other forms, so set them too here
			genderDict.update({u"gender": u"misc", u"genderNoun": u"Person", u"genderNounYoung": u"Kid", u"pronoun": u"they", u"possessivePronoun": u"their", u"personalPronoun": u"them",
							   u"they": u"they", u"their": u"their", u"them": u"them",
							   u"isAre": u"are", u"wasWere": u"were", u"verbS": u"", u"verbEs": u""})
		return genderDict

	@staticmethod
	def parseGrammarDict(grammarDict, trigger, parameters=None, variableDict=None):
		if variableDict is None:
			variableDict = {}
		#Store the trigger so grammars can know how they got called
		variableDict[u'_trigger'] = StringUtil.forceToUnicode(trigger)

		#First check if the starting field exists
		if u'start' in grammarDict:
			startString = u"<start>"
		elif u'_start' in grammarDict:
			#Force the old '_start' into 'start' to prevent 'unknown command' errors
			grammarDict[u'start'] = grammarDict[u'_start']
			del grammarDict[u'_start']
			startString = u"<start>"
		else:
			Command.logWarning(u"[Gen] Missing 'start' or '_start' field in grammar '{}'".format(grammarDict.get(u'_name', u'[noname]')))
			raise GrammarException(u"Error: No 'start' field found!")

		#Make sure the parameters are unicode, since for grammars everything should be unicode
		if parameters and not isinstance(parameters[0], unicode):
			parameters = [unicode(param, encoding='utf-8', errors='replace') for param in parameters if not isinstance(param, unicode)]

		#Parse any initializers specified
		for initializerKey in (u'_initializers', u'_initialisers', u'_init', u'_options'):
			if initializerKey in grammarDict:
				Command.parseInitializers(grammarDict[initializerKey], parameters, variableDict)
				break

		#Since chance dictionaries ('{"20": "20% of this text", "80": "60% (80-20) of this text", "100: "20% chance"}') have to have string keys to be valid JSON,
		# the keys need to be converted to integers for correct sorting (so "100" doesn't come before "20"). We'll do that as we encounter them, so we need to
		# keep track of which dictionaries we've converted and which we haven't yet. We do that by storing references to them in a list, in the variableDict
		variableDict[u'_convertedChanceDicts'] = []

		#Start the parsing!
		return Command.parseGrammarString(startString, grammarDict, parameters, variableDict)

	@staticmethod
	def parseInitializers(initializers, parameters, variableDict):
		if isinstance(initializers, basestring):
			initializers = [initializers]
		# Parse initializers in order, and if an initializer needs a parameter, only look at the first parameter in the parameters list.
		# This prevents odd behaviour where it thinks you specified a gender if in the middle of the parameters there's 'man', for instance
		for initializer in initializers:
			if initializer == u'parseGender':
				gender = None
				if parameters and Command.isGenderParameter(parameters[0]):
					gender = parameters.pop(0)
				variableDict.update(Command.getGenderWords(gender))  # If no gender was provided, 'getGenderWords' will pick a random one
			elif initializer == u'generateName':
				# If a gender was provided or requested, use that to generate a name, otherwise make the function pick a gender
				variableDict[u'name'] = Command.generateName(variableDict.get(u'gender', None))
				# Make first and last names separately accessible
				nameparts = variableDict[u'name'].split(' ')
				variableDict[u'firstname'] = nameparts[0]
				variableDict[u'lastname'] = nameparts[-1]  # Use -1 because names
			# A lot of generators support repeating output. Support it through an option
			elif initializer == u'parseRepeats':
				Command.parseRepeatsFromParams(parameters, variableDict)
			# Support an optional parameter indicating the max repeats allowed, check if that's in there
			elif initializer.startswith(u"parseRepeats:"):
				# Separation character is a colon
				maxRepeats = initializer.split(u':', 1)[1]
				if not maxRepeats or not maxRepeats.isnumeric():
					raise GrammarException(u"Initializer '{}' specifies a non-numeric maximum repeat count.  Format is 'parseRepeats:[maxRepeats], or just 'parseRepeats' if no max is wanted".format(initializer))
				maxRepeats = int(maxRepeats, 10)
				if maxRepeats <= 0:
					raise GrammarException(u"Initializer '{}' specifies a negative or zero maximum number of repeats, which isn't supported".format(initializer))
				Command.parseRepeatsFromParams(parameters, variableDict, maxRepeats)
			else:
				raise GrammarException(u"Unkown initializer '{}' specified".format(initializer))

	@staticmethod
	def parseRepeatsFromParams(parameters, variableDict, maximumRepeats=None):
		repeats = None
		# Go through all the parameters and remove the first number from it, assuming it's the repeat count
		if parameters and parameters[0].isnumeric():
			# Remove the parameter from the parameters list, so the parameters can be used for other things in a generator too
			repeats = parameters.pop(0)
		if not repeats:
			repeats = 1
		else:
			# Make sure the repeat parameter is within the allowed range
			repeats = int(repeats, 10)
			if repeats < 1:
				repeats = 1
			elif maximumRepeats and repeats > maximumRepeats:
				repeats = maximumRepeats
		variableDict[u'_repeats'] = repeats

	@staticmethod
	def parseGrammarString(grammarString, grammar, parameters=None, variableDict=None):
		if variableDict is None:
			variableDict = {}

		#Parse the parameters as a string (if there are any) in such a way that users don't have access to special fields
		# This to prevent abuse like infinite loops or creating heavy load
		#Store that string inside the variableDict under the key '_params', makes lookup and checking easier
		if parameters:
			if not isinstance(parameters[0], unicode):
				variableDict[u'_params'] = unicode(" ".join(parameters), encoding="utf-8", errors="replace")
			else:
				variableDict[u'_params'] = u" ".join(parameters)
			variableDict[u'_params'] = variableDict[u'_params'].replace(u"/", u"//").replace(u"<", u"/<").replace(u">", u"/>")

		#Make sure the input string is Unicode, since that's what we expect
		if not isinstance(grammarString, unicode):
			grammarString = grammarString.decode("utf-8", errors="replace")

		outputString = grammarString
		startIndex = 0

		iteration = variableDict.get(u'_iteration', 0)
		if not isinstance(iteration, int) or iteration < 0:
			iteration = 0
		variableDict[u'_iteration'] = iteration
		variableDict[u'_maxIterations'] = Command.MAX_LOOP_COUNT
		while iteration < Command.MAX_LOOP_COUNT:
			# Some commands can increase the iterations, but don't allow them to decrease it
			iteration = max(iteration, variableDict[u'_iteration']) + 1
			variableDict[u'_iteration'] = iteration
			variableDict[u'_maxIterationsLeft'] = Command.MAX_LOOP_COUNT - iteration

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
					parsedGrammarBlock = Command.parseGrammarBlock(grammarParts, grammar, variableDict)
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
					Command.logWarning(u"[Gen] Grammar '{}' is missing a closing bracket in line '{}'".format(grammar.get(u"_name", u"[noname]"), outputString))
					return u"Error: Missing closing bracket"
				#Otherwise, we're done! Break out of the while-loop
				break
		else:
			#We reached the loop limit, so there's probably an infinite loop. Report that
			Command.logWarning(u"[Gen] Grammar '{}' reached the parse loop limit while parsing string '{}'".format(grammar.get(u"_name", u"[noname]"), outputString))
			raise GrammarException(u"Error: Loop limit reached, there's probably an infinite loop in the grammar file")

		#Unescape escaped characters so they display properly
		outputString = re.sub(ur"/(.)", ur"\1", outputString)
		#Done!
		return outputString

	@staticmethod
	def parseGrammarBlock(grammarBlockParts, grammar, variableDict=None):
		fieldKey = grammarBlockParts.pop(0)

		#If the last field starts with '&', it specifies one or more modifiers, like making text bold.
		# Multiple options are separated by commas. Retrieve those options
		firstModifier = None
		remainingModifiers = None
		if grammarBlockParts and grammarBlockParts[-1].startswith(modifiersPrefix):
			modifierBlockPart = grammarBlockParts.pop().lstrip(modifiersPrefix)
			if u',' in modifierBlockPart:
				firstModifier, remainingModifiers = modifierBlockPart.split(u',', 1)
			else:
				firstModifier = modifierBlockPart

		# Grammar commands start with the command prefix, check if this block is a grammar command
		if fieldKey.startswith(fieldCommandPrefix):
			# First check if the requested command exists as a custom command inside the grammar dict
			if fieldKey in grammar:
				# Custom command, declared in the grammar dict like '"$myCommand": "First argument is %1"',
				# where '%1' should be replaced with the first argument, '%2' with the second, etc.
				# Numbered arguments when there's less than that amount of arguments will be replaced with an empty string
				def replaceNumberedArguments(matchObject):
					# A uneven amount of escape symbols means the % was escaped, so keep it unchanged
					if len(matchObject.group(1)) % 2 == 1:
						return matchObject.group(0)
					argumentIndex = int(matchObject.group(2), 10) - 1  # -1 because the arguments in the command start at 1 but list indexes start at 0
					# Keep the slashes in front if they didn't escape anything
					returnstring = matchObject.group(1)
					# If the index isn't referring to anything in the argument list, leave it empty, otherwise fill it in
					if argumentIndex < len(grammarBlockParts):
						returnstring += grammarBlockParts[argumentIndex]
					return returnstring
				replacement = re.sub(r"(/*)%(\d+)", replaceNumberedArguments, grammar[fieldKey])
			#Otherwise let the Commands class handle it
			else:
				#Have the GrammarCommands class try and execute the provided command name
				replacement = GrammarCommands.runCommand(fieldKey[len(fieldCommandPrefix):], grammarBlockParts, grammar, variableDict)
		# No command, so check if it's a valid key
		elif fieldKey not in grammar:
			raise GrammarException(u"Field '{}' not found in grammar file".format(fieldKey))
		# All's well, fill it in
		else:
			if isinstance(grammar[fieldKey], list):
				# It's a list! Just pick a random entry
				replacement = random.choice(grammar[fieldKey])
			elif isinstance(grammar[fieldKey], dict):
				# Dictionary! The keys are chance percentages, the values are the replacement strings
				if fieldKey not in variableDict[u'_convertedChanceDicts']:
					Command.convertChanceDict(grammar[fieldKey])
					variableDict[u'_convertedChanceDicts'].append(fieldKey)
				replacement = Command.parseChanceDict(grammar[fieldKey], variableDict)
			elif isinstance(grammar[fieldKey], basestring):
				# If it's a string (either the string class or the unicode class), just dump it in
				replacement = grammar[fieldKey]
			else:
				raise GrammarException(u"No handling defined for type '{}' found in field '{}'".format(type(grammar[fieldKey]), fieldKey))

		# We assume all replacements are unicode strings, so make sure this replacement is too
		replacement = StringUtil.forceToUnicode(replacement)

		#Turn the modifier into a new grammarblock
		if firstModifier:
			#Store the original replacement because we need to add it as a parameter to the modifier command
			variableDict[u'_'] = replacement
			#Check if there are any parameters passed
			if u':' not in firstModifier:
				modifierParams = [replacement]
			else:
				modifierParams = firstModifier.split(u':')
				firstModifier = modifierParams.pop(0)
				#If the replacement string isn't used explicitely as a parameter, add it as the last parameter
				if argumentIsVariablePrefix + u'_' not in modifierParams:
					modifierParams.append(replacement)
			replacement = u"<{commandPrefix}{firstModifier}|{params}".format(commandPrefix=fieldCommandPrefix, firstModifier=firstModifier, params=u"|".join(modifierParams))
			if remainingModifiers:
				replacement += u"|" + modifiersPrefix + remainingModifiers
			replacement += u">"

		#Done!
		return replacement

	@staticmethod
	def parseChanceDict(chanceDict, variableDict):
		closestChanceMatch = 101
		closestChanceMatchValue = u""
		randomValue = random.randint(1, 100)
		#Find the lowest chance dict key that's higher than our roll
		for chanceKey, chanceValue in chanceDict.iteritems():
			#If the key is a variable name, replace it with the variable's value
			if isinstance(chanceKey, basestring) and chanceKey.startswith(argumentIsVariablePrefix):
				#Replace variable with current value
				varName = chanceKey[1:]
				if varName not in variableDict:
					raise GrammarException(u"Variable '{}' used in chance dictionary, but that variable isn't set".format(varName))
				varValue = variableDict[varName]
				if not isinstance(varValue, int):
					try:
						varValue = int(varValue, 10)
					except ValueError:
						raise GrammarException(u"Variable '{}' used in chance dictionary is set to '{}', which could not be parsed as a number".format(varName, varValue))
				chanceKey = varValue
			#Check if this chance dict key is closer to the stored chance dict key while still being larger than the roll
			if chanceKey >= randomValue and chanceKey < closestChanceMatch:
				closestChanceMatchValue = chanceValue
				closestChanceMatch = chanceKey
		return closestChanceMatchValue

	@staticmethod
	def convertChanceDict(grammarDictToConvert):
		"""
		Convert a chance dict with the chances as strings to a dict with the chances as ints
		:param grammarDictToConvert: The dict to convert the keys of
		:return: The converted dictionary. It also gets stored in the grammar dict under the original key
		"""
		for key in grammarDictToConvert.keys():
			if not isinstance(key, (basestring, int)):
				raise GrammarException(u"Key '{}' of chance dictionary is an invalid type, should be a variable string or a number".format(key))
			#If they value is already an integer, or if it's a variable name, no need to do anything
			if isinstance(key, int) or key.startswith(argumentIsVariablePrefix):
				continue
			try:
				keyAsInt = int(key, 10)
				grammarDictToConvert[keyAsInt] = grammarDictToConvert.pop(key)
			except ValueError:
				raise GrammarException(u"Key '{}' from chance dictionary could not be parsed as a number".format(key))
		print u"Converted dict: " + repr(grammarDictToConvert)
		return grammarDictToConvert


	@staticmethod
	def generateName(parameters=None):
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
				if Command.isGenderParameter(param):
					genderDict = Command.getGenderWords(param, False)
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
			genderDict = Command.getGenderWords(None, False)

		names = []
		for i in xrange(namecount):
			# First get a last name
			lastName = Command.getLineFromFile("LastNames.txt")
			#Get the right name for the provided gender
			if genderDict['gender'] == 'f':
				firstName = Command.getLineFromFile("FirstNamesFemale.txt")
			else:
				firstName = Command.getLineFromFile("FirstNamesMale.txt")

			#with a chance add a middle letter:
			if (parameters and "addletter" in parameters) or random.randint(1, 100) <= 15:
				names.append(u"{} {}. {}".format(firstName, Command.getBasicOrSpecialLetter(50, 75).upper(), lastName))
			else:
				names.append(u"{} {}".format(firstName, lastName))

		return StringUtil.joinWithSeparator(names)


	@staticmethod
	def generateWord(parameters=None):
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
			repeats = StringUtil.parseInt(parameters[0], 1, 1, 25)

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

	@staticmethod
	def generateWord2(parameters=None):
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
			repeats = StringUtil.parseInt(parameters[0], 1, 1, 25)

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
						word += Command.getBasicOrSpecialLetter("consonant", basicLetterChance)
					else:
						word += random.choice(onsets)

				#Nucleus!
				if random.randint(1, 100) <= simpleLetterChance:
					word += Command.getBasicOrSpecialLetter("vowel", basicLetterChance)
				else:
					word += random.choice(nuclei)

				#Add a coda in most cases (Always add it if this is the last syllable of the word and it'd be too short otherwise)
				if (j == syllableCount - 1 and len(word) < 3) or random.randint(1, 100) <= 75:
					if random.randint(1, 100) <= simpleLetterChance:
						word += Command.getBasicOrSpecialLetter("consonant", basicLetterChance)
					else:
						word += random.choice(codas)

			word = word[0].upper() + word[1:]
			words.append(word)

		return u", ".join(words)


#Store some data about grammar commands, so we can do some initial argument verification. Keeps the actual commands nice and short
grammarCommandOptions = {}

def validateArguments(argumentCount=0, numericArgumentIndexes=None):
	"""
	A decorator to store options on how grammar commands should be executed and how the input should be checked
	:param argumentCount: The minimum number of arguments this grammar command needs. An error is thrown if the command is called with fewer arguments
	:param numericArgumentIndexes: A tuple or list of the argument indexes that should be turned from strings into numbers (indexes start at 0).
			If an index specified here is larger than 'count', it's considered an optional arg
	"""
	#If the numericArgumentIndexes was provided as just a single index number, turn it into a tuple for easier parsing
	if isinstance(numericArgumentIndexes, int):
		numericArgumentIndexes = (numericArgumentIndexes,)
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
			raise GrammarException(u"Unknown command '{}' called".format(commandName))
		#Get the settings for the method
		requiredArgumentCount, numericArgIndexes = grammarCommandOptions.get(command, (0, None))
		#Check if enough arguments were passed, if not, return an error
		if len(argumentList) < requiredArgumentCount:
			raise GrammarException(GrammarCommands._constructNotEnoughParametersErrorMessage(command, requiredArgumentCount, len(argumentList)))
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
					raise GrammarException(u"Field '{}' references variable name '{}', but that isn't set".format(commandName, varname))
				argumentList[argIndex] = u"{}{}".format(variableDict[varname], argumentSuffix)
			#If the arg is in the 'numericalArg' list, (try to) convert it to a number
			if numericArgIndexes and argIndex in numericArgIndexes:
				try:
					argumentList[argIndex] = int(argumentList[argIndex], 10)
				except ValueError:
					raise GrammarException(u"Argument '{}' (index {}) of command '{}' should be numeric, but couldn't get properly converted to a number".format(argumentList[argIndex], argIndex, commandName))
		#All checks passed, call the command
		try:
			return command(argumentList, grammarDict, variableDict)
		except GrammarException as grammarException:
			raise grammarException
		except Exception as e:
			raise GrammarException(u"Something went wrong when executing the '{}' command: {}".format(commandName, e.message if e.message else e))

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

	@staticmethod
	def _checkIfVariableIsWriteable(varname):
		if varname.startswith(u"_"):
			raise GrammarException(u"Variable '{}' starts with an underscore, which means it's an internal variables and can't be changed".format(varname))

	@staticmethod
	def _evaluateAsBoolean(inputToEvaluate, *extraValuesToAcceptAsTrue):
		"""
		Checks whether the inputToEvaluate should evaluate to 'True'. The input should be a unicode string
		'True' is when the string is 'true' or '1' (case-insensitive)
		You can also specify extra values that should qualify as truthy too (these ARE case-sensitive)
		:param inputToEvaluate: The unicode string to parse as a boolean
		:param extraValuesToAcceptAsTrue: One or more strings that should also qualify as truthy
		:return: True if the input should evaluate to true, False otherwise
		"""
		if not inputToEvaluate or not isinstance(inputToEvaluate, unicode):
			return False
		inputToEvaluate = inputToEvaluate.lower()
		return inputToEvaluate in (u'true', u'1') or inputToEvaluate in extraValuesToAcceptAsTrue

	#################
	#Saving and loading variables

	@staticmethod
	@validateArguments(argumentCount=2)
	def command_setvar(argumentList, grammarDict, variableDict):
		"""
		<$setvar|varname|value[|shouldShowValue]>
		Stores a value under the provided name, for future use.
		By default this produces no output, but if the optional parameter 'shouldShowValue' is 'show' or 'true', the value will be displayed
		If you want to always show the value, use '$storeas'
		"""
		GrammarCommands._checkIfVariableIsWriteable(argumentList[0])
		variableDict[argumentList[0]] = argumentList[1]
		if len(argumentList) > 2 and GrammarCommands._evaluateAsBoolean(argumentList[2], u'show'):
			return argumentList[1]
		else:
			return u""

	@staticmethod
	@validateArguments(argumentCount=2)
	def command_storeandhide(argumentList, grammarDict, variableDict):
		"""
		<$storeandhide|varname|value>
		Stores a value under the provided name for future use, with empty output
		If you want to see the variable value, use <$storeandshow>.
		Also look at <$setvar>, which has a 'shouldShowValue' argument
		"""
		modifiedArgs = [argumentList[0], argumentList[1], u'false']
		return GrammarCommands.command_setvar(modifiedArgs, grammarDict, variableDict)

	@staticmethod
	@validateArguments(argumentCount=2)
	def command_storeandshow(argumentList, grammarDict, variableDict):
		"""
		<$storeandshow|varname|value>
		Stores a value under the provided name for future use, with the value as output
		If you don't want to see the variable value, use <$storeandhide>
		Also look at <$setvar>, which has a 'shouldShowValue' argument
		"""
		modifiedArgs = [argumentList[0], argumentList[1], u'true']
		return GrammarCommands.command_setvar(modifiedArgs, grammarDict, variableDict)


	@staticmethod
	@validateArguments(argumentCount=2)
	def command_setvarrandom(argumentList, grammarDict, variableDict):
		"""
		<$setvarrandom|varname|value1|value2|...>
		Picks one of the provided values at random, and stores it under the provided name, for future use
		"""
		GrammarCommands._checkIfVariableIsWriteable(argumentList[0])
		variableDict[argumentList[0]] = random.choice(argumentList[1:])
		return u""

	@staticmethod
	@validateArguments(argumentCount=3)
	def command_hasvar(argumentList, grammarDict, variableDict):
		"""
		<$hasvar|varname|stringIfVarnameExists|stringIfVarnameDoesntExist>
		Checks if the variable with the provided name exists. Returns the first string if it does, and the second one if it doesn't
		"""
		if argumentList[0] in variableDict:
			return argumentList[1]
		else:
			return argumentList[2]

	@staticmethod
	@validateArguments(argumentCount=1)
	def command_var(argumentList, grammarDict, variableDict):
		"""
		<$var|varname|[valueIfVarNotSet]>
		Returns the value stored under the provided variable name. The second argument is optional, and if set will be returned if the variable isn't stored
		"""
		# Check if the named variable was stored
		if argumentList[0] in variableDict:
			return variableDict[argumentList[0]]
		else:
			# If a second parameter was passed, use it as a fallback value
			if len(argumentList) > 1:
				return argumentList[1]
			# Otherwise, throw an error
			else:
				raise GrammarException(u"Referenced undefined variable '{}' in 'var' call".format(argumentList[0]))

	@staticmethod
	@validateArguments(argumentCount=2)
	def command_prependtovar(argumentList, grammarDict, variableDict):
		"""
		<$prependtovar|varname|stringToPrepend>
		Prepends stringToPrepend to what is stored in the specified variable name, and stores it under that name.
		If the variable wasn't set before, it will be set to 'stringToPrepend'.
		Doesn't print anything, use the $var command to print the result
		"""
		GrammarCommands._checkIfVariableIsWriteable(argumentList[0])
		if argumentList[0] not in variableDict:
			variableDict[argumentList[0]] = argumentList[1]
		else:
			variableDict[argumentList[0]] = argumentList[1] + variableDict[argumentList[0]]
		return u""

	@staticmethod
	@validateArguments(argumentCount=2)
	def command_appendtovar(argumentList, grammarDict, variableDict):
		"""
		<$appendtovar|varname|stringToAppend[|string2ToAppend[|string3ToAppend[|...]]]>
		Appends all the 'stringToAppend' arguments to what is stored in the specified variable name, and stores it under that name.
		If the variable wasn't set before, it will be set to the joined 'stringToAppend's.
		Doesn't print anything, use the $var command to print the result
		"""
		GrammarCommands._checkIfVariableIsWriteable(argumentList[0])
		variableDict[argumentList[0]] = variableDict.get(argumentList[0], u"") + u"".join(argumentList[1:])
		return u""

	@staticmethod
	@validateArguments(argumentCount=1)
	def command_remvar(argumentList, grammarDict, variableDict):
		"""
		<$remvar|varname>
		Removes the value stored under this variable name. Does nothing if the variable doesn't exist
		"""
		GrammarCommands._checkIfVariableIsWriteable(argumentList[0])
		if argumentList[0] in variableDict:
			del variableDict[argumentList[0]]
		return u""

	@staticmethod
	@validateArguments(argumentCount=1)
	def command_removevar(argumentList, grammarDict, variableDict):
		"""
		<$removevar|varname>
		Alias for 'remvar', removes the stored variable
		"""
		return GrammarCommands.command_remvar(argumentList, grammarDict, variableDict)

	#################
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
			return argumentList[2]
		else:
			return argumentList[3]

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
		if argumentList[1] in argumentList[0]:
			return argumentList[2]
		else:
			return argumentList[3]

	@staticmethod
	@validateArguments(argumentCount=4)
	def command_ifstartswith(argumentList, grammarDict, variableDict):
		"""
		<$ifstartswith|string|substringToCheckFor|resultIfStringStartsWithSubstring|resultIfStringDoesntStartWithSubstring>
		Checks if the provided string starts with the provided substring
		"""
		return argumentList[2] if argumentList[0].startswith(argumentList[1]) else argumentList[3]

	@staticmethod
	@validateArguments(argumentCount=4)
	def command_ifendswith(argumentList, grammarDict, variableDict):
		"""
		<$ifendswith|string|substringToCheckFor|resultIfStringEndsWithSubstring|resultIfStringDoesntEndWithSubstring>
		Checks if the provided string ends with the provided substring
		"""
		return argumentList[2] if argumentList[0].endswith(argumentList[1]) else argumentList[3]

	@staticmethod
	@validateArguments(argumentCount=4)
	def command_ifmatch(argumentList, grammarDict, variableDict):
		"""
		<$ifmatch|string|regexToMatch|resultIfMatch|resultIfNoMatch[|shouldIgnoreCase]>
		Checks if the provided regular expression matches the provided string
		If the last parameter is provided and is anything but 'false' or empty, the match will be done in a case-insensitive manner
		"""
		#First check which regex flags we need to use
		regexFlags = re.DOTALL  # DOTALL so it can handle newlines in messages properly
		if len(argumentList) > 4 and len(argumentList[4]) > 0 and GrammarCommands._evaluateAsBoolean(argumentList[4]):
			regexFlags |= re.IGNORECASE
		#Make sure we un-escape the regex, so it can use characters like < and | without messing up our parsing
		regex = re.compile(re.sub(r"/(.)", r"\1", argumentList[1]), flags=regexFlags)
		try:
			if re.search(regex, argumentList[0]):
				return argumentList[2]
			else:
				return argumentList[3]
		except re.error as e:
			raise GrammarException(u"Invalid regex '{}' in 'ifmatch' call ({})".format(argumentList[1], e.message))

	#Numeric functions
	@staticmethod
	@validateArguments(argumentCount=3)
	def command_isnumber(argumentList, grammarDict, variableDict):
		"""
		<$isnumber|stringToCheckAsNumber|resultIfNumber|resultIfNotNumber>
		Checks if the provided string can be converted to a number. Returns the 'IfNumber' result if it can, and the 'IfNotNumber' result otherwise
		Can be useful to verify that the provided parameter is a number, for instance
		"""
		try:
			int(argumentList[0], 10)
			return argumentList[1]
		except ValueError:
			return argumentList[2]


	@staticmethod
	@validateArguments(argumentCount=4, numericArgumentIndexes=(0, 1))
	def command_ifsmaller(argumentList, grammarDict, variableDict):
		"""
		<$ifsmaller|firstValue|secondValue|resultIfFirstValueIsSmaller|resultIfFirstValueIsNotSmaller>
		Returns the first result if the first value is smaller than the second value, and the second result if the first value is equal to or larger than the second value
		"""
		if argumentList[0] < argumentList[1]:
			return argumentList[2]
		else:
			return argumentList[3]

	@staticmethod
	@validateArguments(argumentCount=4, numericArgumentIndexes=(0, 1))
	def command_ifsmallerorequal(argumentList, grammarDict, variableDict):
		"""
		<$ifsmallerorequal|firstValue|secondValue|resultIfFirstValueIsSmallerOrEqual|resulOtherwise>
		Returns the first result if the first value is smaller than or equal to the second value, and the second result if the first value is larger than the second value
		"""
		if argumentList[0] <= argumentList[1]:
			return argumentList[2]
		else:
			return argumentList[3]

	@staticmethod
	@validateArguments(argumentCount=1, numericArgumentIndexes=(0, 1))
	def command_increase(argumentList, grammarDict, variableDict):
		"""
		<$increase|numberToIncrease[|increaseAmount]>
		Increases the provided number. If the 'increaseAmount' is specified, numberToIncrease is increased by that amount, otherwise 1 is added
		"""
		increaseAmount = 1 if len(argumentList) <= 1 else argumentList[1]
		return argumentList[0] + increaseAmount

	@staticmethod
	@validateArguments(argumentCount=1, numericArgumentIndexes=(0, 1))
	def command_decrease(argumentList, grammarDict, variableDict):
		"""
		<$decrease|numberToDecrease[|decreaseAmount]>
		Decreases the provided number. If the 'decreaseAmount' is specified, numberToDecrease is decreased by that amount, otherwise 1 is subtracted
		"""
		decreaseAmount = 1 if len(argumentList) <= 1 else argumentList[1]
		return argumentList[0] - decreaseAmount

	@staticmethod
	@validateArguments(argumentCount=4, numericArgumentIndexes=1)
	def command_islength(argumentList, grammarDict, variableDict):
		"""
		<$islength|stringToCheck|lengthToEqual|resultIfStringIsLength|resultOtherwise>
		"""
		if len(argumentList[0]) == argumentList[1]:
			return argumentList[2]
		else:
			return argumentList[3]

	@staticmethod
	@validateArguments(argumentCount=4, numericArgumentIndexes=1)
	def command_isshorter(argumentList, grammarDict, variableDict):
		"""
		<$isshorter|stringToCheck|lengthToEqual|resultIfStringIsShorter|resultOtherwise>
		"""
		if len(argumentList[0]) < argumentList[1]:
			return argumentList[2]
		else:
			return argumentList[3]

	@staticmethod
	@validateArguments(argumentCount=4, numericArgumentIndexes=1)
	def command_isshorterorequal(argumentList, grammarDict, variableDict):
		"""
		<$isshorterorequal|stringToCheck|lengthToEqual|resultIfStringIsShorterOrEqual|resultOtherwise>
		"""
		if len(argumentList[0]) <= argumentList[1]:
			return argumentList[2]
		else:
			return argumentList[3]

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
				raise GrammarException(u"Missing colon in parameter '{}' to 'switch' command".format(caseString))
			case, stringIfCase = caseString.split(u':', 1)
			caseDict[case] = stringIfCase
		#Then see if we can find a matching case
		if argumentList[0] in caseDict:
			return caseDict[argumentList[0]]
		elif u'_default' in caseDict:
			return caseDict[u'_default']
		else:
			raise GrammarException(u"'switch' command contains no case for '{}', and no '_default' fallback case".format(argumentList[0]))

	#################
	#Parameter functions

	@staticmethod
	@validateArguments(argumentCount=2)
	def command_hasparams(argumentList, grammarDict, variableDict):
		"""
		<$hasparams|stringIfHasParams|stringIfDoesntHaveParams>
		Checks if there are any parameters provided. Returns the first string if any parameters exist, and the second one if not
		"""
		if variableDict.get(u'_params', None):
			return argumentList[0]
		else:
			return argumentList[1]

	@staticmethod
	@validateArguments(argumentCount=3)
	def command_hasparameter(argumentList, grammarDict, variableDict):
		"""
		<$hasparameter|paramToCheck|stringIfHasParam|stringIfDoesntHaveParam>
		Checks if the the provided parameter string is equal to a string. Returns the first string if it matches, and the second one if it doesn't.
		If no parameter string was provided, the 'doesn't match' string is returned
		"""
		if u'_params' in variableDict and argumentList[0] == variableDict[u'_params']:
			return argumentList[1]
		else:
			return argumentList[2]

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
		return variableDict.get(u'_params', u"")

	#################
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
		return unicode(str(value), 'utf-8')

	@staticmethod
	@validateArguments(argumentCount=2, numericArgumentIndexes=(0, 1, 2, 3))
	def command_dice(argumentList, grammarDict, variableDict):
		"""
		<$dice|numberOfDice|numberOfSides[lowestRollsToRemove|highestRollsToRemove]>
		Rolls a number of dice and returns the total. First argument is how many dice to roll, second argument is how many sides each die should have
		The third argument is how many of the lowest rolls should be removed. So if you roll three dice - say 1, 3, 4 - and specify 1 for this argument, it'll ignore the 1 and return 7
		The fourth argument works the same way, except for the highest rolls (so the total would be 4 in the example if you specify 1 here instead of 1 for lowest)
		The third and fourth arguments are optional
		"""
		if argumentList[0] <= 0 or argumentList[1] <= 0:
			raise GrammarException(u"Dice command can't handle negative values or zero")
		diceLimit = 1000
		sidesLimit = 10**9
		if argumentList[0] > diceLimit or argumentList[1] > sidesLimit:
			raise GrammarException(u"Dice count shouldn't be higher than {:,} and sides count shouldn't be higher than {:,}".format(diceLimit, sidesLimit))

		#Check if we need to remove some highest or lowest values later
		lowestRollsToRemove = 0
		highestRollsToRemove = 0
		if len(argumentList) > 2:
			if argumentList[2] <= 0 or argumentList[2] >= argumentList[0]:
				raise GrammarException(u"Invalid number for lowestRollsToRemove parameter, it's not allowed to be lower than 0 or equal to or larger than the number of rolls")
			lowestRollsToRemove = argumentList[2]
			if len(argumentList) > 3:
				if argumentList[3] <= 0 or argumentList[3] >= argumentList[0]:
					raise GrammarException(u"Invalid number for highestRollsToRemove parameter, it's not allowed to be lower than 0 or equal to or larger than the number of rolls")
				highestRollsToRemove = argumentList[3]
				if lowestRollsToRemove + highestRollsToRemove >= argumentList[0]:
					raise GrammarException(u"Lowest and highest rolls to remove are equal to or larger than the total number of rolls")

		#Roll the dice!
		rolls = []
		for i in xrange(argumentList[0]):
			rolls.append(random.randint(1, argumentList[1]))
		rolls.sort()

		#The time of (possibly) removing high and low rolls is now
		if highestRollsToRemove:
			rolls = rolls[:argumentList[0] - highestRollsToRemove]
		if lowestRollsToRemove:
			rolls = rolls[lowestRollsToRemove:]

		#Add up the (remaining) rolls
		total = 0
		for roll in rolls:
			total += roll
		return total

	@staticmethod
	@validateArguments(argumentCount=1)
	def command_choose(argumentList, grammarDict, variableDict):
		"""
		<$choose|option1|option2|...>
		Chooses a random option from the ones provided. Useful if the options are short and it'd feel like a waste to make a separate field for each of them
		"""
		return random.choice(argumentList)

	@staticmethod
	@validateArguments(argumentCount=3, numericArgumentIndexes=0)
	def command_choosemultiple(argumentList, grammarDict, variableDict):
		"""
		<$choosemultiple|numberOfOptionsToChoose|separator|option1|option2|...>
		Chooses the provided number of random options from the option list, and returns them in a random order,	with the provided separator between the options
		"""
		numberOfOptionsToChoose = argumentList.pop(0)
		separator = argumentList.pop(0)
		if numberOfOptionsToChoose <= 0 or numberOfOptionsToChoose >= len(argumentList):
			#Invalid choice number, just shuffle the list and return that
			random.shuffle(argumentList)
			return separator.join(argumentList)
		#Number of options to choose is less than number of provided options, pick that number
		return separator.join(random.sample(argumentList, numberOfOptionsToChoose))

	@staticmethod
	@validateArguments(argumentCount=1)
	def command_choosewithchance(argumentList, grammarDict, variableDict):
		"""
		<$choosewithchance|chancegroup1:optionIfChance[|chancegroup2:optionIfChance[|...]]>
		Works the same as a separate chance dict field: Chances have to be between 0 and 100 (inclusive)
		When called, a random number is chosen also between 1 and 100. Then the proper chance group is chosen by picking the lowest chancegroup chance that's larger than the random number
		So if the command field is '<$choosewithchance|15:option1|100:option2>', if the random number is 8, 'option1' is chosen. If then random number is 64, 'option2' is chosen
		If no chancegroup is provided for the random number, and empty string is returned
		"""
		chanceDict = {}
		for arg in argumentList:
			if not u":" in arg:
				raise GrammarException(u"Invalid option '{}' in 'choosewithchance' field, arguments should be 'chance:optionIfChance'".format(arg))
			chance, optionIfChance = arg.split(u":", 1)
			try:
				chance = int(chance, 10)
			except ValueError:
				raise GrammarException(u"Chance '{}' from 'choosewithchance' field argument '{}' could not be parsed to a number".format(chance, arg))
			chanceDict[chance] = optionIfChance
		return Command.parseChanceDict(chanceDict, variableDict)

	@staticmethod
	@validateArguments(argumentCount=1, numericArgumentIndexes=1)
	def command_file(argumentList, grammarDict, variableDict):
		"""
		<$file|filename[|lineNumber]>
		Load a random line from the specified file. Useful for not cluttering up the grammar file with a lot of options
		The file has to exists in the same directory the grammar file is in
		If the line number parameter is specified, that specific line will be returned instead of a random line (line count starts at 0)
		Specifying a line number is mainly useful for testing
		"""
		return Command.getLineFromFile(argumentList[0], lineNumber=None if len(argumentList) == 1 else argumentList[1])

	#################
	#Text formatting

	@staticmethod
	@validateArguments(argumentCount=1)
	def command_lowercase(argumentList, grammarDict, variableDict):
		"""
		<$lowercase|stringToMakeLowercase>
		Returns the provided string with every letter made lowercase
		"""
		return argumentList[0].lower()

	@staticmethod
	@validateArguments(argumentCount=1)
	def command_uppercase(argumentList, grammarDict, variableDict):
		"""
		<$uppercase|stringToMakeUppercase>
		Returns the provided string with every letter made uppercase
		"""
		return argumentList[0].upper()

	@staticmethod
	@validateArguments(argumentCount=1)
	def command_titlecase(argumentList, grammarDict, variableDict):
		"""
		<$titlecase|stringToMakeTitlecase>
		Returns the provided string with every word starting with a capital letter and the rest of the word lowercase
		"""
		return argumentList[0].title()

	@staticmethod
	@validateArguments(argumentCount=1)
	def command_firstletteruppercase(argumentList, grammarDict, variableDict):
		"""
		<$firstletteruppercase|stringToFormat>
		Returns the provided string with the first character made uppercase and the rest left as provided
		"""
		s = argumentList[0]
		return s[0].upper() + s[1:]

	@staticmethod
	@validateArguments(argumentCount=1)
	def command_bold(argumentList, grammarDict, variableDict):
		"""
		<$bold|stringToMakeBold>
		Returns the provided string formatted so it looks like bold text in IRC
		"""
		return IrcFormattingUtil.makeTextBold(argumentList[0])

	@staticmethod
	@validateArguments(argumentCount=1, numericArgumentIndexes=0)
	def command_numbertotext(argumentList, grammarDict, variableDict):
		"""
		<$numbertotext|numberToDisplayAsText>
		Converts the provided number to its English representation. For instance, '4' would get turned into 'four'
		"""
		return Command.numberToText(argumentList[0])

	#################
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
				raise GrammarException(u"Invalid optional replacement count value '{}' passed to 'replace' call".format(argumentList[3]))
		#Now replace what we need to replace
		return argumentList[0].replace(argumentList[1], argumentList[2], replacementCount)

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
				raise GrammarException(u"Invalid optional replacement count value '{}' passed to 'regexreplace' call".format(argumentList[3]))
		try:
			# Unescape any characters inside the regex (like < and |)
			regex = re.compile(re.sub(r"/(.)", r"\1", argumentList[1]), flags=re.DOTALL)  # DOTALL so it can handle newlines in messages properly
			return re.sub(regex, argumentList[2], argumentList[0], count=replacementCount)
		except re.error as e:
			raise GrammarException(u"Unable to parse regular expression '{}' in 'regexreplace' call ({})".format(argumentList[1], e.message))

	@staticmethod
	@validateArguments(argumentCount=2, numericArgumentIndexes=2)
	def command_replacerandomword(argumentList, grammarDict, variableDict):
		"""
		<$replacerandomword|stringToReplaceIn|replacementString[|amountOfWordsToReplace]>
		Replaces a random word in the provided 'stringToReplace' with the 'replacementString', where words are assumed to be separated by spaces
		If the 'amountOfWordsToReplace' is provided, this many words are replaced instead of just one
		"""
		inputParts = argumentList[0].split(u' ')
		replacementCount = max(1, argumentList[2]) if len(argumentList) > 2 else 1
		if replacementCount >= len(inputParts):
			# Asked to replace more sections than we can, replace everything, with a space in between
			if replacementCount == 1:
				return argumentList[1]
			else:
				return (argumentList[1] + u" ") * (replacementCount - 1) + argumentList[1]
		else:
			indexesToReplace = random.sample(xrange(0, len(inputParts)), replacementCount)
			for indexToReplace in indexesToReplace:
				inputParts[indexToReplace] = argumentList[1]
			return u" ".join(inputParts)

	@staticmethod
	@validateArguments(argumentCount=2, numericArgumentIndexes=0)
	def command_repeat(argumentList, grammarDict, variableDict):
		"""
		<$repeat|timesToRepeat|stringToRepeat[|stringToPutBetweenRepeats]>
		Repeats the provided stringToRepeat the amount of times specified in timesToRepeat. If timesToRepeat is zero or less, nothing will be returned
		If the third argument stringToPutBetweenRepeats is specified, this string will be inserted between each repetition of stringToRepeat
		"""
		#If there's nothing to repeat, stop immediately
		if argumentList[0] <= 0:
			return u""
		#Check if there's something to put between the repeated string
		joinString = None
		if len(argumentList) > 2:
			joinString = argumentList[2]
		#Do the actual repeating (-1 because we already start with one repetition)
		resultString = argumentList[1]
		for i in xrange(argumentList[0] - 1):
			if joinString:
				resultString += joinString
			resultString += argumentList[1]
		#Done!
		return resultString

	@staticmethod
	@validateArguments(argumentCount=1)
	def command_modulecommand(argumentList, grammarDict, variableDict):
		"""
		<$modulecommand|commandName[|argument1|argument2|key1=value1|key2=value2|...]>
		Runs a shared command in another bot module. The first parameter is the name of that command, the rest are unnamed and named parameters to pass on, and are all optional
		"""
		if not GlobalStore.commandhandler.hasCommandFunction(argumentList[0]):
			raise GrammarException(u"Unknown module command '{}'".format(argumentList[0]))
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
			StringUtil.dictToString(moduleCommandResult)
		else:
			raise GrammarException(u"Module command '{}' returned non-text object".format(argumentList[0]))
		#Everything parsed and converted fine
		return moduleCommandResult

	@staticmethod
	@validateArguments(argumentCount=3)
	def command_hasgenerator(argumentList, grammarDict, variableDict):
		"""
		<$hasgenerator|generatorName|stringIfGeneratorExists|stringIfGeneratorDoesNotExist>
		Check if the generator specified by 'generatorName' exists. If it does, 'stringIfGeneratorExists' is returned. If it doesn't exist, 'stringIfGeneratorDoesNotExist' is returned
		"""
		if argumentList[0].lower() in Command.generators:
			return argumentList[1]
		else:
			return argumentList[2]

	@staticmethod
	@validateArguments(argumentCount=1)
	def command_generator(argumentList, grammarDict, variableDict):
		"""
		<$generator|generatorName|shouldCopyVariableDict[|parameter1[|parameter2[...]]]>
		Run a different generator specified by 'generatorName' and get the result. If 'shouldCopyVariableDict' is 'true', then all variables stored by the called generator will be copied to our variableDict
		You can also pass parameters to that generator by adding them as arguments here
		Please note that the iterations of the called generator count against the current iteration limit. So it's not possible to use this to bypass the iteration limit
		"""
		#To make sure the combined iterations don't exceed the limit, pass the current iteration to the execution method
		calledGeneratorVariableDict = {u'_iteration': variableDict[u'_iteration']}
		resultString = Command.executeGrammarByTrigger(argumentList[0].lower(), parameters=argumentList[2:], variableDict=calledGeneratorVariableDict)
		#Copy the variables from the called generator if requested
		if GrammarCommands._evaluateAsBoolean(argumentList[1]):
			variableDict.update(calledGeneratorVariableDict)
		else:
			#Set the iteration that the called generator reached as our current iteration, so we can't exceed the iteration limit
			variableDict[u'_iteration'] = calledGeneratorVariableDict[u'_iteration']
		return resultString

	@staticmethod
	@validateArguments(argumentCount=0)
	def command_hide(argumentList, grammarDict, variableDict):
		"""
		<$hide[|optionalText]>
		This command returns nothing. Useful if you want to add comments in your grammar.
		Mainly added for backwards compatibility with the old 'extraOptions' system which had a 'hide' option
		"""
		return u""


class GrammarException(Exception):
	def __init__(self, message):
		self.message = message if message else u"Something went wrong with executing a grammar command"

	def __str__(self):
		return self.message

