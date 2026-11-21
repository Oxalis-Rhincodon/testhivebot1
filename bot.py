import logging
import os
from typing import Optional

import discord
from discord import app_commands
from discord.ext import commands
from dotenv import load_dotenv

from db import Database

load_dotenv()
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
log = logging.getLogger("modbot")


class ModBot(commands.Bot):
    def __init__(self):
        intents = discord.Intents.default()
        intents.members = True          # privileged: enable in the developer portal
        intents.message_content = True  # privileged: enable in the developer portal
        super().__init__(command_prefix=commands.when_mentioned, intents=intents, help_command=None)
        self.db = Database()
        self.tree.on_error = self.on_tree_error

    async def setup_hook(self):
        await self.db.connect()
        await self.load_extension("cogs.logs")
        await self.load_extension("cogs.moderation")

        dev_guild = os.getenv("DEV_GUILD_ID")
        if dev_guild:
            # Guild sync is instant, handy while developing.
            guild = discord.Object(id=int(dev_guild))
            self.tree.copy_global_to(guild=guild)
            await self.tree.sync(guild=guild)
        else:
            # Global sync can take a little while to show up in Discord.
            await self.tree.sync()

    async def close(self):
        await self.db.close()
        await super().close()

    async def on_ready(self):
        log.info("Logged in as %s (%s) in %d guild(s)", self.user, self.user.id, len(self.guilds))

    async def send_log(
        self,
        guild: discord.Guild,
        log_type: str,
        embed: discord.Embed,
        file: Optional[discord.File] = None,
    ):
        """Send an embed to the channel configured for this log type (if any)."""
        channel_id = await self.db.get_log_channel(guild.id, log_type)
        if not channel_id:
            return
        channel = guild.get_channel(channel_id)
        if channel is None:
            return
        try:
            await channel.send(embed=embed, file=file) if file else await channel.send(embed=embed)
        except (discord.Forbidden, discord.HTTPException):
            log.exception("Couldn't send %s log in guild %s", log_type, guild.id)

    async def on_tree_error(self, interaction: discord.Interaction, error: app_commands.AppCommandError):
        if isinstance(error, app_commands.MissingPermissions):
            msg = "You don't have permission to use that command."
        elif isinstance(error, app_commands.BotMissingPermissions):
            perms = ", ".join(p.replace("_", " ") for p in error.missing_permissions)
            msg = f"I'm missing permissions I need for that: {perms}."
        elif isinstance(error, app_commands.NoPrivateMessage):
            msg = "That command only works in a server."
        else:
            log.exception("Unhandled command error", exc_info=error)
            msg = "Something went wrong running that command."

        if interaction.response.is_done():
            await interaction.followup.send(msg, ephemeral=True)
        else:
            await interaction.response.send_message(msg, ephemeral=True)


def main():
    token = os.environ["DISCORD_TOKEN"]
    ModBot().run(token)


if __name__ == "__main__":
    main()
