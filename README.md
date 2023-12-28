# DideRobot

A modular Python 3 IRC bot built with Gevent

### 1) Initial Setup
1. Install the libraries listed in 'requirements.txt', either manually or (preferably) by pointing pip to it with 'python -m pip install -r requirements.txt'
2. In the 'serverSettings' folder, make a copy of 'globalsettings.json.example'
3. Rename the copy to 'globalsettings.json'
4. Open the file in your favourite text editor
5. Set all values the way you want them. (See section 3 for an explanation of what each setting does). These will be the default values for new server setting files you create later

### 2) Adding A New Server To Connect To
1. In the 'serverSettings' folder, create a new folder. Name it whatever you want (but no spaces). You will use this name later to make the bot connect to this server, so make it something you can remember
2. In your new folder, create a new file called 'settings.json' (or copy over 'globalsettings.json' and rename it, so you don't have to remember all the field names)
3. Open the new 'settings.json' in your favourite text editor
4. Add or change the settings you want (See section 3 for setting explanations). If the value would be the same as in 'globalsettings.json', you can delete the line, which will make the setting default back to the global value
5. The 'server' field is required. It's also smart to add at least one user address and/or nickname to the 'admins' list, so you can control the bot

### 3) Settings Explanation
* server: The URL of the IRC server this bot should connect to (For instance 'irc.example.com')
* port: The port number the bot should use for the connection. If you're unsure, just leave it at the default of 6667
* serverpassword: Some IRC servers require you to send a password before you're allowed to connect. Set that here, or leave it empty if no password is required (Most servers don't require one)
* nickname: The nickname the bot will try to connect with. If the specified nickname is not available, it will append an underscore and try again, until it finds a nickname that's free
* realname: The 'real' name the bot will report to the server. This is usually not too important. If this field is missing, it will be set to the nickname
* maxConnectionRetries: If the bot can't establish a connection to the server, or if it loses connection, it will try to re-establish the connection as often as specified here, with an increasingly long wait between attempts. If the number specified is lower than 0, it will keep retrying forever
* minSecondsBetweenMessages: A float specifying how many seconds the bot will wait between sending messages to the server. Useful in case the server has rate-limiting
* keepChannelLogs, keepPrivateLogs, keepSystemLogs: A boolean that specifies whether the bot should respectively write messages from channels, private messages, or from the server itself to a log file (which will be stored in the 'serverSettings' folder of this server, in a 'logs' subfolder)
* commandPrefix: If a message starts with the character specified here, the bot will interpret the message as a possible command, and will send it to the modules. The bot will do the same for messages starting with its nickname (f.i. 'DideRobot help')
* joinChannels: A list of channels the bot should join when it connects to the server. Can be empty
* allowedChannels: A list of channels the bot is allowed to join through a 'join' command. Admins can make the bot join channels not in this list, but normal users can't
* admins: A list of user addresses and/or nicknames of people that are allowed to call important commands that affect the whole bot, even outside this server, like 'shutdown' and 'changeSettings'. Only put nicknames in this list if you are sure nobody can impersonate that nick
* serverAdmins: A list of user addresses and/or nicknames of people that are allowed to call important commands that affect the bot on this server, like 'quit' and changing the bot's nickname. Also gives 'serverAdmins' and 'channelAdmins' permissions. Only put nicknames in this list if you are sure nobody can impersonate that nick
* channelAdmins: A list of user addresses and/or nicknames of people that are allowed to call important commands that affect the bot on channels, like 'leave', or adding things to watch to Watcher modules. Also gives 'channelAdmins' permissions. Only put nicknames in this list if you are sure nobody can impersonate that nick
* userIgnoreList: A list of user addresses and/or nicknames that the bot should ignore commands from. Useful if there are other bots in a channel to prevent accidental command calls
* commandAllowlist: Only the commands in this list are allowed to respond to messages on this server. List entries should be the exact same name as the command filename. Supercedes the blocklist
* commandBlocklist: These commands are not allowed to respond to messages on this server. List entries should be the exact same name as the command filename. If a command allowlist is also provided, this field is ignored
* textDecoration: An optional field. If provided and set to anything but 'irc', all text decorations, like bold and colours, are removed from all the bot output. Useful for servers or channels that don't support or discourage text decorations
* channelSettings: A special dictionary that can override the above settings but only for a specified channel. '. Example: 'channelSettings: {"#myChannel": {"channelAdmins": ["aNickName"], "commandPrefix": "?"}}'

### 4) Starting The Bot
1. Navigate to the 'DideRobot' folder
2. Call 'start.py' with a single argument: a comma-separated list of server settings folders. For each folder specified, it will (try to) connect to the URL specified in the 'server' field of the corresponding 'settings.json' file, and join all channels specified in the 'joinChannels' list, if any

### 5) Stopping The Bot
0. Connect to a server the bot is connected to, if you're not connected already
1. Either in a channel the bot is in, or in a private message, type the specified command character, followed by either 'quit' to make the bot leave just that server, or 'shutdown' to make the bot disconnect from all servers it is connected to. Make sure the settings file for the bot specifies you as an admin, because only bot admins can make the bot quit or shut down
2. Once DideRobot isn't connected to any server (Either because it quit from the last server it was connected to, or because of a 'shutdown' call), the program will exit

### 6) Bot Maintenance
There are three important commands for keeping the bot up-to-date, all of which can only be used by bot admins:
* !update: Fetches all the latest code updates from DideRobot's GitHub repository. This does NOT immediately put the code changes in effect
* !reload: Call this command, followed by the name(s) of the command module(s) to reload. Usually commits listed by !update mention which command module(s) have been changed. Modules need to be reloaded before changes retrieved with !update will take effect
* !restartfull: This fully restarts the bot, putting all code changes from !update in effect. This is needed when core files (like a util method, a handler, or the bot code itself) were updated, since those can't be reloaded with !reload. Restarting in this way will show as the bot quitting all the channels and servers it's in, and then rejoining after 10 to 15 seconds (Just enough time to get worried something broke). It will rejoin all the servers originally provided on the commandline when the bot was started, so if you made the bot leave or join any servers while it was running, you'll have to do that again

### Bonus) Creating Your Own Command Module
1. Create a new '.py' file in the 'commands' subfolder
2. In that file, create a new class called 'Command', and have it inherit from 'CommandTemplate'
3. Check the 'CommandTemplate' class to see which class variables you can set. The most important one is 'triggers' since that determines how your command gets called
4. While you're in the 'CommandTemplate' class, look at the methods defined in there. You should at least implement the 'execute' method in your command, since that gets called when one of your triggers is used in a chat. The other methods described there might come in handy too
##### Some suggestions
* It's probably helpful to look at a simple command like 'Info' or 'Uptime' for basic examples of commands. 'Choice' is also a good one since it uses the 'IrcMessage' class, which represents the chat message the bot received and what 'execute' receives. You'll probably use the 'IrcMessage' class a lot in your commands
* To have your command be able to reply when it gets called, you can use 'message.reply' inside the 'execute' method
* Commands can also have a method that periodically gets called, 'executeScheduledFunction', and you set the period with the 'scheduledFunctionTime' class variable
* If you have long replies, and you don't want to exceed the maximum IRC message length, you can use 'message.replyWithLengthLimit'. It takes either a single string, or a StringWithSuffix instance

### Python 2
DideRobot was originally written in Python 2. After 9 years, and Python 2 being unsupported for 3 years, I finally decided to port DideRobot to Python 3.  
The Python 2 version can still be found in the 'python2' branch, but that branch won't receive fixes anymore.  

### Twitch
Since Twitch Chat is based on IRC, DideRobot should work there too, so DideRobot can be used as a Twitch bot. However, this has not been extensively tested. One thing that does not work is formatting, so output might be a bit harder to read than on actual IRC.  
You already need to have made a Twitch account for the bot. Then you need to set the 'serverpassword' field to the OAUTH token you can get as described [in the Twitch documentation](https://dev.twitch.tv/docs/irc/authenticate-bot/)  
