CTCP_DELIMITER = chr(1)
MAX_LINE_LENGTH = 510  # Officially 512 bytes, but lines always end with '\r\n', so subtract 2
MAX_MESSAGE_LENGTH = 325  # The maximum number of characters in message to send. Message format is ':[nick,32]![username,12]@[hostmask,64] PRIVMSG [target,64] :[messagetext]', which leaves 326 characters for messagetext, round it down a bit to be safe
CHANNEL_PREFIXES = "#&!+.~"  #All the characters that could possibly indicate something is a channel name (usually just '#' though)
#Since a grey separator is often used to separate parts of a message, provide an easy way to get one
GREY_SEPARATOR = u' \x0314|\x03 '  #'\x03' is the 'color' control char, 14 is the colour code for grey
