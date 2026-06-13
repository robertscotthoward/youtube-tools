import random
from time import sleep
from youtube_transcript_api import YouTubeTranscriptApi
import yt_dlp
import json
import os
import re
import typer
from typing import Optional
from bs4 import BeautifulSoup
from lib.modelstack import ModelStack
import lib.tools as tools
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request
from googleapiclient.discovery import build
from dotenv import load_dotenv

load_dotenv()

app = typer.Typer()


fromSeconds, toSeconds = 30, 60


cfg = tools.getYaml('config')
modelstack = ModelStack.from_config(cfg['modelstack'])
summarize_prompt = cfg['summarize']['prompt']


def build_md_header(title=None, url=None):
    lines = []
    if title:
        lines.append(f"- Title: {title}")
    if url:
        lines.append(f"- URL: {url}")
    return "\n".join(lines) + "\n\n" if lines else ""


def build_prompt(transcript_text):
    return f"{summarize_prompt}\n\n{transcript_text}"


def get_youtube_service():
    client_id = os.environ['YOUTUBE_CLIENT_ID']
    client_secret = os.environ['YOUTUBE_CLIENT_SECRET']
    scopes = os.environ['YOUTUBE_SCOPES'].split(',')
    token_file = 'cache/youtube_token.json'

    creds = None
    if os.path.exists(token_file):
        creds = Credentials.from_authorized_user_file(token_file, scopes)

    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            client_config = {
                "installed": {
                    "client_id": client_id,
                    "client_secret": client_secret,
                    "redirect_uris": ["urn:ietf:wg:oauth:2.0:oob", "http://localhost"],
                    "auth_uri": "https://accounts.google.com/o/oauth2/auth",
                    "token_uri": "https://oauth2.googleapis.com/token",
                }
            }
            flow = InstalledAppFlow.from_client_config(client_config, scopes)
            creds = flow.run_local_server(port=0)
        os.makedirs('cache', exist_ok=True)
        tools.writeText(token_file, creds.to_json())

    return build('youtube', 'v3', credentials=creds)


def fetch_subscriptions():
    service = get_youtube_service()
    raw = []  # list of (title, channel_id)
    next_page_token = None

    while True:
        response = service.subscriptions().list(
            part='snippet',
            mine=True,
            maxResults=50,
            pageToken=next_page_token,
            order='alphabetical',
        ).execute()

        for item in response.get('items', []):
            snippet = item['snippet']
            title = snippet['title']
            channel_id = snippet['resourceId']['channelId']
            raw.append((title, channel_id))

        next_page_token = response.get('nextPageToken')
        if not next_page_token:
            break

    # Resolve @handle URLs and descriptions in batches of 50
    channel_info_map = {}  # channel_id -> (url, description)
    ids = [channel_id for _, channel_id in raw]
    for i in range(0, len(ids), 50):
        batch = ids[i:i + 50]
        ch_response = service.channels().list(
            part='snippet',
            id=','.join(batch),
        ).execute()
        for ch in ch_response.get('items', []):
            ch_id = ch['id']
            snippet = ch['snippet']
            custom_url = snippet.get('customUrl')
            url = f"https://www.youtube.com/{custom_url}" if custom_url else f"https://www.youtube.com/channel/{ch_id}"
            description = re.sub(r'\s+', ' ', snippet.get('description', '')).strip()
            channel_info_map[ch_id] = (url, description)

    subscriptions = []
    for title, channel_id in raw:
        url, description = channel_info_map.get(channel_id, (f"https://www.youtube.com/channel/{channel_id}", ''))
        subscriptions.append((title, url, description))

    return sorted(subscriptions, key=lambda x: x[0].lower())


#print(modelstack.query("What city was Benjamin Franklin born in?"))

nWait = 0
def waitSomeTime():
    global nWait
    nWait = nWait + 1
    if nWait > 1:
        sleep(random.randint(fromSeconds, toSeconds)) # Otherwise Youtube blocks requests.


def get_json_cache(filename, func, force=False):
    if force and os.path.exists(filename):
        return tools.readJson(filename)
    data = func()
    tools.writeJson(filename, data)
    return data


def get_transcript(video_url):
    if "youtu.be/" in video_url:
        video_id = video_url.split("youtu.be/")[1].split("?")[0]
    else:
        video_id = video_url.split("v=")[1].split("&")[0]
    ytt_api = YouTubeTranscriptApi()
    
    try:
        transcript = ytt_api.fetch(video_id)
    except Exception as e:
        if "YouTube is blocking requests from your IP" in str(e):
            print("  YouTube is blocking requests from your IP. Try again later.")
            raise Exception("YouTube is blocking requests from your IP. Try again later.")
        elif "Subtitles are disabled for this video" in str(e):
            print("  No subtitles available.")
        elif "Could not retrieve a transcript" in str(e):
            print("  No transcripts available.")
        else:
            print(f"  Error fetching transcript: {e}")
        return None
        
    return transcript.to_raw_data()


def get_transcript_string(video_url, force=False):
    def func():
        waitSomeTime()
        j = get_transcript(video_url)
        if not j:
            return j
        s = " ".join([item['text'] for item in j]).strip().replace(".", ".\n")
        s = [x.strip() for x in s.splitlines("\n")]
        s = "\n".join(s)
        return s
    fn = f"cache/transcripts/transcript_{tools.md5(video_url)}.json"
    return get_json_cache(fn, func)


def all_videos(channel_url):
    options = {
        'quiet': True,
        'extract_flat': True,        # True = Faster, gets metadata without downloading
        'skip_download': True,
        'force_generic_extractor': False,
        'js_runtimes': {'nodejs': {}, 'deno': {}},
        'extractor_args': {
            'youtube': {
                'player_client': ['web', 'android'],  # avoid the broken clients
                'skip': ['web_safari', 'web_legacy'], # skip problematic ones
            }
        },
    }

    with yt_dlp.YoutubeDL(options) as ydl:
        def func():
            # This automatically handles @handle, /channel/, /c/, /user/, etc.
            info = ydl.extract_info(channel_url, download=False)
            return info
        channel_name = channel_url.split('/@')[1].split('/')[0]
        fn = tools.clean_filename(channel_url)
        fn = f"cache/{fn}.json"
        info = get_json_cache(fn, func)

        if 'entries' not in info:
            print("No videos found or invalid channel URL.")
            return []

        print(f"Found {len(info['entries'])} videos. Processing...")

        for entry in info['entries']:
            if entry is None:
                continue  # Sometimes happens with age-restricted/private videos

            video = {
                "id": entry.get('id'),
                "title": entry.get('title'),
                "url": f"https://www.youtube.com/watch?v={entry.get('id')}",
                "duration": entry.get('duration'),  # in seconds
                "view_count": entry.get('view_count'),
                "upload_date": entry.get('upload_date'),  # YYYYMMDD format
                "thumbnail": entry.get('thumbnail'),
                "uploader": entry.get('uploader'),
                "channel_name": channel_name
            }

            yield video


def compile_transcripts(channel_url):
    fn = tools.clean_filename(channel_url)
    fn = f"cache/{fn}.json"
    videos = tools.readJson(fn)
    with open(f"cache/output.txt", "w") as f:
        for video in videos['entries']:
            fn = video['id']
            fn = f"cache/videos/{fn}.json"
            if not os.path.exists(fn):
                continue
            v = tools.readJson(fn)
            f.write("-" * 100 + "\n")
            f.write(f"Title: {video['title']}\n")
            f.write(f"Transcript: {v['transcript']}\n\n\n")
        

def pull_transcripts(url):
    if '/@' in url:
        # The url is a channel url - a page with a list of videos. Ex: https://www.youtube.com/@EmergingVoicesStudio
        channel_name = url.split('/@')[1].split('/')[0]
        url = f"https://www.youtube.com/@{channel_name}/videos"
        videos = all_videos(url)
    else:
        # The url is a video url - a single video. Ex: https://www.youtube.com/watch?v=78T1ysWu9hw
        videos = [
            {
                'id': url.split('v=')[1],
                'title': url.split('v=')[1],
                'url': url,
            }
        ]
        

    videos = list(videos)
    n = 0
    for video in videos:
        def func():
            v = video.copy()
            v['transcript'] = get_transcript_string(video['url'])
            v['channel_name'] = channel_name
            return v
        fn = video['id']
        fn = f"cache/videos/{fn}.json"
        if os.path.exists(fn):
            j = tools.readJson(fn)
            if not j.get('channel_name'):   
                j['channel_name'] = channel_name
                tools.writeJson(fn, j)
            continue
        n = n + 1
        print(f"{n:>03}. {video['title']}...", end="")
        v = get_json_cache(fn, func)
        print("OK")
        pass
    

def update_one(jFn):
    "Read a JSON transcript file and write out the transcript to the summaries folder as a txt file."
    j = tools.readJson(jFn)
    txtFn = jFn.replace(".json", ".txt").replace("cache/videos/", "cache/summaries/")
    
    if j['transcript'] is None:
        n += 1
        print(n, jFn)
        t = get_transcript_string(f"https://www.youtube.com/watch?v={j['id']}", force=True)
        j['transcript'] = t
        tools.writeJson(jFn, j)

    if j.get('summary') is None:
        prompt = build_prompt(j['transcript'])
        j['summary'] = modelstack.query(prompt)
        tools.writeJson(jFn, j)
    
    if not os.path.exists(txtFn):
        s = f"""
Id: {j['id']}
Title: {j['title']}
Description: {j.get('description', '')}
Summary: {j.get('summary', '')}
Category: {', '.join(j.get('categories', []))}
Tags: {', '.join(j.get('tags', []))}
Transcript: {j.get('transcript', '')}
""".strip()
        s = [x.strip() for x in s.splitlines("\n")]
        s = "\n".join(s)
        tools.writeText(txtFn, s)    


def update_all():
    urls = """
https://www.youtube.com/@ClimateDN/videos
https://www.youtube.com/@PrometheanAction/videos
https://www.youtube.com/@matthew_berman/videos
https://www.youtube.com/@EmergingVoicesStudio/videos
https://www.youtube.com/@StephenGardner1/videos
https://www.youtube.com/@AmericaUncovered/videos
https://www.youtube.com/@ChinaUncensored/videos
https://www.youtube.com/@victordavishanson7273/videos
https://www.youtube.com/@DailySignal/videos
https://www.youtube.com/@ChrisWillx/videos
https://www.youtube.com/@BillWhittleChannel/videos
https://www.youtube.com/@truthrevoltoriginals9835/videos
https://www.youtube.com/@prageru/videos
https://www.youtube.com/@MichaelKnowles/videos
https://www.youtube.com/@NewDiscourses/videos
https://www.youtube.com/@DrJordanBPetersonClips/videos
https://www.youtube.com/@GDiesen1/videos"""

    for url in urls.splitlines():
        url = url.strip()
        if not url:
            continue
        pull_transcripts(url)

    "For all videos in cache, update their json and txt summary files."
    n = 0
    for fn in os.listdir("cache/videos/"):
        if not fn.endswith(".json"):
            continue
        jFn = f"cache/videos/{fn}"
        update_one(jFn)
    pass


def summarize_all():
    """Summarize all .txt files that don't have a corresponding .md file."""
    summaries_dir = "cache/summaries"
    if not os.path.exists(summaries_dir):
        print(f"Directory {summaries_dir} does not exist")
        return

    count = 0
    for fn in os.listdir(summaries_dir):
        if not fn.endswith(".txt"):
            continue

        txt_file = os.path.join(summaries_dir, fn)
        md_file = txt_file.replace(".txt", ".md")

        if os.path.exists(md_file):
            continue

        print(f"Summarizing {fn}...")
        transcript_text = tools.readText(txt_file)
        video_id = fn.replace(".txt", "")
        json_file = os.path.join("cache/videos", f"{video_id}.json")
        title, url = None, None
        if os.path.exists(json_file):
            meta = tools.readJson(json_file)
            title = meta.get('title')
            url = meta.get('url') or f"https://www.youtube.com/watch?v={video_id}"
        prompt = build_prompt(transcript_text)
        summary = build_md_header(title=title, url=url) + modelstack.query(prompt)
        tools.writeText(md_file, summary)
        print(f"  Created {md_file}")
        count += 1

    print(f"Summarized {count} file(s)")

            
def pull_transcript(video_url):
    fn = video_url.split("v=")[1]
    fnBase = f"cache/videos/{fn}"
    fn = f"{fnBase}.json"
    txtFn = fn.replace(".json", ".txt").replace("cache/videos/", "cache/summaries/")
    if os.path.exists(fn) and os.path.exists(txtFn):
        return

    def func():
        options = {
            'quiet': True,
            'extract_flat': True,        # True = Faster, gets metadata without downloading
            'skip_download': True,
            'force_generic_extractor': False,
            'js_runtimes': {'node': {}, 'deno': {}},
        }

        with yt_dlp.YoutubeDL(options) as ydl:
            v = {}
            v = ydl.extract_info(video_url, download=False)
            v['transcript'] = get_transcript_string(video_url)
            print(f"Id: {v['id']} - {v['title']}")
            tools.writeText(f"{fnBase}.txt", f"""
Id: {v['id']}
Title: {v['title']}
Category: {', '.join(v.get('categories', []))}
Tags: {', '.join(v.get('tags', []))}
Transcript: {v['transcript']}
""".strip())
            return v
        
    v = get_json_cache(fn, func)

    summarize_one(v)


def extract_video_id(video_url):
    """Extract video ID from a YouTube URL."""
    if "v=" in video_url:
        return video_url.split("v=")[1].split("&")[0]
    elif "youtu.be/" in video_url:
        return video_url.split("youtu.be/")[1].split("?")[0]
    return None


def pull_video(video_url):
    """
    Pull video data based on what files are missing:
    - cache/videos/{video_id}.json - video metadata with transcript
    - cache/summaries/{video_id}.txt - transcript text
    - cache/summaries/{video_id}.md - summary
    """
    video_id = extract_video_id(video_url)
    if not video_id:
        print(f"Could not extract video ID from: {video_url}")
        return

    # Ensure folders exist
    os.makedirs("cache/videos", exist_ok=True)
    os.makedirs("cache/summaries", exist_ok=True)

    videos_json_file = f"cache/videos/{video_id}.json"
    txt_file = f"cache/summaries/{video_id}.txt"
    md_file = f"cache/summaries/{video_id}.md"

    transcript_text = None

    # Step 1: Pull metadata and transcript to cache/videos if json doesn't exist
    if not os.path.exists(videos_json_file):
        print(f"Pulling metadata for {video_id}...")
        options = {
            'quiet': True,
            'extract_flat': True,
            'skip_download': True,
            'force_generic_extractor': False,
            'js_runtimes': {'node': {}, 'deno': {}},
        }
        with yt_dlp.YoutubeDL(options) as ydl:
            info = ydl.extract_info(video_url, download=False)

            # Get transcript
            transcript = get_transcript(video_url)
            if transcript:
                transcript_text = " ".join([item['text'] for item in transcript]).strip()
                transcript_text = transcript_text.replace(".", ".\n")
                transcript_text = "\n".join([line.strip() for line in transcript_text.splitlines()])

            # Extract channel name from URL if available
            channel_name = None
            if info.get('channel'):
                channel_name = info.get('channel')
            elif info.get('uploader'):
                channel_name = info.get('uploader')

            # Create structured JSON
            video_data = {
                "id": video_id,
                "title": info.get('title'),
                "url": video_url,
                "duration": info.get('duration'),
                "view_count": info.get('view_count'),
                "upload_date": info.get('upload_date'),
                "thumbnail": info.get('thumbnail'),
                "uploader": info.get('uploader'),
                "channel_name": channel_name,
                "transcript": transcript_text
            }
            tools.writeJson(videos_json_file, video_data)
            print(f"  Created {videos_json_file}")
    else:
        print(f"  {videos_json_file} already exists")
        # Load existing data to get transcript
        video_data = tools.readJson(videos_json_file)
        transcript_text = video_data.get('transcript')

    # Step 2: Create txt file in summaries if it doesn't exist
    title = video_data.get('title') if video_data else None
    url = (video_data.get('url') if video_data else None) or video_url
    txt_header = ""
    if title:
        txt_header += f"Title: {title}\n"
    if url:
        txt_header += f"URL: {url}\n"
    if txt_header:
        txt_header += "\n"

    if not os.path.exists(txt_file):
        if transcript_text:
            tools.writeText(txt_file, txt_header + transcript_text)
            print(f"  Created {txt_file}")
        else:
            print(f"  No transcript available for {video_id}")
    else:
        existing = tools.readText(txt_file)
        if url and url not in existing:
            tools.writeText(txt_file, txt_header + existing)
            print(f"  Updated {txt_file} with title/URL header")
        else:
            print(f"  {txt_file} already exists")

    # Step 3: Summarize if md doesn't exist (requires txt to exist)
    if not os.path.exists(md_file):
        if os.path.exists(txt_file):
            print(f"Summarizing transcript for {video_id}...")
            transcript_text = tools.readText(txt_file)
            v_title = video_data.get('title')
            v_url = video_data.get('url') or video_url
            prompt = build_prompt(transcript_text)
            summary = build_md_header(title=v_title, url=v_url) + modelstack.query(prompt)
            tools.writeText(md_file, summary)
            print(f"  Created {md_file}")
        else:
            print(f"  Cannot create {md_file} - no transcript available")
    else:
        print(f"  {md_file} already exists")


def organize_videos():
    for fn in os.listdir("cache/videos/"):
        if not fn.endswith(".json"):
            continue
        src = f"cache/videos/{fn}"
        j = tools.readJson(src)
        if not j.get('channel_name'):
            continue
        channel_name = j['channel_name']
        dstFolder = f"cache/channels/{channel_name}"
        channel_url = f"https://www.youtube.com/@{channel_name}"
        if not os.path.exists(dstFolder):
            os.makedirs(dstFolder)
        dst = f"{dstFolder}/{fn}"
        # Make a hardlink from src to dst
        if not os.path.exists(dst):
            os.link(src, dst)
        

@app.command()
def pull(url: str = typer.Argument(..., help="YouTube video or channel URL")):
    """Pull transcripts from a YouTube URL."""
    if "youtube.com/" in url or "youtu.be/" in url:
        if "/watch" in url or "youtu.be/" in url:
            pull_video(url)
        else:
            pull_transcripts(url)
    else:
        typer.echo("Invalid YouTube URL")
        raise typer.Exit(1)


@app.command()
def update():
    """Update files to new version."""
    update_all()


@app.command()
def summarize():
    """Summarize all .txt files that don't have a corresponding .md file."""
    summarize_all()


@app.command()
def organize():
    """Organize video transcripts."""
    organize_videos()


@app.command()
def subscriptions():
    """List your YouTube subscriptions."""
    subs = fetch_subscriptions()
    for title, url, description in subs:
        line = f"- [{title}]({url})"
        if description:
            line += f" - {description}"
        typer.echo(line)


def format_date_iso(date_str: str) -> str:
    """Convert date like 'Apr 25, 2026, 9:40:27 PM MST' to 'YYYY-MM-DD'."""
    from datetime import datetime
    # Remove timezone abbreviation (MST, PST, etc.)
    date_str = re.sub(r' [A-Z]{2,4}$', '', date_str)
    try:
        dt = datetime.strptime(date_str, '%b %d, %Y, %I:%M:%S %p')
        return dt.strftime('%Y-%m-%d')
    except ValueError:
        return date_str  # Return original if parsing fails


def parse_search_history(html_content: str) -> list[tuple[str, str]]:
    """Parse search-history.html and return list of (date, search_term) tuples."""
    soup = BeautifulSoup(html_content, 'html.parser')
    results = []

    # Find all content cells with search data
    content_cells = soup.find_all('div', class_='content-cell')

    for cell in content_cells:
        text = cell.get_text()
        if 'Searched for' not in text:
            continue

        # Find the search link
        link = cell.find('a')
        if not link:
            continue

        search_term = link.get_text()
        # Normalize whitespace in search term
        search_term = re.sub(r'\s+', ' ', search_term).strip()

        # Extract the date from the cell text
        # Normalize whitespace (newlines, narrow no-break spaces, etc.)
        cell_text = cell.get_text(separator=' ')
        cell_text = re.sub(r'[\s\u202f]+', ' ', cell_text)  # Normalize all whitespace

        # Date format: "Apr 25, 2026, 9:40:27 PM MST"
        date_match = re.search(r'([A-Z][a-z]{2} \d{1,2}, \d{4}, \d{1,2}:\d{2}:\d{2} [AP]M [A-Z]+)', cell_text)
        if date_match:
            date_str = format_date_iso(date_match.group(1))
            results.append((date_str, search_term))

    return results


def parse_watch_history(html_content: str) -> tuple[list[tuple[str, str, str, str]], dict[str, str]]:
    """
    Parse watch-history.html and return:
    - list of (date, video_title, video_url, channel_name) tuples
    - dict of {channel_name: channel_url} for unique channels
    """
    soup = BeautifulSoup(html_content, 'html.parser')
    results = []
    channels = {}  # channel_name -> channel_url

    # Find all content cells with watch data
    content_cells = soup.find_all('div', class_='content-cell')

    for cell in content_cells:
        text = cell.get_text()
        if 'Watched' not in text:
            continue

        # Find all links in this cell
        links = cell.find_all('a')
        if len(links) < 1:
            continue

        # First link is the video
        video_link = links[0]
        video_url = video_link.get('href', '')
        video_title = video_link.get_text()
        # Normalize whitespace in video title
        video_title = re.sub(r'\s+', ' ', video_title).strip()

        # Skip if not a youtube watch link
        if 'youtube.com/watch' not in video_url:
            continue

        # Second link (if exists) is the channel
        channel_name = None
        channel_url = None
        if len(links) >= 2:
            channel_link = links[1]
            channel_url = channel_link.get('href', '')
            channel_name = channel_link.get_text()
            # Normalize whitespace in channel name
            channel_name = re.sub(r'\s+', ' ', channel_name).strip()

            # Only add if it's a channel link
            if channel_url and 'youtube.com/channel' in channel_url:
                channels[channel_name] = channel_url

        # Extract the date from cell text
        # Normalize whitespace (newlines, narrow no-break spaces, etc.)
        cell_text = cell.get_text(separator=' ')
        cell_text = re.sub(r'[\s\u202f]+', ' ', cell_text)

        date_match = re.search(r'([A-Z][a-z]{2} \d{1,2}, \d{4}, \d{1,2}:\d{2}:\d{2} [AP]M [A-Z]+)', cell_text)
        date_str = format_date_iso(date_match.group(1)) if date_match else ''

        results.append((date_str, video_title, video_url, channel_name))

    return results, channels


@app.command()
def pullhistory(folder_name: str = typer.Argument(..., help="Name of the takeout folder in cache/historyexports/")):
    """Extract YouTube search and watch history from Google Takeout export."""
    base_path = f"cache/historyexports/{folder_name}"

    if not os.path.exists(base_path):
        typer.echo(f"Error: Folder not found: {base_path}")
        raise typer.Exit(1)

    output_file = f"cache/historyexports/{folder_name}.md"
    output_lines = []

    # Process search history
    search_history_path = f"{base_path}/Takeout/YouTube and YouTube Music/history/search-history.html"
    if os.path.exists(search_history_path):
        typer.echo(f"Processing search history: {search_history_path}")
        html_content = tools.readText(search_history_path)
        search_results = parse_search_history(html_content)

        output_lines.append("# Search History")
        output_lines.append("")
        for date_str, search_term in search_results:
            output_lines.append(f"- {date_str} - {search_term}")
        output_lines.append("")
        typer.echo(f"  Found {len(search_results)} search entries")
    else:
        typer.echo(f"Warning: Search history file not found: {search_history_path}")

    # Process watch history
    watch_history_path = f"{base_path}/Takeout/YouTube and YouTube Music/history/watch-history.html"
    if os.path.exists(watch_history_path):
        typer.echo(f"Processing watch history: {watch_history_path}")
        html_content = tools.readText(watch_history_path)
        watch_results, channels = parse_watch_history(html_content)

        output_lines.append("# Watch History")
        output_lines.append("")
        for date_str, video_title, video_url, channel_name in watch_results:
            output_lines.append(f"- [{video_title}]({video_url})")
        output_lines.append("")
        typer.echo(f"  Found {len(watch_results)} watch entries")

        # Add channels section
        output_lines.append("# Channels")
        output_lines.append("")
        for channel_name, channel_url in sorted(channels.items()):
            output_lines.append(f"- [{channel_name}]({channel_url})")
        typer.echo(f"  Found {len(channels)} unique channels")
    else:
        typer.echo(f"Warning: Watch history file not found: {watch_history_path}")

    # Write output file
    tools.writeText(output_file, "\n".join(output_lines))
    typer.echo(f"Output written to: {output_file}")


if __name__ == "__main__":
    app()
