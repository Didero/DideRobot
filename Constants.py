CTCP_DELIMITER = chr(1)
MAX_MESSAGE_LENGTH = 450  #Officially 512 including the newline characters, but let's be on the safe side
CHANNEL_PREFIXES = "#&!+.~"  #All the characters that could possibly indicate something is a channel name (usually just '#' though)
#Since a grey separator is often used to separate parts of a message, provide an easy way to get one
GREY_SEPARATOR = u' \x0314|\x0f '  #'\x03' is the 'color' control char, 14 is grey, and '\x0f' is the 'reset' character ending any decoration
IRC_NUMERIC_TO_NAME = {"001": "RPL_WELCOME", "315": "RPL_ENDOFWHO", "352": "RPL_WHOREPLY", "372": "RPL_MOTD", "375": "RPL_MOTDSTART", "376": "RPL_ENDOFMOTD",
					   "412": "ERR_NOTEXTTOSEND", "433": "ERR_NICKNAMEINUSE"}
