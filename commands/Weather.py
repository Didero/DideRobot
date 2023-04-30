# -*- coding: utf-8 -*-

import datetime, json, time

import requests

from commands.CommandTemplate import CommandTemplate
from IrcMessage import IrcMessage
import Constants, GlobalStore
from util import IrcFormattingUtil


class Command(CommandTemplate):
	triggers = ['weather', 'forecast']
	helptext = "Gets the weather or the forecast for the provided location"

	def execute(self, message):
		"""
		:type message: IrcMessage
		"""

		replytext = ""
		if 'openweathermap' not in GlobalStore.commandhandler.apikeys:
			replytext = "No API key for OpenWeatherMap found, please tell my owner so they can fix this"
		elif message.messagePartsLength == 0:
			replytext = "Please enter the name of a city"
		else:
			params = {"APPID": GlobalStore.commandhandler.apikeys['openweathermap'], "q": message.message, "units": "metric"}
			requestType = 'weather'
			if message.trigger == 'forecast':
				requestType = 'forecast/daily'
				params['cnt'] = 4  #Number of days to get forecast for
			try:
				req = requests.get("http://api.openweathermap.org/data/2.5/" + requestType, params=params, timeout=5.0)
				data = json.loads(req.text)
			except requests.exceptions.Timeout:
				replytext = "Sorry, the weather API took too long to respond. Please try again in a little while"
			except ValueError:
				replytext = "Sorry, I couldn't retrieve that data. Try again in a little while, maybe it'll work then"
				self.logError("[weather] JSON load error. Data received:")
				self.logError(req.text)
			else:
				if data['cod'] != 200 and data['cod'] != "200":
					if data['cod'] == 404 or data['cod'] == '404':
						replytext = "I'm sorry, I don't know where that is"
					else:
						replytext = "An error occurred, please tell my owner to look at the debug output, or try again in a little while ({}: {})".format(data['cod'], data['message'])
						self.logError("[weather] ERROR in API lookup:")
						self.logError(data)
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
						if dataAge <= 0:
							dataAgeDisplay = "brand new"
						else:
							dataAgeDisplay = "{dataAge:.0f} minute"
							if dataAge > 1:
								dataAgeDisplay += "s"
							dataAgeDisplay += " old"
							dataAgeDisplay = dataAgeDisplay.format(dataAge=dataAge)

						windString = "{:.1f} m/s".format(data['wind']['speed'])
						#Only add a wind direction if we know it
						if 'deg' in data['wind']:
							windString += ", " + getWindDirection(data['wind']['deg'])

						#Not all replies include a placename or a countryname
						placename = data['name'] if 'name' in data and len(data['name']) > 0 else None
						countryname = data['sys']['country'] if 'sys' in data and 'country' in data['sys'] and len(data['sys']['country']) > 0 else None
						if placename and countryname:
							replytext = "{} ({})".format(placename, countryname)
						elif placename:
							replytext = "{}".format(placename)
						elif countryname:
							replytext = "Somewhere in {}".format(countryname)
						else:
							replytext = "Somewhere unknown"

						#Add the actual weather info
						replytext += ": {tempC:.1f}°C / {tempF:.1f}°F, {weatherType}. Wind: {windString}. Humidity of {humidity}% (Data is {dataAge})"
						replytext = replytext.format(tempC=data['main']['temp'], tempF=celsiusToFahrenheit(data['main']['temp']), weatherType=data['weather'][0]['description'],
													 windString=windString, humidity=data['main']['humidity'], dataAge=dataAgeDisplay)

					else:
						#Forecast
						placename = data['city']['name'] if 'city' in data and 'name' in data['city'] and len(data['city']['name']) > 0 else None
						countryname = data['city']['country'] if 'city' in data and 'country' in data['city'] and len(data['city']['country']) > 0 else None
						replytext = "Forecast for "
						if placename and countryname:
							replytext += "{} ({})".format(placename, countryname)
						elif placename:
							replytext += placename
						elif countryname:
							replytext += countryname
						else:
							replytext += "somewhere unknown"
						replytext += ": "

						forecasts = []
						for day in data['list']:
							dayname = datetime.datetime.utcfromtimestamp(day['dt']).strftime("%a").upper()

							forecast = "{dayname}: {minTempC:.0f}-{maxTempC:.0f}°C / {minTempF:.0f}-{maxTempF:.0f}°F, {weatherType}, {humidity}% hum., {windSpeed:.0f}m/s {windDir} wind"
							forecast = forecast.format(dayname=IrcFormattingUtil.makeTextBold(dayname), minTempC=day['temp']['min'], maxTempC=day['temp']['max'],
													   minTempF=celsiusToFahrenheit(day['temp']['min']), maxTempF=celsiusToFahrenheit(day['temp']['max']),
													   humidity=day['humidity'], windSpeed=day['speed'], windDir=getWindDirection(day['deg']), weatherType=day['weather'][0]['description'])
							forecasts.append(forecast)
						replytext += Constants.GREY_SEPARATOR.join(forecasts)

		message.bot.sendMessage(message.source, replytext)
