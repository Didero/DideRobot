def getValuesFromDict(dictToCopyFrom, *keysToCopy):
	copiedDict = {}
	for keyToCopy in keysToCopy:
		copiedDict[keyToCopy] = dictToCopyFrom.get(keyToCopy, None)
	return copiedDict
