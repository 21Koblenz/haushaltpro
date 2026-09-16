from pathlib import Path
root=Path(__file__).resolve().parents[1]
html=(root/'static/index.html').read_text()
css=(root/'static/style.css').read_text()
main=(root/'app/main.py').read_text()
assert (('APP_VERSION = "0.11.1"' in main) or (('APP_VERSION = "0.21.0"' in main or 'APP_VERSION = "0.21.2"' in main or ('APP_VERSION = "0.21.3"' in main or ('APP_VERSION = "0.21.4"' in main or ('APP_VERSION = "0.21.5"' in main or ('APP_VERSION = "0.21.6"' in main or ('APP_VERSION = "0.21.8"' in main or 'APP_VERSION = "0.21.9-dev.3"' in main)))))))) or (('APP_VERSION = "0.21.0"' in main or 'APP_VERSION = "0.21.2"' in main or ('APP_VERSION = "0.21.3"' in main or ('APP_VERSION = "0.21.4"' in main or ('APP_VERSION = "0.21.5"' in main or ('APP_VERSION = "0.21.6"' in main or ('APP_VERSION = "0.21.8"' in main or 'APP_VERSION = "0.21.9-dev.3"' in main)))))))
assert 'panel table-wrap investment-table-panel' in html
assert '#view-investments > .hero-grid{margin-bottom:20px}' in css
assert '#view-investments > .investment-table-panel{margin-top:0}' in css
assert '@media(max-width:800px){#view-investments > .hero-grid{margin-bottom:16px}}' in css
print('v0.11.1 investment layout spacing: PASS')
