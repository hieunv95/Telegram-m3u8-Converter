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

api_id = os.environ['API_ID']
api_hash = os.environ['API_HASH']
bot_token = os.environ['BOT_TOKEN']
dump_id = int(os.environ['DUMP_ID'])
xconfession_domain = 'https://next-prod-api.xconfessions.com/api/movies/'
xconfession_token = os.environ['XCONFESSION_TOKEN']
xconfession_headers = {"Authorization": f"Bearer {xconfession_token}"}

# Dropbox App Credentials
dropbox_token = os.environ['DROPBOX_ACCESS_TOKEN']
team_member_id = 'dbmid:AADtqt5k9g4iR19G4cUAzefiAKIe3U1lxTQ'
DBX_APP_KEY = os.environ['DBX_APP_KEY']
DBX_APP_SECRET = os.environ['DBX_APP_SECRET']
DBX_REFRESH_TOKEN = os.environ['DBX_REFRESH_TOKEN']

def get_new_access_token():
    """Fetch a new access token using the refresh token."""
    url = "https://api.dropboxapi.com/oauth2/token"
    data = {
        "grant_type": "refresh_token",
        "refresh_token": DBX_REFRESH_TOKEN
    }
    auth = (DBX_APP_KEY, DBX_APP_SECRET)

    response = requests.post(url, data=data, auth=auth)
    if response.status_code == 200:
        return response.json().get("access_token")
    else:
        print("Failed to refresh Dropbox token:", response.json())
        return None

# dbx = dropbox.DropboxTeam(dropbox_token)

# try:
#     members = dbx.team_members_list().members
#     for member in members:
#         print(f"Member ID: {member.profile.team_member_id} - Email: {member.profile.email}")
# except Exception as e:
#     print(f"❌ Error: {e}")



app = Client('m3u8', api_id, api_hash, bot_token=bot_token)

# with app:
#     user = app.get_me()
#     print(user)

def download_image(url, filename="thumbnail.jpg"):
    response = requests.get(url)
    if response.status_code == 200:
        with open(filename, "wb") as f:
            f.write(response.content)
        return filename
    return None

def requestXConfession(path):
    url = f"{xconfession_domain}{path}"
    response = requests.get(url, headers=xconfession_headers)
    if response.status_code == 200:
        return response.json()
    return None

# Dropbox chunk size (48MB is a safe choice)
CHUNK_SIZE = 48 * 1024 * 1024  # 48MB

def upload_to_dropbox(file_path, dropbox_path, token = ''):
    """
    Uploads a file to Dropbox. Uses chunked upload if file is larger than 150MB.
    """
    dbx = dropbox.DropboxTeam(token if token else dropbox_token)
    dbx = dbx.as_user(team_member_id)

    file_size = os.path.getsize(file_path)
    print(f"📂 File size: {file_size / (1024 * 1024):.2f} MB")

    try:
        with open(file_path, "rb") as f:
            if file_size <= 150 * 1024 * 1024:  # If file <= 150MB, use simple upload
                print("📤 Using simple upload...")
                dbx.files_upload(f.read(), dropbox_path, mode=dropbox.files.WriteMode("add"))
            else:
                print("📤 Using chunked upload...")
                upload_session_start_result = dbx.files_upload_session_start(f.read(CHUNK_SIZE))
                cursor = dropbox.files.UploadSessionCursor(session_id=upload_session_start_result.session_id, offset=f.tell())
                commit = dropbox.files.CommitInfo(path=dropbox_path)

                while f.tell() < file_size:
                    print(f"⏳ Uploading chunk... {f.tell() / file_size:.2%} done")
                    dbx.files_upload_session_append(f.read(CHUNK_SIZE), cursor.session_id, cursor.offset)
                    cursor.offset = f.tell()

                # Finish upload
                dbx.files_upload_session_finish(f.read(CHUNK_SIZE), cursor, commit)
                print("✅ Upload complete!")
    except dropbox.exceptions.AuthError as e:
        if "expired_access_token" in str(e):
            print("🔄 Access token expired. Refreshing token...")
            token = get_new_access_token()
            if token:
                upload_to_dropbox(file_path, dropbox_path, token)
            else:
                print("❌ Failed to refresh token. Upload aborted.")
        else:
            print("❌ Dropbox upload error:", e)   


def extract_best_stream(m3u8_content, base_url, duration=0, stream_type="video", prefer_highest_quality=False):
    """
    Extracts the best available stream URL from an M3U8 playlist.
    - If `prefer_highest_quality=True`, returns the highest quality stream.
    - Otherwise, selects the best stream under 2GB. If all exceed 2GB, returns the lowest quality.

    Parameters:
        m3u8_content (str): The content of the M3U8 file.
        duration (int): The total video duration in seconds.
        base_url (str): The base URL of the M3U8 file to construct full URLs.
        stream_type (str): "video" (default) or "audio" to filter specific streams.
        prefer_highest_quality (bool): If True, returns the highest quality stream.

    Returns:
        str: The full stream URL or None if not found.
    """

    # Regex pattern to find EXT-X-STREAM-INF (video) with BANDWIDTH
    if stream_type == "video":
        pattern = r'#EXT-X-STREAM-INF:.*?BANDWIDTH=(\d+).*?\n(.*?)\n'
    elif stream_type == "audio":
        pattern = r'#EXT-X-MEDIA:TYPE=AUDIO.*?URI="([^"]+)"'
    else:
        raise ValueError("stream_type must be 'video' or 'audio'")

    # Find all matching streams
    matches = re.findall(pattern, m3u8_content)

    if not matches:
        return None  # No valid stream found

    # Sort streams by BANDWIDTH (highest first)
    sorted_streams = sorted(matches, key=lambda x: int(x[0]), reverse=True)

    if prefer_highest_quality:
        print("🔹 Returning highest quality stream.")
        selected_stream = sorted_streams[0][1].strip()
        return urljoin(base_url, selected_stream)

    for bandwidth, stream_url in sorted_streams:
        bandwidth = int(bandwidth)
        stream_url = stream_url.strip()

        # Estimate file size in GB
        estimated_size = (bandwidth * duration) / (8 * 10**9)
        print(f"Checking {stream_url} - Estimated Size: {estimated_size:.2f} GB")

        # If file size <= 2GB, return it immediately
        if estimated_size <= 2:
            return urljoin(base_url, stream_url)

    # If all streams exceed 2GB, return the lowest quality stream
    print("All streams >2GB, selecting the lowest quality stream.")
    return urljoin(base_url, sorted_streams[-1][1].strip())

def time_to_seconds(time_str):
    """Parses duration from 'H:M:S' or 'Xh Ymin Zs' formats into total seconds."""
    
    # Check if format is H:M:S
    if ":" in time_str:
        parts = time_str.split(":")
        parts = [int(p) if p.isdigit() else 0 for p in parts]  # Convert to int safely
        
        hours = parts[0] if len(parts) == 3 else 0
        minutes = parts[1] if len(parts) >= 2 else 0
        seconds = parts[2] if len(parts) == 3 else 0
        
    else:  # Handle '1h 54min 30s' format
        match = re.match(r'(?:(\d+)h)?\s*(?:(\d+)min)?\s*(?:(\d+)s)?', time_str)
        if not match:
            return None  # Return None if invalid format
        
        hours = int(match.group(1)) if match.group(1) else 0
        minutes = int(match.group(2)) if match.group(2) else 0
        seconds = int(match.group(3)) if match.group(3) else 0
    
    # Convert to total seconds
    total_seconds = (hours * 3600) + (minutes * 60) + seconds
    
    return total_seconds

def extract_audio_url(m3u8_content, base_url):
    """Extracts the audio .m3u8 URL from M3U8 content."""
    
    match = re.search(r'#EXT-X-MEDIA:TYPE=AUDIO.*?URI="([^"]+)"', m3u8_content)
    if match:
        stream_url = match.group(1).strip()
        return urljoin(base_url, stream_url)
    return None


def extract_english_subtitle(m3u8_content, base_url):
    # Find English subtitle entry
    match = re.search(r'#EXT-X-MEDIA:TYPE=SUBTITLES.*LANGUAGE="en".*URI="(.*?)"', m3u8_content)

    if match:
        stream_url = match.group(1).strip()
        return urljoin(base_url, stream_url)

    return None


@app.on_message(filters.command('start'))
async def start(_, message):
    await message.reply(f'''Use: `/convert m3u8_link`
Github Repo: [Click to go.](https://github.com/hieunv95/Telegram-m3u8-Converter/)
''')

@app.on_message(filters.command(['convert', 'c']))
async def convert(client, message):
    try:
        link = message.text.split(' ', 1)[1]
    except:
        print_exc()
        return await message.reply(f'''Use: `/convert m3u8_link`
Github Repo: [Click to go.](https://github.com/hieunv95/Telegram-m3u8-Converter/)
''')
    _info = await message.reply('Please wait...')

    id = link
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
    chat_id = dump_id if dump_id else message.chat.id;
    
    video_data = requestXConfession(f"{id}/play");
    stream_link = video_data['data']['streaming_links']['ahls']
    print(f"stream_link: {stream_link}")
    m3u8_res = requests.get(stream_link);
    m3u8_content = m3u8_res.text;
    base_url = urljoin(stream_link, '.');
    print(f"base_url: {base_url}")
    link = extract_best_stream(m3u8_content, base_url, duration=duration)
    print(f"link: {link}")

    audio_link = extract_audio_url(m3u8_content, base_url)
    print(f"audio_link: {audio_link}")
    try: 
        audio_filename = f'{id}_{int(time())}'
        audio_proc = await asyncio.create_subprocess_shell(
            f'ffmpeg -fflags +genpts -i "{audio_link}" -c copy -bufsize 20M -probesize 20M -threads 8 -preset ultrafast -flush_packets 1 -protocol_whitelist file,http,https,tcp,tls -multiple_requests 1 "{audio_filename}.aac"',
            stdout=PIPE,
            stderr=PIPE
        )
        await _info.edit("Converting file to aac...")
        out, err = await audio_proc.communicate()
        await _info.edit('File aac successfully converted.')
        print('\n\n\n', out, err, sep='\n')

        subtitle_link = extract_english_subtitle(m3u8_content, base_url)
        subtitle_filename = f'{id}_{int(time())}'
        subtitle_proc = await asyncio.create_subprocess_shell(
            f'ffmpeg -i {subtitle_link} -c copy {subtitle_filename}.vtt && ffmpeg -i {subtitle_filename}.vtt {subtitle_filename}.srt',
            stdout=PIPE,
            stderr=PIPE
        )
        await _info.edit("Converting file to srt...")
        out, err = await subtitle_proc.communicate()
        await _info.edit('File srt successfully converted.')
        print('\n\n\n', out, err, sep='\n')

        #link = 'https://cloudflarestream.com/607315e23ecdd2a05ad6879d5198cc33/manifest/stream_tffe8f5b68ebf5b39c09f0447ad45d4a3_r897789428.m3u8?useVODOTFE=false'


        dropbox_link = extract_best_stream(m3u8_content, base_url, prefer_highest_quality=True)
        print(f"dropbox_link: {dropbox_link}")

        filename = f'{id}_{int(time())}'
        proc = await asyncio.create_subprocess_shell(
            f'ffmpeg -i {link} -i {audio_filename}.aac -c copy {filename}.mp4',
            stdout=PIPE,
            stderr=PIPE
        )
        await _info.edit("Converting file to mp4...")
        out, err = await proc.communicate()
        await _info.edit('File successfully converted.')
        print('\n\n\n', out, err, sep='\n')

        dropbox_filename = filename if dropbox_link == link else f'{id}_{int(time())}'
        if dropbox_link != link:
          drop_proc = await asyncio.create_subprocess_shell(
            f'ffmpeg -i {dropbox_link} -i {audio_filename}.aac -c copy {dropbox_filename}.mp4',
            stdout=PIPE,
            stderr=PIPE
          )
          out, err = await drop_proc.communicate()
          await _info.edit('File Dropbox successfully converted.')
          print('\n\n\n', out, err, sep='\n')
        await _info.edit('Adding thumbnail...')
        thumbnail_path = download_image(thumbnail_url)

        await _info.edit('Uploading to Telegram...')

        await _info.edit("Uploading file to Telegram...")
        def progress(current, total):
            print(message.from_user.first_name, ' -> ', current, '/', total, sep='')
        
        performers = ", ".join(f"{performer['name']} {performer['last_name']}" for performer in metadata['data']['performers'])
        director_name = metadata['data']['director']['name']
        director_last_name = metadata['data']['director']['last_name']
        release_date = metadata['data']['release_date'].split()[0]
        year = release_date[:4]
        caption = f"""\
          **XConfessions**      {title} ({year})
**Cast:** __{performers}__
**Director:** {director_name} {director_last_name}
**Released:** {release_date}
          """

        await client.send_media_group(
            chat_id,
            [
                InputMediaPhoto(cover_title_picture_url),
                InputMediaPhoto(poster_picture_url),
                InputMediaPhoto(cover_picture_url + '&width=1274'),
                InputMediaPhoto(mobile_detail_picture_url),
                InputMediaVideo(f'{filename}.mp4', duration=duration, caption = f'{caption}', thumb=f'{thumbnail_path}', parse_mode=ParseMode.MARKDOWN, supports_streaming=True),
            ]
        )

        await client.send_animation(chat_id, cover_title_animation_url, caption = f'{title}')

        await _info.edit("Uploading file to Dropbox...")
        upload_to_dropbox(f'{dropbox_filename}.mp4', f"/XConfessions/{title}.mp4")
        
        os.remove(f'{filename}.mp4')
        os.remove(f'{audio_filename}.aac')
        os.remove(f'{thumbnail_path}')
        if dropbox_filename != filename:
          os.remove(f'{dropbox_filename}.mp4')
        if os.path.exists(f'{subtitle_filename}.vtt'):
          os.remove(f'{subtitle_filename}.vtt')
        if os.path.exists(f'{subtitle_filename}.srt'):
          upload_to_dropbox(f'{subtitle_filename}.srt', f"/XConfessions/{title}.srt")
          os.remove(f'{subtitle_filename}.srt')
    except:
        if os.path.exists(f'{filename}.mp4'):
          os.remove(f'{filename}.mp4')
        if os.path.exists(f'{thumbnail_path}'):
          os.remove(f'{thumbnail_path}')
        if os.path.exists(f'{subtitle_filename}.vtt'):
          os.remove(f'{subtitle_filename}.vtt')
        if os.path.exists(f'{subtitle_filename}.srt'):
          os.remove(f'{subtitle_filename}.srt')
        if os.path.exists(f'{audio_filename}.aac'):
          os.remove(f'{audio_filename}.aac')
        print_exc()
        return await _info.edit('`An error occurred.`')


app.run()
