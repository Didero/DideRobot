import datetime, os, random, sqlite3, time, unicodedata

from commands.CommandTemplate import CommandTemplate
from IrcMessage import IrcMessage
import GlobalStore
from CustomExceptions import CommandInputException, WebRequestException
from util import IrcFormattingUtil, WebUtil
import PermissionLevel


class Command(CommandTemplate):
	triggers = ['list', 'listf']
	helptext = "Create and add to lists. Format: {commandPrefix}list[f] [subcommand] (listname) (parameters). " \
			   "'{commandPrefix}listf' adds more info to a returned entry than '{commandPrefix}list'. " \
			   "Subcommands: list, create, destroy, add, remove, get, random, getbyid, search, getall, info, rename, edit, setdescription, cleardescription, setadmin. " \
			   "Use '{commandPrefix}help list [subcommand]' to get details on how to use that subcommand"

	databasePath = os.path.join(GlobalStore.scriptfolder, "data", "Lists.db")

	def onLoad(self):
		GlobalStore.commandhandler.addCommandFunction(__file__, 'getRandomListEntry', self.getRandomListEntry)
		# The 'edited_by' and 'edited_date' columns were added later, so we can't be sure the current database has those. Make sure they exist
		if os.path.isfile(self.databasePath):
			with sqlite3.connect(self.databasePath) as connection:
				cursor = connection.cursor()
				if self.doTablesExist(cursor) and not cursor.execute("SELECT COUNT(*) FROM pragma_table_info('list_entries') WHERE name='edited_by'").fetchone()[0]:
					self.logInfo("[List] Updating old database, adding 'edited_by' and 'edited_date' columns")
					cursor.execute("ALTER TABLE list_entries ADD COLUMN edited_by TEXT")
					cursor.execute("ALTER TABLE list_entries ADD COLUMN edited_date REAL")
					connection.commit()

	def getHelp(self, message):
		if message.messagePartsLength <= 1:
			# No subcommand provided, return normal help text
			return CommandTemplate.getHelp(self, message)
		# Show help text for the provided subcommand
		subcommand = message.messageParts[1].lower()
		if subcommand == 'list':
			helptext = "{commandPrefix}list list. Lists all available lists for this server and channel"
		elif subcommand == 'create':
			helptext = "{commandPrefix}list create ('admin') ('server'/'channel') [name] (description). 'admin' is optional and indicates only bot admins can add entries. " \
					   "'server' means it's a server-wide list, 'channel' means the list is for this channel only; 'channel' is the default when this subcommand is called in a channel, 'server' when called in a private message. " \
					   "'name' is the name of the list; it can't contain spaces. 'description' is optional and can be a description of the list, which will show up in an 'info' call"
		else:
			helptext = "{commandPrefix}list {subcommand} [name]"
			if subcommand == 'destroy':
				helptext += ". Destroys the list specified by 'name'. This completely removes all data of this list and all entries, which is non-reversible, so triple-check your spelling"
			elif subcommand == 'add':
				helptext += " [text]. Adds 'text' as an entry to the list specified by 'name', if that list exists"
			elif subcommand == 'remove':
				helptext += " [id]. Removes entry number 'id' from the list specified by 'name', if that list and id exist"
			elif subcommand == 'get':
				helptext += " [(id)/(searchquery)]. Get an entry from the list specified by 'name'. If an id is specified, the entry with that id will be returned, if it exists (Same as 'getbyid'). " \
							"If a searchquery is provided, it returns entries that contain the provided text (Same as 'searchquery'). If neither is provided, a random entry from the list will be picked (Same as 'random')"
			elif subcommand == 'random':
				helptext += ". Get a random entry from the list specified by 'name'"
			elif subcommand == 'getbyid':
				helptext += " [id]. Get the entry specified by 'id' from the list specified by 'name'"
			elif subcommand == 'search':
				helptext += " [search query]. Searches the list specified by 'name' for entries matching 'search query'. '*' and '%' are multi-character wildcards, '?' and '_' are single-character wildcards. " \
							"If no wildcards are added, a multi-character wildcard character will be added to the start and end of the provided query"
			elif subcommand == 'getall':
				helptext += " [(search query)]. Shows all entries of the list specified by 'name', or only the entries matching the optional search query if one is provided. Uploads the resuls and links them, so it's not spammy"
			elif subcommand == 'info':
				helptext += ". Shows info about the list specified by 'name'"
			elif subcommand == 'rename':
				helptext += " [newListname]. Changes the name of the list specified by 'name' to 'newListname', if that list doesn't exist already"
			elif subcommand == 'edit':
				helptext += " [id] [newEntryText]. Edits the entry specified by 'id' in the list specified by 'name'. The text of that entry will be replaced with the provided 'newEntryText'. The {commandPrefix}listf output for that entry will show that it has been edited"
			elif subcommand == 'setdescription':
				helptext += " [description]. Sets the description for the list specified by 'name'. This description can be seen by doing '{CP}list info [name]'"
			elif subcommand == 'cleardescription':
				helptext += ". Clears the description for the list specified by 'name'."
			elif subcommand == 'setadmin':
				helptext += " [setAdminOnly]. Sets whether only admins can add and remove entries from the list specified by 'name'. Parameter should be \"true\" or \"false\""
			else:
				helptext = "Unknown list subcommand '{subcommand}'. Maybe you made a typo? Use '{commandPrefix}help list' to see all the available subcommands"
		# Some subcommands show more info when the 'listf' command is used instead of 'list'. Add that
		if subcommand in ('get', 'random', 'getbyid', 'search', 'info'):
			helptext += ". Using '{commandPrefix}listf' instead of '{commandPrefix}list' shows extra info"
		# Some commands can only be used by bot admins, add that
		elif subcommand in ('create', 'destroy', 'rename', 'setdescription', 'cleardescription', 'setadmin'):
			helptext += ". This subcommand is admin-only"
		return helptext.format(commandPrefix=message.bot.getCommandPrefix(message.source), subcommand=subcommand)


	def execute(self, message):
		"""
		:type message: IrcMessage
		"""
		if message.messagePartsLength == 0:
			return message.reply(self.getHelp(message))

		subcommand = message.messageParts[0].lower()

		if subcommand == 'help':
			return message.reply(self.getHelp(message))

		shouldAddEntryInfo = (message.trigger == 'listf')
		with sqlite3.connect(self.databasePath) as connection:
			cursor = connection.cursor()
			servername = message.bot.serverfolder
			channelname = message.source
			if subcommand == 'list':
				if not self.doTablesExist(cursor):
					return message.reply("Seems like there's no lists at all. Seems a bit boring, to be honest")
				# List all available lists
				result = cursor.execute("SELECT name, channel FROM lists WHERE server=? AND (channel=? OR channel IS NULL)", (servername, channelname)).fetchall()
				if not result:
					return message.reply("I couldn't find any lists. You should think up a good idea for one!")
				channelListNames = []
				serverListNames = []
				for resultEntry in result:
					listname = resultEntry[0]
					listsource = resultEntry[1]
					if listsource:
						channelListNames.append(listname)
					else:
						serverListNames.append(listname)
				replytext = ""
				if serverListNames:
					replytext += " Server lists: {}".format(", ".join(sorted(serverListNames)))
				if channelListNames:
					replytext += " Channel lists: {}".format(", ".join(sorted(channelListNames)))
				return message.reply(replytext.lstrip())

			elif subcommand == 'create':
				if message.messagePartsLength == 1:
					raise CommandInputException("You'll need to add at least a name of the list to create, read the 'create' subcommand help for other options")
				createParams = message.messageParts[1:]

				createParam = createParams.pop(0).lower()
				# Check if the optional 'admin' parameter was provided, making it an admin-only list
				isListAdminOnly = False
				if createParam == 'admin':
					isListAdminOnly = True
					createParam = createParams.pop(0).lower()

				# Check if a server/channel parameter was passed
				# If the command was called in a channel, assume a channel-only list. If it was called in a PM, assume a server list
				isChannelList = not message.isPrivateMessage
				if createParam == 'server' or createParam == 'channel':
					isChannelList = createParam == 'channel'
					createParam = createParams.pop(0).lower()
				if isChannelList and message.isPrivateMessage:
					raise CommandInputException("Creating a channel list doesn't work in private messages, either create a server list or create this list in a channel")
				if not message.doesSenderHavePermission(PermissionLevel.CHANNEL if isChannelList else PermissionLevel.SERVER):
					raise CommandInputException("Sorry, only {0} admins are allowed to create {0} lists".format("channel" if isChannelList else "server"))

				listname = self.normalizeListname(createParam)
				listDescription = ' '.join(createParams) if createParams else None

				# Check if the database exists
				if not self.doTablesExist(cursor):
					cursor.execute("CREATE TABLE lists ("
								   "id INTEGER PRIMARY KEY, name TEXT NOT NULL, description TEXT, server TEXT NOT NULL, channel TEXT, creator TEXT, creation_date REAL, is_admin_only INTEGER)")
					cursor.execute("CREATE TABLE list_entries ("
								   "id INTEGER NOT NULL, list_id INTEGER NOT NULL, text TEXT NOT NULL, creator TEXT, creation_date REAL, edited_by TEXT, edited_date REAL,"
								   "PRIMARY KEY (id, list_id), FOREIGN KEY(list_id) REFERENCES lists(id))")
				# If the database exists, check whether a list with the provided name already exists for the provided server
				else:
					if self.getBasicListData(cursor, listname, servername, channelname)[0] is not None:
						# A match has been found, so the list already exists, either for this channel or for the server. Abort
						raise CommandInputException("A list with the name '{}' already exists. That's easier for both of us, you just need to add your ideas to that list then!".format(listname))

				# Create the list
				cursor.execute("INSERT INTO lists (name, description, server, channel, creator, creation_date, is_admin_only) "
							   "VALUES (:listname, :description, :servername, :channelname, :creator, :creation_date, :isadmin)",
							   {'listname': listname, 'description': listDescription, 'servername': servername, 'channelname': channelname if isChannelList else None,
								'creator': message.userNickname, 'creation_date': time.time(), 'isadmin': isListAdminOnly if isListAdminOnly else None})
				connection.commit()
				return message.reply("Successfully created the '{}' list. Now add some entries to it with the 'add' subcommand. Enjoy!".format(listname))

			# All subsequent subcommands need a list, so check if a listname was provided, and check if that list exists
			if message.messagePartsLength < 2:
				raise CommandInputException("Please provide a list name, or use the 'list' subcommand to see all the available lists")
			if not self.doTablesExist(cursor):
				return message.reply("Hmm, I don't seem to have any lists stored yet, so I can't execute that subcommand. Sorry!")
			listname = self.normalizeListname(message.messageParts[1])
			listId, isListAdminOnly, isChannelSpecificList = self.getBasicListData(cursor, listname, servername, channelname)
			if not listId:
				raise CommandInputException("I couldn't find a list called '{}'. Maybe you made a typo? See the available lists with the 'list' subcommand".format(listname))

			if subcommand == 'destroy':
				if not message.doesSenderHavePermission(PermissionLevel.CHANNEL if isChannelSpecificList else PermissionLevel.SERVER):
					raise CommandInputException("Sorry, only my {0} admins are allowed to destroy {0} lists".format("channel" if isChannelSpecificList else "server"))
				entryCount = cursor.execute("SELECT COUNT(*) FROM list_entries WHERE list_id=?", (listId,)).fetchone()[0]
				# Delete all the list entries
				if entryCount > 0:
					cursor.execute("DELETE FROM list_entries WHERE list_id=?", (listId,))
				cursor.execute("DELETE FROM lists WHERE id=?", (listId,))
				# Destroying a large list may leave the database fragmented, the sqlite 'vacuum' command solves that (it's kind of like defragging)
				# This needs extra diskspace though, because it basically recreates the database file and then replaces the existing file with the new one
				cursor.execute("VACUUM")
				connection.commit()
				return message.reply("Ok, the '{}' list and its {:,} entr{} are gone forever. I hope none of that was important!".format(listname, entryCount, 'y' if entryCount == 1 else 'ies'))

			elif subcommand == 'get':
				# 'get' can accept no arguments (works same as 'random'), a numeric entry id argument (works same as 'getbyid'), or a text searchquery argument (works the same as 'search')
				if message.messagePartsLength < 3:
					# No ID or search query provided, pick a random entry
					replytext = self.getRandomEntry(cursor, listname, listId, shouldAddEntryInfo=shouldAddEntryInfo)
				else:
					# Check if the provided argument is an ID number or a search query
					try:
						entryId = int(message.messageParts[2], 10)
					except ValueError:
						# Argument isn't a number, use it as a search query
						replytext = self.searchForEntry(cursor, listname, listId, self.normalizeSearchQuery(" ".join(message.messageParts[2:])), shouldAddEntryInfo)
					else:
						# Get entry by ID
						replytext = self.formatEntry(self.getEntryById(cursor, listname, listId, entryId), shouldAddEntryInfo)
				return message.reply(replytext)

			elif subcommand == 'random':
				return message.reply(self.getRandomEntry(cursor, listname, listId, shouldAddEntryInfo=shouldAddEntryInfo))

			elif subcommand == 'add':
				if message.messagePartsLength < 3:
					raise CommandInputException("Please provide some text to add to the '{}' list. I''m not good at making stuff up myself".format(listname))
				if isListAdminOnly and not message.doesSenderHavePermission(PermissionLevel.CHANNEL if isChannelSpecificList else PermissionLevel.SERVER):
					raise CommandInputException("Sorry, only my  {listtype} admins are allowed to add entries to the '{listname}' {listtype} list. Ask one of them to add your idea!"
												.format(listtype="channel" if isChannelSpecificList else "server", listname=listname))
				maxIdResult = cursor.execute("SELECT max(id) FROM list_entries WHERE list_id=?", (listId,)).fetchone()
				entryId = maxIdResult[0] + 1 if maxIdResult[0] else 1
				entryText = " ".join(message.messageParts[2:])
				cursor.execute(u"INSERT INTO list_entries VALUES (:id, :listId, :text, :creator, :creationDate, NULL, NULL)",
							   {'id': entryId, 'listId': listId, 'text': entryText, 'creator': message.userNickname, 'creationDate': time.time()})
				connection.commit()
				return message.reply("Added your entry to the '{}' list under entry id {}".format(listname, entryId))

			# 'getbyid' and 'remove' need to do a lot of the same checks, so combine them
			elif subcommand in ('getbyid', 'remove'):
				if message.messagePartsLength < 3:
					raise CommandInputException("Please provide an entry ID for the '{}' list. I'm not gonna guess one (though if you want that, use the 'get' subcommand without an id)".format(listname))
				try:
					entryId = int(message.messageParts[2], 10)
				except ValueError:
					raise CommandInputException("The provided entry id '{}' couldn't be parsed as a number. Please check that you entered it correctly".format(message.messageParts[2]))
				entry = self.getEntryById(cursor, listname, listId, entryId)
				if subcommand == 'remove':
					if isListAdminOnly and not message.doesSenderHavePermission(PermissionLevel.CHANNEL if isChannelSpecificList else PermissionLevel.SERVER):
						raise CommandInputException("Sorry, only my {listtype} admins are allowed to remove entries from the '{listname}' {listtype} list".format(listtype="channel" if isChannelSpecificList else "server", listname=listname))
					cursor.execute("DELETE FROM list_entries WHERE list_id=? AND id=?", (listId, entryId))
					connection.commit()
					return message.reply("Successfully deleted {} from the '{}' list".format(self.formatEntry(entry, True), listname))
				else:
					# 'getbyid'
					return message.reply(self.formatEntry(entry, shouldAddEntryInfo))

			elif subcommand == 'search':
				if message.messagePartsLength < 3:
					raise CommandInputException("Please enter a search query too. Or if you want a random entry, use the 'random' subcommand")
				searchquery = self.normalizeSearchQuery(" ".join(message.messageParts[2:]))
				return message.reply(self.searchForEntry(cursor, listname, listId, searchquery, shouldAddEntryInfo))

			elif subcommand == 'getall':
				searchQuery = None if message.messagePartsLength < 3 else self.normalizeSearchQuery(" ".join(message.messageParts[2:]))
				sqlQuery = "SELECT * FROM list_entries WHERE list_id=:listId"
				if searchQuery:
					sqlQuery += " AND text LIKE :searchQuery"
				entries = cursor.execute(sqlQuery, {'listId': listId, 'searchQuery': searchQuery}).fetchall()
				# Don't bother uploading if the list is empty or short
				if len(entries) == 0:
					return message.reply("The '{}' list doesn't have any entries at all, so listing those is easy:  . Done!".format(listname))
				elif len(entries) == 1:
					return message.reply("The '{}' list only has one entry: {}".format(listname, self.formatEntry(entries[0], shouldAddEntryInfo)))
				# Destructively iterate over the found entries so long lists don't use a lot of memory
				formattedEntries = []
				while entries:
					entry = entries.pop(0)
					formattedEntries.append(self.formatEntry(entry, True))
				try:
					pasteLink = WebUtil.uploadText("\n".join(formattedEntries), "Entries for the '{}' list".format(listname), 600)
				except WebRequestException as wre:
					self.logError("[List] An error occurred while trying to upload '{}' list entries (Search query is '{}': {}".format(listname, searchQuery, wre))
					return message.reply("Uh oh, something went wrong with uploading the '{}' list entries. Try again in a bit, and if it keeps happening, please tell my owner(s)".format(listname))
				return message.reply("Here's all the entries for the '{}' list{}: {} (Link expires in 10 minutes)".format(listname, " that match your query" if searchQuery else "", pasteLink))

			elif subcommand == 'info':
				listResult = cursor.execute("SELECT * FROM lists WHERE id=?", (listId,)).fetchone()
				entryCount = cursor.execute("SELECT COUNT(*) FROM list_entries WHERE list_id=?", (listId,)).fetchone()[0]
				replytext = "{} list '{}' ".format('Channel' if listResult[4] else 'Server', listname)
				if shouldAddEntryInfo:
					replytext += "was created on {} by {} and ".format(self.formatTimestamp(listResult[6]), listResult[5])
				replytext += "has {:,} entr{}".format(entryCount, 'y' if entryCount == 1 else 'ies')
				if listResult[7]:
					replytext += ". Only my admin(s) can add and remove entries from this list"
				description = listResult[2]
				if description:
					replytext += ". Description: {}".format(description)
				else:
					replytext += ". No list description has been set"
				return message.reply(replytext)

			elif subcommand == 'rename':
				if not message.doesSenderHavePermission(PermissionLevel.CHANNEL if isChannelSpecificList else PermissionLevel.SERVER):
					raise CommandInputException("Sorry, only my admins can rename {} lists".format("channel" if isChannelSpecificList else "server"))
				if message.messagePartsLength < 3:
					raise CommandInputException("Please add a new list name too, because I'm not good at thinking up names")
				newListname = self.normalizeListname(message.messageParts[2])
				if listname == newListname:
					raise CommandInputException("But... those two names are the same, the list is already called that. I don't think that qualifies as 'renaming' then")
				if self.getBasicListData(cursor, newListname, servername, channelname)[0] is not None:
					raise CommandInputException("The list '{}' already exists, so I can't rename the '{}' list to that".format(newListname, listname))
				cursor.execute("UPDATE lists SET name=? WHERE id=?", (newListname, listId))
				connection.commit()
				return message.reply("Successfully renamed the '{}' list to '{}'. Don't forget to tell people about the rename though, they might think it got deleted".format(listname, newListname))

			elif subcommand == 'edit':
				if isListAdminOnly and not message.doesSenderHavePermission(PermissionLevel.CHANNEL if isChannelSpecificList else PermissionLevel.SERVER):
					raise CommandInputException("Sorry, only my {0} admins can edit entries in this {0} list".format("channel" if isChannelSpecificList else "server"))
				if message.messagePartsLength < 3:
					raise CommandInputException("Please add the id of the entry to edit and the new text for that entry. Nobody wants me to replace a random entry with gibberish")
				if message.messagePartsLength < 4:
					raise CommandInputException("Please add the new text for the provided entry, because neither of us want me to change it to something random")
				try:
					entryId = int(message.messageParts[2], 10)
				except ValueError:
					raise CommandInputException("I can't parse '{}' as a number, and it should be an entry ID".format(message.messageParts[1]))
				oldEntry = self.getEntryById(cursor, listname, listId, entryId)
				newEntryText = " ".join(message.messageParts[3:])
				cursor.execute("UPDATE list_entries SET text = ?, edited_by = ?, edited_date = ? WHERE list_id=? AND id=?", (newEntryText, message.userNickname, time.time(), listId, entryId))
				connection.commit()
				return message.reply("Successfully updated entry {} in list {} from '{}' to '{}'".format(entryId, listname, self.formatEntry(oldEntry, False), newEntryText))

			elif subcommand == 'setdescription' or subcommand == 'cleardescription':
				if not message.doesSenderHavePermission(PermissionLevel.CHANNEL if isChannelSpecificList else PermissionLevel.SERVER):
					raise CommandInputException("Sorry, only my {0} admins are allowed to change a {0} list's description".format("channel" if isChannelSpecificList else "server"))
				description = None
				if subcommand == 'setdescription':
					if message.messagePartsLength < 3:
						raise CommandInputException("Please add a description to set. If you just want to remove the existing description, use the 'cleardescription' subcommand")
					description = " ".join(message.messageParts[2:])
				cursor.execute("UPDATE lists SET description=? WHERE id=?", (description, listId))
				connection.commit()
				return message.reply("Successfully {} the description for the '{}' list".format('cleared' if subcommand == 'cleardescription' else 'updated', listname))

			elif subcommand == 'setadmin':
				if not message.doesSenderHavePermission(PermissionLevel.CHANNEL if isChannelSpecificList else PermissionLevel.SERVER):
					raise CommandInputException("Sorry, only my {0} admins can toggle the admin-only state of {0} lists. Makes sense too, otherwise the feature would be pretty useless!".format("channel" if isChannelSpecificList else "server"))
				if message.messagePartsLength < 3:
					raise CommandInputException("Please add whether you want to make the provided list admin-only or not")
				shouldBeAdminOnly = message.messageParts[2].lower()
				if shouldBeAdminOnly not in ('true', 'false'):
					raise CommandInputException("I don't know how to interpret the setting value '{}', sorry. Please use either 'true' or 'false'".format(message.messageParts[2]))
				shouldBeAdminOnly = shouldBeAdminOnly == 'true'
				if shouldBeAdminOnly is isListAdminOnly:
					return message.reply("The '{}' list is already set to {}admin-only. Saves me updating this database!".format(listname, '' if isListAdminOnly else 'non-'))
				cursor.execute("UPDATE lists SET is_admin_only=? WHERE id=?", (shouldBeAdminOnly, listId))
				connection.commit()
				return message.reply("Successfully made the '{}' list {}admin-only".format(listname, '' if shouldBeAdminOnly else 'non-'))

			else:
				return message.reply("I don't know what to do with the subcommand '{}', sorry. Maybe (re)read the list help text?".format(subcommand))

	def doTablesExist(self, cursor):
		"""
		Check if the tables with list data exist
		:param cursor: The cursor to use to query the database
		:return: True if the required list tables exist, False otherwise
		"""
		cursor.execute("SELECT name FROM sqlite_master	WHERE type = 'table' AND name='lists'")
		return True if cursor.fetchone() else False

	def getBasicListData(self, cursor, listname, servername, channelname=None):
		"""
		Get basic info for the provided list for the provided server and channel, or for the server if there's no channel-specific list
		:param cursor: The cursor to use for the data retrieval
		:param listname: The name of the list to retrieve the info for
		:param servername: The servername to retrieve the list for
		:param channelname: The (optional) channelname to retrieve the list for. If there's a channel-specific list named 'listname', that will get retrieved, otherwise a serverwide list will
		:return: A tuple with the first entry the list id or None if no list for the parameters could be found, the second entry says whether the list is admin-only, and the third entry whether it's a channel-specific list (values can be either None, True, or False)
		"""
		# First check if there's a channel list, so we don't accidentally return the serverlist if there's one with the same name
		result = None
		isChannelSpecificList = None
		if channelname:
			cursor.execute("SELECT id, is_admin_only FROM lists WHERE name=? AND server=? AND channel=?", (listname, servername, channelname))
			result = cursor.fetchone()
			if result:
				isChannelSpecificList = True
		# If no channellist was found, or no channelname was provided, try to find a serverlist
		if result is None:
			# Check if there's a server list
			result = cursor.execute("SELECT id, is_admin_only FROM lists WHERE name=? AND server=? AND channel IS NULL", (listname, servername)).fetchone()
			if result is None:
				return None, None, None
			isChannelSpecificList = False
		# SQLite doesn't support booleans, so 'true' is 1 and 'false' is 0. Turn it into a boolean so it's easier and more intuitive to use
		isAdminOnly = True if result[1] else False
		return result[0], isAdminOnly, isChannelSpecificList

	def normalizeSearchQuery(self, inputSearchQuery):
		if not inputSearchQuery:
			return None
		outputSearchQuery = inputSearchQuery
		# SQL queries use % and _ as multi- and single-character wildcards, respectively. * and ? are more common, so replace those
		outputSearchQuery = outputSearchQuery.replace('*', '%').replace('?', '_')
		# Since it's natural to assume searching doesn't only search for the literal string, add wildcards to the start and end if there are no wildcards yet
		if '_' not in outputSearchQuery and '%' not in outputSearchQuery:
			outputSearchQuery = "%{}%".format(outputSearchQuery)
		return outputSearchQuery

	def normalizeListname(self, inputListname):
		outputListname = inputListname
		# There's multiple ways to create unicode characters, and there's duplicate characters for historical reasons
		# Python and SQLite kind of disagree on that, so normalize it here to prevent any disagreements resulting in errors
		outputListname = unicodedata.normalize('NFKC', outputListname)
		outputListname = IrcFormattingUtil.removeFormatting(outputListname)
		outputListname = outputListname.lower()
		return outputListname

	def getRandomEntry(self, cursor, listname=None, listId=None, searchquery=None, shouldAddEntryInfo=False, randomGenerator=None):
		# Inner select is to get a count of entries, the random offset picks a random one of those, the outer select actually retrieves the entry
		entryData = cursor.execute("SELECT * FROM list_entries WHERE list_id=:listId{0} LIMIT 1 OFFSET CAST((SELECT COUNT(*) FROM list_entries WHERE list_id=:listId{0}) * :randomFloat AS INT)".format(" AND text LIKE :query" if searchquery else ''),
						   {'listId': listId, 'randomFloat': randomGenerator.random() if randomGenerator else random.random(), 'query': searchquery}).fetchone()
		if not entryData:
			if searchquery:
				return "The '{}' list doesn't have any entries that match your search query, sorry".format(listname)
			else:
				return "Huh, seems the '{}' list is empty. Weird that somebody made a list but then didn't add anything to it".format(listname)
		return self.formatEntry(entryData, shouldAddEntryInfo)

	def getRandomListEntry(self, servername, channelname, listname, searchquery=None, randomGenerator=None):
		"""
		Get a random entry from the provided list for the provided server and channel
		:param servername: The name of the server to get the list for
		:param channelname: The name of the channel to get the list for. Can be empty for a server-list, but even if it's set a server-list will be found if it exists
		:param listname: The name of the list to get a randomentry from
		:param searchquery: An optional search query, a random entry will be picked from the entries that match this query. If not provided, a random entry will be picked from all the list entries
		:param randomGenerator: An optional random generator to use. Useful if you want to have seeded randomness. Should be a random.Random() instance
		:return: The text of the randomly picked entry
		"""
		with sqlite3.connect(self.databasePath) as connection:
			cursor = connection.cursor()
			listname = self.normalizeListname(listname)
			listId = self.getBasicListData(cursor, listname, servername, channelname)[0]
			if listId is None:
				raise CommandInputException("No matching list found for listname '{}' on server '{}' and channel '{}'".format(listname, servername, channelname))
			return self.getRandomEntry(connection.cursor(), listname, listId, self.normalizeSearchQuery(searchquery), randomGenerator=randomGenerator)

	def searchForEntry(self, cursor, listname, listId, searchquery, shouldAddEntryInfo=False):
		matchCount = cursor.execute("SELECT COUNT(*) FROM list_entries WHERE list_id=? AND text LIKE ?", (listId, searchquery)).fetchone()[0]
		if matchCount == 0:
			replytext = "Sorry, the '{}' list doesn't have any entries that match your search query".format(listname)
		elif matchCount == 1:
			matchedEntry = cursor.execute("SELECT * FROM list_entries WHERE list_id=? AND text LIKE ?", (listId, searchquery)).fetchone()
			replytext = self.formatEntry(matchedEntry, shouldAddEntryInfo)
		else:
			replytext = self.getRandomEntry(cursor, listId=listId, searchquery=searchquery, shouldAddEntryInfo=shouldAddEntryInfo)
			if shouldAddEntryInfo:
				replytext += " ({:,} more match{})".format(matchCount - 1, '' if matchCount == 2 else 'es')
		return replytext

	def getEntryById(self, cursor, listname, listId, entryId):
		if entryId <= 0:
			raise CommandInputException("Entry IDs can't be zero or smaller, they start at 1")
		entry = cursor.execute("SELECT * FROM list_entries WHERE list_id=? AND id=?", (listId, entryId)).fetchone()
		if not entry:
			raise CommandInputException("The '{}' list doesn't have an entry with ID {}, that's weird. Are you sure you typed it correctly?".format(listname, entryId))
		return entry

	def formatEntry(self, entryData, shouldAddEntryInfo=False):
		if shouldAddEntryInfo:
			formattedEntry = "Entry {:,}: {} (by {} on {}".format(entryData[0], entryData[2], entryData[3], self.formatTimestamp(entryData[4]))
			if entryData[5] and entryData[6]:
				formattedEntry += ", edited by {} on {}".format(entryData[5], self.formatTimestamp(entryData[6]))
			formattedEntry += ")"
			return formattedEntry
		else:
			return entryData[2]

	def formatTimestamp(self, timestamp):
		return datetime.datetime.utcfromtimestamp(timestamp).strftime("%Y-%m-%d %H:%M UTC")
