import datetime, glob, inspect, json, os, random, re, string

from commands.CommandTemplate import CommandTemplate
from IrcMessage import IrcMessage
from util import FileUtil
from util import IrcFormattingUtil
from util import StringUtil
import Constants, GlobalStore
from CustomExceptions import CommandException


fieldCommandPrefix = "$"
argumentIsVariablePrefix = "%"
modifiersPrefix = "&"


class Command(CommandTemplate):
	triggers = ['generate', 'gen', 'generateseeded', 'genseeded']
	helptext = "Generate random stories or words. Reload generators with '{commandPrefix}generate reload'. Call a specific generator with '{commandPrefix}generate [genName]'. Enter 'random' to let me pick, or choose from: "
	callInThread = True

	generators = {}
	filesLocation = os.path.join(GlobalStore.scriptfolder, "data", "generators")
	MAX_LOOP_COUNT = 300
	sharedCommandFunctionName = 'parseGrammarDict'

	def onLoad(self):
		#Make the grammar parsing function available to other modules
		GlobalStore.commandhandler.addCommandFunction(__file__, Command.sharedCommandFunctionName, Command.parseGrammarDict)
		#Some modules may want to escape strings before sending them to be parsed, so make the escape method also available
		GlobalStore.commandhandler.addCommandFunction(__file__, 'escapeGrammarString', escapeString)
		Command.loadGenerators()

	@staticmethod
	def loadGenerators():
		#Make sure there aren't any lingering keys
		Command.generators.clear()
		#First fill the generators dict with a few built-in generators
		Command.generators.update({'name': Command.generateName, 'word': Command.generateWord, 'word2': Command.generateWord2})
		#Go through all available .grammar files and store their 'triggers'
		for grammarFilePath in glob.iglob(os.path.join(Command.filesLocation, '*.grammar')):
			grammarFileName = os.path.basename(grammarFilePath)
			with open(grammarFilePath, 'r', encoding='utf-8') as grammarFile:
				try:
					grammarJson = json.load(grammarFile)
				except ValueError as e:
					Command.logError("[Generators] Error parsing grammar file '{}', invalid JSON: {}".format(grammarFileName, e))
				else:
					if '_triggers' not in grammarJson:
						Command.logError("[Gen] Grammar file '{}' is missing a '_triggers' field so it can't be called".format(os.path.basename(grammarFileName)))
					else:
						triggers = grammarJson['_triggers']
						if isinstance(triggers, str):
							#If there's only one trigger, make it a list anyway so we can loop as normal, saves duplicate code
							triggers = [triggers]
						for trigger in triggers:
							trigger = trigger.lower()
							#Check if the trigger isn't in there already
							if trigger in Command.generators:
								Command.logError("[Gen] Trigger '{}' is in multiple generators ('{}' and '{}')".format(trigger, grammarJson.get('_name', grammarFileName), Command.generators[trigger]))
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
		if isinstance(generator, str):
			with open(os.path.join(Command.filesLocation, generator), 'r', encoding='utf-8') as grammarFile:
				grammarDict = json.load(grammarFile)
				if '_description' in grammarDict:
					helpstring = "{}{} {}: {}".format(message.bot.commandPrefix, message.messageParts[0], requestedTrigger, grammarDict['_description'])
					if '_version' in grammarDict:
						helpstring += " [Version {}]".format(grammarDict['_version'])
					return helpstring
				else:
					return "The '{}' generator file didn't specify a help text, sorry!".format(requestedTrigger)
		#Match is one of the built-in functions
		elif callable(generator):
			#Show the function's docstring, if it has one, otherwise show an error
			helptext = "No helptext was set for this generator, sorry"
			if generator.__doc__:
				#Get the docstring, with the newlines and tabs removed
				helptext = StringUtil.removeNewlines(inspect.cleandoc(generator.__doc__))
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
			return message.reply("Ok, I reloaded all the generators from disk. I now have these {:,} generators loaded: {}".format(len(Command.generators), ", ".join(Command.getAvailableTriggers())))

		if message.trigger.endswith('seeded'):
			#Extract the seed prompt from the message parameters
			if message.messagePartsLength < 2:
				return message.reply("If you want to use a seed, it'll probably help if you provide that seed (I don't know how to phrase this without sounding creepy, sorry)")
			seedInput = message.messageParts[1]
			parameters = message.messageParts[2:]
		else:
			seedInput = None
			parameters = message.messageParts[1:]

		#Add some variables from the IRC message
		variableDict = {'_sourceserver': message.bot.serverfolder, '_sourcechannel': message.source, '_sourcenick': message.userNickname}
		message.reply(Command.executeGrammarByTrigger(trigger=message.messageParts[0].lower(), parameters=parameters, variableDict=variableDict, seedInput=seedInput))

	@staticmethod
	def getAvailableTriggers():
		return sorted(Command.generators.keys())

	@staticmethod
	def executeGrammarByTrigger(trigger, parameters=None, variableDict=None, seedInput=None):
		"""
		Looks to see if there's a grammar that should fire on the provided trigger, and executes it if so.
		If the grammar can't be found, or if something goes wrong during execution, a GrammarException will be thrown
		:param trigger: The grammar trigger to execute
		:param parameters: A string with space-delimited parameters to pass on to the grammar
		:param variableDict: An optional dictionary with pre-set variables to use while parsing
		:param seedInput: An optional string with comma-separated values to use in building a seed for random generation
		:return: A string with the grammar result
		:raises GrammarException if no generators are loaded, if there is no grammar that should fire on the provided trigger, or if something goes wrong during execution
		"""
		if not Command.generators:
			raise GrammarException("That's weird, I don't seem to have any generators loaded, sorry. Try updating, reloading this module, or writing your own generator!")

		if trigger == 'random':
			wantedGenerator = random.choice(list(Command.generators.values()))
		elif trigger in Command.generators:
			wantedGenerator = Command.generators[trigger]
		else:
			#No suitable generator found, list the available ones
			raise GrammarException("'{}' is not a valid generator name. Use 'random' to let me pick, or choose from: {}".format(trigger, ", ".join(Command.getAvailableTriggers())), False)

		seed = Command.parseSeedString(seedInput.split(','), variableDict) if seedInput else None

		#The generator can either be a module function, or a string pointing to a grammar file. Check which it is
		if isinstance(wantedGenerator, str):
			path = os.path.join(Command.filesLocation, wantedGenerator)
			#Grammar file! First check if it still exists
			if not os.path.isfile(path):
				Command.loadGenerators()
				raise GrammarException("Huh, the '{}' generator did exist last time I looked, but now it's... gone, for some reason. Please don't rename my files without telling me. I'll just refresh my generator list".format(trigger))
			#It exists! Send it to the parser
			with open(path, 'r', encoding='utf-8') as grammarfile:
				try:
					grammarDict = json.load(grammarfile)
				except ValueError as e:
					Command.logError("[Gen] Grammar file '{}' is invalid JSON: {}".format(wantedGenerator, e))
					raise GrammarException("The grammar file for '{}' is broken, for some reason. Tell my owner(s), hopefully they can fix it".format(trigger))
				return Command.parseGrammarDict(grammarDict, trigger, parameters=parameters, variableDict=variableDict, seed=seed)
		else:
			randomizer = random.Random()
			if seed:
				randomizer.seed(seed)
			#Function! Just call it, with the message so it can figure it out from there itself
			return wantedGenerator(randomizer, parameters)

	@staticmethod
	def getLineFromFile(randomizer, filename, filelocation=None, lineNumber=None):
		"""
		Gets a line from the provided file. If no line number is provided, a random line will be returned
		:param randomizer: An instance of random.Random(), possibly a seeded one
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
		if not os.path.isfile(filepath):
			raise GrammarException("The file '{}' does not seem to exist".format(filename))
		if lineNumber and lineNumber >= 0:
			line = FileUtil.getLineFromFile(filepath, lineNumber)
		else:
			linecount = FileUtil.getLineCount(filepath)
			randomLineNumber = randomizer.randrange(0, linecount)
			line = FileUtil.getLineFromFile(filepath, randomLineNumber)
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
			number //= 1000

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
				numberTextParts.append(baseNumberNames[periodValue // 100])
				numberTextParts.append('hundred')
				periodValue %= 100

			#If the number period is smaller than 20, it's in the base list
			# Skip zero though, otherwise 100 becomes 'one hundred zero'
			if 0 < periodValue < 20:
				numberTextParts.append(baseNumberNames[periodValue])
			#Otherwise we need to split it up a bit more
			else:
				tensValue = periodValue // 10
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
	def getBasicOrSpecialLetter(randomizer, vowelOrConsonant, basicLetterChance):
		if isinstance(vowelOrConsonant, int):
			#Assume the provided argument is a chance percentage of vowel
			if randomizer.randint(1, 100) <= vowelOrConsonant:
				vowelOrConsonant = "vowel"
			else:
				vowelOrConsonant = "consonant"

		if vowelOrConsonant == "vowel":
			basicLetters = ('a', 'e', 'i', 'o', 'u')
			specialLetters = ('y',)
		else:
			basicLetters = ('b', 'c', 'd', 'f', 'g', 'h', 'k', 'l', 'm', 'n', 'p', 'r', 's', 't')
			specialLetters = ('j', 'q', 'v', 'w', 'x', 'z')

		if randomizer.randint(1, 100) <= basicLetterChance:
			return randomizer.choice(basicLetters)
		else:
			return randomizer.choice(specialLetters)


	@staticmethod
	def isGenderParameter(arg):
		return arg.lower() in ("f", "female", "woman", "girl", "m", "male", "man", "boy", "misc", "other", "queer")

	@staticmethod
	def getGenderWords(randomizer, genderString, allowUnspecified=True):
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
			roll = randomizer.randint(1, 100)
			if allowUnspecified and roll <= 45 or roll <= 50:
				gender = "f"
			elif allowUnspecified and roll <= 90 or roll <= 100:
				gender = "m"
			else:
				gender = "misc"

		#Set some verb variables, so using both 'they' and 'he/his' in sentences is easier
		#For instance in grammar files you can do '<_var|they> <_var|isAre>' or '<_var|they> make<_var|verbS>'
		#First set them to the 'he' and 'she' values, since then we only have to change them in one case
		genderDict = {"isAre": "is", "wasWere": "was", "verbS": "s", "verbEs": "es"}
		#Then set the pronouns
		if gender == "f":
			genderDict.update({"gender": "f", "genderNoun": "woman", "genderNounYoung": "girl", "pronoun": "she", "possessivePronoun": "her", "personalPronoun": "her",
							   "they": "she", "their": "her", "them": "her"})
		elif gender == "m":
			genderDict.update({"gender": "m", "genderNoun": "man", "genderNounYoung": "boy", "pronoun": "he", "possessivePronoun": "his", "personalPronoun": "him",
							   "they": "he", "their": "his", "them": "him"})
		else:
			#Since the pronoun is 'they', verbs need other forms, so set them too here
			genderDict.update({"gender": "misc", "genderNoun": "person", "genderNounYoung": "kid", "pronoun": "they", "possessivePronoun": "their", "personalPronoun": "them",
							   "they": "they", "their": "their", "them": "them",
							   "isAre": "are", "wasWere": "were", "verbS": "", "verbEs": ""})
		return genderDict

	@staticmethod
	def parseInitializers(initializers, grammarParseState):
		"""
		:type initializers: list[str]
		:type grammarParseState: GrammarParseState
		"""
		if isinstance(initializers, str):
			initializers = [initializers]
		shouldUpdateParamsVar = False
		# Parse initializers in order, and if an initializer needs a parameter, only look at the first parameter in the parameters list.
		# This prevents odd behaviour where it thinks you specified a gender if in the middle of the parameters there's 'man', for instance
		for initializerString in initializers:
			if ':' in initializerString:
				initializerParameters = initializerString.split(':')
				initializer = initializerParameters.pop(0)
			else:
				initializerParameters = None
				initializer = initializerString

			if initializer == 'parseGender':
				gender = None
				if grammarParseState.parameterList:
					for paramIndex, param in enumerate(grammarParseState.parameterList):
						if Command.isGenderParameter(param):
							gender = grammarParseState.parameterList.pop(paramIndex)
							shouldUpdateParamsVar = True
							break
				grammarParseState.variableDict.update(Command.getGenderWords(grammarParseState.random, gender))  # If no gender was provided, 'getGenderWords' will pick a random one
			elif initializer == 'generateName':
				# If a gender was provided or requested, use that to generate a name, otherwise make the function pick a gender
				grammarParseState.variableDict['name'] = Command.generateName(grammarParseState.random, grammarParseState.variableDict.get('gender', None))
				# Make first and last names separately accessible
				nameparts = grammarParseState.variableDict['name'].split(' ')
				grammarParseState.variableDict['firstname'] = nameparts[0]
				grammarParseState.variableDict['lastname'] = nameparts[-1]  # Use -1 because names might have a middle initial
			# A lot of generators support repeating output. Support it through an option. Optional arguments are a maximum repeat count, and a default value if no repeat count is provided
			elif initializer == 'parseRepeats':
				maxRepeats = None
				defaultValue = 1
				if initializerParameters:
					maxRepeats = initializerParameters[0]
					if not maxRepeats.isnumeric():
						raise GrammarException(f"Initializer '{initializerString}' specifies a non-numeric maximum repeat count.  Format is 'parseRepeats:[maxRepeats]', or just 'parseRepeats' if no max is wanted")
					maxRepeats = int(maxRepeats, 10)
					if maxRepeats <= 0:
						raise GrammarException("Initializer '{}' specifies a negative or zero maximum number of repeats, which isn't supported".format(initializer))
					if len(initializerParameters) >= 2:
						defaultValue = initializerParameters[1]
						if not defaultValue.isnumeric():
							raise GrammarException(f"Initializer '{initializerString}' specifies a non-numeric default value.  Format is 'parseRepeats:[maxRepeats]:[defaultValue]', "
												   "or just 'parseRepeats:[maxRepeats]' if no default value is wanted")
						defaultValue = int(defaultValue, 10)

				repeats = None
				# Go through all the parameters and remove the first number from it, assuming it's the repeat count
				if grammarParseState.parameterList:
					for paramIndex, param in enumerate(grammarParseState.parameterList):
						if param.isnumeric():
							# Remove the parameter from the parameters list, so the parameters can be used for other things in a generator too
							repeats = grammarParseState.parameterList.pop(paramIndex)
							break
				if not repeats:
					repeats = defaultValue
				else:
					# Make sure the repeat parameter is within the allowed range
					repeats = int(repeats, 10)
					if repeats < 1:
						repeats = 1
					elif maxRepeats and repeats > maxRepeats:
						repeats = maxRepeats
				# Store as a string, since that's what the code assumes, and the commands that need this as a number already convert it to an int
				grammarParseState.variableDict['_repeats'] = str(repeats)
				shouldUpdateParamsVar = True
			elif initializer == "setSeed":
				#If a seed has already been set, don't overwrite it
				if not grammarParseState.seed:
					grammarParseState.setSeed(Command.parseSeedString(initializerParameters))
			else:
				raise GrammarException("Unkown initializer '{}' specified".format(initializer))
		if shouldUpdateParamsVar:
			grammarParseState.updateParamsVar()

	@staticmethod
	def parseSeedString(seedParts, variableDict=None):
		"""
		Turn the provided seed parts into a seed usable for random generation
		:param seedParts: A list of parts touse in creating the seed
		:type seedParts: list of str
		:param variableDict: A dictionary with shared variables used in parsing the grammar. Seed parts may need some of these
		:return: A seed to use in random generation
		"""
		parsedSeedParts = []
		#A lot of possible seed part variables depend on the date, so retrieve that now
		now = datetime.datetime.utcnow()
		dateRelatedSeedParts = {'year': "%y", 'month': "%m", 'week': "%W", 'date': "%y-%m-%d", 'dayofyear': "%j", 'hour': "%H"}
		variableRelatedSeedParts = {'server': '_sourceserver', 'channel': '_sourcechannel', 'nick': '_sourcenick'}
		for seedPart in seedParts:
			if seedPart.startswith(argumentIsVariablePrefix):
				seedPart = seedPart[len(argumentIsVariablePrefix):].lower()
				if seedPart in dateRelatedSeedParts:
					seedPart = now.strftime(dateRelatedSeedParts[seedPart])
				elif seedPart in variableRelatedSeedParts:
					varToGet = variableRelatedSeedParts[seedPart]
					if not variableDict or varToGet not in variableDict:
						raise GrammarException("Unable to get the '{}' variable from the variable dictionary for building the seed, because either the variable isn't stored or there is no variable dictionary".format(varToGet))
					seedPart = variableDict[varToGet]
				elif seedPart == "source":
					#'%source' is a combination of server, channel, and nick
					seedPart = Command.parseSeedString(['%server', '%channel', '%nick'], variableDict)
				else:
					raise GrammarException("Unknown variable '{}' used in the seed parameter".format(seedPart))
			parsedSeedParts.append(seedPart)
		return "|".join(parsedSeedParts)

	@staticmethod
	def parseGrammarDict(grammarDict, trigger, parameters=None, variableDict=None, seed=None):
		"""
		Parse the provided grammar dict, filling in fields and running grammar commands until only a string remains
		:param grammarDict: The grammar dictionary to parse
		:param trigger: The trigger with which the grammar parsing was initiated (Usually one of the values in the '_triggers' grammar dict field
		:param parameters: A list of strings with parameters that can be used during the parsing. Can be None if no parameters are provided or needed
		:param variableDict: An optional dict with pre-set variables that can be used during the parsing
		:param seed: Provide a seed for the random generator. Optional
		:return: A string resulting from parsing the grammar dict
		:raises GrammarException: Raised if something goes wrong during parsing or if parsing takes too many steps
		"""

		grammarParseState = GrammarParseState(grammarDict, variableDict, parameters, seed)

		#Store the trigger so grammars can know how they got called
		grammarParseState.variableDict['_trigger'] = trigger

		#Parse any initializers specified
		for initializerKey in ('_initializers', '_initialisers', '_init', '_options'):
			if initializerKey in grammarDict:
				Command.parseInitializers(grammarDict[initializerKey], grammarParseState)
				break

		#Start the parsing!
		iteration = grammarParseState.variableDict.get('_iteration', 0)
		if not isinstance(iteration, int) or iteration < 0:
			iteration = 0
		grammarParseState.variableDict['_iteration'] = iteration
		while iteration < Command.MAX_LOOP_COUNT:
			# Some commands can increase the iterations, but don't allow them to decrease it
			iteration = max(iteration, grammarParseState.variableDict['_iteration']) + 1
			grammarParseState.variableDict['_iteration'] = iteration
			grammarParseState.variableDict['_maxIterationsLeft'] = Command.MAX_LOOP_COUNT - iteration

			nestedBracketLevel = 0
			characterIsEscaped = False
			grammarParts = [""]
			#Go through the string to find the first bracketed section
			for index in range(grammarParseState.currentParseStringIndex, len(grammarParseState.currentParseString)):
				character = grammarParseState.currentParseString[index]

				#Handle character escaping first, since that overrides everything else
				if characterIsEscaped or character == "/":
					characterIsEscaped = not characterIsEscaped  #Only escape one character, so flip it back. Or it's the escape character, so flip to True
					if nestedBracketLevel > 0:
						grammarParts[-1] += character
					continue

				if nestedBracketLevel == 0 and character == "<":
					#Store this position for the next loop, so we don't needlessly check bracket-less text multiple times
					grammarParseState.currentParseStringIndex = index
					#And go up a level
					nestedBracketLevel = 1
				elif nestedBracketLevel == 1 and character == "|":
					#Start a new gramamr part
					grammarParts.append("")
				elif nestedBracketLevel == 1 and character == ">":
					#We found the end of the grammar block. Have it parsed
					parsedGrammarBlock = Command.parseGrammarBlock(grammarParts, grammarParseState)
					#Everything went fine, replace the grammar block with the output
					grammarParseState.currentParseString = grammarParseState.currentParseString[:grammarParseState.currentParseStringIndex] + parsedGrammarBlock + grammarParseState.currentParseString[index + 1:]
					#Done with this parsing loop, start a new one! (break out of the for-loop to start a new while-loop iteration)
					break
				#Don't append characters if we're not inside a grammar block
				elif nestedBracketLevel > 0:
					#We always want to append the character now
					grammarParts[-1] += character
					#Keep track of how many levels deep we are
					if character == "<":
						nestedBracketLevel += 1
					elif character == ">":
						nestedBracketLevel -= 1
			else:
				#We reached the end of the output string. If we're not at top level, the gramamr block isn't closed
				if nestedBracketLevel > 0:
					Command.logWarning("[Gen] Grammar '{}' is missing a closing bracket in line '{}'".format(grammarParseState.grammarDict.get("_name", "[noname]"), grammarParseState.currentParseString))
					return "Error: Missing closing bracket"
				#Otherwise, we're done! Break out of the while-loop
				break
		else:
			#We reached the loop limit, so there's probably an infinite loop. Report that
			Command.logWarning("[Gen] Grammar '{}' reached the parse loop limit while parsing string '{}'".format(grammarParseState.grammarDict.get("_name", "[noname]"), grammarParseState.currentParseString))
			raise GrammarException("Error: Loop limit reached, there's probably an infinite loop in the grammar file")

		#Unescape escaped characters so they display properly
		grammarParseState.currentParseString = re.sub(r"/(.)", r"\1", grammarParseState.currentParseString)
		#Done!
		return grammarParseState.currentParseString

	@staticmethod
	def parseGrammarBlock(grammarBlockParts, grammarParseState):
		"""
		:type grammarBlockParts: list
		:type grammarParseState: GrammarParseState
		"""
		fieldKey = grammarBlockParts.pop(0)

		#If the last field starts with '&', it specifies one or more modifiers, like making text bold.
		# Multiple options are separated by commas. Retrieve those options
		firstModifier = None
		remainingModifiers = None
		if grammarBlockParts and grammarBlockParts[-1].startswith(modifiersPrefix):
			modifierBlockPart = grammarBlockParts.pop().lstrip(modifiersPrefix)
			if ',' in modifierBlockPart:
				firstModifier, remainingModifiers = modifierBlockPart.split(',', 1)
			else:
				firstModifier = modifierBlockPart

		# Grammar commands start with the command prefix, check if this block is a grammar command
		if fieldKey.startswith(fieldCommandPrefix):
			# First check if the requested command exists as a custom command inside the grammar dict
			if fieldKey in grammarParseState.grammarDict:
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
				replacement = re.sub(r"(/*)%(\d+)", replaceNumberedArguments, grammarParseState.grammarDict[fieldKey])
			#Otherwise let the Commands class handle it
			else:
				#Have the GrammarCommands class try and execute the provided command name
				replacement = GrammarCommands.runCommand(fieldKey[len(fieldCommandPrefix):], grammarBlockParts, grammarParseState)
		# No command, so check if it's a valid key
		elif fieldKey not in grammarParseState.grammarDict:
			raise GrammarException("Field '{}' not found in grammar file".format(fieldKey))
		else:
			# All's well, fill it in
			fieldValue = grammarParseState.grammarDict[fieldKey]
			if isinstance(fieldValue, list):
				# It's a list! Just pick a random entry
				replacement = grammarParseState.random.choice(fieldValue)
			elif isinstance(fieldValue, dict):
				# Dictionary! The keys are chance percentages, the values are the replacement strings
				if fieldKey not in grammarParseState.convertedChanceDicts:
					Command.convertChanceDict(fieldValue)
					grammarParseState.convertedChanceDicts.append(fieldKey)
				replacement = Command.parseChanceDict(fieldValue, grammarParseState)
			elif isinstance(fieldValue, str):
				# If it's a string, just dump it in
				replacement = fieldValue
			else:
				raise GrammarException("No handling defined for type '{}' found in field '{}'".format(type(fieldValue), fieldKey))

		#Turn the modifier into a new
		if firstModifier:
			#Store the original replacement because we need to add it as a parameter to the modifier command
			grammarParseState.variableDict['_'] = replacement
			#Check if there are any parameters passed
			if ':' not in firstModifier:
				modifierParams = [replacement]
			else:
				modifierParams = firstModifier.split(':')
				firstModifier = modifierParams.pop(0)
				#If the replacement string isn't used explicitly as a parameter, add it as the last parameter
				if argumentIsVariablePrefix + '_' not in modifierParams:
					modifierParams.append(replacement)
			replacement = "<{commandPrefix}{firstModifier}|{params}".format(commandPrefix=fieldCommandPrefix, firstModifier=firstModifier, params="|".join(modifierParams))
			if remainingModifiers:
				replacement += "|" + modifiersPrefix + remainingModifiers
			replacement += ">"

		#Done!
		return replacement

	@staticmethod
	def parseChanceDict(chanceDict, grammarParseState):
		closestChanceMatch = 101
		closestChanceMatchValue = ""
		randomValue = grammarParseState.random.randint(1, 100)
		#Find the lowest chance dict key that's higher than our roll
		for chanceKey, chanceValue in chanceDict.items():
			#If the key is a variable name, replace it with the variable's value
			if isinstance(chanceKey, str) and chanceKey.startswith(argumentIsVariablePrefix):
				#Replace variable with current value
				varName = chanceKey[1:]
				if varName not in grammarParseState.variableDict:
					raise GrammarException("Variable '{}' used in chance dictionary, but that variable isn't set".format(varName))
				varValue = grammarParseState.variableDict[varName]
				if not isinstance(varValue, int):
					try:
						varValue = int(varValue, 10)
					except ValueError:
						raise GrammarException("Variable '{}' used in chance dictionary is set to '{}', which could not be parsed as a number".format(varName, varValue))
				chanceKey = varValue
			#Check if this chance dict key is closer to the stored chance dict key while still being larger than the roll
			if chanceKey >= randomValue and chanceKey < closestChanceMatch:
				closestChanceMatchValue = chanceValue
				closestChanceMatch = chanceKey
		return closestChanceMatchValue

	@staticmethod
	def convertChanceDict(chanceDictToConvert):
		"""
		Convert a chance dict with the chances as strings to a dict with the chances as ints
		:param chanceDictToConvert: The dict to convert the keys of
		:return: The converted dictionary. It also gets stored in the grammar dict under the original key
		"""
		for key in list(chanceDictToConvert.keys()):
			if not isinstance(key, (str, int)):
				raise GrammarException("Key '{}' of chance dictionary is an invalid type, should be a variable string or a number".format(key))
			#If they value is already an integer, or if it's a variable name, no need to do anything
			if isinstance(key, int) or key.startswith(argumentIsVariablePrefix):
				continue
			try:
				keyAsInt = int(key, 10)
				chanceDictToConvert[keyAsInt] = chanceDictToConvert.pop(key)
			except ValueError:
				raise GrammarException("Key '{}' from chance dictionary could not be parsed as a number".format(key))
		return chanceDictToConvert


	@staticmethod
	def generateName(randomizer, parameters=None):
		"""
		Generates a random first and last name. You can provide a parameter to specify the gender
		:type randomizer: random.Random
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
					genderDict = Command.getGenderWords(randomizer, param, False)
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
			genderDict = Command.getGenderWords(randomizer, None, False)

		names = []
		for i in range(namecount):
			# First get a last name
			lastName = Command.getLineFromFile(randomizer, "LastNames.txt")
			#Get the right name for the provided gender
			if genderDict['gender'] == 'f':
				firstName = Command.getLineFromFile(randomizer, "FirstNamesFemale.txt")
			else:
				firstName = Command.getLineFromFile(randomizer, "FirstNamesMale.txt")

			#with a chance add a middle letter:
			shouldAddInitial = None
			if parameters:
				if "addLetter" in parameters:
					shouldAddInitial = True
				elif "noLetter" in parameters:
					shouldAddInitial = False
			if shouldAddInitial is None:
				shouldAddInitial = randomizer.randint(1, 100) <= 15
			if shouldAddInitial:
				names.append("{} {}. {}".format(firstName, Command.getBasicOrSpecialLetter(randomizer, 50, 75).upper(), lastName))
			else:
				names.append("{} {}".format(firstName, lastName))

		return Constants.GREY_SEPARATOR.join(names)


	@staticmethod
	def generateWord(randomizer, parameters=None):
		"""
		Generates a word by putting letters together in semi-random order. Provide a number to generate that many words
		:type randomizer: random.Random
		"""
		# Initial set-up
		vowels = ('a', 'e', 'i', 'o', '')
		specialVowels = ('y',)

		consonants = ('b', 'c', 'd', 'f', 'g', 'h', 'k', 'l', 'm', 'n', 'p', 'r', 's', 't')
		specialConsonants = ('j', 'q', 'v', 'w', 'x', 'z')

		newLetterFraction = 5
		vowelChance = 50  #percent

		#Determine how many words we're going to have to generate
		repeats = 1
		if parameters and len(parameters) > 0:
			repeats = StringUtil.parseInt(parameters[0], 1, 1, 25)

		words = []
		for i in range(0, repeats):
			word = ""
			currentVowelChance = vowelChance
			currentNewLetterFraction = newLetterFraction
			consonantCount = 0
			while randomizer.randint(0, currentNewLetterFraction) <= 6:
				if randomizer.randint(1, 100) <= currentVowelChance:
					consonantCount = 0
					#vowel. Check if we're going to add a special or normal vowel
					if randomizer.randint(1, 100) <= 10:
						word += randomizer.choice(specialVowels)
						currentVowelChance -= 30
					else:
						word += randomizer.choice(vowels)
						currentVowelChance -= 20
				else:
					consonantCount += 1
					#consonant, same deal
					if randomizer.randint(1, 100) <= 25:
						word += randomizer.choice(specialConsonants)
						currentVowelChance += 30
					else:
						word += randomizer.choice(consonants)
						currentVowelChance += 20
					if consonantCount > 3:
						currentVowelChance = 100
				currentNewLetterFraction += 1

			#Enough letters added. Finish up
			word = word[0].upper() + word[1:]
			words.append(word)

		#Enough words generated, let's return the result
		return ", ".join(words)

	@staticmethod
	def generateWord2(randomizer, parameters=None):
		"""
		Another method to generate a word. Tries to generate pronounceable syllables and puts them together. Provide a number to generate that many words
		:type randomizer: random.Random
		"""

		##Initial set-up
		#A syllable consists of an optional onset, a nucleus, and an optional coda
		#Sources:
		# http://en.wikipedia.org/wiki/English_phonology#Phonotactics
		# http://en.wiktionary.org/wiki/Appendix:English_pronunciation
		onsets = ("ch", "pl", "bl", "cl", "gl", "pr", "br", "tr", "dr", "cr", "gr", "tw", "dw", "qu", "pu",
				  "fl", "sl", "fr", "thr", "shr", "wh", "sw",
				  "sp", "st", "sk", "sm", "sn", "sph", "spl", "spr", "str", "scr", "squ", "sm")  #Plus the normal consonants
		nuclei = ("ai", "ay", "ea", "ee", "y", "oa", "au", "oi", "oo", "ou")  #Plus the normal vowels
		codas = ("ch", "lp", "lb", "lt", "ld", "lch", "lg", "lk", "rp", "rb", "rt", "rd", "rch", "rk", "lf", "lth",
				 "lsh", "rf", "rth", "rs", "rsh", "lm", "ln", "rm", "rn", "rl", "mp", "nt", "nd", "nch", "nk", "mph",
				 "mth", "nth", "ngth", "ft", "sp", "st", "sk", "fth", "pt", "ct", "kt", "pth", "ghth", "tz", "dth",
				 "ks", "lpt", "lfth", "ltz", "lst", "lct", "lx","rmth", "rpt", "rtz", "rst", "rct","mpt", "dth",
				 "nct", "nx", "xth", "xt")  #Plus normal consonants

		simpleLetterChance = 65  #percent, whether a single letter is chosen instead of an onset/nucleus/coda
		basicLetterChance = 75  #percent, whether a simple consonant/vowel is chosen over  a more rare one

		#Prevent unnecessary and ugly code repetition

		#Start the word
		repeats = 1
		if parameters and len(parameters) > 0:
			repeats = StringUtil.parseInt(parameters[0], 1, 1, 25)

		words = []
		for i in range(0, repeats):
			syllableCount = 2
			if randomizer.randint(1, 100) <= 50:
				syllableCount -= 1
			if randomizer.randint(1, 100) <= 35:
				syllableCount += 1

			word = ""
			for j in range(0, syllableCount):
				#In most cases, add an onset
				if randomizer.randint(1, 100) <= 75:
					if randomizer.randint(1, 100) <= simpleLetterChance:
						word += Command.getBasicOrSpecialLetter(randomizer, "consonant", basicLetterChance)
					else:
						word += randomizer.choice(onsets)

				#Nucleus!
				if randomizer.randint(1, 100) <= simpleLetterChance:
					word += Command.getBasicOrSpecialLetter(randomizer, "vowel", basicLetterChance)
				else:
					word += randomizer.choice(nuclei)

				#Add a coda in most cases (Always add it if this is the last syllable of the word and it'd be too short otherwise)
				if (j == syllableCount - 1 and len(word) < 3) or randomizer.randint(1, 100) <= 75:
					if randomizer.randint(1, 100) <= simpleLetterChance:
						word += Command.getBasicOrSpecialLetter(randomizer, "consonant", basicLetterChance)
					else:
						word += randomizer.choice(codas)

			word = word[0].upper() + word[1:]
			words.append(word)

		return ", ".join(words)


class GrammarParseState(object):
	def __init__(self, grammarDict, variableDict=None, parameterList=None, seed=None):
		self.grammarDict = grammarDict
		if variableDict is None or not isinstance(variableDict, dict):
			self.variableDict = {}
		else:
			self.variableDict = variableDict
		self.convertedChanceDicts = []

		#Set up user-provided parameters
		self.parameterList = []
		if parameterList:
			if isinstance(parameterList, str):
				parameterList = [parameterList]
			for param in parameterList:
				self.parameterList.append(param)
		self.updateParamsVar()

		#Because formatting has to be done after a grammar block is fully parsed, we need to store where a formatting block starts
		#This should be a dict, key is start index, value is a list of formatting functions to call
		# The value is a list because one start index can be the start of multiple formatting blocks
		#The formatting function should take a single string parameter and return a formatted string
		self.formattingBlocks = {}

		#We need a 'random' instance in case we need to use a seed
		self.random = random.Random()
		self.seed = None # First set to None to make clear that the field exists
		self.setSeed(seed)

		#Set up the initial string to parse
		if 'start' in grammarDict:
			self.currentParseString = "<start>"
		elif '_start' in grammarDict:
			self.currentParseString = "<_start>"
		else:
			Command.logWarning("[Gen] Missing 'start' or '_start' field in grammar '{}'".format(grammarDict.get('_name', '[noname]')))
			raise GrammarException("Error: No 'start' field found!")
		self.currentParseStringIndex = 0

	def updateParamsVar(self):
		# Escape special characters to prevent abuse by users
		self.variableDict['_params'] = escapeString(" ".join(self.parameterList))

	def setSeed(self, seed):
		if seed:
			self.seed = seed
			self.random.seed(seed)

	def __str__(self):
		return "GrammarParseState for generator '{}', output string: '{}', variables: {}, params: {}, formatting blocks: {}, seed: {}".format(self.grammarDict.get('_name', '[noname]'), self.currentParseString, self.variableDict, self.parameterList, self.formattingBlocks, self.seed)


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
	def runCommand(commandName, argumentList, grammarParseState):
		"""
		This method calls a grammar command method if it exists, and optionally does some sanity checks beforehand, depending on their decorator
		:param commandName: The name of the grammar command that should be executed (without the preceding underscore from the grammar file)
		:param argumentList: A list of arguments to pass along to the command. Is optionally checked for length before the command is called, depending on decorator settings
		:param grammarParseState: An instance of GrammarParseState, that contains data on the grammar being parsed and variables and the like
		:type grammarParseState: GrammarParseState
		:return: A tuple, with the first entry a boolean indicating success, and the second entry a string. If something went wrong, either with the preliminary checks
			or during the grammar command execution, this is False, and the string is the error message. If everything went right, the boolean is True and the string is
			the outcome of the grammar command, ready to be substituted into the grammar string in place of the command
		"""
		command = getattr(GrammarCommands, 'command_' + commandName.lower(), None)
		#First check if the requested command exists
		if not command:
			raise GrammarException("Unknown command '{}' called".format(commandName))
		#Get the settings for the method
		requiredArgumentCount, numericArgIndexes = grammarCommandOptions.get(command, (0, None))
		#Check if enough arguments were passed, if not, return an error
		if len(argumentList) < requiredArgumentCount:
			raise GrammarException(GrammarCommands._constructNotEnoughParametersErrorMessage(command, requiredArgumentCount, len(argumentList)))
		#Check each arg for certain settings
		for argIndex in range(len(argumentList)):
			#Check if the arg start with the variables prefix, in which case it should be replaced by that variable's value
			if argumentList[argIndex].startswith(argumentIsVariablePrefix):
				varname = argumentList[argIndex][len(argumentIsVariablePrefix):]
				argumentSuffix = ''
				#Commands like $switch have arguments with a colon in them, to split the case and the value. Check for that too
				if ':' in varname:
					varname, argumentSuffix = varname.split(':', 1)
					argumentSuffix = ':' + argumentSuffix
				if varname not in grammarParseState.variableDict:
					Command.logError("Variable '{}' referenced but it isn't set, {}".format(varname, grammarParseState))
					raise GrammarException("Field '{}' references variable name '{}', but that isn't set".format(commandName, varname))
				argumentList[argIndex] = "{}{}".format(grammarParseState.variableDict[varname], argumentSuffix)
			#If the arg is in the 'numericalArg' list, (try to) convert it to a number
			if numericArgIndexes and argIndex in numericArgIndexes:
				try:
					argumentList[argIndex] = int(argumentList[argIndex], 10)
				except ValueError:
					raise GrammarException("Argument '{}' (index {}) of command '{}' should be numeric, but couldn't get properly converted to a number".format(argumentList[argIndex], argIndex, commandName))
		#All checks passed, call the command
		try:
			return command(argumentList, grammarParseState)
		except GrammarException as grammarException:
			raise grammarException
		except Exception as e:
			raise GrammarException("Something went wrong when executing the '{}' command: {}".format(commandName, e))

	#Shared internal methods
	@staticmethod
	def _constructNotEnoughParametersErrorMessage(command, requiredNumber, foundNumber):
		#Each method should have a usage string as the first line of its docstring
		usageString = inspect.cleandoc(command.__doc__).splitlines()[0]
		#Display that no parameters were provided in a grammatically correct and sensible way
		if foundNumber == 0:
			foundNumberString = "none were provided"
		else:
			foundNumberString = "only found {}".format(foundNumber)
		#Return the results, formatted nicely
		return "'{}' call needs at least {} parameter{}, but {}. Command usage: {}".format(command.__name__, requiredNumber, 's' if requiredNumber > 1 else '',
																						   foundNumberString, usageString)

	@staticmethod
	def _checkIfVariableIsWriteable(varname):
		if varname.startswith("_"):
			raise GrammarException("Variable '{}' starts with an underscore, which means it's an internal variables and can't be changed".format(varname))

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
		if not inputToEvaluate or not isinstance(inputToEvaluate, str):
			return False
		inputToEvaluate = inputToEvaluate.lower()
		return inputToEvaluate in ('true', '1') or inputToEvaluate in extraValuesToAcceptAsTrue

	@staticmethod
	def _startFormattingBlock(grammarParseState, textToFormat, formattingFunctionToCall):
		"""
		For formatting commands, this method stores where the formatting should start and the formatting function,
		and it will return an unformatted string with an '<$endFormattingBlock>' command at the end
		:param grammarParseState: The current grammar's parse state
		:type grammarParseState: GrammarParseState
		:param formattingFunctionToCall: The function that will do the actual formatting. Should take a single string argument and return a formatted string
		:return: The text to format followed by an 'endOfFormattingBlock' command, that can be returned as the formatting command's result
		"""
		if not "<" in textToFormat and not ">" in textToFormat:
			#The provided text doesn't contain any grammar blocks, so it won't change later. We can do the formatting now
			return formattingFunctionToCall(textToFormat)
		if grammarParseState.currentParseStringIndex not in grammarParseState.formattingBlocks:
			grammarParseState.formattingBlocks[grammarParseState.currentParseStringIndex] = []
		grammarParseState.formattingBlocks[grammarParseState.currentParseStringIndex].append(formattingFunctionToCall)
		return "{}<{}endofformattingblock|{}>".format(textToFormat, fieldCommandPrefix, grammarParseState.currentParseStringIndex)

	#################
	#Saving and loading variables

	@staticmethod
	@validateArguments(argumentCount=2)
	def command_setvar(argumentList, grammarParseState):
		"""
		<$setvar|varname|value[|shouldShowValue]>
		Stores a value under the provided name, for future use.
		By default this produces no output, but if the optional parameter 'shouldShowValue' is 'show' or 'true', the value will be displayed
		If you want to always show the value, use '$storeas'
		"""
		GrammarCommands._checkIfVariableIsWriteable(argumentList[0])
		grammarParseState.variableDict[argumentList[0]] = argumentList[1]
		if len(argumentList) > 2 and GrammarCommands._evaluateAsBoolean(argumentList[2], 'show'):
			return argumentList[1]
		else:
			return ""

	@staticmethod
	@validateArguments(argumentCount=2)
	def command_storeandhide(argumentList, grammarParseState):
		"""
		<$storeandhide|varname|value>
		Stores a value under the provided name for future use, with empty output
		If you want to see the variable value, use <$storeandshow>.
		Also look at <$setvar>, which has a 'shouldShowValue' argument
		"""
		modifiedArgs = [argumentList[0], argumentList[1], 'false']
		return GrammarCommands.command_setvar(modifiedArgs, grammarParseState)

	@staticmethod
	@validateArguments(argumentCount=2)
	def command_storeandshow(argumentList, grammarParseState):
		"""
		<$storeandshow|varname|value>
		Stores a value under the provided name for future use, with the value as output
		If you don't want to see the variable value, use <$storeandhide>
		Also look at <$setvar>, which has a 'shouldShowValue' argument
		"""
		modifiedArgs = [argumentList[0], argumentList[1], 'true']
		return GrammarCommands.command_setvar(modifiedArgs, grammarParseState)


	@staticmethod
	@validateArguments(argumentCount=2)
	def command_setvarrandom(argumentList, grammarParseState):
		"""
		<$setvarrandom|varname|value1|value2|...>
		Picks one of the provided values at random, and stores it under the provided name, for future use
		"""
		GrammarCommands._checkIfVariableIsWriteable(argumentList[0])
		grammarParseState.variableDict[argumentList[0]] = grammarParseState.random.choice(argumentList[1:])
		return ""

	@staticmethod
	@validateArguments(argumentCount=3)
	def command_hasvar(argumentList, grammarParseState):
		"""
		<$hasvar|varname|stringIfVarnameExists|stringIfVarnameDoesntExist>
		Checks if the variable with the provided name exists. Returns the first string if it does, and the second one if it doesn't
		"""
		if argumentList[0] in grammarParseState.variableDict:
			return argumentList[1]
		else:
			return argumentList[2]

	@staticmethod
	@validateArguments(argumentCount=1)
	def command_var(argumentList, grammarParseState):
		"""
		<$var|varname|[valueIfVarNotSet]>
		Returns the value stored under the provided variable name. The second argument is optional, and if set will be returned if the variable isn't stored
		"""
		# Check if the named variable was stored
		if argumentList[0] in grammarParseState.variableDict:
			return grammarParseState.variableDict[argumentList[0]]
		else:
			# If a second parameter was passed, use it as a fallback value
			if len(argumentList) > 1:
				return argumentList[1]
			# Otherwise, throw an error
			else:
				raise GrammarException("Referenced undefined variable '{}' in 'var' call".format(argumentList[0]))

	@staticmethod
	@validateArguments(argumentCount=2)
	def command_prependtovar(argumentList, grammarParseState):
		"""
		<$prependtovar|varname|stringToPrepend>
		Prepends stringToPrepend to what is stored in the specified variable name, and stores it under that name.
		If the variable wasn't set before, it will be set to 'stringToPrepend'.
		Doesn't print anything, use the $var command to print the result
		"""
		GrammarCommands._checkIfVariableIsWriteable(argumentList[0])
		if argumentList[0] not in grammarParseState.variableDict:
			grammarParseState.variableDict[argumentList[0]] = argumentList[1]
		else:
			grammarParseState.variableDict[argumentList[0]] = argumentList[1] + grammarParseState.variableDict[argumentList[0]]
		return ""

	@staticmethod
	@validateArguments(argumentCount=2)
	def command_appendtovar(argumentList, grammarParseState):
		"""
		<$appendtovar|varname|stringToAppend[|string2ToAppend[|string3ToAppend[|...]]]>
		Appends all the 'stringToAppend' arguments to what is stored in the specified variable name, and stores it under that name.
		If the variable wasn't set before, it will be set to the joined 'stringToAppend's.
		Doesn't print anything, use the $var command to print the result
		"""
		GrammarCommands._checkIfVariableIsWriteable(argumentList[0])
		grammarParseState.variableDict[argumentList[0]] = grammarParseState.variableDict.get(argumentList[0], "") + "".join(argumentList[1:])
		return ""

	@staticmethod
	@validateArguments(argumentCount=1)
	def command_remvar(argumentList, grammarParseState):
		"""
		<$remvar|varname>
		Removes the value stored under this variable name. Does nothing if the variable doesn't exist
		"""
		GrammarCommands._checkIfVariableIsWriteable(argumentList[0])
		if argumentList[0] in grammarParseState.variableDict:
			del grammarParseState.variableDict[argumentList[0]]
		return ""

	@staticmethod
	@validateArguments(argumentCount=1)
	def command_removevar(argumentList, grammarParseState):
		"""
		<$removevar|varname>
		Alias for 'remvar', removes the stored variable
		"""
		return GrammarCommands.command_remvar(argumentList, grammarParseState)

	#################
	#Variable checking

	@staticmethod
	@validateArguments(argumentCount=4)
	def command_ifequals(argumentList, grammarParseState):
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
	def command_if(argumentList, grammarParseState):
		"""
		<$if|varname|stringToMatch|stringIfIdentical|stringIfNotIdentical>
		Alias for 'ifequals' left in for backwards compatibility. Functionality could change in the future, use 'ifequals' instead
		"""
		return GrammarCommands.command_ifequals(argumentList, grammarParseState)

	@staticmethod
	@validateArguments(argumentCount=4)
	def command_ifcontains(argumentList, grammarParseState):
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
	def command_ifstartswith(argumentList, grammarParseState):
		"""
		<$ifstartswith|string|substringToCheckFor|resultIfStringStartsWithSubstring|resultIfStringDoesntStartWithSubstring>
		Checks if the provided string starts with the provided substring
		"""
		return argumentList[2] if argumentList[0].startswith(argumentList[1]) else argumentList[3]

	@staticmethod
	@validateArguments(argumentCount=4)
	def command_ifendswith(argumentList, grammarParseState):
		"""
		<$ifendswith|string|substringToCheckFor|resultIfStringEndsWithSubstring|resultIfStringDoesntEndWithSubstring>
		Checks if the provided string ends with the provided substring
		"""
		return argumentList[2] if argumentList[0].endswith(argumentList[1]) else argumentList[3]

	@staticmethod
	@validateArguments(argumentCount=4)
	def command_ifmatch(argumentList, grammarParseState):
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
			raise GrammarException("Invalid regex '{}' in 'ifmatch' call ({})".format(argumentList[1], e))

	#Numeric functions
	@staticmethod
	@validateArguments(argumentCount=3)
	def command_isnumber(argumentList, grammarParseState):
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
	def command_ifsmaller(argumentList, grammarParseState):
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
	def command_ifsmallerorequal(argumentList, grammarParseState):
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
	def command_increase(argumentList, grammarParseState):
		"""
		<$increase|numberToIncrease[|increaseAmount]>
		Increases the provided number. If the 'increaseAmount' is specified, numberToIncrease is increased by that amount, otherwise 1 is added
		"""
		increaseAmount = 1 if len(argumentList) <= 1 else argumentList[1]
		return argumentList[0] + increaseAmount

	@staticmethod
	@validateArguments(argumentCount=1, numericArgumentIndexes=(0, 1))
	def command_decrease(argumentList, grammarParseState):
		"""
		<$decrease|numberToDecrease[|decreaseAmount]>
		Decreases the provided number. If the 'decreaseAmount' is specified, numberToDecrease is decreased by that amount, otherwise 1 is subtracted
		"""
		decreaseAmount = 1 if len(argumentList) <= 1 else argumentList[1]
		return argumentList[0] - decreaseAmount

	@staticmethod
	@validateArguments(argumentCount=4, numericArgumentIndexes=1)
	def command_islength(argumentList, grammarParseState):
		"""
		<$islength|stringToCheck|lengthToEqual|resultIfStringIsLength|resultOtherwise>
		"""
		if len(argumentList[0]) == argumentList[1]:
			return argumentList[2]
		else:
			return argumentList[3]

	@staticmethod
	@validateArguments(argumentCount=4, numericArgumentIndexes=1)
	def command_isshorter(argumentList, grammarParseState):
		"""
		<$isshorter|stringToCheck|lengthToEqual|resultIfStringIsShorter|resultOtherwise>
		"""
		if len(argumentList[0]) < argumentList[1]:
			return argumentList[2]
		else:
			return argumentList[3]

	@staticmethod
	@validateArguments(argumentCount=4, numericArgumentIndexes=1)
	def command_isshorterorequal(argumentList, grammarParseState):
		"""
		<$isshorterorequal|stringToCheck|lengthToEqual|resultIfStringIsShorterOrEqual|resultOtherwise>
		"""
		if len(argumentList[0]) <= argumentList[1]:
			return argumentList[2]
		else:
			return argumentList[3]

	@staticmethod
	@validateArguments(argumentCount=2)
	def command_switch(argumentList, grammarParseState):
		"""
		<$switch|stringToCheck|case1:stringIfCase1|case2:stringIfCase2|...|[_default:stringIfNoCaseMatch]>
		Checks which provided case matches the string to check. The '_default' field is not mandatory, but if it's missing and no suitable case can be found, an error is returned
		"""
		#First construct the comparison dict
		caseDict = {}
		for caseString in argumentList[1:]:
			if ":" not in caseString:
				raise GrammarException("Missing colon in parameter '{}' to 'switch' command".format(caseString))
			case, stringIfCase = caseString.split(':', 1)
			caseDict[case] = stringIfCase
		#Then see if we can find a matching case
		if argumentList[0] in caseDict:
			return caseDict[argumentList[0]]
		elif '_default' in caseDict:
			return caseDict['_default']
		else:
			raise GrammarException("'switch' command contains no case for '{}', and no '_default' fallback case".format(argumentList[0]))

	#################
	#Parameter functions

	@staticmethod
	@validateArguments(argumentCount=2)
	def command_hasparams(argumentList, grammarParseState):
		"""
		<$hasparams|stringIfHasParams|stringIfDoesntHaveParams>
		Checks if there are any parameters provided. Returns the first string if any parameters exist, and the second one if not
		"""
		if grammarParseState.variableDict.get('_params', None):
			return argumentList[0]
		else:
			return argumentList[1]

	@staticmethod
	@validateArguments(argumentCount=3)
	def command_hasparameter(argumentList, grammarParseState):
		"""
		<$hasparameter|paramToCheck|stringIfHasParam|stringIfDoesntHaveParam>
		Checks if the the provided parameter string is equal to a string. Returns the first string if it matches, and the second one if it doesn't.
		If no parameter string was provided, the 'doesn't match' string is returned
		"""
		if '_params' in grammarParseState.variableDict and argumentList[0] == grammarParseState.variableDict['_params']:
			return argumentList[1]
		else:
			return argumentList[2]

	@staticmethod
	@validateArguments(argumentCount=3)
	def command_hasparam(argumentList, grammarParseState):
		"""
		<$hasparam|paramToCheck|stringIfHasParam|stringIfDoesntHaveParam>
		Checks if the the provided parameters are equal to a string. Returns the first string if it matches, and the second one if it doesn't.
		If no parameter string was provided, the 'doesn't match' string is returned
		"""
		return GrammarCommands.command_hasparameter(argumentList, grammarParseState)

	@staticmethod
	@validateArguments(argumentCount=0)
	def command_params(argumentList, grammarParseState):
		"""
		<$params>
		Returns the user-provided parameter string, or an empty string if no parameter string was provided
		"""
		# Fill in the provided parameter(s) in this field
		return grammarParseState.variableDict.get('_params', "")

	#################
	#Random choices

	@staticmethod
	@validateArguments(argumentCount=2, numericArgumentIndexes=(0, 1))
	def command_randint(argumentList, grammarParseState):
		"""
		<$randint|lowerBound|higherBound>
		Returns a number between the lower and upper bound, inclusive on both sides
		"""
		if argumentList[1] < argumentList[0]:
			value = grammarParseState.random.randint(argumentList[1], argumentList[0])
		else:
			value = grammarParseState.random.randint(argumentList[0], argumentList[1])
		return str(value)

	@staticmethod
	@validateArguments(argumentCount=2, numericArgumentIndexes=(0, 1))
	def command_randomnumber(argumentList, grammarParseState):
		"""
		<$randomnumber|lowerBound|higherBound>
		Returns a number between the lower and upper bound, inclusive on both sides
		"""
		return GrammarCommands.command_randint(argumentList, grammarParseState)

	@staticmethod
	@validateArguments(argumentCount=2, numericArgumentIndexes=(0, 1, 2, 3))
	def command_dice(argumentList, grammarParseState):
		"""
		<$dice|numberOfDice|numberOfSides|[lowestRollsToRemove|highestRollsToRemove]>
		Rolls a number of dice and returns the total. First argument is how many dice to roll, second argument is how many sides each die should have
		The third argument is how many of the lowest rolls should be removed. So if you roll three dice - say 1, 3, 4 - and specify 1 for this argument, it'll ignore the 1 and return 7
		The fourth argument works the same way, except for the highest rolls (so the total would be 4 in the example if you specify 1 here instead of 1 for lowest)
		The third and fourth arguments are optional
		"""
		if argumentList[0] <= 0 or argumentList[1] <= 0:
			raise GrammarException("Dice command can't handle negative values or zero")
		diceLimit = 1000
		sidesLimit = 10**9
		if argumentList[0] > diceLimit or argumentList[1] > sidesLimit:
			raise GrammarException("Dice count shouldn't be higher than {:,} and sides count shouldn't be higher than {:,}".format(diceLimit, sidesLimit))

		#Check if we need to remove some highest or lowest values later
		lowestRollsToRemove = 0
		highestRollsToRemove = 0
		if len(argumentList) > 2:
			if argumentList[2] <= 0 or argumentList[2] >= argumentList[0]:
				raise GrammarException("Invalid number for lowestRollsToRemove parameter, it's not allowed to be lower than 0 or equal to or larger than the number of rolls")
			lowestRollsToRemove = argumentList[2]
			if len(argumentList) > 3:
				if argumentList[3] <= 0 or argumentList[3] >= argumentList[0]:
					raise GrammarException("Invalid number for highestRollsToRemove parameter, it's not allowed to be lower than 0 or equal to or larger than the number of rolls")
				highestRollsToRemove = argumentList[3]
				if lowestRollsToRemove + highestRollsToRemove >= argumentList[0]:
					raise GrammarException("Lowest and highest rolls to remove are equal to or larger than the total number of rolls")

		#Roll the dice!
		rolls = []
		for i in range(argumentList[0]):
			rolls.append(grammarParseState.random.randint(1, argumentList[1]))
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
	def command_choose(argumentList, grammarParseState):
		"""
		<$choose|option1|option2|...>
		Chooses a random option from the ones provided. Useful if the options are short and it'd feel like a waste to make a separate field for each of them
		"""
		return grammarParseState.random.choice(argumentList)

	@staticmethod
	@validateArguments(argumentCount=3, numericArgumentIndexes=0)
	def command_choosemultiple(argumentList, grammarParseState):
		"""
		<$choosemultiple|numberOfOptionsToChoose|separator|option1|option2|...>
		Chooses the provided number of random options from the option list, and returns them in a random order,	with the provided separator between the options
		"""
		numberOfOptionsToChoose = argumentList.pop(0)
		separator = argumentList.pop(0)
		if numberOfOptionsToChoose <= 0 or numberOfOptionsToChoose >= len(argumentList):
			#Invalid choice number, just shuffle the list and return that
			grammarParseState.random.shuffle(argumentList)
			return separator.join(argumentList)
		#Number of options to choose is less than number of provided options, pick that number
		return separator.join(grammarParseState.random.sample(argumentList, numberOfOptionsToChoose))

	@staticmethod
	@validateArguments(argumentCount=1)
	def command_choosewithchance(argumentList, grammarParseState):
		"""
		<$choosewithchance|chancegroup1:optionIfChance[|chancegroup2:optionIfChance[|...]]>
		Works the same as a separate chance dict field: Chances have to be between 0 and 100 (inclusive)
		When called, a random number is chosen also between 1 and 100. Then the proper chance group is chosen by picking the lowest chancegroup chance that's larger than the random number
		So if the command field is '<$choosewithchance|15:option1|100:option2>', if the random number is 8, 'option1' is chosen. If then random number is 64, 'option2' is chosen
		If no chancegroup is provided for the random number, and empty string is returned
		"""
		chanceDict = {}
		for arg in argumentList:
			if not ":" in arg:
				raise GrammarException("Invalid option '{}' in 'choosewithchance' field, arguments should be 'chance:optionIfChance'".format(arg))
			chance, optionIfChance = arg.split(":", 1)
			try:
				chance = int(chance, 10)
			except ValueError:
				raise GrammarException("Chance '{}' from 'choosewithchance' field argument '{}' could not be parsed to a number".format(chance, arg))
			chanceDict[chance] = optionIfChance
		return Command.parseChanceDict(chanceDict, grammarParseState)

	@staticmethod
	@validateArguments(argumentCount=2)
	def command_chooseunique(argumentList, grammarParseState):
		"""
		<$chooseunique|fieldOrListToPickFrom|option1ToSkip[|option2ToSkip[|...]]>
		Pick a random entry from the provided field or list, but it will never return one of the provided optionsToSkip
		'fieldOrListToPickFrom' can be either the name of a list field in the grammar file, or it can be a colon-separated list of possible options
		"""
		if argumentList[0] in grammarParseState.grammarDict:
			listToPickFrom = grammarParseState.grammarDict[argumentList[0]]
			if not isinstance(listToPickFrom, list):
				raise GrammarException("Invalid first argument specified in 'chooseunique' command: The grammar field '{}' is not a list".format(listToPickFrom))
			valuesToSkip = argumentList[1:]
			#Make a list of indexes to skip in the list to pick from. We'll later pick a random index, and adjust based on this list
			indexesToSkip = []
			for entryIndex, entry in enumerate(listToPickFrom):
				if entry in valuesToSkip:
					indexesToSkip.append(entryIndex)
			if len(indexesToSkip) >= len(listToPickFrom):
				#We can't pick any entry without returning a duplicate. Give up
				raise GrammarException("'{}chooseunique|{}' command can't pick an option that isn't a duplicate".format(fieldCommandPrefix, argumentList[0]))
			#Pick a random index, then increase that index for each indexToSkip below or equal to the picked index
			#This should ensure we don't pick a value we should skip, while giving the allowed entries an equal chance to be picked
			randomIndex = grammarParseState.random.randrange(0, len(listToPickFrom) - len(indexesToSkip))
			for indexToSkip in indexesToSkip:
				#For each skip index smaller than the one we picked, we need to move up the picked index, to compensate for the reduced range when picking the index
				if indexToSkip <= randomIndex:
					randomIndex += 1
				else:
					#Skip indexes higher than our picked index don't matter, so stop checking
					break
			return listToPickFrom[randomIndex]
		elif ":" in argumentList[0]:
			listToPickFrom = argumentList[0].split(":")
			for index in range(1, len(argumentList)):
				#Use 'while' instead of 'if' to handle possible duplicate values in 'listToPickFrom'
				while argumentList[index] in listToPickFrom:
					listToPickFrom.remove(argumentList[index])
			if len(listToPickFrom) == 0:
				raise GrammarException("'{}chooseunique' command can't pick an option that isn't a duplicate".format(fieldCommandPrefix, argumentList[0]))
			return grammarParseState.random.choice(listToPickFrom)
		else:
			raise GrammarException("Invalid first argument '{}' specified in 'chooseunique' command: It should either refer to a list field in the grammar or be a colon-separated list of options".format(argumentList[0]))

	@staticmethod
	@validateArguments(argumentCount=1, numericArgumentIndexes=1)
	def command_file(argumentList, grammarParseState):
		"""
		<$file|filename[|lineNumber]>
		Load a random line from the specified file. Useful for not cluttering up the grammar file with a lot of options
		The file has to exists in the same directory the grammar file is in
		If the line number parameter is specified, that specific line will be returned instead of a random line (line count starts at 0)
		Specifying a line number is mainly useful for testing
		"""
		return Command.getLineFromFile(grammarParseState.random, argumentList[0], lineNumber=None if len(argumentList) == 1 else argumentList[1])

	#################
	#Text formatting

	@staticmethod
	@validateArguments(argumentCount=1)
	def command_lowercase(argumentList, grammarParseState):
		"""
		<$lowercase|stringToMakeLowercase>
		Returns the provided string with every letter made lowercase
		"""
		return GrammarCommands._startFormattingBlock(grammarParseState, argumentList[0], string.lower)

	@staticmethod
	@validateArguments(argumentCount=1)
	def command_uppercase(argumentList, grammarParseState):
		"""
		<$uppercase|stringToMakeUppercase>
		Returns the provided string with every letter made uppercase
		"""
		return GrammarCommands._startFormattingBlock(grammarParseState, argumentList[0], string.upper)

	@staticmethod
	@validateArguments(argumentCount=1)
	def command_titlecase(argumentList, grammarParseState):
		"""
		<$titlecase|stringToMakeTitlecase>
		Returns the provided string with every word starting with a capital letter and the rest of the word lowercase
		"""
		return GrammarCommands._startFormattingBlock(grammarParseState, argumentList[0], string.capwords)

	@staticmethod
	@validateArguments(argumentCount=1)
	def command_firstletteruppercase(argumentList, grammarParseState):
		"""
		<$firstletteruppercase|stringToFormat>
		Returns the provided string with the first character made uppercase and the rest left as provided
		"""
		if not argumentList[0]:
			#If the provided string is empty, do nothing
			return ""
		return GrammarCommands._startFormattingBlock(grammarParseState, argumentList[0], lambda s: s[0].upper() + s[1:])

	@staticmethod
	@validateArguments(argumentCount=1)
	def command_bold(argumentList, grammarParseState):
		"""
		<$bold|stringToMakeBold>
		Returns the provided string formatted so it looks like bold text in IRC
		"""
		return IrcFormattingUtil.makeTextBold(argumentList[0])

	@staticmethod
	@validateArguments(argumentCount=1, numericArgumentIndexes=0)
	def command_numbertotext(argumentList, grammarParseState):
		"""
		<$numbertotext|numberToDisplayAsText>
		Converts the provided number to its English representation. For instance, '4' would get turned into 'four'
		"""
		return Command.numberToText(argumentList[0])

	@staticmethod
	@validateArguments(argumentCount=1)
	def command_escape(argumentList, grammarParseState):
		"""
		<$escape|stringToEscape>
		Escapes all the special grammar command characters in the provided string, so the resulting string doesn't get executed as a grammar command
		"""
		return escapeString(argumentList[0])

	@staticmethod
	@validateArguments(argumentCount=1)
	def command_unescape(argumentList, grammarParseState):
		"""
		<$unescape|stringToUnscape>
		Unescapes all the special grammar command characters in the provided string, so the resulting string can get executed as a grammar command
		"""
		return unescapeString(argumentList[0])

	@staticmethod
	@validateArguments(argumentCount=1, numericArgumentIndexes=0)
	def command_endofformattingblock(argumentList, grammarParseState):
		"""
		<$endofformattingblock|startIndexOfFormattingBlock>
		This command is only for internal use, and shouldn't be used in grammar files
		It is used to indicate the end of a formatting block, when we know which text we for instance need to make lowercase
		This is needed because formatting can only be properly done after all grammar blocks are fully parsed
		The argument is the index in the outputstring where the formatting block starts. It needs to have been stored before,
		by calling the '_startFormattingBlock' method from another grammar command method
		:type grammarParseState: GrammarParseState
		"""
		if not grammarParseState.formattingBlocks:
			raise GrammarException("Unable to process end of formatting block because no formatting blocks are stored, {}".format(grammarParseState))
		if argumentList[0] not in grammarParseState.formattingBlocks:
			raise GrammarException("Can't format block starting at index {} because no info on it is stored, {}".format(argumentList[0], grammarParseState))
		formattingFunction = grammarParseState.formattingBlocks[argumentList[0]].pop(0)
		#Because formatting can change parse string length, we need to know the length change,
		# so we can update the new parsing starting index
		formatString = grammarParseState.currentParseString[argumentList[0]:grammarParseState.currentParseStringIndex]
		formatStringLengthBeforeFormatting = len(formatString)
		formatString = formattingFunction(formatString)
		parseStringLengthChange = len(formatString) - formatStringLengthBeforeFormatting
		#Update the parse index so we continue at the same place in the parse string as before
		grammarParseState.currentParseStringIndex += parseStringLengthChange
		#Insert the formatted string back into the parse string
		grammarParseState.currentParseString = grammarParseState.currentParseString[:argumentList[0]] + formatString + grammarParseState.currentParseString[grammarParseState.currentParseStringIndex:]
		#If this was the last formatting block for the provided start index, remove it from the formattingblocks dict
		if not grammarParseState.formattingBlocks[argumentList[0]]:
			del grammarParseState.formattingBlocks[argumentList[0]]
		#Done!
		return ""

	#################
	#Miscellaneous

	@staticmethod
	@validateArguments(argumentCount=3, numericArgumentIndexes=(3,))
	def command_replace(argumentList, grammarParseState):
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
				raise GrammarException("Invalid optional replacement count value '{}' passed to 'replace' call".format(argumentList[3]))
		#Now replace what we need to replace
		return argumentList[0].replace(argumentList[1], argumentList[2], replacementCount)

	@staticmethod
	@validateArguments(argumentCount=3, numericArgumentIndexes=(3,))
	def command_regexreplace(argumentList, grammarParseState):
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
				raise GrammarException("Invalid optional replacement count value '{}' passed to 'regexreplace' call".format(argumentList[3]))
		try:
			# Unescape any characters inside the regex that are used both in regexes and in grammar command (like < and |)
			regex = re.compile(re.sub(r"/(.)", r"\1", argumentList[1]), flags=re.DOTALL)  # DOTALL so it can handle newlines in messages properly
			return regex.sub(argumentList[2], argumentList[0], count=replacementCount)
		except re.error as e:
			raise GrammarException("Unable to parse regular expression '{}' in 'regexreplace' call ({})".format(argumentList[1], e.message))

	@staticmethod
	@validateArguments(argumentCount=2, numericArgumentIndexes=2)
	def command_replacerandomword(argumentList, grammarParseState):
		"""
		<$replacerandomword|stringToReplaceIn|replacementString[|amountOfWordsToReplace]>
		Replaces a random word in the provided 'stringToReplace' with the 'replacementString', where words are assumed to be separated by spaces
		If the 'amountOfWordsToReplace' is provided, this many words are replaced instead of just one
		"""
		inputParts = argumentList[0].split(' ')
		replacementCount = max(1, argumentList[2]) if len(argumentList) > 2 else 1
		if replacementCount >= len(inputParts):
			# Asked to replace more sections than we can, replace everything, with a space in between
			if replacementCount == 1:
				return argumentList[1]
			else:
				return (argumentList[1] + " ") * (replacementCount - 1) + argumentList[1]
		else:
			indexesToReplace = grammarParseState.random.sample(range(0, len(inputParts)), replacementCount)
			for indexToReplace in indexesToReplace:
				inputParts[indexToReplace] = argumentList[1]
			return " ".join(inputParts)

	@staticmethod
	@validateArguments(argumentCount=2, numericArgumentIndexes=0)
	def command_repeat(argumentList, grammarParseState):
		"""
		<$repeat|timesToRepeat|stringToRepeat[|stringToPutBetweenRepeats]>
		Repeats the provided stringToRepeat the amount of times specified in timesToRepeat. If timesToRepeat is zero or less, nothing will be returned
		If the third argument stringToPutBetweenRepeats is specified, this string will be inserted between each repetition of stringToRepeat
		"""
		#If there's nothing to repeat, stop immediately
		if argumentList[0] <= 0:
			return ""
		#Check if there's something to put between the repeated string
		joinString = None
		if len(argumentList) > 2:
			joinString = argumentList[2]
		#Do the actual repeating (-1 because we already start with one repetition)
		resultString = argumentList[1]
		for i in range(argumentList[0] - 1):
			if joinString:
				resultString += joinString
			resultString += argumentList[1]
		#Done!
		return resultString

	@staticmethod
	@validateArguments(argumentCount=1)
	def command_modulecommand(argumentList, grammarParseState):
		"""
		<$modulecommand|commandName[|argument1|argument2|key1=value1|key2=value2|...]>
		Runs a shared command in another bot module. The first parameter is the name of that command, the rest are unnamed and named parameters to pass on, and are all optional
		"""
		if argumentList[0] == Command.sharedCommandFunctionName:
			raise GrammarException("Please use the '{}generate' grammar command to call another generator".format(fieldCommandPrefix))
		if not GlobalStore.commandhandler.hasCommandFunction(argumentList[0]):
			raise GrammarException("Unknown module command '{}'".format(argumentList[0]))
		# Turn the arguments into something we can call a function with
		commandArguments = []
		keywordCommandArguments = {}
		for argument in argumentList[1:]:
			# Remove any character escaping (so arguments can contain '<' without messing up)
			argument = re.sub(r"/(.)", r"\1", argument)
			if '=' not in argument:
				commandArguments.append(argument)
			else:
				key, value = argument.split('=', 1)
				keywordCommandArguments[key] = value
		# Call the module function!
		moduleCommandResult = GlobalStore.commandhandler.runCommandFunction(argumentList[0], "", *commandArguments, **keywordCommandArguments)
		# Escape special characters in the result, so for instance |' don't confuse future command calls
		moduleCommandResult = escapeString(moduleCommandResult)
		#Everything parsed and converted fine
		return moduleCommandResult

	@staticmethod
	@validateArguments(argumentCount=3)
	def command_hasgenerator(argumentList, grammarParseState):
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
	def command_generate(argumentList, grammarParseState):
		"""
		<$generate|generatorName[|shouldCopyVariableDict[|parameter1[|parameter2[...]]]]>
		Run a different generator specified by 'generatorName' and get the result. If 'shouldCopyVariableDict' is 'true', then all variables stored by the called generator will be copied to our variableDict
		You can also pass parameters to that generator by adding them as arguments here
		Please note that the iterations of the called generator count against the current iteration limit. So it's not possible to use this to bypass the iteration limit
		"""
		#To make sure the combined iterations don't exceed the limit, pass the current iteration to the execution method
		calledGeneratorVariableDict = {'_iteration': grammarParseState.variableDict['_iteration']}
		resultString = Command.executeGrammarByTrigger(argumentList[0].lower(), parameters=argumentList[2:], variableDict=calledGeneratorVariableDict, seedInput=grammarParseState.seed)
		#Copy the variables from the called generator if requested
		if len(argumentList) > 1 and GrammarCommands._evaluateAsBoolean(argumentList[1]):
			grammarParseState.variableDict.update(calledGeneratorVariableDict)
		else:
			#Set the iteration that the called generator reached as our current iteration, so we can't exceed the iteration limit
			grammarParseState.variableDict['_iteration'] = calledGeneratorVariableDict['_iteration']
		return resultString

	@staticmethod
	@validateArguments(argumentCount=1)
	def command_generator(argumentList, grammarParseState):
		"""
		Alias for '$generate'
		"""
		return GrammarCommands.command_generate(argumentList, grammarParseState)

	@staticmethod
	@validateArguments(argumentCount=1)
	def command_list(argumentList, grammarParseState):
		"""
		<$list|listname[|searchquery]>
		Use the List module to get a random entry from the list specified by 'listname'. Optionally add a searchquery to limit the result to list entries that match the searchquery
		"""
		# The 'getRandomListEntry' method needs a servername, a channelname, a listname, and an optional searchquery. The first two are in the variableDict, the second two are the arguments to this command
		return GlobalStore.commandhandler.runCommandFunction('getRandomListEntry', "", grammarParseState.variableDict['_sourceserver'], grammarParseState.variableDict['_sourcechannel'],
															 argumentList[0], argumentList[1] if len(argumentList) > 1 else None, grammarParseState.random)

	@staticmethod
	@validateArguments(argumentCount=0)
	def command_hide(argumentList, grammarParseState):
		"""
		<$hide[|optionalText]>
		This command returns nothing. Useful if you want to add comments in your grammar.
		Mainly added for backwards compatibility with the old 'extraOptions' system which had a 'hide' option
		"""
		return ""

	@staticmethod
	@validateArguments(argumentCount=1)
	def command_stop(argumentList, grammarParseState):
		"""
		<$stop|stopMessage>
		This command stops execution of the generator. The stop message will be displayed to the user.
		This can be useful if for instance the grammar only accepts certain parameters and a wrong one is provided
		"""
		raise GrammarException(argumentList[0] if argumentList[0] else "Grammar file '{}' execution stopped with Stop command".format(grammarParseState.grammarDict.get('_name', "[[unknown]]")), shouldLogError=False)


class GrammarException(CommandException):
	def __init__(self, message, shouldLogError=True):
		super(GrammarException, self).__init__(message, shouldLogError)


def escapeString(stringToEscape):
	"""
	Escape special grammar characters in the provided string
	Special characters are <, |, and >, and the escape character is /
	:param stringToEscape: The string to escape special grammar characters in
	:return: The provided string with the special characters escaped
	"""
	return re.sub(r"([</|>])", r"/\1", stringToEscape)

def unescapeString(stringToUnescape):
	"""
	Unscape special grammar characters in the provided string
	Special characters are <, |, and >, and the escape character is /
	:param stringToUnescape: The string to unescape special grammar characters in
	:return: The provided string with the special characters unescaped
	"""
	return re.sub(r"/([</|>])", r"\1", stringToUnescape)

