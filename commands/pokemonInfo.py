# -*- coding: latin-1 -*-

import re
import xml.etree.ElementTree as ElementTree

import requests

from CommandTemplate import CommandTemplate
import GlobalStore


class Command(CommandTemplate):
	triggers = ['pokemon']
	helptext = "Looks up info on the provided Pokemon"
	callInThread = True #WolframAlpha can be a bit slow

	def execute(self, message):
		replytext = u""
		if message.messagePartsLength == 0:
			replytext = u"Please provide the name of a Pokemon to search for"
		elif not GlobalStore.commandhandler.apikeys.has_section('wolframalpha') or not GlobalStore.commandhandler.apikeys.has_option('wolframalpha', 'key'):
			replytext = u"No API key for Wolfram Alpha found. That's kinda sloppy, owner"
		else:
			searchstring = "pokemon " + message.message
			params = {'appid': GlobalStore.commandhandler.apikeys.get('wolframalpha', 'key'), 'format': 'plaintext', 'input': searchstring}
			apireturn = requests.get("http://api.wolframalpha.com/v2/query", params=params)
			xmltext = apireturn.text
			xmltext = xmltext.replace(r'\:', r'\u') #weird WolframAlpha way of writing Unicode
			#Replace '\u0440' and the like with the actual character (first encode with latin-1 and not utf-8, otherwise pound signs and stuff mess up with a weird accented A in front)
			xmltext = unicode(xmltext.encode('latin-1', 'ignore'), encoding="unicode-escape").encode('utf-8')#.replace(u'é',u'e')
			#print xmltext
			xml = ElementTree.fromstring(xmltext)
			if xml.attrib['error'] != 'false':
				replytext = u"An error occurred"
				print xmltext
			elif xml.attrib['success'] != 'true':
				replytext = u"Nothing was found, sorry"
				print xmltext
			else:
				pokemondata = {}
				dataKeysToKeep = ['name', u'Pokédex number', 'type', 'generation', 'species', 'evolves from', 'evolves into', 'natural abilities',
								  'hit points', 'attack', 'defense', 'special attack', 'special defense', 'speed']

				#Go through all the pods and subpods to collect interesting data
				for pod in xml.findall('pod')[1:]:
					text = pod.find('subpod').find('plaintext').text
					if text:
						tableAsDict = self.turnWolframTableIntoDict(text)
						for key, value in tableAsDict.iteritems():
							if key in dataKeysToKeep:
								value = re.sub(' *\| *', ', ', value)  #'type' for instance is displayed as 'fire  |  flying' sometimes. Clean that up
								pokemondata[key] = value
				print "Collected data: ", pokemondata

				if len(pokemondata) == 0:
					replytext = u"No data was found, for some reason"
				else:
					#Let's turn the collected data into something presentable!
					replytext = u"{pokemondata[name]} ({pokemondata[generation]} nr {pokemondata[Pokédex number]}) is a {pokemondata[species]} of type '{pokemondata[type]}'."
					if 'evolves from' in pokemondata:
						replytext += u" Evolves from {pokemondata[evolves from]}."
					if 'evolves into' in pokemondata:
						replytext += u" Evolves into {pokemondata[evolves into]}."
					replytext += u" {pokemondata[hit points]} HP, {pokemondata[attack]} Atk, {pokemondata[defense]} Def, "
					replytext += u"{pokemondata[special attack]} SAtk, {pokemondata[special defense]} SDef, {pokemondata[speed]} Spd."
					replytext = replytext.format(pokemondata=pokemondata)

		message.bot.say(message.source, replytext)

	def turnWolframTableIntoDict(self, text):
		text = text.replace('<plaintext>', '').replace('</plaintext>', '')
		tableAsDict = {}
		lines = text.splitlines()
		for line in lines:
			parts = line.split(r'|', 1)
			#print "turned '{}' into '{}'".format(line, ", ".join(parts))
			if len(parts) > 1:
				parts[0] = parts[0].strip()
				parts[1] = parts[1].strip()
				if len(parts[0]) > 0 and len(parts[1]) > 0:
				   tableAsDict[parts[0]] = parts[1]
		return tableAsDict