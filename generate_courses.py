"""
CEI Course Material Generator
==============================
Searches YouTube for 10 videos per course, pulls transcripts, generates
entrepreneur-focused summaries, and builds course markdown documents.

Usage (from youtube-tools directory):
    uv run generate_courses.py

Output:
    C:/Users/rob/OneDrive/.../odin/videos/{video_id}.txt   -- transcript
    C:/Users/rob/OneDrive/.../odin/videos/{video_id}.md    -- entrepreneur summary
    C:/Users/rob/OneDrive/.../odin/courses/Course-N.md     -- course document
    C:/Users/rob/OneDrive/.../odin/courses/journey.md      -- master index
"""

import os
import sys
import time
import random
import subprocess
from pathlib import Path

from dotenv import load_dotenv
from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build

import lib.tools as tools
from lib.modelstack import ModelStack

load_dotenv()

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------

TOOLS_DIR   = Path(__file__).parent
ODIN_DIR    = Path("C:/Users/rob/OneDrive/Business/DuppaSwilling/CEI/cei-jeff-michelle/odin")
VIDEOS_DIR  = ODIN_DIR  / "videos"
COURSES_DIR = ODIN_DIR  / "courses"
SEARCHES_DIR = TOOLS_DIR / "cache" / "searches"
SUMMARIES_DIR = TOOLS_DIR / "cache" / "summaries"

for d in [VIDEOS_DIR, COURSES_DIR, SEARCHES_DIR]:
    d.mkdir(parents=True, exist_ok=True)

# ---------------------------------------------------------------------------
# Config and model
# ---------------------------------------------------------------------------

cfg = tools.getYaml("config")
modelstack = ModelStack.from_config(cfg["modelstack"])

# ---------------------------------------------------------------------------
# CEI curriculum
# ---------------------------------------------------------------------------

PATHWAYS = [
    (1, "Company Foundation", [
        (0,  "Competency Assessment"),
        (1,  "Company Formation & Legal Setup"),
        (2,  "Intellectual Property Strategy"),
        (3,  "Ownership & Founder Agreements"),
        (4,  "Founder Operations"),
    ]),
    (2, "Business Validation", [
        (5,  "Market & Competitive Analysis"),
        (6,  "Customer Discovery"),
        (7,  "Validation Strategy"),
        (8,  "Value Proposition & Positioning"),
        (9,  "Business Model Development"),
        (10, "Business Planning & Forecasting"),
        (11, "Pitch Development & Storytelling"),
    ]),
    (3, "Product Development", [
        (12, "Product Strategy"),
        (13, "Prototype Development & Testing"),
        (14, "Technical & Commercial Validation"),
        (15, "Product Documentation"),
        (16, "Regulatory & Compliance Basics"),
        (17, "Medical Device Regulatory Pathway"),
        (18, "Therapeutics & Biologics Regulatory Pathway"),
        (19, "Diagnostics & Laboratory Testing Regulatory Pathway"),
    ]),
    (4, "Operations & Execution", [
        (20, "Organizational Design"),
        (21, "Systems & Documentation"),
        (22, "Operational Excellence"),
        (23, "Business Scaling Decisions"),
    ]),
    (5, "Manufacturing & Supply Chain", [
        (24, "Manufacturing Strategy"),
        (25, "Packaging & Inventory"),
        (26, "Logistics & Distribution"),
        (27, "Vendor & Supply Chain Management"),
        (28, "Production Operations"),
    ]),
    (6, "Finance & Funding", [
        (29, "Financial Planning & Management"),
        (30, "Accounting Systems"),
        (31, "Capital Strategy"),
        (32, "SBIR/STTR & Non-Dilutive Funding"),
        (33, "Investor Readiness"),
        (34, "Banking & Financial Infrastructure"),
    ]),
    (7, "Sales, Marketing & Growth", [
        (35, "Brand Positioning & Messaging"),
        (36, "Marketing Systems"),
        (37, "Market Visibility & PR"),
        (38, "Partnerships & Business Development"),
        (39, "Sales Execution"),
    ]),
    (8, "Team, Leadership & Governance", [
        (40, "Hiring & Team Development"),
        (41, "HR Systems & Compliance"),
        (42, "Employee Management"),
        (43, "Leadership & Culture"),
        (44, "Boards & Advisors"),
    ]),
]

WAIT_SECONDS = (30, 60)  # randomized wait between youtube-tools pull calls

# ---------------------------------------------------------------------------
# YouTube API
# ---------------------------------------------------------------------------

def get_youtube_service():
    client_id     = os.environ["YOUTUBE_CLIENT_ID"]
    client_secret = os.environ["YOUTUBE_CLIENT_SECRET"]
    scopes        = ["https://www.googleapis.com/auth/youtube.readonly"]
    token_file    = str(TOOLS_DIR / "cache" / "youtube_token.json")

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
        tools.writeText(token_file, creds.to_json())

    return build("youtube", "v3", credentials=creds)


def search_videos(service, course_num, course_title, pathway_name, max_results=10):
    """Search YouTube and return list of video dicts. Results cached per course."""
    cache_file = SEARCHES_DIR / f"course_{course_num:02d}.json"
    if cache_file.exists():
        videos = tools.readJson(str(cache_file))
        print(f"    [cached search] {len(videos)} videos")
        return videos

    # Build a context-aware query
    if pathway_name == "Product Development" and course_num >= 17:
        query = f"{course_title} FDA startup regulatory"
    elif "SBIR" in course_title or "STTR" in course_title:
        query = f"{course_title} small business grant funding"
    else:
        query = f"{course_title} entrepreneur startup business"

    print(f"    Searching: \"{query}\"")
    response = service.search().list(
        q=query,
        part="snippet",
        type="video",
        maxResults=max_results,
        order="relevance",
        relevanceLanguage="en",
        videoCaption="closedCaption",
    ).execute()

    videos = []
    for item in response.get("items", []):
        video_id = item["id"]["videoId"]
        videos.append({
            "id":      video_id,
            "title":   item["snippet"]["title"],
            "channel": item["snippet"]["channelTitle"],
            "url":     f"https://www.youtube.com/watch?v={video_id}",
        })

    tools.writeJson(str(cache_file), videos)
    print(f"    Found {len(videos)} videos")
    return videos

# ---------------------------------------------------------------------------
# Transcript pull
# ---------------------------------------------------------------------------

def pull_video_transcript(url):
    """Call youtube-tools CLI to pull a single video. Returns True on success."""
    result = subprocess.run(
        ["uv", "run", "main.py", "pull", url],
        capture_output=True,
        text=True,
        encoding="utf-8",
        cwd=str(TOOLS_DIR),
    )
    if result.stdout:
        print("      " + result.stdout.strip().replace("\n", "\n      "))
    if result.returncode != 0:
        print(f"      ERROR: {result.stderr[:300]}")
        return False
    return True

# ---------------------------------------------------------------------------
# Summary generation
# ---------------------------------------------------------------------------

ENTREPRENEUR_PROMPT = """\
You are a curriculum designer for the Center for Entrepreneurial Innovation (CEI) \
at Gateway Community College in Arizona. You build learning materials for adult entrepreneurs \
who are launching new businesses over an 18-month program.

The video "{video_title}" covers "{course_title}", which belongs to the "{pathway_name}" \
pathway. Write a structured markdown summary of the transcript below.

Your summary must include:

**Why Watch This** (2-3 sentences): Explain why this video matters to a new entrepreneur \
and how it fits their 18-month journey of launching a business.

**Key Concepts** (5-7 bullet points): Bold the concept name, then one sentence on \
why it matters to an entrepreneur starting out.

**Why This Matters** (2-3 sentences): Connect this topic to real decisions the entrepreneur \
will face in their first 18 months.

Rules: plain language, no unexplained jargon, direct voice, no filler phrases like \
"it is important to note" or "furthermore".

Transcript:
{transcript}
"""

OVERVIEW_PROMPT = """\
Write a 3-sentence course overview for a CEI (Center for Entrepreneurial Innovation) course.

Course: "{course_title}"
Pathway: "{pathway_name}"
Audience: Adult entrepreneurs launching a new business over 18 months at \
Gateway Community College in Arizona.

Cover: (1) what this course is about, (2) why it matters at this stage of building a business, \
(3) what the entrepreneur can do after completing it.

Direct voice. No filler phrases. No hedging.
"""

BRIEF_PROMPT = """\
In one sentence of 20 words or fewer, state why "{course_title}" is essential to an \
entrepreneur building a new business. Be specific and direct.
"""


def generate_entrepreneur_summary(transcript, video_title, course_title, pathway_name):
    prompt = ENTREPRENEUR_PROMPT.format(
        video_title=video_title,
        course_title=course_title,
        pathway_name=pathway_name,
        transcript=transcript[:8000],
    )
    return modelstack.query(prompt)


def generate_course_overview(course_title, pathway_name):
    prompt = OVERVIEW_PROMPT.format(course_title=course_title, pathway_name=pathway_name)
    return modelstack.query(prompt)


def generate_course_brief(course_title):
    prompt = BRIEF_PROMPT.format(course_title=course_title)
    return modelstack.query(prompt).strip().split("\n")[0]

# ---------------------------------------------------------------------------
# Per-video processing
# ---------------------------------------------------------------------------

def process_video(video, course_title, pathway_name):
    """
    Pull transcript and write odin/videos/{id}.txt and odin/videos/{id}.md.
    Returns (video_id, title, url) on success, None on failure.
    """
    video_id = video["id"]
    out_txt   = VIDEOS_DIR / f"{video_id}.txt"
    out_md    = VIDEOS_DIR / f"{video_id}.md"

    if out_txt.exists() and out_md.exists():
        print(f"    [skip] {video_id} already in odin/videos/")
        return video

    cache_txt = SUMMARIES_DIR / f"{video_id}.txt"

    # Pull from YouTube if not yet cached in youtube-tools
    if not cache_txt.exists():
        print(f"    Pulling {video_id}: {video['title'][:60]}")
        ok = pull_video_transcript(video["url"])
        if not ok:
            return None
        wait = random.randint(*WAIT_SECONDS)
        print(f"    Waiting {wait}s before next pull...")
        time.sleep(wait)
    else:
        print(f"    [cached] {video_id}")

    # Read transcript
    if not cache_txt.exists():
        print(f"    [no transcript] {video_id}")
        return None

    transcript = cache_txt.read_text(encoding="utf-8")

    # Write transcript to odin/videos/
    if not out_txt.exists():
        out_txt.write_text(transcript, encoding="utf-8")

    # Generate and write entrepreneur summary to odin/videos/
    if not out_md.exists():
        print(f"    Summarizing {video_id}...")
        summary = generate_entrepreneur_summary(
            transcript, video["title"], course_title, pathway_name
        )
        header = (
            f"- Title: {video['title']}\n"
            f"- URL: {video['url']}\n"
            f"- Course: {course_title}\n"
            f"- Pathway: {pathway_name}\n\n"
        )
        out_md.write_text(header + summary, encoding="utf-8")

    return video

# ---------------------------------------------------------------------------
# Course document
# ---------------------------------------------------------------------------

def generate_course_doc(course_num, course_title, pathway_num, pathway_name, processed_videos):
    out_file = COURSES_DIR / f"Course-{course_num}.md"
    if out_file.exists():
        print(f"  [skip] {out_file.name} already exists")
        return

    print(f"  Building {out_file.name}...")
    overview = generate_course_overview(course_title, pathway_name)

    lines = [
        f"# Course {course_num}: {course_title}",
        "",
        f"**Pathway {pathway_num}: {pathway_name}**",
        "",
        "## Overview",
        "",
        overview.strip(),
        "",
        "---",
        "",
        "## Videos",
        "",
    ]

    for i, video in enumerate(processed_videos, 1):
        if video is None:
            continue
        video_id = video["id"]
        md_path  = VIDEOS_DIR / f"{video_id}.md"
        link     = f"[{video['title']}]({video['url']})"

        lines.append(f"### {i}. {link}")
        lines.append("")

        if md_path.exists():
            lines.append(md_path.read_text(encoding="utf-8").strip())
        else:
            lines.append("*(Transcript not available for this video.)*")

        lines.append("")
        lines.append("---")
        lines.append("")

    out_file.write_text("\n".join(lines), encoding="utf-8")
    print(f"  Created {out_file.name}")

# ---------------------------------------------------------------------------
# Journey index
# ---------------------------------------------------------------------------

def generate_journey_doc():
    out_file = COURSES_DIR / "journey.md"

    lines = [
        "# CEI Client Program — Learning Journey",
        "",
        "A guided map through all 45 courses across 8 pathways of the Gateway Community College",
        "Center for Entrepreneurial Innovation program.",
        "Each course builds toward launching a viable business within 18 months.",
        "",
    ]

    for pathway_num, pathway_name, courses in PATHWAYS:
        lines.append(f"## Pathway {pathway_num}: {pathway_name}")
        lines.append("")
        for course_num, course_title in courses:
            course_file = f"Course-{course_num}.md"
            course_path = COURSES_DIR / course_file
            brief = generate_course_brief(course_title)
            if course_path.exists():
                lines.append(f"- [Course {course_num}: {course_title}]({course_file}) — {brief}")
            else:
                lines.append(f"- Course {course_num}: {course_title} *(not generated)* — {brief}")
        lines.append("")

    out_file.write_text("\n".join(lines), encoding="utf-8")
    print(f"Created {out_file}")

# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    print("=" * 70)
    print("CEI Course Material Generator")
    print(f"Output: {ODIN_DIR}")
    print("=" * 70)

    # Verify Ollama is reachable before starting the long run
    try:
        test = modelstack.query("Reply with the single word: ready")
        if "ready" not in test.lower():
            print(f"WARNING: LLM responded unexpectedly: {test[:100]}")
        else:
            print("LLM: OK")
    except Exception as e:
        print(f"ERROR: Cannot reach LLM (Ollama): {e}")
        print("Start Ollama and re-run.")
        sys.exit(1)

    youtube = get_youtube_service()
    print("YouTube API: OK")
    print()

    total_courses = sum(len(cs) for _, _, cs in PATHWAYS)
    done = 0

    for pathway_num, pathway_name, courses in PATHWAYS:
        print(f"\n{'='*60}")
        print(f"Pathway {pathway_num}: {pathway_name}")
        print(f"{'='*60}")

        for course_num, course_title in courses:
            done += 1
            print(f"\n[{done}/{total_courses}] Course {course_num}: {course_title}")

            # 1. Search
            videos = search_videos(youtube, course_num, course_title, pathway_name, max_results=10)

            # 2. Pull and summarize each video
            processed = []
            for video in videos:
                result = process_video(video, course_title, pathway_name)
                processed.append(result)

            # 3. Build course document
            generate_course_doc(course_num, course_title, pathway_num, pathway_name, processed)

    # 4. Build journey index
    print("\n" + "=" * 60)
    print("Building journey.md...")
    generate_journey_doc()

    print("\n" + "=" * 70)
    print("Done.")
    print(f"Courses: {COURSES_DIR}")
    print(f"Videos:  {VIDEOS_DIR}")
    print("=" * 70)


if __name__ == "__main__":
    main()
