import os, typing
if typing.TYPE_CHECKING:
	from BotHandler import BotHandler
	from CommandHandler import CommandHandler

scriptfolder: str = os.path.dirname(os.path.abspath(__file__))
bothandler: "BotHandler" = None
commandhandler: "CommandHandler" = None
