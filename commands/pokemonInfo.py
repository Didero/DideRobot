# -*- coding: latin-1 -*-

import re
import xml.etree.ElementTree as ElementTree

import requests

from CommandTemplate import CommandTemplate
import GlobalStore


class Command(CommandTemplate):
	triggers = ['pokemon']
	helptext = "Looks up info on the provided Pokemon"
	callInThread = True  #WolframAlpha can be a bit slow

	def execute(self, message):
		replytext = u""
		if message.messagePartsLength == 0:
			replytext = u"Please provide the name of a Pokemon to search for"
		else:
			wolframReply = GlobalStore.commandhandler.runCommandFunction('fetchWolframAlphaData', None, "pokemon " + message.message, -1)
			if not wolframReply:
				replytext = u"Sorry, no WolframAlpha module found"
			elif not wolframReply[0]:
				replytext = wolframReply[1]
			else:
				print "[pokemon] Data received:"
				print wolframReply[1].encode('utf8')
				pokemondata = {}
				dataKeysToKeep = ['name', u'Pokédex number', 'type', 'generation', 'species', 'evolves from', 'evolves into', 'natural abilities',
								  'hit points', 'attack', 'defense', 'special attack', 'special defense', 'speed']
				tableAsDict = self.turnWolframTableIntoDict(wolframReply[1])
				for key, value in tableAsDict.iteritems():
					if key in dataKeysToKeep:
						value = re.sub(' *\| *', ', ', value)  #'type' for instance is displayed as 'fire  |  flying' sometimes. Clean that up
						pokemondata[key] = value
				if len(pokemondata) == 0:
					replytext = u"No data on that Pokemon was found, for some reason. Did you make a typo?"
				else:
					print "[pokemon] Collected data:"
					print pokemondata
					#Let's turn the collected data into something presentable!
					replytext = u"{name} ({generation} nr {Pokédex number}) is a {species} of type '{type}'."
					if 'evolves from' in pokemondata:
						replytext += u" Evolves from {evolves from}."
					if 'evolves into' in pokemondata:
						replytext += u" Evolves into {evolves into}."
					replytext += u" {hit points} HP, {attack} Atk, {defense} Def, "
					replytext += u"{special attack} SAtk, {special defense} SDef, {speed} Spd."
					replytext = replytext.format(**pokemondata)

		message.bot.sendMessage(message.source, replytext)

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