import random
from time import sleep
from youtube_transcript_api import YouTubeTranscriptApi
import yt_dlp
import json
import os
from lib.modelstack import ModelStack
import lib.tools as tools


fromSeconds, toSeconds = 30, 60


config = {
    'class': 'ollama',  
    'host':'http://localhost:11434',
    'model': 'tinyllama:1.1b'
}
modelstack = ModelStack.from_config(config)
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
    video_id = video_url.split("v=")[1]
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
        prompt = f"Summarize the following YouTube video transcript in a concise paragraph:\n\n{j['transcript']}"
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


def update():
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


def summarize():
    for fn in os.listdir("cache/summaries/"):
        pass # ???

            
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
    - cache/summaries/{video_id}.json - video metadata
    - cache/summaries/{video_id}.txt - transcript
    - cache/summaries/{video_id}.md - summary
    """
    video_id = extract_video_id(video_url)
    if not video_id:
        print(f"Could not extract video ID from: {video_url}")
        return

    # Ensure cache/summaries folder exists
    os.makedirs("cache/summaries", exist_ok=True)

    json_file = f"cache/summaries/{video_id}.json"
    txt_file = f"cache/summaries/{video_id}.txt"
    md_file = f"cache/summaries/{video_id}.md"

    # Step 1: Pull metadata if json doesn't exist
    if not os.path.exists(json_file):
        print(f"Pulling metadata for {video_id}...")
        options = {
            'quiet': True,
            'extract_flat': True,
            'skip_download': True,
            'force_generic_extractor': False,
        }
        with yt_dlp.YoutubeDL(options) as ydl:
            info = ydl.extract_info(video_url, download=False)
            tools.writeJson(json_file, info)
            print(f"  Created {json_file}")
    else:
        print(f"  {json_file} already exists")

    # Step 2: Pull transcript if txt doesn't exist
    if not os.path.exists(txt_file):
        print(f"Pulling transcript for {video_id}...")
        transcript = get_transcript(video_url)
        if transcript:
            text = " ".join([item['text'] for item in transcript]).strip()
            text = text.replace(".", ".\n")
            text = "\n".join([line.strip() for line in text.splitlines()])
            tools.writeText(txt_file, text)
            print(f"  Created {txt_file}")
        else:
            print(f"  No transcript available for {video_id}")
    else:
        print(f"  {txt_file} already exists")

    # Step 3: Summarize if md doesn't exist (requires txt to exist)
    if not os.path.exists(md_file):
        if os.path.exists(txt_file):
            print(f"Summarizing transcript for {video_id}...")
            transcript_text = tools.readText(txt_file)
            prompt = f"Summarize the main points of the following YouTube video transcript:\n\n{transcript_text}"
            summary = modelstack.query(prompt)
            tools.writeText(md_file, summary)
            print(f"  Created {md_file}")
        else:
            print(f"  Cannot create {md_file} - no transcript available")
    else:
        print(f"  {md_file} already exists")


def organize():
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
        

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("-p", "--pull", help="Pull transcripts from url")
    parser.add_argument("-u", "--update", help="Update files to new version", action="store_true")
    parser.add_argument("-s", "--summarize", help="Summarize video transcripts", action="store_true")
    parser.add_argument("-o", "--organize", help="Organize video transcripts", action="store_true")
    
    args = parser.parse_args()

    if args.pull:
        url = args.pull
        if "youtube.com/" in url or "youtu.be/" in url:
            if "/watch" in url or "youtu.be/" in url:
                pull_video(url)
            else:
                pull_transcripts(url)
    elif args.update:
        update()
    elif args.summarize:
        summarize()
    elif args.organize:
        organize()
    else:
        print("Please provide a channel URL or a single video URL with the --channel or --video parameter")
    #compile_transcripts(channel_url)
