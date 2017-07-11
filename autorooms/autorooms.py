import os
import asyncio
import discord
from discord.ext import commands
from cogs.utils.dataIO import dataIO
from .utils import checks


class AutoRooms:
    """
    auto spawn rooms
    """
    __author__ = "mikeshardmind"
    __version__ = "1.2"

    def __init__(self, bot):
        self.bot = bot
        self.settings = dataIO.load_json('data/autorooms/settings.json')

    @commands.group(name="autoroomset", pass_context=True, no_pm=True)
    async def autoroomset(self, ctx):
        """Configuration settings for AutoRooms"""
        if ctx.invoked_subcommand is None:
            await self.bot.send_cmd_help(ctx)

    def initial_config(self, server_id):
        """makes an entry for the server, defaults to turned off"""

        if server_id not in self.settings:
            self.settings[server_id] = {'toggleactive': False,
                                        'channels': [],
                                        'clones': [],
                                        'cache': [],
                                        'prepend': 'Auto:'
                                        }
            self.save_json()

    @checks.admin_or_permissions(Manage_channels=True)
    @autoroomset.command(name="toggleactive", pass_context=True, no_pm=True)
    async def autoroomtoggle(self, ctx):
        """
        turns autorooms on and off
        """
        server = ctx.message.server
        if server.id not in self.settings:
            self.initial_config(server.id)

        if self.settings[server.id]['toggleactive'] is True:
            self.settings[server.id]['toggleactive'] = False
            self.save_json()
            await self.bot.say('Auto Rooms disabled.')
        else:
            self.settings[server.id]['toggleactive'] = True
            self.save_json()
            await self.bot.say('Auto Rooms enabled.')

    @checks.admin_or_permissions(Manage_channels=True)
    @autoroomset.command(name="setprepend", pass_context=True, no_pm=True)
    async def setprepend(self, ctx, *, prepend):
        """
        Sets the text prepended to the generated channels
        Default is "Auto:"
        """
        server = ctx.message.server
        if server.id not in self.settings:
            self.initial_config(server.id)
        if prepend is None:
            return await self.bot.say("I will not create channels of the same"
                                      "as their origin. Please specify text "
                                      "to prepend to channel names")

        self.settings[server.id]['prepend'] = str(prepend)
        self.save_json()
        await self.bot.say("I am now prepending `{}` to channels I "
                           "make".format(str(prepend)))

    @checks.admin_or_permissions(Manage_channels=True)
    @autoroomset.command(name="makeclone", pass_context=True, no_pm=True)
    async def setclone(self, ctx, chan):
        """makes a channel for cloning"""
        server = ctx.message.server
        if server.id not in self.settings:
            self.initial_config(server.id)
        if chan is not None:
            self.settings[server.id]['channels'].append(chan)
            self.save_json()
            await self.bot.say('channel set')

    @checks.admin_or_permissions(Manage_channels=True)
    @autoroomset.command(name="delclone", pass_context=True, no_pm=True)
    async def killclone(self, ctx, chan):
        """removess a channel for cloning"""
        server = ctx.message.server
        if server.id not in self.settings:
            self.initial_config(server.id)
        if chan is not None:
            self.settings[server.id]['channels'].remove(chan)
            self.save_json()
            await self.bot.say('channel removed')

    def save_json(self):
        dataIO.save_json("data/autorooms/settings.json", self.settings)

    async def autorooms(self, memb_before, memb_after):
        """This cog is Self Cleaning"""
        server = memb_before.server
        if self.settings[server.id]['toggleactive']:
            if memb_after.voice.voice_channel is not None:
                chan = memb_after.voice.voice_channel
                prepend = self.settings[server.id]['prepend']
                if chan.id in self.settings[server.id]['channels']:
                    cname = "{}{}".format(prepend, chan.name)
                    overwrites = chan.overwrites
                    channel = await self.bot.create_channel(
                            server, cname, *overwrites,
                            type=discord.ChannelType.voice)
                    await self.bot.move_member(memb_after, channel)
                    self.settings[server.id]['clones'].append(channel.id)
                self.save_json()

        if memb_after.voice.voice_channel is not None:
            channel = memb_after.voice.voice_channel
            if channel.id in self.settings[server.id]['clones']:
                if channel.id not in self.settings[server.id]['cache']:
                    self.settings[server.id]['cache'].append(channel.id)
                    self.save_json()

        channel = memb_before.voice.voice_channel
        if channel.id in self.settings[server.id]['cache']:
            if len(channel.voice_members) == 0:
                await self.bot.delete_channel(channel)
                self.settings[server.id]['cache'].remove(channel.id)
                self.settings[server.id]['clones'].remove(channel.id)
                self.save_json()


def check_folder():
    f = 'data/autorooms'
    if not os.path.exists(f):
        os.makedirs(f)


def check_file():
    f = 'data/autorooms/settings.json'
    if dataIO.is_valid_json(f) is False:
        dataIO.save_json(f, {})


def setup(bot):
    check_folder()
    check_file()
    n = AutoRooms(bot)
    bot.add_listener(n.autorooms, 'on_voice_state_update')
bot.add_cog(n)
