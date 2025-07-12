# /modules/gdrive_sync.py

import os
import io
import json
import logging
import asyncio
from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseDownload, MediaFileUpload
from googleapiclient.errors import HttpError

log = logging.getLogger(__name__)

class GDriveSync:
    """
    Handles all authentication and file synchronization with Google Drive.
    This version is a refactor of the user's proven, working gdrive_handler.
    """
    def __init__(self, local_db_path: str, gdrive_folder_id: str):
        self.local_db_path = local_db_path
        self.db_filename = os.path.basename(local_db_path)
        self.gdrive_folder_id = gdrive_folder_id
        self.drive_service = None # This will hold the authenticated service object
        self._file_id_cache = None

    async def authenticate(self) -> bool:
        """Authenticates with Google using the proven service account method."""
        def blocking_auth():
            creds_json_string = os.getenv('GOOGLE_CREDENTIALS_JSON')
            if not creds_json_string:
                log.critical("GOOGLE_CREDENTIALS_JSON environment variable not set.")
                return False
            try:
                creds_info = json.loads(creds_json_string)
                scopes = ['https://www.googleapis.com/auth/drive']
                creds = service_account.Credentials.from_service_account_info(creds_info, scopes=scopes)
                self.drive_service = build('drive', 'v3', credentials=creds)
                log.info("✅ Google Drive authentication SUCCESSFUL.")
                return True
            except Exception as e:
                log.critical(f"Google Drive authentication FAILED: {e}", exc_info=True)
                return False
        
        return await asyncio.to_thread(blocking_auth)

    def _find_remote_file(self):
        """Finds the database file in Google Drive, caching the ID."""
        if self._file_id_cache:
            try:
                # Test the cache by fetching metadata. If it fails, we'll search again.
                self.drive_service.files().get(fileId=self._file_id_cache, fields='id').execute()
                return self._file_id_cache
            except HttpError as e:
                if e.resp.status == 404:
                    log.warning("Cached file ID not found. Searching again.")
                    self._file_id_cache = None
                else: raise

        query = f"'{self.gdrive_folder_id}' in parents and name = '{self.db_filename}' and trashed = false"
        response = self.drive_service.files().list(q=query, spaces='drive', fields='files(id)').execute()
        files = response.get('files', [])
        
        if files:
            self._file_id_cache = files[0].get('id')
            log.debug(f"Found remote file ID: {self._file_id_cache}")
            return self._file_id_cache
        return None

    async def download_database(self):
        """Downloads the database file from Google Drive."""
        def blocking_download():
            file_id = self._find_remote_file()
            if file_id:
                log.info(f"Downloading '{self.db_filename}' from Google Drive...")
                try:
                    request = self.drive_service.files().get_media(fileId=file_id)
                    fh = io.FileIO(self.local_db_path, 'wb')
                    downloader = MediaIoBaseDownload(fh, request)
                    done = False
                    while not done:
                        status, done = downloader.next_chunk()
                        if status:
                            log.debug(f"Download progress: {int(status.progress() * 100)}%.")
                    log.info("Database download complete.")
                except Exception as e:
                    log.error(f"A critical error occurred during download: {e}", exc_info=True)
            else:
                log.warning("No database file found on Google Drive. A new one will be created on the first write.")
        
        await asyncio.to_thread(blocking_download)

    async def upload_database(self):
        """Uploads the local database file to Google Drive."""
        if not os.path.exists(self.local_db_path):
            log.error(f"Cannot upload database: Local file '{self.local_db_path}' not found.")
            return

        def blocking_upload():
            file_id = self._find_remote_file()
            media = MediaFileUpload(self.local_db_path, mimetype='application/x-sqlite3', resumable=True)
            try:
                if not file_id:
                    log.info(f"Creating new file '{self.db_filename}' on Google Drive...")
                    file_metadata = {'name': self.db_filename, 'parents': [self.gdrive_folder_id]}
                    created_file = self.drive_service.files().create(body=file_metadata, media_body=media, fields='id').execute()
                    self._file_id_cache = created_file.get('id')
                    log.info("New file created and uploaded successfully.")
                else:
                    log.info(f"Updating file ID {file_id} on Google Drive...")
                    self.drive_service.files().update(fileId=file_id, media_body=media).execute()
                    log.info("File updated successfully.")
            except Exception as e:
                log.error(f"FAILED to upload DB: {e}", exc_info=True)

        await asyncio.to_thread(blocking_upload)