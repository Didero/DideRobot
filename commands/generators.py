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
					self.generators[grammarFilename] = tuple(grammarJson['_triggers'])
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
					helptext = "No helptext was set for this generator, sorry"
					if requestedTrigger == 'name':
						helptext = "Generates a random first and last name. You can provide a parameter to specify the gender"
					elif requestedTrigger == 'game' or requestedTrigger == 'videogame':
						helptext = "Generates random video game names. You can provide a number to make it generate that many game names, " \
								 "and replacement words that will get inserted into the generated name"
					elif requestedTrigger == 'word' or requestedTrigger == 'word2':
						helptext = "Generates a random word, or tries to. Add a number to make it generate that many words, increasing the chance one of them is pronounceable"
					return "{}{} {}: {}".format(message.bot.commandPrefix, message.messageParts[0], requestedTrigger, helptext)
		#No matching generator trigger was found
		return "I'm not familiar with the '{}' generator, though if you think it would make a good one, feel free to inform my owner(s), maybe they'll create it!".format(requestedTrigger)

	def execute(self, message):
		"""
		:type message: IrcMessage
		"""

		if message.messagePartsLength == 0 or message.messageParts[0].lower() == 'help':
			return message.reply(self.getHelp(message))

		wantedGeneratorName = message.messageParts[0].lower()
		wantedGenerator = None

		if wantedGeneratorName == 'random':
			wantedGenerator = random.choice(self.generators.keys())
		else:
			#Check to see if it's a registered generator
			for generator, triggers in self.generators.iteritems():
				if isinstance(triggers, basestring):
					triggers = (triggers,)
				for trigger in triggers:
					if trigger == wantedGeneratorName:
						wantedGenerator = generator
						break
				if wantedGenerator is not None:
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

	def getRandomLine(self, filename, filelocation=None):
		if not filelocation:
			filelocation = self.filesLocation
		filepath = os.path.abspath(os.path.join(GlobalStore.scriptfolder, filelocation, filename))
		#Check if the provided file is in our 'generator' folder
		if not filepath.startswith(self.filesLocation):
			#Trying to get out of the 'generators' folder
			self.logWarning("[Gen] User is trying to access files outside the 'generators' folder with filename '{}'".format(filename))
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
		basicLetters = []
		specialLetters = []

		if isinstance(vowelOrConsonant, int):
			#Assume the provided argument is a chance percentage of vowel
			if random.randint(1, 100) <= vowelOrConsonant:
				vowelOrConsonant = "vowel"
			else:
				vowelOrConsonant = "consonant"

		if vowelOrConsonant == "vowel":
			basicLetters = ['a', 'e', 'i', 'o', 'u']
			specialLetters = ['y']
		else:
			basicLetters = ['b', 'c', 'd', 'f', 'g', 'h', 'k', 'l', 'm', 'n', 'p', 'r', 's', 't']
			specialLetters = ['j', 'q', 'v', 'w', 'x', 'z']

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
		if u'_start' not in grammarDict:
			return u"Error: No '_start' field found!"

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
				#If a gender was provided or requested, use that to generate a name
				if u'gender' in variableDict:
					variableDict[u'name'] = self.generateName([variableDict[u'gender']])
				#Otherwise have the function decide
				else:
					variableDict[u'name'] = self.generateName()
				nameparts = variableDict[u'name'].split(' ')
				variableDict[u'firstname'] = nameparts[0]
				variableDict[u'lastname'] = nameparts[-1]

		#Start the parsing!
		return self.parseGrammarString(grammarDict[u'_start'], grammarDict, parameters, variableDict)


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
			print "Converting to unicode, grammarString is now", type(grammarString)

		outputString = grammarString
		loopcount = 0
		while loopcount < 150:
			loopcount += 1
			try:
				outputString, bracketString = re.split(ur"(?<!/)<", outputString, maxsplit=1)
			except ValueError:
				#No more bracketed parts found, done
				break

			grammarParts = [u""]
			grammarPartIndex = 0
			nestedBracketLevel = 0
			characterIsEscaped = False
			#Go through all the characters to divide the bracketed string up in parts for parsing
			for characterIndex, character in enumerate(bracketString):
				if nestedBracketLevel == 0 and not characterIsEscaped:
					if character == u"|":
						#New section, write any new characters to the new section
						grammarParts.append(u"")
						grammarPartIndex += 1
						continue
					elif character == u">":
						#End of this bracket block. Parse the block, and append the rest of the string to it
						success, parsedBracketString = self.parseGrammarBlock(grammarParts, grammar, parameterString, variableDict)
						if not success:
							#If parsing failed, return the error
							return parsedBracketString
						else:
							#Otherwise, insert it into the output string and try to parse it again until all the brackets are filled in
							outputString += parsedBracketString + bracketString[characterIndex+1:]
							break
				#Store the character
				grammarParts[grammarPartIndex] += character
				#Make sure if this character is escaped, the next one won't be
				if characterIsEscaped:
					characterIsEscaped = False
				#If this character isn't escaped, parse it if necessary
				else:
					if character == u"/":
						# Escape character. Save the next character without parsing it
						characterIsEscaped = True
					elif character == u"<":
						# Start of a bracketed part that we need to store
						nestedBracketLevel += 1
					elif character == u">":
						# End of a bracketed part
						nestedBracketLevel -= 1
			else:
				#If we didn't break out of the character loop, we didn't find the end bracket. Complain about that
				return u"Error: Missing closing bracket"
		else:
			#We reached the loop limit, so there's probably an infinite loop. Report that
			return u"Error: Loop limit reached, there's probably an infinite loop in the grammar file"

		#Remove any escapes we put in to prevent abuse
		outputString = outputString.replace(u"/<", u"<").replace(u"//", u"/")
		#Done, return what we have
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
			if fieldKey == u"_randint" or fieldKey == u"_randintasword":
				if len(grammarParts) < 2:
					return (False, u"Error: Not enough parameters to the '{}' call. Need 2, found {}".format(fieldKey, len(grammarParts)))
				try:
					value = random.randint(int(grammarParts[0]), int(grammarParts[1]))
				except ValueError:
					return (False, u"Invalid argument provided to '{}', '{}' or '{}' couldn't be parsed as a number".format(fieldKey, grammarParts[0], grammarParts[1]))
				if fieldKey == u"_randint":
					replacement = unicode(value)
				elif fieldKey == u"_randintasword":
					replacement = self.numberToText(value)
			elif fieldKey == u"_file":
				# Load a sentence from the specified file. Useful for not cluttering up the grammar file with a lot of options
				replacement = self.getRandomLine(grammarParts[0])
			elif fieldKey == u"_setvar":
				# <_setvar|varname|value>
				if len(grammarParts) < 2:
					return (False, u"Error: Not enough parameters to the '{}' call, need at least 2, only found {}".format(fieldKey, len(grammarParts)))
				variableDict[grammarParts[0]] = grammarParts[1]
			elif fieldKey == u"_setvarrandom":
				# <_setvarrandom|varname|value1|value2|value3> to pick a random value and set the variable to that
				if len(grammarParts) < 2:
					return (False, u"Error: Not enough parameters to the '{}' call, need at least 2, only found {}".format(fieldKey, len(grammarParts)))
				variableDict[grammarParts[0]] = random.choice(grammarParts[1:])
			elif fieldKey == u"_remvar":
				if grammarParts[0] in variableDict:
					del variableDict[grammarParts[0]]
			elif fieldKey == u"_hasvar":
				# <_hasvar|varname|stringIfVarnameExists|stringIfVarnameDoesntExist>
				if grammarParts[0] in variableDict:
					replacement = grammarParts[1]
				else:
					replacement = grammarParts[2]
			elif fieldKey == u"_variable" or fieldKey == u"_var":
				# Variable, fill it in if it's in the variable dictionary
				if grammarParts[0] not in variableDict:
					return (False, u"Error: Referenced undefined variable '{}' in field '<{}|{}>'".format(grammarParts[0], fieldKey, u"|".join(grammarParts)))
				else:
					replacement = variableDict[grammarParts[0]]
			elif fieldKey == u"_if":
				# <_if|varname=string|stringIfTrue|stringIfFalse>
				firstArgumentParts = grammarParts[0].split('=')
				if len(grammarParts) < 3:
					return (False, u"Error: Not enough arguments in 'if' for field '<{}|{}>', found {}, expected 3".format(fieldKey, u"|".join(grammarParts), len(grammarParts)))
				if firstArgumentParts[0] not in variableDict:
					return (False, u"Error: Referenced undefined variable '{}' in field '<{}|{}>'".format(firstArgumentParts[0], fieldKey, u"|".join(grammarParts)))
				if variableDict[firstArgumentParts[0]] == firstArgumentParts[1]:
					replacement = grammarParts[1]
				else:
					replacement = grammarParts[2]
			elif fieldKey == u"_ifcontains":
				# <_ifcontains|string|substringToCheckFor|stringIfSubstringInString|stringIfSubstringNotInString>
				if len(grammarParts) < 4:
					return (False, u"Error: Not enough parameters in field '<{}|{}>'. 4 fields required, found {}".format(fieldKey, u"|".join(grammarParts), len(grammarParts)))
				if grammarParts[0] == u"_params":
					grammarParts[0] = parameterString if parameterString else ""
				if grammarParts[1] in grammarParts[0]:
					replacement = grammarParts[2]
				else:
					replacement = grammarParts[3]
			elif fieldKey == u"_switch":
				# <_switch|varname/_params|case1:stringIfCase1|case2:stringIfCase2|...|_default:stringIfNoCaseMatch>
				# The '_default' field is not mandatory, if it's missing an empty string will be returned
				caseDict = {}
				for caseString in grammarParts[1:]:
					case, stringIfCase = caseString.split(u':', 1)
					caseDict[case] = stringIfCase
				if grammarParts[0] == u"_params" and parameterString in caseDict:
					replacement = caseDict[parameterString]
				elif grammarParts[0] not in variableDict:
					return (False, u"Error: variable '{}' was specified in a '{}' call, but it isn't set".format(grammarParts[0], fieldKey))
				elif variableDict[grammarParts[0]] in caseDict:
					replacement = caseDict[variableDict[grammarParts[0]]]
				elif u'_default' in caseDict:
					replacement = caseDict[u'_default']
				else:
					replacement = u""
			elif fieldKey == u"_hasparameters" or fieldKey == u"_hasparams":
				# <_hasparams|stringIfHasParams|stringIfDoesntHaveParams>"
				# Checks if there are any parameters provided
				if parameterString:
					replacement = grammarParts[0]
				else:
					replacement = grammarParts[1]
			elif fieldKey == u"_hasparameter" or fieldKey == u"_hasparam":
				# <_hasparam|paramToCheck|stringIfHasParam|stringIfDoesntHaveParam>
				# Used to check if the literal parameter was passed in the message calling this generator
				if parameterString:
					replacement = grammarParts[1]
				else:
					replacement = grammarParts[2]
			elif fieldKey == u"_params":
				# Fill in the provided parameter(s) in this field
				if not parameterString:
					replacement = u""
				else:
					# The parameters will be strings. Convert them to unicode
					replacement = parameterString
					#Prevent file access
					if u"<_file" in replacement:
						return (False, u"Error: File access from parameters is not allowed")
			elif fieldKey == u"_replace":
				# <_replace|string|whatToReplace|whatToReplaceItWith>
				if len(grammarParts) < 3:
					return (False, u"Error: Not enough parameters in field '<{}|{}>'. Need 3, found {}".format(fieldKey, u"|".join(grammarParts), len(grammarParts)))
				replacement = grammarParts[0]
				if replacement == u"_params":
					replacement = parameterString
				replacement = replacement.replace(grammarParts[1], grammarParts[2])
			elif fieldKey == u"_" or fieldKey == u"_dummy":
				replacement = u""
			else:
				return (False, u"Error: Unknown command '{key}' in field '<{key}|{args}>' found!".format(key=fieldKey, args=u"|".join(grammarParts)))
		# No command, so check if it's a valid key
		elif fieldKey not in grammar:
			return (False, u"Error: Field '{}' not found in grammar file!".format(fieldKey))
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
				return (False, u"Error: No handling defined for type '{}' found in field '{}'".format(type(grammar[fieldKey]), fieldKey))

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
					return (False, u"Error: Invalid 'storeas' argument for field '<{}|{}|&{}>', should be 'storeas:[varname]'".format(fieldKey, u"|".join(grammarParts), u",".join(extraOptions)))
				varname = option.split(u':', 1)[1]
				variableDict[varname] = replacement

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
		"""Generate a word by putting letters together in semi-random order. Based on an old mIRC script of mine"""
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
		"""Another method to generate a word. Based on a slightly more advanced method, from an old project of mine that didn't go anywhere"""

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
