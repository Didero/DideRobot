class PermissionLevel:
	def __init__(self, rank: int, description: str):
		self._rank = rank
		self._description = description

	def __str__(self):
		return self._description

	def __repr__(self):
		return f"{self._description} [{self._rank}]"

	#### Define comparison methods, so you can easily do 'if userPemissionLevel > BASIC'
	def __lt__(self, other):
		if isinstance(other, PermissionLevel):
			return self._rank < other._rank
		elif isinstance(other, int):
			return self._rank < other
		else:
			return NotImplemented
	def __le__(self, other):
		if isinstance(other, PermissionLevel):
			return self._rank <= other._rank
		elif isinstance(other, int):
			return self._rank <= other
		else:
			return NotImplemented

	def __eq__(self, other):
		if isinstance(other, PermissionLevel):
			return self._rank == other._rank
		elif isinstance(other, int):
			return self._rank == other
		else:
			return NotImplemented

	def __ge__(self, other):
		if isinstance(other, PermissionLevel):
			return self._rank >= other._rank
		elif isinstance(other, int):
			return self._rank >= other
		else:
			return NotImplemented
	def __gt__(self, other):
		if isinstance(other, PermissionLevel):
			return self._rank > other._rank
		elif isinstance(other, int):
			return self._rank > other
		else:
			return NotImplemented

BASIC = PermissionLevel(1, "Basic")
CHANNEL = PermissionLevel(2, "Channel Admin")
SERVER = PermissionLevel(3, "Server Admin")
BOT = PermissionLevel(4, "Bot Admin")
