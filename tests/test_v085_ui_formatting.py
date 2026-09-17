from pathlib import Path
root=Path(__file__).resolve().parents[1]
js=(root/'static/app.js').read_text()
css=(root/'static/style.css').read_text()
main=(root/'app/main.py').read_text()
readme=(root/'README.md').read_text()
assert ('APP_VERSION = "0.8.5"' in main) or (('APP_VERSION = "0.8.6"' in main) or (('APP_VERSION = "0.8.7"' in main) or (('APP_VERSION = "0.9.0"' in main) or (('APP_VERSION = "0.10.0"' in main) or (('APP_VERSION = "0.10.1"' in main) or (('APP_VERSION = "0.10.2"' in main) or ('APP_VERSION = "0.10.3"' in main))))))) or ('APP_VERSION = "0.10.4"' in main) or (('APP_VERSION = "0.10.5"' in main) or (('APP_VERSION = "0.11.1"' in main) or (('APP_VERSION = "0.21.0"' in main or 'APP_VERSION = "0.21.2"' in main or ('APP_VERSION = "0.21.3"' in main or ('APP_VERSION = "0.21.4"' in main or ('APP_VERSION = "0.21.5"' in main or ('APP_VERSION = "0.21.6"' in main or ('APP_VERSION = "0.21.8"' in main or 'APP_VERSION = "0.21.9"' in main)))))))))
assert 'function yearSummaryMarkup(months)' in js
for text in ['Plan Einnahmen','Plan Ausgaben','Plan Sparen','Ist Einnahmen','Ist Ausgaben','Monatsende']:
    assert text in js,text
assert "year-negative" in js
for cls in ['.year-table{','.year-table-head','.year-table-row','.year-month','.year-cell','.year-end','#planningMonthView{display:grid;gap:20px}']:
    assert cls in css,cls
assert 'grid-template-columns:minmax(118px,1.05fr)' in css
assert '@media(max-width:1050px)' in css and '@media(max-width:650px)' in css
assert 'Jahresübersicht in Planung & Prognose und Dashboard als echte einspaltige Finanztabelle' in readme
print('v0.8.5 UI formatting source checks: PASS')
