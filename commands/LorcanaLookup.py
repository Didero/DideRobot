import json, os, random, re
from typing import Any, Dict, List

import requests

import Constants, GlobalStore, PermissionLevel
from commands.CommandTemplate import CommandTemplate
from CustomExceptions import CommandException, CommandInputException
from IrcMessage import IrcMessage
from util import IrcFormattingUtil, StringUtil


class Command(CommandTemplate):
	triggers = ('lorcana', 'lorcanafull', 'lorcanaimage')
	helptext = ("Search Lorcana cards. Provide (part of) the name of a card to get info on that card, or use 'random' to get a random card. "
				"Or provide key-value pairs to search for specific fields, see https://lorcanajson.org for which fields are available, for instance: '{commandPrefix}lorcana random color: Ruby' to get a random Ruby card. "
				"Searches support regular expressions. '{commandPrefix}lorcanafull' adds extra information to the card output, '{commandPrefix}lorcanaimage' links to an image of the found card")
	scheduledFunctionTime = 172800.0  # Every other day, since it doesn't update too often

	MAX_CARDS_TO_LIST = 5
	VERSION_FILE_PATH = os.path.join(GlobalStore.scriptfolder, "data", "LorcanaVersion.json")
	CARD_FILE_PATH = os.path.join(GlobalStore.scriptfolder, "data", "LorcanaCards.json")
	FORMAT_VERSION = 1

	def executeScheduledFunction(self):
		if self.shouldUpdate():
			self.updateCardData()

	def execute(self, message: IrcMessage):
		if message.messagePartsLength == 0:
			return message.reply(self.getHelp(message))

		if not os.path.isfile(self.CARD_FILE_PATH):
			message.reply("I don't seem to have my Lorcana cards data file at all, so I'll have to update. This should only take a few seconds")
			self.resetScheduledFunctionGreenlet()
			self.updateCardData()

		parameter = message.messageParts[0].lower()

		if parameter == 'update' or parameter == 'forceupdate':
			if parameter == 'update' and not self.shouldUpdate():
				return message.reply("I checked, and apparently an update is not necessary, since I've got all the latest Lorcana data already. Hooray")
			elif parameter == 'forceupdate' and not message.doesSenderHavePermission(PermissionLevel.BOT):
				return message.reply("Sorry, only my admins are allowed to force an update. Ask one of them if they think it's necessary")
			# We need to update
			message.reply("Ok, I'll update my Lorcana knowledge, feel free to test it in like half a minute")
			self.resetScheduledFunctionGreenlet()
			self.updateCardData()
			return

		if parameter == 'version':
			with open(self.VERSION_FILE_PATH, "r", encoding="utf-8") as versionFile:
				versionData = json.load(versionFile)
			return message.reply(f"I'm currently using the Lorcana data created on {versionData['generatedOn']} from https://lorcanajson.org")

		# Card file exists and is needed, load it into memory
		with open(self.CARD_FILE_PATH, "r", encoding="utf-8") as cardFile:
			cardsData = json.load(cardFile)

		if parameter in ("random", "search"):
			matchingCards = self.searchCards(cardsData, " ".join(message.messageParts[1:]), parameter)
		else:
			# No specific search type provided, assume the whole message is the search query
			matchingCards = self.searchCards(cardsData, message.message)

		showFullCardInfo = message.trigger == 'lorcanafull'
		numberOfCardsFound = len(matchingCards)
		if numberOfCardsFound == 0:
			replytext = "Hmm, that doesn't seem to match any of the cards I have on file. Maybe you made a typo?"
		elif numberOfCardsFound == 1 or parameter == 'random':
			if numberOfCardsFound == 1:
				matchingCard = matchingCards[0]
			else:
				matchingCard = random.choice(matchingCards)
			if message.trigger == 'lorcanaimage':
				replytext = f"{matchingCard['fullName']}: {matchingCard['images']['full']}"
			else:
				replytext = self.formatCardData(matchingCard, cardsData['sets'], showFullCardInfo)
			if parameter == 'random' and numberOfCardsFound > 1:
				replytext += f" ({numberOfCardsFound - 1:,} more)"
		else:
			replytext = f"Found {numberOfCardsFound:,} matches: "
			# Pick some random names from the found results
			names = [card['fullName'] for card in (random.sample(matchingCards, self.MAX_CARDS_TO_LIST) if numberOfCardsFound > self.MAX_CARDS_TO_LIST else matchingCards)]
			replytext += Constants.GREY_SEPARATOR.join(names)
			if numberOfCardsFound > self.MAX_CARDS_TO_LIST:
				replytext += f" ({numberOfCardsFound - self.MAX_CARDS_TO_LIST:,} more)"
		message.reply(replytext)

	def searchCards(self, cardsData: Dict, searchString: str, searchType: str = "search") -> List[Dict]:
		if searchType == 'random' and not searchString:
			# Pick one card from all cards
			return [random.choice(cardsData['cards'])]

		if not searchString:
			raise CommandInputException("Please also add a search query. Add (part of) a name to search for, or check my help text to find which query fields are available")

		# Allow searching for specific fields
		if ':' in searchString:
			searchDict = StringUtil.stringToDict(searchString)
		else:
			# No dict, assume it's a name search
			searchDict = {'name': searchString}
		if 'name' in searchDict:
			searchName = searchDict.pop('name')
			# If this isn't a specific regex search, make the search more useful by having it check if each word is in the name, instead of a literal match
			# Since re.escape also escape spaces, pre-replace them in our comparison so it doesn't trip over that
			if searchName.replace(" ", "\\ ") == re.escape(searchName):
				searchName = ".*" + searchName.replace(" ", ".+") + ".*"
			searchDict['fullName' if ' - ' in searchName else 'simpleName'] = searchName

		# Turn the search dict into regexes, to speed up checks
		searchRegexDict = {}
		for fieldName, fieldSearch in searchDict.items():
			searchRegexDict[fieldName] = re.compile(fieldSearch, re.IGNORECASE)

		# Do the search, matching all the different searched-for fields
		matchingCards = []
		fullNamesMatched = set()
		for cardIndex in range(len(cardsData['cards'])):
			card = cardsData['cards'].pop()
			try:
				for fieldName, fieldRegex in searchRegexDict.items():
					if fieldName not in card:
						raise StopIteration()
					elif isinstance(card[fieldName], str):
						if not fieldRegex.search(card[fieldName]):
							raise StopIteration()
					elif isinstance(card[fieldName], list):
						if isinstance(card[fieldName][0], str):
							# A list of strings, like for effects
							for fieldEntry in card[fieldName]:
								if fieldRegex.search(fieldEntry):
									break
							else:
								raise StopIteration()
						elif isinstance(card[fieldName][0], dict):
							foundMatch = False
							# A list of dicts, like for abilities
							for fieldEntry in card[fieldName]:
								for fieldEntryName, fieldEntryValue in fieldEntry.items():
									if fieldRegex.search(fieldEntryValue):
										foundMatch = True
										break
								else:
									raise StopIteration()
								if foundMatch:
									break
							else:
								raise StopIteration()
						else:
							raise CommandException(f"Unsupported card list entry type '{type(card[fieldName][0])}' in card {card['fullName']} (ID {card['id']})")
					else:
						raise CommandException(f"Unsupported card entry type '{type(card[fieldName]).__name__}' in card {card['fullName']} (ID {card['id']})")
			except StopIteration:
				# Card doesn't match, move on to the next one
				continue
			else:
				# Card matches the search query, store it if we don't already have a card of that name (to filter out duplicate enchanted and promo cards)
				if card['fullName'] not in fullNamesMatched:
					matchingCards.append(card)
					fullNamesMatched.add(card['fullName'])
		return matchingCards

	def formatCardData(self, card: Dict[str, Any], setsData: Dict[str, Any], addExtendedInfo: bool = False) -> str:
		outputParts = [IrcFormattingUtil.makeTextBold(card['fullName']), card['type']]
		if 'subtypes' in card:
			outputParts.append(", ".join(card['subtypes']))
		if card['color']:
			outputParts.append(card['color'])
		else:
			outputParts.append("No color")
		outputParts.append(f"{card['cost']}⬡, {'Inkable' if card['inkwell'] == 'True' else 'Non-inkable'}")
		singleValues = []
		if 'moveCost' in card:
			singleValues.append(f"{card['moveCost']}⭳")
		if 'strength' in card:
			singleValues.append(f"{card['strength']}¤")
		if 'willpower' in card:
			singleValues.append(f"{card['willpower']}⛉")
		if 'lore' in card:
			singleValues.append(f"{card['lore']}◊")
		if singleValues:
			outputParts.append(" ".join(singleValues))
		if card['fullTextSections']:
			outputParts.append(IrcFormattingUtil.makeTextColoured(" / ", IrcFormattingUtil.Colours.GREY).join(card['fullTextSections']).replace('\n', ' '))
		if addExtendedInfo:
			outputParts.append(card['rarity'])
			if 'flavorText' in card:
				outputParts.append(IrcFormattingUtil.makeTextColoured(card['flavorText'], IrcFormattingUtil.Colours.GREY).replace('\n', ' '))
			outputParts.append(setsData[card['setCode']]['name'])
			outputParts.append(f"from {card['story']}")
			if 'enchantedId' in card:
				outputParts.append("has Enchanted version")
			if 'promoIds' in card or 'nonPromoId' in card:
				promoPart = ("has" if 'promoIds' in card else "is") + " promo version"
				if len(card['promoIds']) > 1:
					promoPart += "s"
				outputParts.append(promoPart)
		return Constants.GREY_SEPARATOR.join(outputParts)

	def shouldUpdate(self) -> bool:
		if not os.path.isfile(self.VERSION_FILE_PATH) or not os.path.isfile(self.CARD_FILE_PATH):
			return True
		with open(self.VERSION_FILE_PATH, 'r', encoding='utf-8') as versionFile:
			versionData = json.load(versionFile)
		if versionData.get('_parsedFormatVersion', None) != self.FORMAT_VERSION:
			return True
		metadata = requests.get('https://lorcanajson.org/files/current/en/metadata.json').json()
		for key, value in metadata.items():
			if key not in versionData or value != versionData[key]:
				return True
		return False

	def updateCardData(self):
		cardDownloadRequest = requests.get("https://lorcanajson.org/files/current/en/allCards.json")
		cardData: Dict[str, Any] = cardDownloadRequest.json()
		# We're going to be searching the cards from the end to front of the list, for efficiency. Since promo cards have higher IDs, reverse the list so the 'normal' versions come first
		cardData['cards'].reverse()
		# Store boolean and numerical card values as strings, to match regexes easier while searching
		fieldNamesToStringify = ('cost', 'enchantedId', 'id', 'inkwell', 'lore', 'moveCost', 'nonEnchantedId', 'nonPromoId', 'number', 'promoIds', 'setNumber', 'strength', 'willpower')
		for card in cardData['cards']:
			for fieldName in fieldNamesToStringify:
				if fieldName in card:
					if isinstance(card[fieldName], int):
						card[fieldName] = str(card[fieldName])
					elif isinstance(card[fieldName], list):
						card[fieldName] = [str(fieldValue) for fieldValue in card[fieldName]]
					else:
						self.logError(f"[LorcanaLookup] Encountered unsupported field type '{type(card[fieldName])}' for field '{fieldName}' while updating")
		with open(self.CARD_FILE_PATH, "w", encoding="utf-8") as cardFile:
			json.dump(cardData, cardFile)
		with open(self.VERSION_FILE_PATH, "w", encoding="utf-8") as versionFile:
			versionData = cardData['metadata']
			versionData['_parsedFormatVersion'] = self.FORMAT_VERSION
			json.dump(versionData, versionFile)
