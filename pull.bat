call .venv\Scripts\activate
set "V=%*"
uv run main.py pull "%V%"
