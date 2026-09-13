from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
main=(ROOT/'app/main.py').read_text()
js=(ROOT/'static/app.js').read_text()
html=(ROOT/'static/index.html').read_text()
css=(ROOT/'static/style.css').read_text()
assert 'reportSavingsRateLabel' in html
assert 'reportAvgSavingsLabel' in html
assert 'const savingsRate=income>0?(totalSaved/income*100):0' in js
assert 'explicit_savings_rate_pct' in main and 'average_saved_unit' in main
assert 'const categoryTotal=items.reduce' in js
assert 'const share=total>0?(safeAmount/total*100):0;' in js
assert 'const thickness=Number((4+relative*56).toFixed(1));' in js
assert 'data-flow-share' in js
assert '<svg class="flow-category-svg"' in js
assert '.flow-category-svg polygon' in css
