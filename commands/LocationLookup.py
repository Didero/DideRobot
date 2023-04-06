import json, socket

import requests

import Constants
from CommandTemplate import CommandTemplate
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
		if 'locatorhq' not in GlobalStore.commandhandler.apikeys or 'key' not in GlobalStore.commandhandler.apikeys['locatorhq'] or 'username' not in GlobalStore.commandhandler.apikeys['locatorhq']:
			message.reply(u"I'm sorry, my owner hasn't filled in the required API key for this module. Please poke them to add it")
			return

		replytext = u""
		userAddress = u""

		#no parameters added. Look up location of this user
		if message.messagePartsLength == 0:
			userAddress = message.user
		#Allow for any user address to be entered
		elif u'@' in message.messageParts[0]:
			userAddress = message.messageParts[0]
		#A username was provided. Convert that to a full user address
		else:
			#Check if a channel name was provided as well
			if message.messagePartsLength < 2 and message.isPrivateMessage:
				#If no channel was specified, and we're not in a channel currently, we can't really do anything. Inform the user of that
				replytext = u"If you use this script in a private message, you have to provide the channel to look in as the second parameter, " \
							u"otherwise I don't know where to look"
			else:
				channelname = message.source
				#A channel name was provided, only search that channel
				if message.messagePartsLength >= 2:
					channelname = message.messageParts[1]
					if not channelname[0] in Constants.CHANNEL_PREFIXES:
						channelname = '#' + channelname
				if channelname not in message.bot.channelsUserList:
					replytext = u"I'm not familiar with the channel '{}', sorry".format(channelname)
				else:
					nickToMatch = message.messageParts[0].lower() + '!'  #Add an exclamation mark to make sure the match is the full nick, not just the start
					replytext = u"I'm sorry, but I don't know who you're talking about..."  #Set it in advance, in case we don't find a match
					for channelUserAddress in message.bot.channelsUserList[channelname]:
						if channelUserAddress.lower().startswith(nickToMatch):
							userAddress = channelUserAddress
							break

		if userAddress != u"":
			username = userAddress.split("!", 1)[0]
			if username == userAddress:
				username = u'that user'

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
				replytext = u"I'm sorry, I couldn't determine the IP address of {username}".format(username=username)
			elif userIp == "127.0.0.1":
				if username.lower() == message.bot.nickname.lower():
					replytext = u"I'm right here for you!"
				else:
					replytext = u"That's on my server! And I'm right here"
			else:
				params = {'key': GlobalStore.commandhandler.apikeys['locatorhq']['key'],
						  'user': GlobalStore.commandhandler.apikeys['locatorhq']['username'],
						  'ip': userIp, 'format': 'json'}

				apiReturn = None
				try:
					apiReturn = requests.get("http://api.locatorhq.com", params=params, timeout=10.0)
					data = json.loads(apiReturn.text)
				except requests.exceptions.Timeout:
					replytext = u"I'm sorry, pinpointing {} location took too long for some reason. Maybe try again later?"
					replytext = replytext.format(u"your" if message.messagePartsLength == 0 else username + u"'s")
				except ValueError:
					#If there's an error message in the API output, it's not valid JSON. Check if we know what's wrong
					self.logError("[location] Invalid API reply: '{}'".format(apiReturn.text if apiReturn else "no API reply found"))
					error = apiReturn.text.lower()
					if error == 'no data':
						replytext = u"I'm sorry, I can't find any country data for {username}".format(username=username)
					elif "server too busy" in error:
						replytext = u"The location lookup API is a bit busy, please try again in a little while"
					else:
						#Unknown error, vague error report
						replytext = u"Sorry, an error occurred. Tell my owner to check the debug output, the exact error is in there"
				else:
					if 'countryName' not in data or data['countryName'] in ['-', 'None', None]:
						replytext = u"I'm sorry, but I can't seem to determine which country {username} is from".format(username=username)
					else:
						if username == message.bot.nickname.lower():
							replytext = u"I'm right here for you! And by 'here' I mean {country}".format(country=data['countryName'])
						else:
							replytext = u"{username} appears to be from {country}".format(username=username, country=data['countryName'])

		message.reply(replytext)
