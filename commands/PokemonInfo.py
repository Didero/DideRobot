# -*- coding: utf-8 -*-

import re

from commands.CommandTemplate import CommandTemplate
import GlobalStore
from CustomExceptions import CommandException, CommandInputException


class Command(CommandTemplate):
	triggers = ['pokemon']
	helptext = "Looks up info on the provided Pokémon"
	callInThread = True  #WolframAlpha can be a bit slow

	def execute(self, message):
		if not GlobalStore.commandhandler.hasCommandFunction('fetchWolframAlphaData'):
			raise CommandException("Sorry, no WolframAlpha module found")

		if message.messagePartsLength == 0:
			raise CommandInputException("Please provide the name of a Pokémon to search for")

		wolframReply = GlobalStore.commandhandler.runCommandFunction('fetchWolframAlphaData', None, "pokemon " + message.message, -1)
		pokemondata = {}
		dataKeysToKeep = ['name', 'Pokédex number', 'type', 'generation', 'species', 'evolves from', 'evolves into', 'natural abilities',
						  'hit points', 'attack', 'defense', 'special attack', 'special defense', 'speed']
		tableAsDict = self.turnWolframTableIntoDict(wolframReply)
		for key, value in tableAsDict.items():
			if key in dataKeysToKeep:
				value = re.sub(' *\| *', ', ', value)  #'type' for instance is displayed as 'fire  |  flying' sometimes. Clean that up
				pokemondata[key] = value
		if len(pokemondata) == 0:
			return message.reply("No data on that Pokémon was found, for some reason. Did you make a typo?")
		#Encode the url name properly
		pokemondata['urlname'] = pokemondata['name'].replace(' ', '_')
		#Not all Pokémon list a species
		if 'species' not in pokemondata:
			pokemondata['species'] = "Pokémon of unknown species,"
		#Let's turn the collected data into something presentable!
		replytext = "{name} ({generation} nr {Pokédex number}) is a {species} of type '{type}'."
		if 'evolves from' in pokemondata:
			replytext += " Evolves from {evolves from}."
		if 'evolves into' in pokemondata:
			replytext += " Evolves into {evolves into}."
		replytext += " {hit points} HP, {attack} Atk, {defense} Def, " \
					 "{special attack} SAtk, {special defense} SDef, {speed} Spd. " \
					 "More info: http://bulbapedia.bulbagarden.net/wiki/{urlname}"
		replytext = replytext.format(**pokemondata)
		message.reply(replytext)

	def turnWolframTableIntoDict(self, text):
		text = text.replace('<plaintext>', '').replace('</plaintext>', '')
		tableAsDict = {}
		lines = text.splitlines()
		for line in lines:
			parts = line.split(r'|', 1)
			if len(parts) > 1:
				parts[0] = parts[0].strip()
				parts[1] = parts[1].strip()
				if len(parts[0]) > 0 and len(parts[1]) > 0:
					tableAsDict[parts[0]] = parts[1]
		return tableAsDict