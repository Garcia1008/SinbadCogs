import os
import asyncio  # noqa: F401
import discord
import logging
from discord.ext import commands
from cogs.utils.dataIO import dataIO
from cogs.utils import checks

log = logging.getLogger('red.CrossQuote')


class CrossQuote:
    """
    Cross server quote by message ID.
    """

    __author__ = "mikeshardmind"
    __version__ = "2.1"

    def __init__(self, bot):

        self.bot = bot
        self.settings = dataIO.load_json('data/crossquote/settings.json')

    def save_json(self):
        dataIO.save_json("data/crossquote/settings.json", self.settings)

    @commands.group(name="crossquoteset",
                    pass_context=True, no_pm=True, hidden=True)
    async def crossquoteset(self, ctx):
        """configuration settings for cross server quotes"""
        if ctx.invoked_subcommand is None:
            await self.bot.send_cmd_help(ctx)

    @checks.admin_or_permissions(Manage_server=True)
    @crossquoteset.command(name="bypasstoggle", pass_context=True, no_pm=True)
    async def allow_without_permission(self, ctx):
        """allows people with manage server to allow users bypass needing
        manage messages to quote from their server to others
        bypass should be True or False. The default value is False"""

        server = ctx.message.server

        if server.id not in self.settings:
            self.init_settings(server)
            self.settings[server.id]['bypass'] = True
            self.save_json()
        else:
            self.settings[server.id]['bypass'] = \
                not self.settings[server.id]['bypass']

        if self.settings[server.id]['bypass']:
            await self.bot.say("Now anyone can quote from this server "
                               "if they can see the message")
        else:
            await self.bot.say("Quoting from this server again requires manage"
                               " messages")

    @checks.is_owner()
    @crossquoteset.command(name="init", hidden=True)
    async def manual_init_settings(self):
        """adds default settings for all servers the bot is in
        can be called manually by the bot owner (hidden)"""

        serv_ids = map(lambda s: s.id, self.bot.servers)
        for serv_id in serv_ids:
            if serv_id not in self.settings:
                self.settings[serv_id] = {'bypass': False,
                                          'whitelisted': [],
                                          'blacklisted': []
                                          }
                self.save_json()

    async def init_settings(self, server=None):
        """adds default settings for all servers the bot is in
        when needed and on join"""

        if server:
            if server.id not in self.settings:
                self.settings[server.id] = {'bypass': False,
                                            'whitelisted': [],
                                            'blacklisted': []
                                            }
                self.save_json()
        else:
            serv_ids = map(lambda s: s.id, self.bot.servers)
            for serv_id in serv_ids:
                if serv_id not in self.settings:
                    self.settings[serv_id] = {'bypass': False,
                                              'whitelisted': [],
                                              'blacklisted': []
                                              }
                    self.save_json()

    @commands.command(pass_context=True, name='crosschanquote',
                      aliases=["ccq", "quote"])
    async def _ccq(self, ctx, message_id: int):
        """
        Quote someone with the message id.
        To get the message id you need to enable developer mode.
        """
        found = False
        server = ctx.message.channel.server
        if server.id not in self.settings:
            await self.init_settings(server)
        for channel in server.channels:
            if not found:
                try:
                    message = await self.bot.get_message(channel,
                                                         str(message_id))
                    if message:
                        found = True
                except Exception as error:
                    log.debug("{}".format(error))
        if found:
            await self.sendifallowed(ctx.message.author,
                                     ctx.message.channel, message)
        else:
            em = discord.Embed(description='I\'m sorry, I couldn\'t find '
                               'that message', color=discord.Color.red())
            await self.bot.send_message(ctx.message.channel, embed=em)

    @checks.is_owner()
    @commands.command(pass_context=True, name="getmsgcontent", hidden=True)
    async def _gmsgcontent(self, ctx, x: str):
        """debugging tool"""

        message = await self.bot.get_message(ctx.message.channel, x)

        if message:
            await self.bot.say("```{}```".format(message.content))
            await self.bot.say("```{}```".format(message.clean_content))

    @commands.command(pass_context=True, name='crossservquote',
                      aliases=["csq", "crossquote"])
    async def _csq(self, ctx, message_id: int):
        """
        Quote someone with the message id.
        To get the message id you need to enable developer mode.
        """
        found = False
        for server in self.bot.servers:
            if server.id not in self.settings:
                await self.init_settings(server)
            for channel in server.channels:
                if not found:
                    try:
                        message = await self.bot.get_message(channel,
                                                             str(message_id))
                        if message:
                            found = True
                    except Exception as error:
                        log.debug("{}".format(error))
        if found:
            if ctx.message.channel.server == message.channel.server:
                em = discord.Embed(description='Using the cross server quote '
                                   'is slow. Use cross channel quote for '
                                   'messages on the same server.',
                                   color=discord.Color.red())
                await self.bot.send_message(ctx.message.author, embed=em)
            await self.sendifallowed(ctx.message.author,
                                     ctx.message.channel, message)
        else:
            em = discord.Embed(description='I\'m sorry, I couldn\'t find '
                               'that message', color=discord.Color.red())
            await self.bot.send_message(ctx.message.channel, embed=em)

    async def sendifallowed(self, who, where, message=None):
        """checks if a response should be sent
        then sends the appropriate response"""

        if message:
            channel = message.channel
            server = channel.server
            self.init_settings(server)
            perms_managechannel = channel.permissions_for(who).manage_messages
            can_bypass = self.settings[server.id]['bypass']
            source_is_dest = where.server.id == server.id
            if perms_managechannel or can_bypass or source_is_dest:
                em = self.qform(message)
            else:
                em = discord.Embed(description='You don\'t have '
                                   'permission to quote from that server',
                                   color=discord.Color.red())
        else:
            em = discord.Embed(description='I\'m sorry, I couldn\'t '
                               'find that message', color=discord.Color.red())
        await self.bot.send_message(where, embed=em)

    def qform(self, message):
        channel = message.channel
        server = channel.server
        content = message.content
        author = message.author
        sname = server.name
        cname = channel.name
        avatar = author.avatar_url if author.avatar \
            else author.default_avatar_url
        footer = 'Said in {} #{}'.format(sname, cname)
        em = discord.Embed(description=content, color=author.color,
                           timestamp=message.timestamp)
        em.set_author(name='{}'.format(author.name), icon_url=avatar)
        em.set_footer(text=footer)
        if message.attachments:
            a = message.attachments[0]
            fname = a['filename']
            url = a['url']
            if fname.split('.')[-1] in ['png', 'jpg', 'gif', 'jpeg']:
                em.set_image(url=url)
            else:
                em.add_field(name='Message has an attachment',
                             value='[{}]({})'.format(fname, url),
                             inline=True)
        return em


def check_folder():
    f = 'data/crossquote'
    if not os.path.exists(f):
        os.makedirs(f)


def check_file():
    f = 'data/crossquote/settings.json'
    if dataIO.is_valid_json(f) is False:
        dataIO.save_json(f, {})


def setup(bot):
    check_folder()
    check_file()
    n = CrossQuote(bot)
    bot.add_listener(n.init_settings, "on_server_join")
    bot.add_cog(n)
