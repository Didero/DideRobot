# -*- coding: utf-8 -*-

import json, time

import requests

from CommandTemplate import CommandTemplate
from IrcMessage import IrcMessage
import GlobalStore


class Command(CommandTemplate):
	triggers = ['weather']
	helptext = "Gets the weather for the provided city"

	def execute(self, message):
		"""
		:type message: IrcMessage
		"""

		replytext = u""
		if not GlobalStore.commandhandler.apikeys.has_section("openweathermap") or not GlobalStore.commandhandler.apikeys.has_option("openweathermap", "key"):
			replytext = u"No API key for OpenWeatherMap found, please tell my owner so they can fix this"
		elif message.messagePartsLength == 0:
			replytext = u"Please enter the name of a city"
		else:
			params = {"APPID": GlobalStore.commandhandler.apikeys.get("openweathermap", "key"), "q": message.message, "units": "metric"}
			req = requests.get("http://api.openweathermap.org/data/2.5/weather", params=params)
			try:
				data = json.loads(req.text)
			except ValueError:
				replytext = u"Sorry, I couldn't retrieve that data. Try again in a little while, maybe it'll work then"
				print "[weather] JSON load error. Data received:"
				print req.text
			else:
				if data['cod'] != 200:
					if data['cod'] == 404 or data['cod'] == '404':
						replytext = u"I'm sorry, I don't know where that is"
					else:
						replytext = u"An error occurred, please tell my owner to look at the debug output, or try again in a little while ({}: {})".format(data['cod'], data['message'])
						print "[weather] ERROR in API lookup:"
						print data
				else:
					#We've got data! Parse it
					#The highest wind angle where the direction applies
					windDirectionTranslation = {11.25: 'N', 33.75: 'NNE', 56.25: 'NE', 78.75: 'ENE', 101.25: 'E', 123.75: 'ESE',
												146.25: 'SE', 168.75: 'SSE', 191.25: 'S', 213.75: 'SSW', 236.25: 'SW',
												258.75: 'WSW', 281.25: 'W', 303.75: 'WNW', 326.25: 'NW', 348.75: 'NNW', 360.0: 'N'}
					windDirection = 'N'
					for maxDegrees in sorted(windDirectionTranslation.keys()):
						if data['wind']['deg'] < maxDegrees:
							break
						else:
							windDirection = windDirectionTranslation[maxDegrees]

					tempInFahrenheit = (data['main']['temp'] * 9 / 5) + 32

					dataAge = round((time.time() - data['dt']) / 60)
					dataAgeDisplay = u""
					if dataAge <= 0:
						dataAge = u"brand new"
					else:
						dataAgeDisplay = u"{dataAge:.0f} minute"
						if dataAge > 1:
							dataAgeDisplay += u"s"
						dataAgeDisplay += u" old"
						dataAgeDisplay = dataAgeDisplay.format(dataAge=dataAge)

					#Not all replies include a placename
					if 'name' in data and len(data['name']) > 0:
						replytext += u"{city} ({country}): "
					elif 'country' in data['sys'] and len(data['sys']['country']) > 0:
						replytext += u"Somewhere in {country}: "
					replytext += u"{tempC:.2g}°C / {tempF:.3g}°F, {weatherType}. Wind: {windSpeed} m/s, {windDir}. Humidity of {humidity}% (Data is {dataAge})"
					replytext = replytext.format(city=data['name'], country=data['sys']['country'], tempC=data['main']['temp'], tempF=tempInFahrenheit, weatherType=data['weather'][0]['description'],
												 windSpeed=data['wind']['speed'], windDir=windDirection, humidity=data['main']['humidity'], dataAge=dataAgeDisplay)

		message.bot.sendMessage(message.source, replytext)