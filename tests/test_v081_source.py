from pathlib import Path
root=Path(__file__).resolve().parents[1]
html=(root/'static/index.html').read_text()
js=(root/'static/app.js').read_text()
css=(root/'static/style.css').read_text()
main=(root/'app/main.py').read_text()
readme=(root/'README.md').read_text()

for needle in [
    'id="txPeriod"','Alle Buchungen','id="txPageSize"','Alle anzeigen',
    'id="planningYearChart"','Jahresübersicht Planung & Prognose',
    'data-view="help"','Hilfe & Anleitung'
]:
    assert needle in html, needle
assert 'Name der Buchung' in js
assert '/api/transactions/paged' in js
assert "interactiveMonthlyChart" in js and "onmousemove" in js and "ontouchmove" in js
assert "/api/planning/year" in main
assert "name: str | None" in main
assert "pagination-bar" in css and 'html[data-theme="light"]' in css
assert "cp .env.example .env" in readme and "HAUSHALTPRO_BIND_IP=0.0.0.0" in readme
assert "CSV-Importdateien werden nicht dauerhaft gespeichert" in readme
print("v0.8.1 source/UI requirements: PASS")
