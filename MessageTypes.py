## All the supported message types ##

# Basic user message types
SAY = 'PRIVMSG'  # The most common message type, a user typed something in a channel or in a private message
ACTION = 'ACTION'  # A user typing a '/me' message
NOTICE = 'NOTICE'  # A special notice-type message sent by a user, a channel, or the server. Don't use 'message.reply' with these in the latter two cases, since that spams the entire channel/server

# Server messages
RPL_CREATED = 'RPL_CREATED'
RPL_ENDOFMOTD = 'RPL_ENDOFMOTD'
RPL_ENDOFNAMES = 'RPL_ENDOFNAMES'
RPL_ENDOFWHO = 'RPL_ENDOFWHO'
RPL_GLOBALUSERS = 'RPL_GLOBALUSERS'
RPL_ISUPPORT = 'RPL_ISUPPORT'
RPL_LOCALUSERS = 'RPL_LOCALUSERS'
RPL_LUSERCHANNELS = 'RPL_LUSERCHANNELS'
RPL_LUSERCLIENT = 'RPL_LUSERCLIENT'
RPL_LUSERME = 'RPL_LUSERME'
RPL_LUSEROP = 'RPL_LUSEROP'
RPL_LUSERUNKNOWN = 'RPL_LUSERUNKNOWN'
RPL_MOTD = 'RPL_MOTD'
RPL_MOTDSTART = 'RPL_MOTDSTART'
RPL_MYINFO = 'RPL_MYINFO'
RPL_NAMREPLY = 'RPL_NAMREPLY'
RPL_NOTOPIC = 'RPL_NOTOPIC'
RPL_TOPIC = 'RPL_TOPIC'
RPL_TOPICWHOTIME = 'RPL_TOPICWHOTIME'
RPL_WELCOME = 'RPL_WELCOME'
RPL_WHOREPLY = 'RPL_WHOREPLY'
RPL_YOURHOST = 'RPL_YOURHOST'

# Errors a server can send
ERR_NICKNAMEINUSE = 'ERR_NICKNAMEINUSE'
ERR_NOTEXTTOSEND = 'ERR_NOTEXTTOSEND'


# Server messages get sent as numbers, provide a conversion dictionary
IRC_NUMERIC_TO_TYPE = {"001": RPL_WELCOME, "002": RPL_YOURHOST, "003": RPL_CREATED, "004": RPL_MYINFO, "005": RPL_ISUPPORT,
					   "251": RPL_LUSERCLIENT, "252": RPL_LUSEROP, "253": RPL_LUSERUNKNOWN, "254": RPL_LUSERCHANNELS, "255": RPL_LUSERME,
					   "265": RPL_LOCALUSERS, "266": RPL_GLOBALUSERS, "315": RPL_ENDOFWHO, "331": RPL_NOTOPIC, "332": RPL_TOPIC, "333": RPL_TOPICWHOTIME,
					   "352": RPL_WHOREPLY, "353": RPL_NAMREPLY, "366": RPL_ENDOFNAMES, "372": RPL_MOTD, "375": RPL_MOTDSTART, "376": RPL_ENDOFMOTD,
					   "412": ERR_NOTEXTTOSEND, "433": ERR_NICKNAMEINUSE}

