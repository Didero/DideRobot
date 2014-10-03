import xml.etree.ElementTree as ElementTree

#from bs4 import BeautifulSoup
import requests

from CommandTemplate import CommandTemplate
import GlobalStore


class Command(CommandTemplate):
	triggers = ['wolfram', 'wolframalpha', 'wa']
	helptext = "Sends the provided query to Wolfram Alpha and shows the results, if any"
	callInThread = True  #WolframAlpha can be a bit slow
	
	def execute(self, message):
		replystring = u""
		if not GlobalStore.commandhandler.apikeys.has_section('wolframalpha') or not GlobalStore.commandhandler.apikeys.has_option('wolframalpha', 'key'):
			replystring = u"No API key for Wolfram Alpha found. That's kinda sloppy, owner"
		elif message.messagePartsLength == 0:
			replystring = u"No query provided. I'm not just gonna make stuff up to send to Wolfram Alpha, I've got an API call limit! Add your query after the command."
		else:
			searchstring = message.message
			params = {'appid': GlobalStore.commandhandler.apikeys.get('wolframalpha', 'key'), 'podindex': '1,2,3', 'input': searchstring}
			apireturn = requests.get("http://api.wolframalpha.com/v2/query", params=params)
			xmltext = apireturn.text
			xmltext = xmltext.replace(r'\:', r'\u')  #weird WolframAlpha way of writing Unicode
			#Replace '\u0440' and the like with the actual character (first encode with latin-1 and not utf-8, otherwise pound signs and stuff mess up with a weird accented A in front)
			try:
				xmltext = unicode(xmltext.encode('latin-1'), encoding='unicode-escape')
			except Exception as e:
				print "[Wolfram] Error while turning unicode escapes into words with latin-1, using utf-8 ({})".format(str(e))
				xmltext = unicode(xmltext.encode('utf-8'), encoding='unicode-escape')
			xml = ElementTree.fromstring(xmltext.encode('utf8'))
			if xml.attrib['error'] != 'false':
				replystring = u"An error occurred"
				print "[Wolfram] An error occurred for the search query '{}'. Reply:".format(message.message)
				print xmltext.encode('utf-8')
			elif xml.attrib['success'] != 'true':
				replystring = u"No results found, sorry"
				#Most likely no results were found. See if there are suggestions for search improvements
				if xml.find('didyoumeans') is not None:
					didyoumeans = xml.find('didyoumeans').findall('didyoumean')
					suggestions = []
					for didyoumean in didyoumeans:
						if didyoumean.attrib['level'] != 'low':
							suggestion = didyoumean.text.replace('\n','').strip()
							if len(suggestion) > 0:
								suggestions.append(suggestion)
					if len(suggestions) > 0:
						replystring += u". Did you perhaps mean: {}".format(", ".join(suggestions))
			else:
				pods = xml.findall('pod')
				resultFound = False
				for pod in pods[1:]:
					if pod.attrib['title'] == "Input":
						continue
					for subpod in pod.findall('subpod'):
						text = subpod.find('plaintext').text
						if text is None:
							continue
						text = text.replace('\n', ' ').strip()
						#If there's no text in this pod (for instance if it's just an image)
						if len(text) == 0:
							continue
						#If the result is useless (searching for '3 usd' for instance returns coin weight first, starts with an opening bracket), skip it
						elif text.startswith('('):
							continue
						replystring += text
						resultFound = True
						break
					if resultFound:
						break

				if not resultFound:
					replystring += u"Sorry, results were either images or non-existent"

			replystring = replystring.replace('  ', ' ')
			#Add the search url
			replystring += u" (http://www.wolframalpha.com/input/?i={})".format(searchstring.replace(" ", "+"))
			
		message.bot.say(message.source, replystring)
