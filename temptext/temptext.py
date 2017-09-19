import discord
from discord.ext import commands
from cogs.utils import checks
from cogs.utils.dataIO import dataIO
import logging
import os
import asyncio
from datetime import datetime, timedelta
from typing import Union
assert asyncio  # shakes fist at linter


log = logging.getLogger("red.TempText")

creationmessage = "Hi {0.mention}, I've created your channel here. " \
                  "People eligible to join can do so by using the following " \
                  "command.\n`{1}jointxt {2.id}`"  # author, prefix, channel


# TODO in future versions
# ====================
# configuration options for channel limits
# possible global limits?
# add additional rate limit option beyond the sanity ones currently in use
# add an ignore option not reliant on the bot's own ignore?

class TmpTxtError(Exception):
    pass


class TempText:

    __author__ = "mikeshardmind"
    __version__ = "1.0a"

    def __init__(self, bot):
        self.bot = bot
        self.settings = dataIO.load_json('data/temptext/settings.json')
        self.channels = dataIO.load_json('data/temptext/channels.json')
        self.everyone_perms = discord.PermissionOverwrite(read_messages=False)
        self.joined_perms = discord.PermissionOverwrite(read_messages=True)
        self.owner_perms = discord.PermissionOverwrite(read_messages=True,
                                                       manage_channels=True,
                                                       manage_roles=True)
        self._load()

    def update_settings(self, server: discord.Server, data=None):
        if server.id not in self.settings:
            self.settings[server.id] = {'active': False,
                                        'ignored': [],  # Todo
                                        'rid': None,
                                        'strict': True,
                                        'schan_limit': 250,  # Todo
                                        'uchan_limit': 3,  # also, Todo
                                        'default_time': 14400  # 4h in s
                                        }
        if data is not None:
            self.settings[server.id].update(data)
        self.save_settings()

    def save_settings(self):
        dataIO.save_json("data/temptext/settings.json", self.settings)

    def save_channels(self):
        dataIO.save_json("data/temptext/channels.json", self.channels)

    def _load(self):

        now = datetime.now()
        valid_chans = [c for c in self.bot.get_all_channels()
                       if c.id in self.channels.keys()]
        self.channels = {k: v for k, v in self.channels.items()
                         if k not in [c.id for c in valid_chans]}
        self.save_channels()

        for channel in valid_chans:
            delete_in = channel.created_at + \
                timedelta(seconds=self.channels[channel.id]['lifetime']) - now

            if delete_in.seconds < 0:
                sec = 0
            else:
                sec = delete_in.seconds

            coro = self._temp_deletion(channel.id)
            self.bot.loop.call_later(sec, self.bot.loop.create_task, coro)

    @checks.admin_or_permissions(manage_server=True)
    @commands.group(name="tmptxtset", pass_context=True, no_pm=True)
    async def tmptxtset(self, ctx):
        """configuration settings for temporary temp channels"""
        if ctx.invoked_subcommand is None:
            await self.bot.send_cmd_help(ctx)

    @tmptxtset.command(name="toggleactive", pass_context=True, no_pm=True)
    async def toggleactive(self, ctx):
        """
        toggles it on/off
        """
        server = ctx.message.server
        if server.id not in self.settings:
            self.update_settings(server)

        active = not self.settings[server.id]['active']
        self.update_settings(server, {'active': active})
        await self.bot.say("Active: {}".format(active))

    @tmptxtset.command(name="togglestrict", pass_context=True, no_pm=True)
    async def togglestrict(self, ctx):
        """
        toggles strict role checking on/off
        when off, the required role or any above it will work

        N.B. This is specifically the role checking on creating a temp channel,
        not on joining one.
        """
        server = ctx.message.server
        if server.id not in self.settings:
            self.update_settings(server)

        strict = not self.settings[server.id]['strict']
        self.update_settings(server, {'strict': strict})
        await self.bot.say("Strict mode: {}".format(strict))

    @tmptxtset.command(name="defaulttime", pass_context=True, no_pm=True)
    async def setdefaulttime(self, ctx, **timevalues):
        """
        sets the time used for temp text channels when no time is provided
        time should be between 10 minutes and 2 days
        takes time in mintes(m), hours (h), days (d) in the format
        interval=quantity
        example usage for 1 hour 30 minutes: [p]tmptxtset defaulttime h=1 m=30
        default is 4h
        """

        seconds = self._parse_time(timevalues)
        if not self._is_valid_interval(seconds):
            return await self.bot.say("That wasn't a valid time")

        self.update_settings(ctx.message.server, {'default_time': seconds})
        await self.bot.say("Default set")

    @tmptxtset.command(name="requiredrole", pass_context=True, no_pm=True)
    async def setrequiredrole(self, ctx, role: discord.Role=None):
        """
        sets the required role this can be set as the lowest role required
        rather than a strict requirement
        clear setting by using without a role
        """

        rid = None
        if role is not None:
            rid = role.id

        self.update_settings(ctx.message.server, {'rid': rid})
        await self.bot.say("Settings updated.")

    @commands.command(pass_context=True, no_pm=True, name="jointxt")
    async def _join_text(self, ctx, chan_id: str):
        """try to join a room"""
        author = ctx.message.author
        c = discord.utils.get(self.bot.get_all_channels(), id=chan_id,
                              server__id=author.server.id)
        if chan_id not in self.channels or c is None:
            return await self.bot.say("That isn't a joinable channel")
        if not self._is_allowed(author, chan_id):
            return await self.bot.say("Sorry, you can't join that room")

        try:
            await self.bot.edit_channel_permissions(c, author,
                                                    self.joined_perms)
        except discord.Forbidden:
            await self.bot.say("Wait what the... who removed my perms?.. "
                               "this is going to break all the things ")
        except discord.HTTPException:
            await self.bot.say("Huh... discord issue, try again later")
        except Exception as e:
            log.debug("{}".format(e))
            await self.bot.say("Something unexpected went wrong. Good luck.")
        else:
            await self.bot.say("Click this. It's a channel link, "
                               "not a hashtag."
                               "\nIf it isn't clickable, it isn't for you"
                               "{0.mention}".format(c))

    @commands.cooldown(1, 300, commands.BucketType.user)
    @commands.command(pass_context=True, name="tmptxt", no_pm=True)
    async def _temp_add(self, ctx, name: str, role: discord.Role=None,
                        **timevalues):
        """
        Makes a temp channel to be automagically deleted in anywhere between
        10 minutes and 2 days in the future
        Optionally set a role requirement to be allowed to join the channel

        Time value is optional, defaulting to whatever your server's default is
        if none is provided
        takes time in mintes(m), hours (h), days (d) in the format
        interval=quantity
        example usage for 1 hour 30 minutes: [p]tmptxtset defaulttime h=1 m=30
        """

        author = ctx.message.author
        if not self._is_allowed(author):
            return
        if role is not None:
            rid = role.id
        else:
            rid = None

        try:
            x = await self._process_temp(ctx.prefix, author,
                                         timevalues, name, rid)
        except TmpTxtError as e:
            await self.bot.say("{}".format(e))
        else:
            await self.bot.say("Channel made -> {0.mention}".format(x))

    async def _process_temp(self, prefix, author: discord.Member, timevalues,
                            channel_name=None, role_id=None):
        server = author.server
        if len(timevalues) == 0:
            seconds = self.settings[server.id]['default_time']
        else:
            seconds = self._parse_time(timevalues)

        if not self._is_valid_interval(seconds):
            raise TmpTxtError("That wasn't a valid time")
            return

        try:
            x = self.bot.create_channel(server, channel_name,
                                        (server.default_role,
                                         self.everyone_perms),
                                        (author, self.owner_perms),
                                        (server.me, self.joined_perms)
                                        )
        except discord.Forbidden:
            raise TmpTxtError("I literally can't even")
            return
        except Exception as e:
            log.debug("{}".format(e))
            raise TmpTxtError("Something unexpected happened. Try again later")
            return

        self.channels[x.id] = {'rid': role_id,
                               'lifetime': seconds,
                               'owner': author.id,
                               'server': server.id}
        self.save_channels()

        coro = self._temp_deletion(x.id)
        self.bot.loop.call_later(seconds, self.bot.loop.create_task, coro)

        await self.bot.send_message(x, creationmessage.format(author, prefix,
                                                              x))

    async def _temp_deletion(self, *channel_ids: str):

        channels = [c for c in self.bot.get_all_channels()
                    if c.id in channel_ids]

        disappeared = [cid for cid in channel_ids
                       if cid not in [c.id for c in channels]]
        self.channels = \
            {k: v for k, v in self.channels.items() if k not in disappeared}

        for channel in channels:
            try:
                cid = channel.id
                await self.bot.delete_channel(channel)
            except Exception as e:
                log.debug("{}".format(e))
            else:
                self.channels.pop(cid, None)

        self.save_channels()

    def _is_allowed(self, author: discord.Member, chan_id=None):
        server = author.server
        if server.id not in self.settings:
            return False
        if not self.settings[server.id].get('active', False):
            return False
        if self._is_ignored(author):
            return False
        if chan_id is not None:
            rid = self.channels[chan_id].get('rid', None)
            if rid is not None:
                role = [r for r in server.roles if r.id == rid][0]
                if role not in author.roles:
                    return False
        else:
            if self._at_channel_limit(author):
                return False
            rid = self.settings[server.id].get('rid', None)
            if rid is not None:
                role = [r for r in server.roles if r.id == rid][0]
                if self.settings[server.id].get('strictrole', True):
                    return role in author.roles
                else:
                    return author.top_role >= role
        return True

    def _parse_time(**kwargs):
        return ((kwargs.pop('d', 0) * 24
                 + kwargs.pop('h', 0)) * 60
                + kwargs.pop('m', 0)) * 60

    def _is_ignored(self, author: Union[discord.Member, discord.Role]):
        ignored = self.settings[author.server.id].get('ignored', [])
        if author.id in ignored:
            return True
        if isinstance(author, discord.Member):
            for role in author.roles:
                if self._is_ignored(role):
                    return True
        return False

    def _is_valid_interval(self, seconds: int):
        return 600 <= seconds <= 172800  # 10m <= seconds <= 2d

    def _at_channel_limit(self, author: discord.Member):
        server = author.server
        scount, ucount = 0, 0
        for k, v in self.channels:
            if v['owner'] == author.id:
                ucount += 1
            if v['server'] == server.id:
                scount += 1

        return (self.settings[server.id]['schan_limit'] > scount and
                self.settings[server.id]['uchan_limit'] > ucount)


def check_folder():
    f = 'data/temptext'
    if not os.path.exists(f):
        os.makedirs(f)


def check_files():
    f = 'data/temptext/channels.json'
    if dataIO.is_valid_json(f) is False:
        dataIO.save_json(f, {})
    f = 'data/temptext/settings.json'
    if dataIO.is_valid_json(f) is False:
        dataIO.save_json(f, {})


def setup(bot):
    check_folder()
    check_files()
    n = TempText(bot)
    bot.add_cog(n)
