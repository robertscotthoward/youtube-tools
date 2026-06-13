# Subscriptions Command Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a `subscriptions` CLI command that authenticates with the YouTube Data API v3 via OAuth2 and prints all of the user's subscriptions as a markdown list to the terminal.

**Architecture:** Read OAuth2 credentials from `config.yaml` (`youtube.client_id`, `youtube.client_secret`, `youtube.scopes`). On first run, open a browser for consent and cache the token to `cache/youtube_token.json`. On subsequent runs, load and auto-refresh the cached token. Fetch all subscription pages and print a sorted markdown list.

**Tech Stack:** `google-api-python-client`, `google-auth-oauthlib`, `typer`, existing `tools.getYaml`

---

### Task 1: Add dependencies

**Files:**
- Modify: `pyproject.toml`

- [ ] **Step 1: Add Google API dependencies**

Edit `pyproject.toml` dependencies list to add:

```toml
    "google-api-python-client>=2.154.0",
    "google-auth-oauthlib>=1.2.1",
```

The full dependencies block should look like:

```toml
dependencies = [
    "youtube-transcript-api>=1.2.3",
    "scrapetube>=2.5.1",
    "yt-dlp>=2025.11.12",
    "ruamel-yaml>=0.18.16",
    "pyyaml>=6.0.3",
    "boto3>=1.41.5",
    "typer>=0.24.2",
    "beautifulsoup4>=4.14.3",
    "google-api-python-client>=2.154.0",
    "google-auth-oauthlib>=1.2.1",
]
```

- [ ] **Step 2: Install dependencies**

Run: `uv sync`
Expected: packages resolved and installed with no errors.

- [ ] **Step 3: Commit**

```bash
git add pyproject.toml uv.lock
git commit -m "feat: add google-api-python-client and google-auth-oauthlib dependencies"
```

---

### Task 2: Implement the subscriptions command

**Files:**
- Modify: `main.py`

- [ ] **Step 1: Add imports at the top of main.py**

After the existing imports block (after `import lib.tools as tools`), add:

```python
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request
from googleapiclient.discovery import build
```

- [ ] **Step 2: Add the auth helper function**

Add this function after the `build_prompt` function (around line 36):

```python
def get_youtube_service():
    yt_cfg = cfg['youtube']
    client_id = yt_cfg['client_id']
    client_secret = yt_cfg['client_secret']
    scopes = yt_cfg['scopes']
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
```

- [ ] **Step 3: Add the fetch subscriptions function**

Add this function immediately after `get_youtube_service`:

```python
def fetch_subscriptions():
    service = get_youtube_service()
    subscriptions = []
    next_page_token = None

    while True:
        request = service.subscriptions().list(
            part='snippet',
            mine=True,
            maxResults=50,
            pageToken=next_page_token,
            order='alphabetical',
        )
        response = request.execute()

        for item in response.get('items', []):
            snippet = item['snippet']
            title = snippet['title']
            resource_id = snippet['resourceId']
            channel_id = resource_id['channelId']

            # Resolve @handle via channels.list
            ch_response = service.channels().list(
                part='snippet',
                id=channel_id,
            ).execute()
            ch_items = ch_response.get('items', [])
            if ch_items:
                custom_url = ch_items[0]['snippet'].get('customUrl')
                if custom_url:
                    url = f"https://www.youtube.com/{custom_url}"
                else:
                    url = f"https://www.youtube.com/channel/{channel_id}"
            else:
                url = f"https://www.youtube.com/channel/{channel_id}"

            subscriptions.append((title, url))

        next_page_token = response.get('nextPageToken')
        if not next_page_token:
            break

    return sorted(subscriptions, key=lambda x: x[0].lower())
```

- [ ] **Step 4: Add the CLI command**

Add this command after the `organize` command (after line 508):

```python
@app.command()
def subscriptions():
    """List your YouTube subscriptions."""
    subs = fetch_subscriptions()
    for title, url in subs:
        typer.echo(f"- [{title}]({url})")
```

- [ ] **Step 5: Verify the command appears in help**

Run: `uv run main.py --help`
Expected: `subscriptions` appears in the Commands list.

- [ ] **Step 6: Commit**

```bash
git add main.py
git commit -m "feat: add subscriptions command using YouTube Data API v3 OAuth2"
```

---

### Task 3: Manual verification

- [ ] **Step 1: Run the subscriptions command**

Run: `uv run main.py subscriptions`

Expected on first run: a browser window opens for Google OAuth consent. After approving, the terminal prints a markdown list like:
```
- [America Uncovered](https://www.youtube.com/@AmericaUncovered)
- [Bill Whittle](https://www.youtube.com/@BillWhittleChannel)
...
```

- [ ] **Step 2: Verify token cached**

Run: `ls cache/youtube_token.json`
Expected: file exists.

- [ ] **Step 3: Run again to verify no re-auth**

Run: `uv run main.py subscriptions`
Expected: no browser opens; list prints immediately.
