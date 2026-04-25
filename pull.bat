call .venv\Scripts\activate
set "V=%*"
python main.py --pull "%V%"
