import json, socket

import requests

from CommandTemplate import CommandTemplate
import GlobalStore
from IrcMessage import IrcMessage


class Command(CommandTemplate):
	triggers = ['location']
	helptext = "Retrieves the country a user is from (or at least it tries to, no promises). Arguments are a user name, and optionally a channel name (which is mainly useful in PMs)"

	def execute(self, message):
		"""
		:type message: IrcMessage
		"""

		#First check for the presence of the API key
		if not GlobalStore.commandhandler.apikeys.has_section('locatorhq') or not GlobalStore.commandhandler.apikeys.has_option('locatorhq', 'key') or not GlobalStore.commandhandler.apikeys.has_option('locatorhq', 'username'):
			message.bot.say(message.source, u"I'm sorry, my owner hasn't filled in the required API key for this module. Please poke them to add it")
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
					if not channelname.startswith('#'):
						channelname = '#' + channelname
				if channelname not in message.bot.channelsUserList:
					replytext = u"That is not a channel I'm familiar with, sorry"
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
			else:
				params = {'key': GlobalStore.commandhandler.apikeys.get('locatorhq', 'key'),
						  'user': GlobalStore.commandhandler.apikeys.get('locatorhq', 'username'), 'ip': userIp, 'format': 'json'}
				apiReturn = requests.get("http://api.locatorhq.com", params=params)

				try:
					data = json.loads(apiReturn.text)
				except ValueError:
					#If there's an error message in the API output, it's not valid JSON. Check if we know what's wrong
					print "[location] ERROR, API returned: '{}'".format(apiReturn.text)
					error = apiReturn.text.lower()
					if error == 'no data':
						replytext = u"I'm sorry, I can't find any country data for {username}".format(username=username)
					elif "server too busy" in error:
						replytext = u"The location lookup API is a bit busy, please try again in a little while"
					else:
						#Unknown error, vague error report
						replytext = u"Sorry, an error occurred. Tell my owner to check the debug output, the exact error is in there"
				else:
					if 'countryName' not in data or data['countryName'] == '-':
						replytext = u"I'm sorry, but I can't seem to determine which country {username} is from".format(username=username)
					else:
						if username == message.bot.nickname.lower():
							replytext = u"I'm right here for you! And by 'here' I mean {country}".format(country=data['countryName'])
						else:
							replytext = u"{username} appears to be from {country}".format(username=username, country=data['countryName'])

		message.bot.say(message.source, replytext)
