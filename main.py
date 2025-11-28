import random
from time import sleep
from youtube_transcript_api import YouTubeTranscriptApi
import yt_dlp
import json
import os
import lib.tools as tools


def get_json_cache(filename, func):
    if os.path.exists(filename):
        return tools.readJson(filename)
    data = func()
    tools.writeJson(filename, data)
    return data


def get_transcript(video_url):
    video_id = video_url.split("v=")[1]
    ytt_api = YouTubeTranscriptApi()
    transcript = ytt_api.fetch(video_id)
    return transcript.to_raw_data()


def get_transcript_string(video_url):
    def func():
        j = get_transcript(video_url)
        s = " ".join([item['text'] for item in j]).replace(".", "\n")
        return s
    return get_json_cache(f"transcript_{tools.md5(video_url)}.json", func)

def all_videos(channel_url):
    options = {
        'quiet': True,
        'extract_flat': True,        # True = Faster, gets metadata without downloading
        'skip_download': True,
        'force_generic_extractor': False,
    }

    with yt_dlp.YoutubeDL(options) as ydl:
        def func():
            # This automatically handles @handle, /channel/, /c/, /user/, etc.
            info = ydl.extract_info(channel_url, download=False)
            return info
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
                "channel_id": entry.get('channel_id'),
                "channel_url": entry.get('channel_url')
            }

            yield video


def compile_transcripts(videos):
    fn = tools.clean_filename(channel_url)
    fn = f"cache/{fn}.json"
    videos = tools.readJson(fn)
    with open(f"cache/output.txt", "w") as f:
        for video in videos['entries']:
            fn = video['id']
            fn = f"cache/transcripts/{fn}.json"
            if not os.path.exists(fn):
                continue
            v = tools.readJson(fn)
            f.write("-" * 100 + "\n")
            f.write(f"Title: {video['title']}\n")
            f.write(f"Transcript: {v['transcript']}\n\n\n")
        

def pull_transcripts(channel_url):
    fn = tools.clean_filename(channel_url)
    fn = f"cache/{fn}.json"
    videos = tools.readJson(fn)
    for video in videos['entries']:
        def func():
            v = video.copy()
            v['transcript'] = get_transcript_string(video['url'])
            sleep(random.randint(30, 60))
            return v
        fn = video['id']
        fn = f"cache/transcripts/{fn}.json"
        if os.path.exists(fn):
            continue
        print(video['title'])
        v = get_json_cache(fn, func)
        pass

if __name__ == "__main__":
    channel_url = "https://www.youtube.com/@PrometheanAction/videos"
    pull_transcripts(channel_url)
    #compile_transcripts(channel_url)
