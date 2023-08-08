import re

#IRC decoration characters, these go before and after the text you want to decorate
BOLD = '\x02'
COLOUR = '\x03'
ITALIC = '\x1D'
UNDERLINE = '\x1F'
CLEAR = '\x0F'

class Colours:
	"""
	This fake-enumeration class contains the numbers IRC uses to specify colours, along with the 'COLOUR' decoration character
	"""
	WHITE = 0
	BLACK = 1
	NAVY_BLUE = 2
	GREEN = 3
	RED = 4
	DARK_RED = 5
	MAROON = 5
	PURPLE = 6
	ORANGE = 7
	YELLOW = 8
	LIGHT_GREEN = 9
	LIME = 9
	TEAL = 10
	CYAN = 11
	LIGHT_BLUE = 11
	BLUE = 12
	PINK = 13
	GREY = 14
	LIGHT_GREY = 15

def decorateText(text, clearAllDecorationsAtEnd=True, *decorators):
	"""
	Decorate a string with IRC decorators (like bold or underline)
	:param text: The string that should be decorated
	:param clearAllDecorationsAtEnd: If True, end the string with the 'clear all decorations' tag, otherwise it will close just the decorators used
	:param decorators: As many decorator constants (also from this file) as you want. Repeated decorators work but cancel each other out
	:return: The text surrounded by the requested decorator(s)
	"""
	if not decorators:
		return text
	decoratorsString = "".join(decorators)
	decoratedText = decoratorsString + text
	#If we need to clear all decorations, just do so
	if clearAllDecorationsAtEnd:
		decoratedText += CLEAR
	#Otherwise, just use the same decorator string again, since for instance a second 'BOLD' character stops just bolding text
	else:
		decoratedText += decoratorsString
	return decoratedText

def makeTextBold(text, clearAllDecorationsAtEnd=False):
	"""
	Make the provided text show up as bold in IRC clients
	:param text: The text to make bold
	:param clearAllDecorationsAtEnd: Set this to True to end the string with the 'clear all decorations' tag. Otherwise it will close just the bold tag (default setting)
	:return: The provided text made up to show up as bold in IRC clients that support it (and most should)
	"""
	return decorateText(text, clearAllDecorationsAtEnd, BOLD)

def makeTextItalic(text, clearAllDecorationsAtEnd=False):
	"""
	Make the provided text show up as italic in IRC clients that support it
	:param text: The text to italicize
	:param clearAllDecorationsAtEnd: Set this to True to end the string with the 'clear all decorations' tag. Otherwise it will close just the italics tag (default setting)
	:return: The provided text made up to show up as italic in IRC clients that support it
	"""
	return decorateText(text, clearAllDecorationsAtEnd, ITALIC)

def makeTextUnderlined(text, clearAllDecorationsAtEnd=False):
	"""
	Make the provided text show up as underlined in IRC clients
	:param text: The text to underline
	:param clearAllDecorationsAtEnd: Set this to True to end the string with the 'clear all decorations' tag. Otherwise it will close just the underline tag (default setting)
	:return: The provided text made up to show up as underlined in IRC clients that support it
	"""
	return decorateText(text, clearAllDecorationsAtEnd, UNDERLINE)

def makeTextColoured(text, textColour, backgroundColour=-1, clearAllDecorationsAtEnd=False):
	"""
	Colour text in the specified colour(s)
	:param text: The text to surround in colour codes
	:param textColour: The colour the text should be, picked from the 'Colour' enumeration also in this file
	:param backgroundColour: The optional background colour. Set this to an invalid value (or leave the parameter out) to set no background colour
	:param clearAllDecorationsAtEnd: Set this to True to end the string with the 'clear all decorations' tag. Otherwise it will close just the colour tag (default setting)
	:return: The text made up so that it will show up as coloured in IRC clients that support it
	"""
	if textColour < 0 or textColour > 15:
		raise ValueError("Invalid colour '{}' provided, should be 0 or more and 15 or less. Please only specify values from the 'Colour' class".format(textColour))
	colourString = ""
	#Prepend a zero if the number is smaller than 10 because it should always be two characters wide. This prevents accidental eating of characters if the character following the colour is also a number
	if textColour < 10:
		colourString += "0"
	colourString += str(textColour)
	if 0 <= backgroundColour < 16:
		colourString += ","
		if backgroundColour < 10:
			colourString += "0"
		colourString += str(backgroundColour)
	return decorateText(colourString + text, clearAllDecorationsAtEnd, COLOUR)

def removeFormatting(text):
	"""
	Remove all IRC formatting from the provided text
	:param text: The text to remove the IRC formatting from
	:return: The provided text without any IRC formatting
	"""
	if COLOUR in text:
		# The colour character is followed by color numbers
		text = re.sub(COLOUR + "\d{1,2}(,\d{1,2})?", '', text)
	for formattingChar in (BOLD, COLOUR, CLEAR, ITALIC, UNDERLINE):
		if formattingChar in text:
			text = text.replace(formattingChar, '')
	if COLOUR in text:
		# The colour character is followed by color numbers
		text = re.sub(COLOUR + "\d{1,2}(,\d{1,2})?", '', text)
	return text
