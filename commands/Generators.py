import glob, json, os, random, re

from CommandTemplate import CommandTemplate
from IrcMessage import IrcMessage
import SharedFunctions
import GlobalStore


class Command(CommandTemplate):
	triggers = ['generate', 'gen']
	helptext = "Generate random stories or words. Call a specific generator with '{commandPrefix}generate [genName]'. Enter 'random' to let me pick, or choose from: "

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
					if generator.__doc__ :
						helptext = generator.__doc__.strip()
						#Remove the newlines and tabs
						helptext = re.sub(r"[\n\t]+", " ", helptext)
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
				#Grammar file! Send it to the parser
				with open(os.path.join(self.filesLocation, wantedGenerator), "r") as grammarfile:
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
		singleNumberNames = {0: u"zero", 1: u"one", 2: u"two", 3: u"three", 4: u"four", 5: u"five", 6: u"six", 7: u"seven",
							 8: u"eight", 9: u"nine", 10: u"ten", 11: u"eleven", 12: u"twelve", 13: u"thirteen",
							 14: u"fourteen", 15: u"fifteen", 16: u"sixteen", 17: u"seventeen", 18: u"eighteen", 19: u"nineteen"}
		if number in singleNumberNames:
			return singleNumberNames[number]
		else:
			#TODO: Handle numbers larger than 19 by combining words, like "twenty" and "two" for 22
			return unicode(number)

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
		return arg.lower() in ("f", "female", "woman", "girl", "m", "male", "man", "boy")

	@staticmethod
	def getGenderWords(genderString, allowUnspecified=True):
		if genderString is not None:
			genderString = genderString.lower()
		if not genderString:
			# No gender specified, pick one on our own
			roll = random.randint(1, 100)
			if allowUnspecified and roll <= 45 or roll <= 50:
				gender = "f"
			elif allowUnspecified and roll <= 90 or roll <= 100:
				gender = "m"
			else:
				gender = "misc"
		elif genderString in ("f", "female", "woman", "girl"):
			gender = "f"
		elif genderString in ("m", "male", "man", "boy"):
			gender = "m"
		elif allowUnspecified:
			gender = "misc"
		else:
			return False

		if gender == "f":
			return {"gender": "f", "genderNoun": "Woman", "genderNounYoung": "Girl", "pronoun": "she",
								 "possessivePronoun": "her", "personalPronoun": "her"}
		elif gender == "m":
			return {"gender": "m", "genderNoun": "Man", "genderNounYoung": "Boy", "pronoun": "he",
								 "possessivePronoun": "his", "personalPronoun": "him"}
		return {"gender": "misc", "genderNoun": "Person", "genderNounYoung": "Kid", "pronoun": "they",
								 "possessivePronoun": "their", "personalPronoun": "them"}

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

		#Start the parsing!
		return self.parseGrammarString(startString, grammarDict, parameters, variableDict)

	def parseGrammarString(self, grammarString, grammar, parameters=None, variableDict=None):
		if variableDict is None:
			variableDict = {}

		#Parse the parameters as a string (if there are any) in such a way that users don't have access to special fields
		# This to prevent abuse like infinite loops or creating heavy load
		if parameters:
			parameterString = " ".join(parameters).decode("utf-8", errors="replace")
			parameterString = parameterString.replace(u"/", u"//").replace(u"<", u"/<")
		else:
			parameterString = None

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
					success, parsedGrammarBlock = self.parseGrammarBlock(grammarParts, grammar, parameterString, variableDict)
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

	def parseGrammarBlock(self, grammarParts, grammar, parameterString=None, variableDict=None):
		fieldKey = grammarParts.pop(0)
		replacement = u""

		#If the last field starts with '&', it specifies special options, like making text bold.
		# Multiple options are separated by commas. Retrieve those options
		extraOptions = []
		if grammarParts and grammarParts[-1].startswith(u'&'):
			extraOptions = grammarParts.pop()[1:].split(u',')

		if fieldKey.startswith(u"_"):
			#Check if the grammar commands class has a method to deal with the provided command
			commandName = fieldKey[1:].lower()
			commandMethod = getattr(GrammarCommands, commandName, None)
			#Also try a 'Command' suffix, so commands can be called the same as Python reserved words without breaking anything
			if not commandMethod:
				commandMethod = getattr(GrammarCommands, commandName + 'Command', None)
			#Check if the command is a registered one
			if commandMethod:
				#Registered function! Call it, and return the result. Whether the call went right or wrong will be handled by the calling function
				isSuccess, replacement = commandMethod(grammarParts, grammar, variableDict, parameterString)
				#If something went wrong, stop now. The replacement string should be an error message, pass that along too
				if not isSuccess:
					return (False, replacement)
			else:
				return (False, u"Unknown command '{key}' in field '<{key}{args}>' found!".format(key=fieldKey, args=u"|" + u"|".join(grammarParts) if grammarParts else u""))
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
				roll = random.randint(1, 100)
				for chance in sorted(grammar[fieldKey].keys()):
					if roll <= int(chance):
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
					return (False, u"Invalid 'storeas' argument for field '<{}|{}|&{}>', should be 'storeas:[varname]'".format(fieldKey, u"|".join(grammarParts), u",".join(extraOptions)))
				varname = option.split(u':', 1)[1]
				variableDict[varname] = replacement
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


class GrammarCommands(object):
	"""
	A class to hold all the commands that can be called from grammar files
	Each function should have the same name as it has in the grammar file, including case
	The parameters a function accepts should always be the same:
	-argumentList, which is a list of the arguments provided to the function
	-grammarDict, the entire grammar dictionary, in case a field from that is needed. Should not be changed
	-variableDict, the dictionary with variables set during grammar parsing. Functions are allowed to change this
	-parameterString, the string passed along with the call to the grammar parser
	Each function should return a tuple. The first value should be a boolean, set to True if executing the command succeeded, or to False if it failed
	The second value should be a unicode string. If command execution succeeded, it should be the string that should be put in the grammar output string
	 instead of this command block. If execution failed, it should be the reason why it failed
	"""

	#Shared internal methods
	@staticmethod
	def _constructNotEnoughParametersErrorMessage(commandName, requiredNumber, foundNumber, usageString):
		return u"'{}' call needs at least {} parameters, only found {}. Usage: {}".format(commandName, requiredNumber, foundNumber, usageString)

	#Saving and loading variables
	@staticmethod
	def setvar(argumentList, grammarDict, variableDict, parameterString):
		"""
		<_setvar|varname|value>
		Stores a value under the provided name, for future use
		"""
		if len(argumentList) < 2:
			return (False, GrammarCommands._constructNotEnoughParametersErrorMessage(u"setvar", 2, len(argumentList)))
		variableDict[argumentList[0]] = argumentList[1]
		return (True, u"")

	@staticmethod
	def setvarrandom(argumentList, grammarDict, variableDict, parameterString):
		"""
		<_setvarrandom|varname|value1|value2|value3>
		Picks one of the provided values at random, and stores it under the provided name, for future use
		"""
		if len(argumentList) < 2:
			return (False, GrammarCommands._constructNotEnoughParametersErrorMessage(u"setvarrandom", 2, len(argumentList)))
		variableDict[argumentList[0]] = random.choice(argumentList[1:])
		return (True, u"")

	@staticmethod
	def hasvar(argumentList, grammarDict, variableDict, parameterString):
		"""
		<_hasvar|varname|stringIfVarnameExists|stringIfVarnameDoesntExist>
		Checks if the provided variable exists. Returns the first string if it does, and the second one if it doesn't
		"""
		if len(argumentList) < 3:
			return (False, GrammarCommands._constructNotEnoughParametersErrorMessage(u"hasvar", 3, len(argumentList)))
		if argumentList[0] in variableDict:
			return (True, argumentList[1])
		else:
			return (True, argumentList[2])

	@staticmethod
	def var(argumentList, grammarDict, variableDict, parameterString):
		"""
		<_variable|varname|[valueIfVarNotSet]>
		Returns the value stored under the provided variable name. The second argument is optional, and if set will be returned if the variable isn't stored
		"""
		if len(argumentList) < 1:
			return (False, u"The call to '_var' doesn't have any parameters")
		# Check if the named variable was stored
		if argumentList[0] in variableDict:
			return (True, variableDict[argumentList[0]])
		else:
			# If a second parameter was passed, use it as a fallback value
			if len(argumentList) > 1:
				return (True, argumentList[1])
			# Otherwise, throw an error
			else:
				return (False, u"Referenced undefined variable '{}'".format(argumentList[0]))

	@staticmethod
	def remvar(argumentList, grammarDict, variableDict, parameterString):
		"""
		<_remvar|varname>
		Removes the value stored under this variable name. Does nothing if the variable doesn't exist
		"""
		if len(argumentList) > 0 and argumentList[0] in variableDict:
			del variableDict[argumentList[0]]
		return (True, u"")

	@staticmethod
	def removevar(argumentList, grammarDict, variableDict, parameterString):
		"""
		<_removevar|varname>
		Alias for 'remvar', removes the stored variable
		"""
		return GrammarCommands.remvar(argumentList, grammarDict, variableDict, parameterString)


	#Variable checking
	@staticmethod
	def ifCommand(argumentList, grammarDict, variableDict, parameterString):
		"""
		<_if|varname=string|stringIfTrue|stringIfFalse>
		Checks if the variable is set to the specified value. Returns the first string if it is, and the second if it isn't. Use '_params' as varname to check the parameters
		"""
		if len(argumentList) < 3:
			return (False, GrammarCommands._constructNotEnoughParametersErrorMessage(u"if", 3, len(argumentList)))
		if u'=' not in argumentList[0]:
			return (False, u"The first parameter in an '_if' call should be formatted like '[varname]=string', '=' is missing")
		#Split up the first parameter into a name and the wanted value
		firstArgumentParts = argumentList[0].split(u'=', 1)
		#If the first part is '_params', use the parameter string
		if firstArgumentParts[0] == u"_params":
			stringToCheck = parameterString if parameterString else u""
		#Otherwise check if it's a valid variable name
		elif firstArgumentParts[0] not in variableDict:
			return (False, u"Referenced undefined variable '{}' in '_if' call".format(firstArgumentParts[0]))
		else:
			stringToCheck = variableDict[firstArgumentParts[0]]
		#Check which string we need to return
		if stringToCheck == firstArgumentParts[1]:
			return (True, argumentList[1])
		else:
			return (True, argumentList[2])

	@staticmethod
	def ifcontains(argumentList, grammarDict, variableDict, parameterString):
		"""
		<_ifcontains|varname/string|substringToCheckFor|stringIfSubstringInString|stringIfSubstringNotInString>
		Checks if the variable contains the provided substring. If varname is '_params', the provided parameters will be checked against
		"""
		if len(argumentList) < 4:
			return (False, GrammarCommands._constructNotEnoughParametersErrorMessage(u"ifcontains", 4, len(argumentList)))
		# Check if we need the parameters, a variable, or literally the entered string
		stringToCheck = argumentList[0]
		if argumentList[0] == u"_params":
			stringToCheck = parameterString if parameterString else u""
		elif argumentList[0] in variableDict:
			stringToCheck = variableDict[argumentList[0]]
		# Now do the 'contains' check
		if argumentList[1] in stringToCheck:
			return (True, argumentList[2])
		else:
			return (True, argumentList[3])

	@staticmethod
	def ifmatch(argumentList, grammarDict, variableDict, parameterString):
		"""
		<_ifmatch|string/varname|regexToMatch|stringIfMatch|stringIfNoMatch>
		Checks if the variable matches the provided regular expression. If varname is '_params', the provided parameters will be checked against
		"""
		if len(argumentList) < 4:
			return (False, GrammarCommands._constructNotEnoughParametersErrorMessage(u"ifmatch", 4, len(argumentList)))
		if argumentList[0] == u"_params":
			stringToMatchAgainst = parameterString if parameterString else u""
		elif argumentList[0] in variableDict:
			stringToMatchAgainst = variableDict[argumentList[0]]
		else:
			stringToMatchAgainst = argumentList[0]
		# Make sure we un-escape the regex, so it can use characters like < and | without messing up our parsing
		regex = re.compile(re.sub(r"/(.)", r"\1", argumentList[1]), flags=re.DOTALL)  # DOTALL so it can handle newlines in messages properly
		try:
			if re.search(regex, stringToMatchAgainst):
				return (True, argumentList[2])
			else:
				return (True, argumentList[3])
		except re.error as e:
			return (False, u"Invalid regex '{}' in '_ifmatch' call ({})".format(argumentList[1], e.message))

	@staticmethod
	def switch(argumentList, grammarDict, variableDict, parameterString):
		"""
		<_switch|varname/_params|case1:stringIfCase1|case2:stringIfCase2|...|_default:stringIfNoCaseMatch>
		Checks which provided case matches the stored variable. If varname is '_params', the provided parameters will be checked against
		The '_default' field is not mandatory, if it's missing an empty string will be returned
		"""
		if len(argumentList) < 2:
			return (False, GrammarCommands._constructNotEnoughParametersErrorMessage(u"switch", 2, len(argumentList)))
		#First construct the comparison dict
		caseDict = {}
		for caseString in argumentList[1:]:
			if u":" not in caseString:
				return (False, u"Missing colon in parameter '{}' to '_switch' field".format(caseString))
			case, stringIfCase = caseString.split(u':', 1)
			caseDict[case] = stringIfCase
		#Now try to see which provided case, if any, we should use
		if argumentList[0] == u"_params" and parameterString in caseDict:
			#Match the parameter string
			return (True, caseDict[parameterString])
		elif argumentList[0] not in variableDict:
			#Tried to match against a variable that doesn't exist
			return (False, u"Variable '{}' was specified in a '_switch' call, but it isn't set".format(argumentList[0]))
		elif variableDict[argumentList[0]] in caseDict:
			#Value found in the case dict
			return (True, caseDict[variableDict[argumentList[0]]])
		elif u'_default' in caseDict:
			#Value not found, fall back to the default value if it exists
			return (True, caseDict[u'_default'])
		else:
			#No match, no fallback. Return empty string
			return (True, u"")


	#Parameter functions
	@staticmethod
	def hasparams(argumentList, grammarDict, variableDict, parameterString):
		"""
		<_hasparams|stringIfHasParams|stringIfDoesntHaveParams>
		Checks if there are any parameters provided. Returns the first string if any parameters exist, and the second one if not
		"""
		if len(argumentList) < 2:
			return (False, GrammarCommands._constructNotEnoughParametersErrorMessage(u"hasparams", 2, len(argumentList)))
		if parameterString:
			return (True, argumentList[0])
		else:
			return (True, argumentList[1])

	@staticmethod
	def hasparam(argumentList, grammarDict, variableDict, parameterString):
		"""
		<_hasparam|paramToCheck|stringIfHasParam|stringIfDoesntHaveParam>
		Checks if the the provided parameters are equal to a string. Returns the first string if it matches, and the second one if it doesn't.
		If no parameter string was provided, the 'doesn't match' string is returned
		"""
		if len(argumentList) < 3:
			return (False, GrammarCommands._constructNotEnoughParametersErrorMessage(u"hasparam", 3, len(argumentList)))
		if parameterString:
			return (True, argumentList[1])
		else:
			return (True, argumentList[2])

	@staticmethod
	def params(argumentList, grammarDict, variableDict, parameterString):
		"""
		<_params>
		Returns the user-provided parameter string, or an empty string if no parameter string was provided
		"""
		# Fill in the provided parameter(s) in this field
		return (True, u"" if not parameterString else parameterString)


	#Random choices
	@staticmethod
	def randint(argumentList, grammarDict, variableDict, parameterString):
		"""
		<_randint|lowerBound|higherBound>
		Returns a number between the lower and upper bound, inclusive on both sides
		"""
		if len(argumentList) < 2:
			return (False, GrammarCommands._constructNotEnoughParametersErrorMessage(u"randint", 2, len(argumentList)))
		try:
			value = random.randint(int(argumentList[0]), int(argumentList[1]))
		except ValueError:
			return (False, u"Invalid argument provided to '_randint' call, '{}' or '{}' couldn't be parsed as a number".format(argumentList[0], argumentList[1]))
		return (True, unicode(value, 'utf-8'))

	@staticmethod
	def randintasword(argumentList, grammarDict, variableDict, parameterString):
		"""
		<_randintasword|lowerBound|upperBound>
		Returns a number between the lower and upper bound, inclusive on both sides, and converts that to a word (so '2' becomes 'two')
		"""
		if len(argumentList) < 2:
			return (False, GrammarCommands._constructNotEnoughParametersErrorMessage(u"randint", 2, len(argumentList)))
		try:
			value = random.randint(int(argumentList[0]), int(argumentList[1]))
		except ValueError:
			return (False, u"Invalid argument provided to '_randint' call, '{}' or '{}' couldn't be parsed as a number".format(argumentList[0], argumentList[1]))
		return (True, Command.numberToText(value))

	@staticmethod
	def choose(argumentList, grammarDict, variableDict, parameterString):
		"""
		<_choose|option1|option2|...>
		Chooses a random option from the ones provided. Useful if the options are short and it'd feel like a waste to make a separate field for each of them
		"""
		if len(argumentList) == 0:
			return (False, u"'_choose' field doesn't specify any choices")
		return (True, random.choice(argumentList))

	@staticmethod
	def file(argumentList, grammarDict, variableDict, parameterString):
		"""
		<_file|filename>
		Load a sentence from the specified file. Useful for not cluttering up the grammar file with a lot of options
		The file has to exists in the same directory the grammar file is in
		"""
		if len(argumentList) == 0:
			return (False, u"Call to '_file' doesn't specify a filename")
		return (True, Command.getRandomLine(argumentList[0]))


	#Miscellaneous
	@staticmethod
	def replace(argumentList, grammarDict, variableDict, parameterString):
		"""
		<_replace|stringToReplaceIn|whatToReplace|whatToReplaceItWith>
		Returns the provided string but with part of it replaced. The substring 'whatToReplace' is replaced by 'whatToReplaceItBy'. String can be a varname or '_params' too
		"""
		if len(argumentList) < 3:
			return (False, GrammarCommands._constructNotEnoughParametersErrorMessage(u"replace", 3, len(argumentList)))
		# Check if the string wants the parameters or a variable name, otherwise use the provided string as-is
		stringToReplaceIn = argumentList[0]
		if argumentList[0] == u"_params":
			stringToReplaceIn = parameterString
		elif argumentList[0] in variableDict:
			stringToReplaceIn = variableDict[argumentList[0]]
		# Now replace what we need to replace
		return (True, stringToReplaceIn.replace(argumentList[1], argumentList[2]))

	@staticmethod
	def regexreplace(argumentList, grammarDict, variableDict, parameterString):
		"""
		<_regexreplace|stringToReplaceIn|regexOfWhatToReplace|whatToReplaceItWith>
		Returns the provided string with part of it replaced. The part to replaced is determined wit the provided regular expression. The string can be a varname or '_params' too
		"""
		if len(argumentList) < 3:
			return (False, GrammarCommands._constructNotEnoughParametersErrorMessage(u"regexreplace", 3, len(argumentList)))
		# Check if the string wants the parameters or a variable name, otherwise use the provided string as-is
		stringToReplaceIn = argumentList[0]
		if argumentList[0] == u"_params":
			stringToReplaceIn = parameterString
		elif argumentList[0] in variableDict:
			stringToReplaceIn = variableDict[argumentList[0]]
		# Now replace what we need to replace
		try:
			# Unescape any characters inside the regex (like < and |)
			regex = re.compile(re.sub(r"/(.)", r"\1", argumentList[1]), flags=re.DOTALL)  # DOTALL so it can handle newlines in messages properly
			return (True, re.sub(regex, argumentList[2], stringToReplaceIn))
		except re.error as e:
			return (False, u"Unable to parse regular expression '{}' in '_regexreplace' call ({})".format(argumentList[1], e.message))

	@staticmethod
	def modulecommand(argumentList, grammarDict, variableDict, parameterString):
		"""
		<_modulecommand|commandName|argument1|argument2|key1=value1|key2=value2|...>
		Runs a shared command in another bot module. The first parameter is the name of that command, the rest are unnamed and named parameters to pass on, and are all optional
		"""
		if len(argumentList) < 1:
			return (False, GrammarCommands._constructNotEnoughParametersErrorMessage(u"modulecommand", 1, len(argumentList)))
		# Call commandFunctions from different modules
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
