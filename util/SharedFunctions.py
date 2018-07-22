import base64, codecs, json, logging, os, random, re

import requests

import Constants, GlobalStore

logger = logging.getLogger('DideRobot')


def makeTextBold(s):
	return '\x02' + s + '\x0f'  #\x02 is the 'bold' control character, '\x0f' cancels all decorations
