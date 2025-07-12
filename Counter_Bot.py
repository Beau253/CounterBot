# Counter_Bot.py

import os
import asyncio
import logging
import discord
from discord.ext import commands
from threading import Thread
from flask import Flask
from dotenv import load_dotenv

from modules.gdrive_sync import GDriveSync
from modules.database_manager import DatabaseManager
from modules.views import CounterView

load_dotenv()
BOT_MODE = os.getenv('BOT_MODE', 'development')
logging.basicConfig(level=logging.DEBUG, format='%(asctime)s|%(levelname)-8s|%(name)-20s| %(message)s')
log = logging.getLogger(__name__)

TOKEN = os.getenv('DISCORD_TOKEN')
GDRIVE_FOLDER_ID = os.getenv('GDRIVE_FOLDER_ID')
DB_FILE_NAME = "counters.db"
SYNC_INTERVAL_SECONDS = 60

class CounterBot(commands.Bot):
    def __init__(self):
        super().__init__(command_prefix="!", intents=discord.Intents.default())
        self.db_manager = DatabaseManager(DB_FILE_NAME)
        self.gdrive_sync = GDriveSync(DB_FILE_NAME, GDRIVE_FOLDER_ID)
        self.db_queue = asyncio.Queue()
        self.locked_groups = set()
        self.db_is_dirty = False
        self.version = "V1.2.0"
        self.mode = BOT_MODE

    async def setup_hook(self):
        log.info("--- Starting Async Setup Hook ---")
        if not await self.gdrive_sync.authenticate():
            log.critical("Google Drive authentication FAILED."); return
        await self.gdrive_sync.download_database()
        self.db_manager.initialize_database()
        self.loop.create_task(self.db_worker())
        self.loop.create_task(self.sync_worker())
        await self.load_cogs()
        await self.re_attach_persistent_views()
        await self.tree.sync()
        log.info("--- Async Setup Hook Finished ---")
        
    async def re_attach_persistent_views(self):
        log.info("[Setup Hook] Re-attaching and refreshing persistent views...")
        active_views = self.db_manager.get_all_active_views()
        count = 0
        for record in active_views:
            try:
                view = CounterView(bot=self, guild_id=record['guild_id'], group_name=record['group_name'])
                await view.update_message_by_id(record['channel_id'], record['message_id'])
                count += 1
            except discord.errors.NotFound:
                message_id_for_log = record.get('message_id', 'Unknown')
                log.warning(f"Message {message_id_for_log} not found.")
                if self.mode == 'development':
                    prompt = f"  > Stale view for message {message_id_for_log} found. Delete from DB? (y/n) (Defaults to 'y' in 3s): "
                    try:
                        loop = asyncio.get_running_loop()
                        future = loop.run_in_executor(None, lambda: input(prompt).lower())
                        choice = await asyncio.wait_for(future, timeout=3.0)
                    except asyncio.TimeoutError:
                        print("\n  > Timed out. Defaulting to 'y'.")
                        choice = 'y'
                    if choice == 'y': self.db_manager.remove_active_view(message_id_for_log); log.info("  > Stale view entry deleted.")
                    else: log.warning("  > Stale view entry kept.")
                else: self.db_manager.remove_active_view(message_id_for_log)
            except Exception as e: log.error(f"Failed to refresh view on startup for record {record}: {e}")
        log.info(f"Successfully refreshed {count} persistent views.")

    async def load_cogs(self):
        log.info("[Setup Hook] Loading command cogs...")
        # Build an absolute path to the cogs directory
        cogs_path = os.path.join(os.path.dirname(__file__), 'cogs')
        for filename in os.listdir(cogs_path):
            if filename.endswith('.py') and not filename.startswith('__'):
                try:
                    await self.load_extension(f'cogs.{filename[:-3]}')
                    log.info(f"✅ Successfully loaded Cog: {filename}")
                except Exception as e:
                    log.error(f"❌ Failed to load cog: {filename}", exc_info=e)

    async def on_ready(self):
        log.info("=" * 30); log.info(f"{self.user} is online. Version: {self.version}"); log.info("=" * 30)
        
    async def purge_group_views(self, guild_id: int, group_name: str):
        log.info(f"Purging all Discord messages for group '{group_name}'...")
        views_to_delete = self.db_manager.get_views_for_group(guild_id, group_name)
        for record in views_to_delete:
            try:
                channel = self.get_channel(record['channel_id']) or await self.fetch_channel(record['channel_id'])
                message = await channel.fetch_message(record['message_id'])
                await message.delete()
                log.info(f"  > Deleted message {record['message_id']}")
            except Exception: pass

    async def proactive_group_refresh(self, guild_id: int, group_name: str, locked: bool):
        log.info(f"Proactively refreshing views for group '{group_name}' to locked={locked}")
        views_to_update = self.db_manager.get_views_for_group(guild_id, group_name)
        for record in views_to_update:
            try:
                view = CounterView(bot=self, guild_id=record['guild_id'], group_name=record['group_name'])
                await view.update_message_by_id(record['channel_id'], record['message_id'], locked=locked)
            except discord.errors.NotFound: self.db_manager.remove_active_view(record['message_id'])
            except Exception as e: log.error(f"Failed to proactively refresh message {record['message_id']}: {e}")

    async def db_worker(self):
        log.info("DB worker started.")
        while True:
            job = await self.db_queue.get()
            group_name = job.get('payload', {}).get('group_name'); guild_id = job.get('payload', {}).get('guild_id')
            try:
                action, payload = job.get('action'), job.get('payload', {})
                if action == 'delete_group': await self.purge_group_views(guild_id, group_name)
                if action == 'create_counter': job['error'] = self.db_manager.create_counter(**payload)
                elif action == 'update_counter': self.db_manager.update_counter(**payload)
                elif action == 'delete_counter': self.db_manager.delete_counter(**payload)
                elif action == 'delete_group': self.db_manager.delete_group(**payload)
                if not job.get('error'): self.db_is_dirty = True; await self.proactive_group_refresh(guild_id, group_name, locked=False)
                else: await self.proactive_group_refresh(guild_id, group_name, locked=False)
            except Exception as e:
                log.error(f"Critical worker error: {e}", exc_info=True); job['error'] = "A critical worker error occurred."
                await self.proactive_group_refresh(guild_id, group_name, locked=False)
            finally:
                if group_name in self.locked_groups: self.locked_groups.remove(group_name)
                if event := job.get('event'): event.set()
                self.db_queue.task_done()

    async def sync_worker(self):
        log.info("Sync worker started.")
        while True:
            await asyncio.sleep(SYNC_INTERVAL_SECONDS)
            if self.db_is_dirty:
                log.info("Database is dirty, starting sync to Google Drive...");
                try: await self.gdrive_sync.upload_database(); self.db_is_dirty = False; log.info("Sync to Google Drive successful.")
                except Exception as e: log.error(f"Failed to sync database to Google Drive: {e}", exc_info=True)

# --- Keep-Alive & Main Execution ---
app = Flask('')
@app.route('/')
def home():
    return "CounterBot is alive!"

def keep_alive():
    Thread(target=lambda: app.run(host='0.0.0.0', port=8080)).start()

if __name__ == "__main__":
    if TOKEN and GDRIVE_FOLDER_ID: keep_alive(); bot = CounterBot(); bot.run(TOKEN)
    else: log.critical("Missing TOKEN or GDRIVE_FOLDER_ID environment variables.")