DideRobot
=========

A modular IRC bot built on Twisted
Based on:
- http://newcoder.io/~drafts/networks/intro/
- https://github.com/MatthewCox/PyMoronBot (and vice versa)

To use this bot, first go to the 'serverSettings' folder. There, make a copy of 'globalsettings.json.example', and rename it to 'globalsettings.json'. Optionally, fill in the settings you want every bot to use.
Then, make a subfolder there for each IRC server you want the bot to connect to. The name of this doesn't matter for the connection, it is just used when you start the bot or ask it to connect to a server. In each subfolder, create a file called 'settings.json'. This file will overwrite settings in 'globalsettings.json' if they're there. At the very least, you will need to set the 'server' field to the address of the server you want to connect to.
Then fire the bot through 'start.py', and as commandline arguments add the names of the subfolders in 'serverSettings' you want to use, separated by commas (so no spaces).

The 'minSecondsBetweenMessages' field, if provided, is a float that indicates the minimum number of seconds between sending messages to the server. This is useful on servers which have flood protection, who kick users when they post more than a set number of messages in a set number of time. If this is not set, no rate limiting will be applied.
The 'commandWhitelist' field, if filled in, is a list of names of the modules you want to allow on that server, disallowing all modules not listed. If the field is absent or empty, all modules are allowed. 'commandBlacklist' conversely blocks the specified modules on that server. These are mutually exclusive, with the whitelist taking precedence over the blacklist.
