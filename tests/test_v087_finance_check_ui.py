from pathlib import Path
root=Path(__file__).resolve().parents[1]
html=(root/'static/index.html').read_text()
css=(root/'static/style.css').read_text()
js=(root/'static/app.js').read_text()
main=(root/'app/main.py').read_text()
assert ('APP_VERSION = "0.8.7"' in main) or (('APP_VERSION = "0.9.0"' in main) or (('APP_VERSION = "0.10.0"' in main) or (('APP_VERSION = "0.10.1"' in main) or (('APP_VERSION = "0.10.2"' in main) or ('APP_VERSION = "0.10.3"' in main))))) or ('APP_VERSION = "0.10.4"' in main) or (('APP_VERSION = "0.10.5"' in main) or (('APP_VERSION = "0.11.1"' in main) or (('APP_VERSION = "0.21.0"' in main or 'APP_VERSION = "0.21.2"' in main or ('APP_VERSION = "0.21.3"' in main or ('APP_VERSION = "0.21.4"' in main or ('APP_VERSION = "0.21.5"' in main or ('APP_VERSION = "0.21.6"' in main or ('APP_VERSION = "0.21.8"' in main or 'APP_VERSION = "0.21.9-dev.5"' in main)))))))))
assert 'finance-check-summary' in html
assert 'finance-check-results' in html
assert '<h2>Prüfergebnisse</h2>' in html
assert '#view-finance-check .finance-check-summary' in css
assert 'margin-bottom:20px' in css
assert '.finance-check-row' in css
assert '.finance-check-badge-ok' in css
assert '.finance-check-code' in css
assert "statusLabel=level=>level==='ok'?'OK':level==='warning'?'Hinweis':'Fehler'" in js
assert 'finance-check-badge' in js
print('v0.8.7 finance-check UI: PASS')
