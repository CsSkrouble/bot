#!/usr/bin/env python3
# encoding: utf-8

import asyncio
import collections
from datetime import datetime
import functools
import math
import re
from typing import Sequence, Union
import urllib.parse

import asyncpg
import discord
from discord.ext import commands
from prettytable import PrettyTable


"""miscellaneous utility functions and constants"""


"""Stanislav#0001's user ID
This is useful to test whether a number is a snowflake:
if it's greater than this number, it probably is"""
SMALLEST_SNOWFLAKE = 21154535154122752

"""Emotes used to indicate success/failure. You can obtain these from the discordbots.org guild,
but I uploaded them to my test server
so that both the staging and the stable versions of the bot can use them"""
SUCCESS_EMOTES = ('<:error:478164511879069707>', '<:success:478164452261363712>')

class PrettyTable(PrettyTable):
	"""an extension of PrettyTable that works with asyncpg's Records and looks better"""
	def __init__(self, rows: Sequence[Union[asyncpg.Record, collections.OrderedDict]], **options):
		defaults = dict(
			# super()'s default is ASCII | - +, which don't join seamlessly and look p bad
			vertical_char='│',
			horizontal_char='─',
			junction_char='┼')
		for option, default in defaults.items():
			options.setdefault(option, default)

		if rows:
			super().__init__(rows[0].keys(), **options)
		else:
			super().__init__()
		# PrettyTable's constructor does not set this property for some reason
		self.align = options.get('align', 'l')	# left align

		for row in rows:
			self.add_row(row)

class LRUDict(collections.OrderedDict):
	"""a dictionary with fixed size, sorted by last use"""

	def __init__(self, size):
		super().__init__()
		self.size = size

	def __getitem__(self, key):
		result = super().__getitem__(key)
		del self[key]
		super().__setitem__(key, result)
		return result

	def __setitem__(self, key, value):
		try:
			# if an entry exists at key, make sure it's moved up
			del self[key]
		except KeyError:
			# we only need to do this when adding a new key
			if len(self) >= self.size:
				self.popitem(last=False)

		super().__setitem__(key, value)

AttrDict = type('AttrDict', (dict,), {
	'__getattr__': dict.__getitem__,
	'__setattr__': dict.__setitem__,
	'__delattr__': dict.__delitem__,
})

def typing(func):
	"""Makes a command function run with the context.typing() context manager.
	This will make the bot appear to be typing until the command returns.
	While you can just wrap your entire code in `async with context.typing()`,
	this isn't ideal if you already have a lot of indents or a long function.
	Also, context.trigger_typing() works but only for 10 seconds.
	"""
	@functools.wraps(func)
	# TODO investigate whether wraps really works on asyncs (probably not).
	# Either way, `wrapt` provides a better @wraps, maybe that would work
	async def wrapped(*args, **kwargs):	 # pylint: disable=missing-docstring
		# if func is a method, args starts with (self, context, ...)
		# otherwise args starts with (context, ...)
		context = args[0] if isinstance(args[0], commands.Context) else args[1]
		async with context.typing():
			# XXX Currently there is a bug in context.typing, or maybe in the official Discord client
			# receiving a message *immediately* after a typing indicator
			# does not cancel the typing indicator.
			# By sleeping, we can work around that bug in case a command fails early.
			# This is also why this decorator should probably not be used
			# if you do not anticipate a command taking more than 10s.
			await asyncio.sleep(0.1)
			await func(*args, **kwargs)
	return wrapped

def bytes_to_int(x):
	return int.from_bytes(x, byteorder='big')

def int_to_bytes(n):
	num_bytes = int(math.ceil(n.bit_length() / 8))
	return n.to_bytes(num_bytes, byteorder='big')

async def codeblock(message, *, lang=''):
	cleaned = message.replace('```', '\N{zero width space}'.join('```'))
	return f'```{lang}\n{cleaned}```'

async def get_message_by_offset(channel, index: int) -> discord.Message:
	"""Gets channel[-index]. For instance get_message(channel, -2) == second to last message.
	Requires channel history permissions"""
	return await channel.history(limit=-index, reverse=True).next()

def fix_first_line(message: str) -> str:
	"""In compact mode, prevent the first line from being misaligned because of the bot's username"""
	if '\n' in message:
		message = '\N{zero width space}\n' + message
	return message

def format_user(bot, id, *, mention=False):
	"""Format a user ID for human readable display."""
	user = bot.get_user(id)
	if user is None:
		return f'Unknown user with ID {id}'
	# not mention: @null byte#8191 (140516693242937345)
	# mention: <@140516693242937345> (null byte#8191)
	# this allows people to still see the username and discrim
	# if they don't share a server with that user
	if mention:
		return f'{user.mention} (@{user})'
	else:
		return f'@{user} ({user.id})'

def format_time(date: datetime):
	"""Format a datetime to look like '2018-02-22 22:38:12 UTC'."""
	return date.strftime('%Y-%m-%d %H:%m:%S %Z')

def strip_angle_brackets(string):
	"""Strip leading < and trailing > from a string.
	Useful if a user sends you a url like <this> to avoid embeds, or to convert emotes to reactions."""
	if string.startswith('<') and string.endswith('>'):
		return string[1:-1]
	return string

def format_http_exception(exception: discord.HTTPException):
	"""Formats a discord.HTTPException for relaying to the user.
	Sample return value:

	BAD REQUEST (status code: 400):
	Invalid Form Body
	In image: File cannot be larger than 256 kb.
	"""
	return (
		f'{exception.response.reason} (status code: {exception.response.status}):'
		f'\n{exception.text}')

def expand_cartesian_product(str) -> (str, str):
	"""expand a string containing one non-nested cartesian product strings into two strings

	>>> expand_cartesian_product('foo{bar,baz}')
	('foobar', 'foobaz')
	>>> expand_cartesian_product('{old,new}')
	('old', 'new')
	>>> expand_cartesian_product('uninteresting')
	('uninteresting', '')
	>>> expand_cartesian_product('{foo,bar,baz}')
	('foo,bar', 'baz')	# edge case that i don't need to fix

	"""

	match = re.search('{([^{}]*),([^{}]*)}', str)
	if match:
		return (
			_expand_one_cartesian_product(str, match, 1),
			_expand_one_cartesian_product(str, match, 2)
		)
	else:
		return (str, '')

def _expand_one_cartesian_product(str, match, group):
	return str[:match.start()] + match.group(group) + str[match.end():]

def load_json_compat(data: str):
	"""evaluate a python dictionary/list/thing, while maintaining some compatibility with JSON"""
	# >HOLD UP! Why the heck are you using eval in production??
	# Short answer: JSON sucks for a configuration format:
	#	It can be hard to read
	#	Only one type of quote is allowed
	#	No trailing commas are allowed
	#	No multi-line strings
	#	But most importantly, NO COMMENTS!
	# >OK but you didn't answer my question
	# Well I would use another configuration language, but they all suck.
	# To really answer your question, the config file is 100% trusted data.
	# NOTHING the user ever sends, ends up in there.
	# Also, consider another common approach: `import config`.
	# Which is arbitrary code execution anyway.
	# Furthermore, the if the user ever does get a hold of the config.py file,
	# then they already have the bot token and have totally compromised the bot.
	globals = dict(true=True, false=False, null=None)
	return eval(data, globals)

async def async_enumerate(async_iterator, start=0):
	i = int(start)
	async for x in async_iterator:
		yield i, x
		i += 1

def clean_content(bot, message, content, *, fix_channel_mentions=False, use_nicknames=True, escape_markdown=False):
	transformations = {}

	if fix_channel_mentions and message.guild:
		def resolve_channel(id, *, _get=message.guild.get_channel):
			ch = _get(id)
			return ('<#%s>' % id), ('#' + ch.name if ch else '#deleted-channel')

		transformations.update(resolve_channel(channel) for channel in message.raw_channel_mentions)

	if use_nicknames and message.guild:
		def resolve_member(id, *, _get=message.guild.get_member):
			m = _get(id)
			return '@' + m.display_name if m else '@deleted-user'
	else:
		def resolve_member(id, *, _get=bot.get_user):
			m = _get(id)
			return '@' + m.name if m else '@deleted-user'


	transformations.update(
		('<@%s>' % member_id, resolve_member(member_id))
		for member_id in message.raw_mentions
	)

	transformations.update(
		('<@!%s>' % member_id, resolve_member(member_id))
		for member_id in message.raw_mentions
	)

	if message.guild:
		def resolve_role(id, *, _find=discord.utils.find, _roles=message.guild.roles):
			r = _find(lambda x: x.id == id, _roles)
			return '@' + r.name if r else '@deleted-role'

		transformations.update(
			('<@&%s>' % role_id, resolve_role(role_id))
			for role_id in message.raw_role_mentions
		)

	def repl(obj):
		return transformations.get(obj.group(0), '')

	pattern = re.compile('|'.join(transformations.keys()))
	result = pattern.sub(repl, content)

	if escape_markdown:
		transformations = {
			re.escape(c): '\\' + c
			for c in ('*', '`', '_', '~', '\\')
		}

		def replace(obj):
			return transformations.get(re.escape(obj.group(0)), '')

		pattern = re.compile('|'.join(transformations.keys()))
		result = pattern.sub(replace, result)

	# Completely ensure no mentions escape:
	return re.sub(r'@(everyone|here|[!&]?[0-9]{17,21})', '@\u200b\\1', result)