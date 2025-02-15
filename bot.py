from pyrogram import Client, filters
import os
import asyncio
from traceback import print_exc
from subprocess import PIPE, STDOUT
from time import time
import requests
import re
from urllib.parse import urljoin

api_id = os.environ['API_ID']
api_hash = os.environ['API_HASH']
bot_token = os.environ['BOT_TOKEN']
#dump_id = os.environ['DUMP_ID']
dump_id = ''
xconfession_domain = 'https://next-prod-api.xconfessions.com/api/movies/'
xconfession_token = os.environ['XCONFESSION_TOKEN']
xconfession_headers = {"Authorization": f"Bearer {xconfession_token}"}


app = Client('m3u8', api_id, api_hash, bot_token=bot_token)

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

def extract_best_stream(m3u8_content, base_url, size_limit=2 * 1024 * 1024 * 1024):
    """
    Extracts 1080p stream if available. If its estimated file size > 2GB, fall back to 720p.
    Returns the best available stream URL.
    """
    # Define regex patterns for 1080p and 720p streams
    patterns = {
        "1080p": re.compile(r'#EXT-X-STREAM-INF:RESOLUTION=1920x1080.*?BANDWIDTH=(\d+).*?\n(.*?)$', re.MULTILINE),
        "720p": re.compile(r'#EXT-X-STREAM-INF:RESOLUTION=1280x720.*?BANDWIDTH=(\d+).*?\n(.*?)$', re.MULTILINE)
    }

    # Try to extract 1080p first
    for quality, pattern in patterns.items():
        match = pattern.search(m3u8_content)
        if match:
            bandwidth = int(match.group(1))  # BANDWIDTH in bits per second
            url = match.group(2).strip()  # Extract stream URL

            # Estimate file size assuming a 2-hour video
            estimated_size = (bandwidth / 8) * (2 * 60 * 60)  # Convert bits to bytes

            # If it's 1080p and too large (>2GB), continue to check 720p
            if quality == "1080p" and estimated_size > size_limit:
                continue  # Skip 1080p and try 720p

            # Otherwise, return the stream URL
            full_url = urljoin(base_url, url)
            return full_url

    return None  # No valid stream found

def time_to_seconds(time_str):
    """
    Converts a time string (H:M:S) to total seconds as an integer.
    Example: "2:15:30" → 8130 seconds
    """
    try:
        parts = list(map(int, time_str.split(":")))  # Convert to list of integers
        if len(parts) == 3:  # Format H:M:S
            hours, minutes, seconds = parts
        elif len(parts) == 2:  # Format M:S (assumes 0 hours)
            hours, minutes, seconds = 0, parts[0], parts[1]
        else:
            raise ValueError("Invalid time format")

        total_seconds = hours * 3600 + minutes * 60 + seconds
        return total_seconds
    except ValueError as e:
        print(f"Error parsing time: {e}")
        return 0  # Default to 0 if parsing fails


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
    
    video_data = requestXConfession(f"{id}/play");
    stream_link = video_data['data']['streaming_links']['ahls']
    print(f"stream_link: {stream_link}")
    m3u8_res = requests.get(stream_link);
    m3u8_content = m3u8_res.text;
    base_url = urljoin(stream_link, '.');
    print(f"base_url: {base_url}")
    link = extract_best_stream(m3u8_content, base_url)
    print(f"link: {link}")

    filename = f'{id}_{int(time())}'
    proc = await asyncio.create_subprocess_shell(
        f'ffmpeg -i {link} -c copy -bsf:a aac_adtstoasc {filename}.mp4',
        stdout=PIPE,
        stderr=PIPE
    )
    await _info.edit("Converting file to mp4...")
    out, err = await proc.communicate()
    await _info.edit('File successfully converted.')
    print('\n\n\n', out, err, sep='\n')
    try: 
        await _info.edit('Adding thumbnail...')
        # proc2 = await asyncio.create_subprocess_shell(
        #     f'ffmpeg -i {filename}.mp4 -ss 00:00:30.000 -vframes 5 {filename}.jpg',
        #     stdout=PIPE,
        #     stderr=PIPE
        # )
        # await proc2.communicate()
        #url = 'https://img.erikalust.com/22751cdd-a48a-498f-8869-d88f6aa992c2.png?auto=compress%2Cformat&ar=16:9&fit=crop&crop=edges&q=60&w=1'
        #url = 'https://img.erikalust.com/0de6444c-2589-46c4-b1a4-c29781081d26.jpg?auto=compress%2Cformat&ar=7:4&fit=crop&crop=faces&auto=compress,format&cs=srgb&q=50&width=4742'
        #url = 'https://img.erikalust.com/9f7ffef1-a358-4757-a820-cdcdfc1ec5cf.jpg?auto=compress%2Cformat&ar=178:252&fit=crop&crop=faces&auto=compress,format&cs=srgb&q=50&width=328'
        # url = 'https://img.erikalust.com/2R3v3gL5YecJF0PZfAq79DbrWWfYdbelgJnoZyNe.gif?auto=compress%2Cformat'
        #url = 'https://img.erikalust.com/da31e66d-b2b7-4c2b-841d-bc804cfc55c0.png?auto=compress%2Cformat'

        thumbnail_path = download_image(thumbnail_url)
        # await _info.edit('Scraping video duration...')
        # proc3 = await asyncio.create_subprocess_shell(
        #     f'ffprobe -v error -show_entries format=duration -of default=noprint_wrappers=1:nokey=1 {filename}.mp4',
        #     stdout=PIPE,
        #     stderr=STDOUT
        # )
        # try:
        #   duration, _ = await proc3.communicate()
        #   print("duration1 : {duration}")
        #   duration = duration.decode().strip()
        #   print("duration2 : {duration}")
        #   duration = int(float(duration))
        #   print("duration3 : {duration}")
        # except (ValueError, AttributeError) as e:
        #     print(f"Error parsing duration: {e}")
        #     duration = 0  # Default value if parsing fails

        await _info.edit('Uploading to Telegram...')

        await _info.edit("Uploading file to Telegram...")
        def progress(current, total):
            print(message.from_user.first_name, ' -> ', current, '/', total, sep='')
        await client.send_video(dump_id if dump_id else message.chat.id, f'{filename}.mp4', duration=duration, thumb=f'{thumbnail_path}', caption = f'{caption}', progress=progress, supports_streaming=True)
        os.remove(f'{filename}.mp4')
        #os.remove(f'{filename}.jpg')
        os.remove(f'{thumbnail_path}')
    except:
        print_exc()
        return await _info.edit('`An error occurred.`')


app.run()
