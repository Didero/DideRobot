# -*- coding: utf-8 -*-

import datetime, json, time

import requests

from CommandTemplate import CommandTemplate
from IrcMessage import IrcMessage
import GlobalStore
import SharedFunctions


class Command(CommandTemplate):
	triggers = ['weather', 'forecast']
	helptext = "Gets the weather or the forecast for the provided location"

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
			requestType = 'weather'
			if message.trigger == 'forecast':
				requestType = 'forecast/daily'
				params['cnt'] = 4  #Number of days to get forecast for
			try:
				req = requests.get("http://api.openweathermap.org/data/2.5/" + requestType, params=params, timeout=5.0)
				data = json.loads(req.text)
			except requests.exceptions.Timeout:
				replytext = u"Sorry, the weather API took too long to respond. Please try again in a little while"
			except ValueError:
				replytext = u"Sorry, I couldn't retrieve that data. Try again in a little while, maybe it'll work then"
				print "[weather] JSON load error. Data received:"
				print req.text
			else:
				if data['cod'] != 200 and data['cod'] != "200":
					if data['cod'] == 404 or data['cod'] == '404':
						replytext = u"I'm sorry, I don't know where that is"
					else:
						replytext = u"An error occurred, please tell my owner to look at the debug output, or try again in a little while ({}: {})".format(data['cod'], data['message'])
						print "[weather] ERROR in API lookup:"
						print data
				else:
					#We've got data! Parse it
					def getWindDirection(angle):
						#The highest wind angle where the direction applies
						windDirectionTranslation = {11.25: 'N', 33.75: 'NNE', 56.25: 'NE', 78.75: 'ENE', 101.25: 'E', 123.75: 'ESE',
													146.25: 'SE', 168.75: 'SSE', 191.25: 'S', 213.75: 'SSW', 236.25: 'SW',
													258.75: 'WSW', 281.25: 'W', 303.75: 'WNW', 326.25: 'NW', 348.75: 'NNW', 360.0: 'N'}
						windDirection = 'N'
						for maxDegrees in sorted(windDirectionTranslation.keys()):
							if angle < maxDegrees:
								break
							else:
								windDirection = windDirectionTranslation[maxDegrees]
						return windDirection

					def celsiusToFahrenheit(celsius):
						return (celsius * 9 / 5) + 32

					if message.trigger == 'weather':
						dataAge = round((time.time() - data['dt']) / 60)
						dataAgeDisplay = u""
						if dataAge <= 0:
							dataAgeDisplay = u"brand new"
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
						replytext += u"{tempC:.1f}°C / {tempF:.1f}°F, {weatherType}. Wind: {windSpeed:.1f} m/s, {windDir}. Humidity of {humidity}% (Data is {dataAge})"
						replytext = replytext.format(city=data['name'], country=data['sys']['country'], tempC=data['main']['temp'], tempF=celsiusToFahrenheit(data['main']['temp']),
													 weatherType=data['weather'][0]['description'], windSpeed=data['wind']['speed'], windDir=getWindDirection(data['wind']['deg']),
													 humidity=data['main']['humidity'], dataAge=dataAgeDisplay)

					else:
						#Forecast
						replytext = u"Forecast for "
						if 'name' in data['city'] and len(data['city']['name']) > 0:
							replytext += u"{city} ({country}). "
						else:
							replytext += u"{country}. "
						replytext = replytext.format(city=data['city']['name'], country=data['city']['country'])
						forecasts = []
						for day in data['list']:
							dayname = datetime.datetime.utcfromtimestamp(day['dt']).strftime(u"%a").upper()

							forecast = u"{dayname}: {minTempC:.0f}-{maxTempC:.0f}°C / {minTempF:.0f}-{maxTempF:.0f}°F, {weatherType}, {humidity}% hum., {windSpeed:.0f}m/s {windDir} wind."
							forecast = forecast.format(dayname=dayname, minTempC=day['temp']['min'], maxTempC=day['temp']['max'],
													minTempF=celsiusToFahrenheit(day['temp']['min']), maxTempF=celsiusToFahrenheit(day['temp']['max']),
													humidity=day['humidity'], windSpeed=day['speed'], windDir=getWindDirection(day['deg']), weatherType=day['weather'][0]['description'])
							forecasts.append(forecast)
						replytext += SharedFunctions.addSeparatorsToString(forecasts)


		message.bot.sendMessage(message.source, replytext)
