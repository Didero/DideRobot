CTCP_DELIMITER = chr(1)
MAX_LINE_LENGTH = 450  #Officially 512 bytes including the newline characters, but let's be on the safe side
MAX_MESSAGE_LENGTH = 300  #The maximum number of characters in message to send. Less than max line length because that includes channel and nickname
CHANNEL_PREFIXES = "#&!+.~"  #All the characters that could possibly indicate something is a channel name (usually just '#' though)
#Since a grey separator is often used to separate parts of a message, provide an easy way to get one
GREY_SEPARATOR = u' \x0314|\x03 '  #'\x03' is the 'color' control char, 14 is the colour code for grey
IRC_NUMERIC_TO_NAME = {"001": "RPL_WELCOME", "002": "RPL_YOURHOST", "003": "RPL_CREATED", "004": "RPL_MYINFO", "005": "RPL_ISUPPORT",
					   "251": "RPL_LUSERCLIENT", "252": "RPL_LUSEROP", "253": "RPL_LUSERUNKNOWN", "254": "RPL_LUSERCHANNELS", "255": "RPL_LUSERME",
					   "265": "RPL_LOCALUSERS", "266": "RPL_GLOBALUSERS", "315": "RPL_ENDOFWHO", "332": "RPL_TOPIC", "333": "RPL_TOPICWHOTIME",
					   "352": "RPL_WHOREPLY", "353": "RPL_NAMREPLY", "366": "RPL_ENDOFNAMES", "372": "RPL_MOTD", "375": "RPL_MOTDSTART", "376": "RPL_ENDOFMOTD",
					   "412": "ERR_NOTEXTTOSEND", "433": "ERR_NICKNAMEINUSE"}
