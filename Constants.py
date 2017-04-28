IRC_numeric_to_name = {"001": "RPL_WELCOME", "315": "RPL_ENDOFWHO", "352": "RPL_WHOREPLY", "372": "RPL_MOTD", "375": "RPL_MOTDSTART", "376": "RPL_ENDOFMOTD",
					   "412": "ERR_NOTEXTTOSEND", "433": "ERR_NICKNAMEINUSE"}
CTCP_DELIMITER = chr(1)
MAX_MESSAGE_LENGTH = 450  #Officially 512 including the newline characters, but let's be on the safe side
