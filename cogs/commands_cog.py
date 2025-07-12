# /cogs/commands_cog.py

import asyncio
import logging
import discord
from discord import app_commands
from discord.ext import commands

from modules.error_handler import send_error_report
from modules.views import CounterView, ConfirmationView

# --- AUTOCOMPLETE HANDLERS (Defined OUTSIDE the class) ---
# This is the correct pattern. They are now standalone functions.

async def get_groups_autocomplete(interaction: discord.Interaction, current: str) -> list[app_commands.Choice[str]]:
    """Provides autocomplete suggestions for group names."""
    try:
        # Access the bot instance via interaction.client
        groups = interaction.client.db_manager.get_all_groups(interaction.guild_id)
        return [
            app_commands.Choice(name=g.capitalize(), value=g)
            for g in groups if current.lower() in g.lower()
        ][:25] # Discord has a limit of 25 choices
    except Exception:
        # On any error, return an empty list to prevent crashing.
        return []

async def get_counters_autocomplete(interaction: discord.Interaction, current: str) -> list[app_commands.Choice[str]]:
    """Provides autocomplete suggestions for counter names within a selected group."""
    group_name = interaction.namespace.group
    if not group_name: return []
    try:
        counters = interaction.client.db_manager.get_counters_in_group(interaction.guild_id, group_name)
        return [
            app_commands.Choice(name=c['name'].capitalize(), value=c['name'])
            for c in counters if current.lower() in c['name'].lower()
        ][:25]
    except Exception:
        return []

# --- MAIN COG CLASS ---

class CommandsCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    async def send_and_delete(self, interaction: discord.Interaction, content: str, delay: int = 3):
        """Sends a followup message and deletes it after a delay."""
        message = await interaction.followup.send(content, ephemeral=True)
        await asyncio.sleep(delay)
        try:
            await message.delete()
        except discord.errors.NotFound:
            pass # User may have dismissed it, which is fine.

    @app_commands.command(name="version", description="Shows the bot's current version and information.")
    async def version(self, interaction: discord.Interaction):
        try:
            await interaction.response.defer(ephemeral=True)
            embed = discord.Embed(title="Counter Bot Information", color=discord.Color.blue())
            embed.add_field(name="Version", value=f"`{self.bot.version}`", inline=False)
            embed.set_footer(text=f"Developed with ❤️ | BOT_MODE: {self.bot.mode}")
            await interaction.followup.send(embed=embed)
        except Exception as e: await send_error_report(interaction, e)

    @app_commands.command(name="createcounter", description="Creates a new counter in a specified group.")
    @app_commands.describe(group="The group name (case-insensitive).", name="The counter name (case-insensitive).")
    @app_commands.autocomplete(group=get_groups_autocomplete)
    async def createcounter(self, interaction: discord.Interaction, group: str, name: str):
        try:
            await interaction.response.defer(ephemeral=True)
            queued_message = await interaction.followup.send(f"➡️ Your request to create counter `{name}` in group `{group}` has been queued.", ephemeral=True)
            job_event = asyncio.Event()
            job = {'action': 'create_counter', 'payload': {'guild_id': interaction.guild.id, 'group_name': group.lower(), 'counter_name': name.lower()}, 'event': job_event}
            await self.bot.db_queue.put(job)
            await job_event.wait()
            try: await queued_message.delete()
            except discord.errors.NotFound: pass
            if job.get('error'):
                await interaction.followup.send(f"❌ **Error:** {job['error']}", ephemeral=True)
            else:
                await self.send_and_delete(interaction, f"✅ Successfully created counter `{name}` in group `{group}`!")
        except Exception as e: await send_error_report(interaction, e)

    @app_commands.command(name="listcounters", description="Lists all interactive counters in a specified group.")
    @app_commands.describe(group="The group you want to list (case-insensitive).")
    @app_commands.autocomplete(group=get_groups_autocomplete)
    async def listcounters(self, interaction: discord.Interaction, group: str):
        try:
            await interaction.response.defer()
            view = CounterView(bot=self.bot, guild_id=interaction.guild.id, group_name=group.lower())
            await view.send_initial_message(interaction)
        except Exception as e: await send_error_report(interaction, e)

    @app_commands.command(name="listgroups", description="Lists all available counter groups in this server.")
    async def listgroups(self, interaction: discord.Interaction):
        try:
            await interaction.response.defer(ephemeral=True)
            groups = self.bot.db_manager.get_all_groups(interaction.guild.id)
            if not groups: await interaction.followup.send("There are no counter groups in this server yet.", ephemeral=True); return
            formatted_list = "\n".join([f"- `{group.capitalize()}`" for group in sorted(groups)])
            embed = discord.Embed(title="Available Counter Groups", description=formatted_list, color=discord.Color.blue())
            await interaction.followup.send(embed=embed, ephemeral=True)
        except Exception as e: await send_error_report(interaction, e)

    @app_commands.command(name="deletecounter", description="Deletes a counter from a group.")
    @app_commands.describe(group="The group the counter belongs to.", name="The counter to delete.")
    @app_commands.autocomplete(group=get_groups_autocomplete, name=get_counters_autocomplete)
    async def deletecounter(self, interaction: discord.Interaction, group: str, name: str):
        try:
            await interaction.response.defer(ephemeral=True)
            group_lower = group.lower(); name_lower = name.lower()
            job_event_del = asyncio.Event()
            job_del = {'action': 'delete_counter', 'payload': {'guild_id': interaction.guild.id, 'group_name': group_lower, 'counter_name': name_lower}, 'event': job_event_del}
            await self.bot.db_queue.put(job_del)
            await job_event_del.wait()
            await self.send_and_delete(interaction, f"✅ Deleted counter `{name}` from group `{group}`.")
            if self.bot.db_manager.is_group_empty(interaction.guild.id, group_lower):
                confirm_view = ConfirmationView(author=interaction.user, confirmation_text=f"The group **`{group.capitalize()}`** is now empty. Would you like to delete it and all its associated messages?")
                await interaction.followup.send(confirm_view.confirmation_text, view=confirm_view, ephemeral=True)
                message = await interaction.original_response()
                confirm_view.message = message
                await confirm_view.wait()
                if confirm_view.value is True:
                    job_event_purge = asyncio.Event()
                    job_purge = {'action': 'delete_group', 'payload': {'guild_id': interaction.guild.id, 'group_name': group_lower}, 'event': job_event_purge}
                    await self.bot.db_queue.put(job_purge)
                    await job_event_purge.wait()
                    await message.edit(content=f"✅ Successfully purged the empty group `{group}`.", view=None)
        except Exception as e: await send_error_report(interaction, e)

    @app_commands.command(name="deletegroup", description="[DANGEROUS] Deletes an entire group and all of its counters.")
    @app_commands.describe(group="The group to delete permanently.")
    @app_commands.autocomplete(group=get_groups_autocomplete)
    async def deletegroup(self, interaction: discord.Interaction, group: str):
        try:
            group_name_lower = group.lower()
            if not self.bot.db_manager.get_all_groups(interaction.guild.id, group_filter=group_name_lower):
                 await interaction.response.send_message(f"No group named `{group}` found.", ephemeral=True); return
            confirmation_text = f"**⚠️ IRREVERSIBLE ACTION ⚠️**\n\nThis will permanently delete:\n1. The group **`{group.capitalize()}`** and all of its counters from the database.\n2. **ALL** interactive counter list messages ever posted for this group.\n\nAre you absolutely sure?"
            view = ConfirmationView(author=interaction.user, confirmation_text=confirmation_text)
            await interaction.response.send_message(confirmation_text, view=view, ephemeral=True)
            message = await interaction.original_response()
            view.message = message
            await view.wait()
            if view.value is True:
                job_event = asyncio.Event()
                job = {'action': 'delete_group', 'payload': {'guild_id': interaction.guild.id, 'group_name': group_name_lower}, 'event': job_event}
                await self.bot.db_queue.put(job)
                await job_event.wait()
                await message.edit(content=f"✅ Successfully purged group `{group}` and all associated data.", view=None)
        except Exception as e: await send_error_report(interaction, e)

async def setup(bot: commands.Bot):
    await bot.add_cog(CommandsCog(bot))