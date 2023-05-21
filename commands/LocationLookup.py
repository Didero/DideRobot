import json, socket

import requests

import Constants
from commands.CommandTemplate import CommandTemplate
import GlobalStore
from IrcMessage import IrcMessage


class Command(CommandTemplate):
	triggers = ['location']
	helptext = "Retrieves the country a user is from (or at least it tries to, no promises). Arguments are a user name, and optionally a channel name (which is mainly useful in PMs)"
	callInThread = True  #Very rarely the lookup is really slow, don't hold up the whole bot then

	def execute(self, message):
		"""
		:type message: IrcMessage
		"""

		#First check for the presence of the API key
		apiKey = GlobalStore.commandhandler.getApiKey('key', 'locatorhq')
		apiUsername = GlobalStore.commandhandler.getApiKey('username', 'locatorhq')
		if not apiKey or not apiUsername:
			message.reply("I'm sorry, my owner hasn't filled in the required API key for this module. Please poke them to add it")
			return

		replytext = ""
		userAddress = ""

		#no parameters added. Look up location of this user
		if message.messagePartsLength == 0:
			userAddress = message.user
		#Allow for any user address to be entered
		elif '@' in message.messageParts[0]:
			userAddress = message.messageParts[0]
		#A username was provided. Convert that to a full user address
		else:
			#Check if a channel name was provided as well
			if message.messagePartsLength < 2 and message.isPrivateMessage:
				#If no channel was specified, and we're not in a channel currently, we can't really do anything. Inform the user of that
				replytext = "If you use this script in a private message, you have to provide the channel to look in as the second parameter, " \
							"otherwise I don't know where to look"
			else:
				channelname = message.source
				#A channel name was provided, only search that channel
				if message.messagePartsLength >= 2:
					channelname = message.messageParts[1]
					if not channelname[0] in Constants.CHANNEL_PREFIXES:
						channelname = '#' + channelname
				if channelname not in message.bot.channelsUserList:
					replytext = "I'm not familiar with the channel '{}', sorry".format(channelname)
				else:
					nickToMatch = message.messageParts[0].lower() + '!'  #Add an exclamation mark to make sure the match is the full nick, not just the start
					replytext = "I'm sorry, but I don't know who you're talking about..."  #Set it in advance, in case we don't find a match
					for channelUserAddress in message.bot.channelsUserList[channelname]:
						if channelUserAddress.lower().startswith(nickToMatch):
							userAddress = channelUserAddress
							break

		if userAddress != "":
			username = userAddress.split("!", 1)[0]
			if username == userAddress:
				username = 'that user'

			#Try to turn the hostname into an IP address. Take off parts from the front until we have one or run out of parts
			userIp = ""
			userHostname = userAddress.split('@', 1)[1]
			userHostnameParts = userHostname.split('.')
			while userIp == "" and len(userHostnameParts) > 1:
				try:
					userIp = socket.gethostbyname(".".join(userHostnameParts))
				except socket.gaierror:
					userHostnameParts.pop(0)

			if userIp == "":
				replytext = "I'm sorry, I couldn't determine the IP address of {username}".format(username=username)
			elif userIp == "127.0.0.1":
				if username.lower() == message.bot.nickname.lower():
					replytext = "I'm right here for you!"
				else:
					replytext = "That's on my server! And I'm right here"
			else:
				apiReturn = None
				try:
					apiReturn = requests.get("http://api.locatorhq.com", params={'key': apiKey, 'user': apiUsername, 'ip': userIp, 'format': 'json'}, timeout=10.0)
					data = apiReturn.json()
				except requests.exceptions.Timeout:
					replytext = "I'm sorry, pinpointing {} location took too long for some reason. Maybe try again later?"
					replytext = replytext.format("your" if message.messagePartsLength == 0 else username + "'s")
				except ValueError:
					#If there's an error message in the API output, it's not valid JSON. Check if we know what's wrong
					self.logError("[location] Invalid API reply: '{}'".format(apiReturn.text if apiReturn else "no API reply found"))
					error = apiReturn.text.lower()
					if error == 'no data':
						replytext = "I'm sorry, I can't find any country data for {username}".format(username=username)
					elif "server too busy" in error:
						replytext = "The location lookup API is a bit busy, please try again in a little while"
					else:
						#Unknown error, vague error report
						replytext = "Sorry, an error occurred. Tell my owner to check the debug output, the exact error is in there"
				else:
					if 'countryName' not in data or data['countryName'] in ['-', 'None', None]:
						replytext = "I'm sorry, but I can't seem to determine which country {username} is from".format(username=username)
					else:
						if username == message.bot.nickname.lower():
							replytext = "I'm right here for you! And by 'here' I mean {country}".format(country=data['countryName'])
						else:
							replytext = "{username} appears to be from {country}".format(username=username, country=data['countryName'])

		message.reply(replytext)
