DideRobot
=========

A modular IRC bot built on Twisted
Based on:
- http://newcoder.io/~drafts/networks/intro/
- https://github.com/MatthewCox/PyMoronBot (and vice versa)

To use this bot, first go to the 'serverSettinsg' folder. There, make a copy of 'globalsettings.ini.example', and rename it to 'globalsettings.ini'. Optionally, fill in the settings you want every bot to use.
Then, make a subfolder there for each IRC server you want the bot to connect to. The name of this doesn't matter for the connection, it is just used when you start the bot or ask it to connect to a server. In each subfolder, create a file called 'settings.ini'. This file will overwrite settings in 'globalsettings.ini' if they're there. At the very least, you will need to set the 'server' field in the 'connection' section to the server you want to connect to.
Then fire the bot through 'start.py', and as commandline arguments add the names of the subfolders in 'serverSettings' you want to use, separated by commas (so no spaces).

The 'connection' section in the settings files also supports the 'minSecondsBetweenMessages' field. If provided, it should be a float, which indicates the minimum number of seconds between sending messages to the server. This is useful on servers which have flood protection, who kick users when they post more than a set number of messages in a set number of time. If this is not set, no rate limiting will be applied.
The 'scripts' section in the settings ini files supports a few more fields not in the example. 'commandWhitelist', if present, is a comma-separated list of the modules you want to allow on that server. If the field is absent, all modules are allowed. 'commandBlacklist' conversely blocks the specified modules on that server. These are mutually exclusive, with the whitelist taking precedence over the blacklist.
