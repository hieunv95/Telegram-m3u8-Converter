from pyrogram import Client, filters
from pyrogram.types import InputMediaPhoto, InputMediaVideo
from pyrogram.enums import ParseMode
import os
import asyncio
from traceback import print_exc
from subprocess import PIPE, STDOUT
from time import time
from pyrogram.types.messages_and_media import audio
import requests
import re
from urllib.parse import urljoin
import dropbox
import subprocess
import aiohttp
import mimetypes
from urllib.parse import urlparse, urlunparse
from pyrogram.errors import FloodWait

api_id = os.environ['API_ID']
api_hash = os.environ['API_HASH']
bot_token = os.environ['BOT_TOKEN']
dump_id = int(os.environ['DUMP_ID'])
xconfession_domain = 'https://next-prod-api.xconfessions.com/api/movies/'
xconfession_token = os.environ['XCONFESSION_TOKEN']
xconfession_headers = {"Authorization": f"Bearer {xconfession_token}"}

dropbox_token = os.environ['DROPBOX_ACCESS_TOKEN']
team_member_id = 'dbmid:AADtqt5k9g4iR19G4cUAzefiAKIe3U1lxTQ'

app = Client('m3u8', api_id, api_hash, bot_token=bot_token)

def sanitize_filename(url):
    """Sanitize the filename by removing the query string and special characters."""
    # Parse the URL to break it into components
    parsed_url = urlparse(url)
    
    # Remove the query string from the URL
    sanitized_url = parsed_url._replace(query="").geturl()
    
    # Get the filename (without query string)
    filename = os.path.basename(sanitized_url)
    
    # Further sanitize filename by replacing spaces or special characters if necessary
    sanitized_filename = filename.replace(' ', '_')  # Example sanitization
    
    return sanitized_filename

DOWNLOAD_DIR = "downloads"
os.makedirs(DOWNLOAD_DIR, exist_ok=True)
async def download_file(url, session):
    """Downloads a file asynchronously and returns the local file path."""
    filename = sanitize_filename(os.path.basename(url))  # Sanitize the filename
    # Safeguard against invalid URLs
    file_extension = None
    mime_type, encoding = mimetypes.guess_type(url)
    if mime_type:
        file_extension = mimetypes.guess_extension(mime_type)

    if file_extension is None:
        file_extension = '.jpg'  # Default to .jpg if no extension can be determined

    file_path = os.path.join(DOWNLOAD_DIR, filename + file_extension)
    async with session.get(url) as response:
        if response.status == 200:
            with open(file_path, "wb") as file:
                file.write(await response.read())
            return file_path
    return None


async def download_all_files(file_urls):
    """Downloads all files asynchronously."""
    async with aiohttp.ClientSession() as session:
        tasks = [download_file(url, session) for url in file_urls]
        return await asyncio.gather(*tasks)


def split_into_batches(files, batch_size=10):
    """Splits the files into batches of a given size."""
    for i in range(0, len(files), batch_size):
        yield files[i:i + batch_size]

def requestXConfession(path):
    url = f"{xconfession_domain}{path}"
    response = requests.get(url, headers=xconfession_headers)
    if response.status_code == 200:
        return response.json()
    return None

@app.on_message(filters.command('start'))
async def start(_, message):
    await message.reply(f'''Use: `/l id1,id2`
Github Repo: [Click to go.](https://github.com/hieunv95/Telegram-m3u8-Converter/)
''')

@app.on_message(filters.command(['list', 'l']))
async def convert(client, message):
    try:
        link = message.text.split(' ', 1)[1]
    except:
        print_exc()
        return await message.reply(f'''Use: `/convert m3u8_link`
Github Repo: [Click to go.](https://github.com/hieunv95/Telegram-m3u8-Converter/)
''')
    _info = await message.reply('Please wait...')
    ids = link.split(',')
    for id in ids:
      await asyncio.sleep(5)
      await send_msg(client, message, id, _info)


async def send_msg(client, message, id, _info):
    try:
        metadata = requestXConfession(id);
        title = metadata['data']['title']
        print(f"title: {title}")
        thumbnail_url = metadata['data']['poster_picture']
        print(f"thumbnail_url: {thumbnail_url}")
        caption = f"{title} - XConfession"
        duration = time_to_seconds(metadata['data']['length'])
        cover_title_picture_url = metadata['data']['cover_title_picture']
        cover_title_picture_url = f"{cover_title_picture_url}&width=4742"
        cover_picture_url = metadata['data']['cover_picture']
        poster_picture_url = metadata['data']['poster_picture']
        mobile_detail_picture_url = metadata['data']['mobile_detail_picture']
        cover_title_animation_url = metadata['data']['cover_title_animation']
        album = metadata['data']['album'];
        chat_id = dump_id if dump_id else message.chat.id;
    
        await _info.edit("Uploading file to Telegram...")
        def progress(current, total):
            print(message.from_user.first_name, ' -> ', current, '/', total, sep='')
        
        performers = ", ".join(f"{performer['name']} {performer['last_name']}" for performer in metadata['data']['performers'])
        director_name = metadata.get('data', {}).get('director', {}).get('name', '')
        director_last_name = metadata.get('data', {}).get('director', {}).get('last_name', '')
        release_date = metadata['data']['release_date'].split()[0]
        year = release_date[:4]
        caption = f"""\
          **XConfessions**      {title} ({year})
**Cast:** __{performers}__
**Director:** {director_name} {director_last_name}
**Released:** {release_date}
**ID: ** {id}
          """

        album_urls = [item["path"] + "&width=1246" for item in album]
        print(album_urls)
        # Download all files
        downloaded_files = await download_all_files(album_urls)
    
        # Remove None values (failed downloads)
        downloaded_files = [file for file in downloaded_files if file]

        for batch in split_into_batches(downloaded_files):
            # Prepare media group for this batch
            media_group = [InputMediaPhoto(file) for file in batch]
            if media_group:
              await client.send_media_group(chat_id, media_group)
            for file in batch:
                try:
                    os.remove(file)
                   #print(f"🗑️ Deleted: {file}")
                except Exception as e:
                    print(f"⚠️ Error deleting {file}: {e}")

        await client.send_media_group(
            chat_id,
            [
                InputMediaPhoto(poster_picture_url),
                InputMediaPhoto(mobile_detail_picture_url),
                InputMediaPhoto(cover_picture_url+'&width=1274'),
                InputMediaPhoto(cover_title_picture_url),
            ] 
        )

        await client.send_animation(chat_id, cover_title_animation_url, caption = f'{caption}')
    except FloodWait as e:
        wait_time = getattr(e, 'value', 400)  # Default to 400 seconds if 'x' is not available
        print(f"Rate limit hit. Waiting for {wait_time} seconds...")
        await asyncio.sleep(wait_time)  # Sleep for the required time and try again
        await send_msg(client, message, id, _info)
    except:
        print_exc()
        return await _info.edit(f'An error occurred. {id} - {title}')


app.run()
