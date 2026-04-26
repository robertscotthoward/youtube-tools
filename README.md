# Usage
```
python main.py pull https://www.youtube.com/watch?v=n2a1FfqjHcU
```
"n2a1FfqjHcU" is the video ID.
If "n2a1FfqjHcU.json" does not exists, then pull it.
If "n2a1FfqjHcU.txt" does not exists, then pull the transcript.
If "n2a1FfqjHcU.md" does not exists, then summarize the main points of the txt file transcript.
The files should be saved under cache\summaries


# Requirements
Create a new command so that this:
python main.py pullhistory takeout-20260426T184923Z-3-001
will find the folder cache\historyexports\takeout-20260426T184923Z-3-001

then find the file:
`cache\historyexports\takeout-20260426T184923Z-3-001\Takeout\YouTube and YouTube Music\history\search-history.html`
find all the search terms and create markdown output file named `cache\historyexports\takeout-20260426T184923Z-3-001.md`
and add the header `# Search History`

For example, there is a list of search DIV tags like this example:
```html
    <div class="outer-cell mdl-cell mdl-cell--12-col mdl-shadow--2dp">
      <div class="mdl-grid">
        <div class="header-cell mdl-cell mdl-cell--12-col">
          <p class="mdl-typography--title">YouTube<br></p>
        </div>
        <div class="content-cell mdl-cell mdl-cell--6-col mdl-typography--body-1">Searched for <a
            href="https://www.youtube.com/results?search_query=how+to+get++Polar%2B+minecraft">how to get Polar+
            minecraft</a><br>Mar 5, 2026, 9:36:36 AM MST<br></div>
        <div class="content-cell mdl-cell mdl-cell--6-col mdl-typography--body-1 mdl-typography--text-right"></div>
        <div class="content-cell mdl-cell mdl-cell--12-col mdl-typography--caption">
          <b>Products:</b><br>&emsp;YouTube<br><b>Why is this here?</b><br>&emsp;This activity was saved to your Google
          Account because the following settings were on:&nbsp;YouTube search history.&nbsp;You can control these
          settings &nbsp;<a href="https://myaccount.google.com/activitycontrols">here</a>.</div>
      </div>
    </div>
```

So generate a bullet line in markdown output file like this:
```
- Mar 5, 2026, 9:36:36 AM MST - how to get Polar+ minecraft
```

When that is completed, find the file `cache\historyexports\takeout-20260426T184923Z-3-001\Takeout\YouTube and YouTube Music\history\watch-history.html`, append a `# Watch History` line to the markdown output file, then for each entry create a bullet list of the video watched and the channel. 
Accumulate a list of channels.

For example, if this item exists:

```html
    <div class="outer-cell mdl-cell mdl-cell--12-col mdl-shadow--2dp">
      <div class="mdl-grid">
        <div class="header-cell mdl-cell mdl-cell--12-col">
          <p class="mdl-typography--title">YouTube<br></p>
        </div>
        <div class="content-cell mdl-cell mdl-cell--6-col mdl-typography--body-1">Watched <a
            href="https://www.youtube.com/watch?v=3JXnY2mTQs8">Is It Bad To Never Restart Your PC?</a><br><a
            href="https://www.youtube.com/channel/UCiKNvzMjBFowg5Sj6pevymA">META PCs</a><br>Jan 26, 2026, 6:50:59 PM
          MST<br></div>
        <div class="content-cell mdl-cell mdl-cell--6-col mdl-typography--body-1 mdl-typography--text-right"></div>
        <div class="content-cell mdl-cell mdl-cell--12-col mdl-typography--caption">
          <b>Products:</b><br>&emsp;YouTube<br><b>Why is this here?</b><br>&emsp;This activity was saved to your Google
          Account because the following settings were on:&nbsp;YouTube watch history.&nbsp;You can control these
          settings &nbsp;<a href="https://myaccount.google.com/activitycontrols">here</a>.</div>
      </div>
    </div>
```

then write this line:
```
- [Is It Bad To Never Restart Your PC?](https://www.youtube.com/watch?v=3JXnY2mTQs8)
```

Then after completed, take the list of accumulated channels and append to the markdown output file this section and channels after:
```
# Channels
- [META PCs](https://www.youtube.com/channel/UCiKNvzMjBFowg5Sj6pevymA)
- ...
```


# Updates
```
uv add --upgrade youtube-transcript-api
```



# UV Template

Use this process to create new Python projects in a convenient manner, such that:
* A virtual environment is created with the powerful [uv](https://docs.astral.sh/uv/guides/tools/)
* Fast: very fast virtual environment creations, dependency installation, re-creations


# Global Environment

## uv
If you want all your projects to be on D drive, then create environment variable: UV_CACHE_DIR=D:\uv
This makes all your projects on D drive use hard links for libraries, which is very fast.


Install `uv`, e.g. scoop, pip, pipx, etc. Verify with `uv --help`


# New Project
You want to create a brand new uv-driven python project "Project1" that uses git.
Here are some good reproducible steps to make a good project.

```
:: IF LOCAL THEN
md Project1
cd Project1
git init
:: ELSE
:: Create the "Project1" repo in Github
:: git clone the repo
cd Project1
:: END


uv init --python 3.10
:: Or just `uv init` to use the latest version of Python. 3.10 tends to be more AI stable.

:: To explicitly create the venv, but uv add PACKAGE does this automatically if venv does not exist.
uv venv .venv



.venv\Scripts\activate
python -m ensurepip --upgrade
python -m pip install --upgrade pip
```

## Specific Scenario

Here's an example from the command line for creating a new local project.
```
md Project1
cd Project1
copy D:\github\zinclusive\tech\python\uv-template
git init
uv init --python 3.10
uv add requests pyyaml pandas
.venv\Scripts\activate
python -m ensurepip --upgrade
python -m pip install --upgrade pip
code .
```

# Copy all the "bat" files into project folder

These bat files are convenient. Here's what they do:
* `activate` - from terminal, quickly activate the virtual environment
* `deactivate` - from terminal, quickly deactivate the virtual environment
* `dev-cmd` - activates the environment, then starts a terminal
* `dev-cursor` - activates the environment, starts a terminal, then starts Cursor
* `dev` - activates the environment, starts a terminal, then starts VS Code
* `reset-venv` - deletes the entire .venv folder, runs sync, and installs pip. Do this if you change python versions.

# Change Python Version

If you want to change the underlying python runtime:

* Change the version in `pyproject.toml` and `.python-version`.
* Run:
```
rm -rf .venv
uv sync
call .venv\Scripts\activate
python -m ensurepip --upgrade
python -m pip install --upgrade pip
```
