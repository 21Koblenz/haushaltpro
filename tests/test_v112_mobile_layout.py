from pathlib import Path
root=Path(__file__).resolve().parents[1]
css=(root/'static/style.css').read_text()
html=(root/'static/index.html').read_text()
js=(root/'static/app.js').read_text()
main=(root/'app/main.py').read_text()
assert ('APP_VERSION = "0.21.0"' in main or 'APP_VERSION = "0.21.2"' in main or ('APP_VERSION = "0.21.3"' in main or ('APP_VERSION = "0.21.4"' in main or ('APP_VERSION = "0.21.5"' in main or ('APP_VERSION = "0.21.6"' in main or 'APP_VERSION = "0.21.8"' in main)))))
assert 'id="mobileNavToggle"' in html and 'id="mainNav"' in html
assert 'function setMobileNav(open)' in js and "setMobileNav(false)" in js
assert '.panel.table-wrap' in css and 'overflow-x:auto' in css
assert '#view-transactions tbody tr' in css and 'grid-template-columns:minmax(0,1fr) minmax(0,1fr)' in css
assert '#txAllView tbody td:nth-child(7)::before{content:"Betrag"}' in css
assert '#txRecurringView tbody td:nth-child(6)::before{content:"Betrag"}' in css
assert 'max-height:calc(100dvh - 20px)' in css
assert '.topbar nav.mobile-open{display:flex}' in css
assert '#forecastHorizon,#scenarioHorizon,#dashPeriod,#planningPeriod' in css
assert 'radial-gradient(900px 650px' in css and ') fixed,' in css
print('v0.11.2 mobile layout/navigation/viewport: PASS')
