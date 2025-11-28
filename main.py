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
        fn = f"cache/videos/{fn}.json"
        if os.path.exists(fn):
            continue
        print(video['title'])
        v = get_json_cache(fn, func)
        pass


def pull_transcript(video_url):
    fn = video_url.split("v=")[1]
    fnBase = f"cache/videos/{fn}"
    fn = f"{fnBase}.json"
    if os.path.exists(fn):
        return
    print(video_url)

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
            tools.writeText(f"{fnBase}.txt", f"""
Id: {v['id']}
Title: {v['title']}
Category: {', '.join(v.get('categories', []))}
Tags: {', '.join(v.get('tags', []))}
Transcript: {v['transcript']}
""".strip())
            return v
        
    v = get_json_cache(fn, func)


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("-p", "--pull", help="Pull transcripts from url")
    parser.add_argument("-c", "--channel", help="Youtube channel url")
    parser.add_argument("-v", "--video", help="A single video url")

    args = parser.parse_args()
    if args.pull:
        url = args.pull
        if "youtube.com/" in url and "/watch" in url:
            pull_transcript(url)
        else:
            pull_transcripts(url)
    else:
        raise ValueError("Please provide a channel URL or a single video URL with the --channel or --video parameter")
    #compile_transcripts(channel_url)
