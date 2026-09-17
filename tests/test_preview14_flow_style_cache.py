from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
html=(ROOT/'static/index.html').read_text(encoding='utf-8')
js=(ROOT/'static/app.js').read_text(encoding='utf-8')
css=(ROOT/'static/style.css').read_text(encoding='utf-8')
assert 'v=0.21.9' in html
assert 'v=0.21.x-preview' not in html
assert '<svg class="flow-category-svg"' in js
assert '.flow-category-svg polygon' in css
assert '.flow-category-arrow>span{display:none!important}' in css
