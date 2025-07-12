# /modules/views.py

import logging
import discord
from discord.ui import View, Button
import math
import asyncio

log = logging.getLogger(__name__)
ITEMS_PER_PAGE = 4

class CounterView(View):
    def __init__(self, bot, guild_id: int, group_name: str, page: int = 1):
        super().__init__(timeout=None)
        self.bot = bot
        self.guild_id = guild_id
        self.group_name = group_name
        self.db_manager = bot.db_manager
        self.db_queue = bot.db_queue
        self.page = page
        self.message: discord.Message = None

    def _get_content(self, locked: bool = False) -> str:
        if locked: return f"**⏳ Processing...**\n*This message will update automatically.*"
        all_items = self.db_manager.get_counters_in_group(self.guild_id, self.group_name)
        title = f"**Counters in Group: `{self.group_name.capitalize()}`**\n"
        if not all_items: return title + "This group has no counters. Use `/createcounter` to add one!"
        return title + "*This is an interactive message.*"

    def _rebuild_ui(self, locked: bool = False):
        self.clear_items()
        all_items = self.db_manager.get_counters_in_group(self.guild_id, self.group_name)
        total_pages = math.ceil(len(all_items) / ITEMS_PER_PAGE) if all_items else 1
        self.page = max(1, min(self.page, total_pages))
        start_index = (self.page - 1) * ITEMS_PER_PAGE
        end_index = start_index + ITEMS_PER_PAGE
        items_on_page = all_items[start_index:end_index]
        for i, item in enumerate(items_on_page):
            name, value = item['name'], item['value']
            self.add_item(Button(label=f"{name.capitalize()}: {value}", style=discord.ButtonStyle.secondary, disabled=True, row=i))
            self.add_item(self.ActionButton(style=discord.ButtonStyle.success, emoji="🔼", custom_id=f"inc:{name}", row=i, disabled=locked))
            self.add_item(self.ActionButton(style=discord.ButtonStyle.danger, emoji="🔽", custom_id=f"dec:{name}", row=i, disabled=locked))
            self.add_item(self.ActionButton(style=discord.ButtonStyle.secondary, emoji="❌", custom_id=f"del:{name}", row=i, disabled=locked))
        self.add_item(self.PaginationButton(label="◀️", custom_id="prev", row=4, disabled=locked or self.page <= 1))
        self.add_item(Button(label=f"Page {self.page}/{total_pages}", style=discord.ButtonStyle.secondary, disabled=True, row=4))
        self.add_item(self.PaginationButton(label="▶️", custom_id="next", row=4, disabled=locked or self.page >= total_pages))
        self.add_item(self.PaginationButton(label="Refresh", emoji="🔄", custom_id="refresh", row=4, disabled=locked))

    async def send_initial_message(self, interaction: discord.Interaction):
        self._rebuild_ui()
        await interaction.followup.send(content=self._get_content(), view=self)
        self.message = await interaction.original_response()
        self.db_manager.add_active_view(message_id=self.message.id, channel_id=self.message.channel.id, guild_id=self.guild_id, group_name=self.group_name)
        self.bot.db_is_dirty = True

    async def update_message_by_id(self, channel_id: int, message_id: int, locked: bool = False):
        channel = self.bot.get_channel(channel_id) or await self.bot.fetch_channel(channel_id)
        self.message = await channel.fetch_message(message_id)
        await self.update_message(locked)

    async def update_message(self, locked: bool = False):
        if self.message:
            self._rebuild_ui(locked=locked)
            await self.message.edit(content=self._get_content(locked=locked), view=self)

    class ActionButton(Button):
        async def callback(self, interaction: discord.Interaction):
            view: CounterView = self.view
            if view.group_name in view.bot.locked_groups:
                await interaction.response.send_message("This group is being updated. Please wait...", ephemeral=True, delete_after=3); return

            action, counter_name = self.custom_id.split(':')
            
            # --- Deletion now has special logic ---
            if action == 'del':
                view.bot.locked_groups.add(view.group_name)
                await interaction.response.defer()
                try:
                    await view.bot.proactive_group_refresh(view.guild_id, view.group_name, locked=True)
                    
                    job_event_del = asyncio.Event()
                    job_del = {'action': 'delete_counter', 'payload': {'guild_id': view.guild_id, 'group_name': view.group_name, 'counter_name': counter_name}, 'event': job_event_del}
                    await view.db_queue.put(job_del)
                    await job_event_del.wait()
                    
                    # Proactive refresh will be called by the worker, no need to call it here.
                    
                    if view.db_manager.is_group_empty(view.guild_id, view.group_name):
                        confirm_view = ConfirmationView(author=interaction.user, confirmation_text=f"The group **`{view.group_name.capitalize()}`** is now empty. Would you like to delete the group and all of its counter lists as well?")
                        await interaction.followup.send(confirm_view.confirmation_text, view=confirm_view, ephemeral=True)
                        message = await interaction.original_response()
                        confirm_view.message = message
                        await confirm_view.wait()
                        
                        if confirm_view.value is True:
                            job_event_purge = asyncio.Event()
                            job_purge = {'action': 'delete_group', 'payload': {'guild_id': view.guild_id, 'group_name': view.group_name}, 'event': job_event_purge}
                            await view.db_queue.put(job_purge)
                            await job_event_purge.wait()
                            await message.edit(content=f"✅ Successfully purged the empty group `{view.group_name}`.", view=None)

                except Exception as e: log.error(f"Error in delete ActionButton: {e}", exc_info=True)
                finally:
                    # Final unlock is still handled by the worker, this just releases the initial lock
                    if view.group_name in view.bot.locked_groups: view.bot.locked_groups.remove(view.group_name)
                return

            # --- Inc/Dec logic remains the same ---
            view.bot.locked_groups.add(view.group_name)
            await interaction.response.defer()
            try:
                await view.bot.proactive_group_refresh(view.guild_id, view.group_name, locked=True)
                job = {'payload': {'guild_id': view.guild_id, 'group_name': view.group_name, 'counter_name': counter_name}}
                if action == 'inc': job.update({'action': 'update_counter', 'payload': {**job['payload'], 'action': 'inc'}})
                elif action == 'dec': job.update({'action': 'update_counter', 'payload': {**job['payload'], 'action': 'dec'}})
                await view.db_queue.put(job)
            except Exception as e:
                log.error(f"Error in ActionButton callback: {e}", exc_info=True)
                if view.group_name in view.bot.locked_groups: view.bot.locked_groups.remove(view.group_name)
                await view.bot.proactive_group_refresh(view.guild_id, view.group_name, locked=False)

    class PaginationButton(Button):
        async def callback(self, interaction: discord.Interaction):
            view: CounterView = self.view
            if view.group_name in view.bot.locked_groups: await interaction.response.send_message("This group is being updated. Please wait...", ephemeral=True, delete_after=3); return
            await interaction.response.defer(); view.message = interaction.message
            if self.custom_id == "prev": view.page -= 1
            elif self.custom_id == "next": view.page += 1
            await view.update_message(locked=False)

class ConfirmationView(View):
    def __init__(self, author: discord.Member, confirmation_text: str):
        super().__init__(timeout=60)
        self.author = author; self.confirmation_text = confirmation_text; self.value = None; self.message = None
    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.author.id: await interaction.response.send_message("You cannot interact with this confirmation.", ephemeral=True); return False
        return True
    async def on_timeout(self):
        for item in self.children: item.disabled = True
        if self.message: await self.message.edit(content="Confirmation timed out.", view=self)
    @discord.ui.button(label="Yes, I'm Sure", style=discord.ButtonStyle.danger)
    async def confirm_callback(self, interaction: discord.Interaction, button: Button):
        await interaction.response.edit_message(content=f"✅ Confirmed. Processing request...", view=None); self.value = True; self.stop()
    @discord.ui.button(label="No, Cancel", style=discord.ButtonStyle.secondary)
    async def cancel_callback(self, interaction: discord.Interaction, button: Button):
        await interaction.response.edit_message(content="Deletion cancelled.", view=None); self.value = False; self.stop()