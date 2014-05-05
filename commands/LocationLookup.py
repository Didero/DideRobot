import json, re, socket

import requests

from CommandTemplate import CommandTemplate
import GlobalStore

class Command(CommandTemplate):
	triggers = ['location']
	helptext = "Retrieves the country a user is from (or at least it tries to, no promises). Arguments are a user name, and optionally a channel name (which is mainly useful in PMs)"

	def execute(self, bot, user, target, triggerInMsg, msg, msgWithoutFirstWord, msgParts, msgPartsLength):
		replytext = u""
		userAddress = u""

		if not GlobalStore.commandhandler.apikeys.has_section('locatorhq') or not GlobalStore.commandhandler.apikeys.has_option('locatorhq', 'key') or not GlobalStore.commandhandler.apikeys.has_option('locatorhq', 'username'):
			bot.say(target, u"I'm sorry, my owner hasn't filled in the required API key for this module. Please poke them to add it")
			return

		#no parameters added. Look up location of this user
		if msgPartsLength <= 1:
			userAddress = user
		#A username was provided. Convert that to a full user address
		else:
			#Check if a channel name was provided as well
			if msgPartsLength < 3 and not target.startswith('#'):
				#If no channel was specified, and we're not in a channel currently, we can't really do anything. Inform the user of that
				replytext = u"If you use this script in a private message, you have to provide the channel to look in as the second parameter"
			else:
				channelname = target
				#A channel name was provided, only search that channel
				if msgPartsLength >= 3:
					channelname = msgParts[2]
					if not channelname.startswith('#'):
						channelname = '#' + channelname
				if channelname not in bot.channelsUserList:
					replytext = u"That is not a channel I'm familiar with, sorry"
				else:
					for channelUserAddress in bot.channelsUserList[channelname]:
						if channelUserAddress.startswith(msgParts[1]):
							userAddress = channelUserAddress
							break
						else:
							replytext = u"I'm sorry, but I don't know who you're talking about..."

		if userAddress != u"":
			print "Using user address: '{}'".format(userAddress)
			userIpMatches = re.search(".*!.*@\D*(\d{1,3}[-.]\d{1,3}[-.]\d{1,3}[-.]\d{1,3}).*", userAddress)
			userIp = ""
			if userIpMatches:
				userIp = userIpMatches.group(1).replace('-', '.')
				print "IP match found, using IP '{}'".format(userIp)
			else:
				userAddressParts = userAddress.split('.')
				try:
					userIp = socket.gethostbyname("{}.{}".format(userAddressParts[-2], userAddressParts[-1]))
					print "No IP match found, getting IP from hostname '{}.{}', using IP '{}'".format(userAddressParts[-2], userAddressParts[-1], userIp)
				except:
					print "[LocationLookup] Unable to determine IP address from host '{}.{}'".format(userAddressParts[-2], userAddressParts[-1])


			if userIp == "":
				replytext = u"I'm sorry, I couldn't determine the IP address of that user"
			else:
				params = {'key': GlobalStore.commandhandler.apikeys.get('locatorhq', 'key'), 'user': GlobalStore.commandhandler.apikeys.get('locatorhq', 'username'), 'ip': userIp, 'format': 'json'}
				apiReturn = requests.get("http://api.locatorhq.com", params=params)
				print u"Url: '{}'".format(apiReturn.url)
				print u"Response:"
				print apiReturn.text
				if apiReturn.text.startswith('Sorry'):
					#An error occurred
					print apiReturn.text
					replytext = u"Sorry, an error occurred. Tell my owner to check the debug output, the exact error is in there"
				elif apiReturn.text.lower() == 'no data':
					replytext = u"I'm sorry, I can't find any country data for that user"
				else:
					data = json.loads(apiReturn.text)
					if 'countryName' not in data or data['countryName'] == '-':
						replytext = u"I'm sorry, but I don't know which country that user is from"
					else:
						replytext = u"{} appears to be from {}".format(userAddress.split('!', 1)[0], data['countryName'])

		bot.say(target, replytext)
