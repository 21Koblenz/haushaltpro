from pathlib import Path
root=Path(__file__).resolve().parents[1]
html=(root/"static/index.html").read_text()
js=(root/"static/app.js").read_text()
main=(root/"app/main.py").read_text()
assert 'id="balanceHelp"' in html
assert 'Stand bis heute' in js
assert 'derselbe Kalendertag wie heute' in js
assert 'd.cutoff' in js
assert ('APP_VERSION = "0.10.5"' in main) or (('APP_VERSION = "0.11.1"' in main) or (('APP_VERSION = "0.21.0"' in main or 'APP_VERSION = "0.21.2"' in main or 'APP_VERSION = "0.21.3"' in main)))
print("v0.10.5 dashboard cutoff explanation: PASS")
