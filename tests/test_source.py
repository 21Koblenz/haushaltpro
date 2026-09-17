from pathlib import Path
import ast
root=Path(__file__).resolve().parents[1]
for path in (root/'app').glob('*.py'):
    ast.parse(path.read_text(), filename=str(path)); print(f"syntax: PASS {path.name}")
html=(root/'static/index.html').read_text(); js=(root/'static/app.js').read_text(); main=(root/'app/main.py').read_text(); db=(root/'app/db.py').read_text()
assert 'id="modalCancel" type="button"' in html
assert "$('modalCancel').onclick=()=>modal.close()" in js
assert '?hard=true' in js and 'include_cancelled: bool = False' in main
assert 'month_start_balance' in main and 'month_end_balance' in main
assert '/api/reports/categories' in main and 'direction' in db
assert 'HAUSHALTPRO_V3_SQLCIPHER4' in db and 'migrate_schema' in db
assert '/assets/style.css' in html and '/assets/app.js' in html
assert 'Die Kategorie bestimmt automatisch' in js and 'categoryTypeLabel' in js
assert 'id="navInvestments"' in html and '/api/investments' in main and 'investmentDialog' in js
print('functional_source_checks: PASS')
js=(root/'static'/'app.js').read_text()
html=(root/'static'/'index.html').read_text()
assert 'id="registerBtn"' in html and 'id="register"' in html
assert 'id="registerPassword"' in html and 'id="registerPasswordConfirm"' in html
assert "$('registerBtn').onclick=showRegister" in js and "$('registerForm').addEventListener('submit'" in js and '/api/register' in js
assert "runtimeStatus.registration_enabled" in js and "$('registerBtn').hidden=setup||!runtimeStatus.registration_enabled" in js
assert 'cursor:crosshair' in (root/'static'/'style.css').read_text()
chart=(root/'static/dashboard-charts.js').read_text()
assert 'canvas.onpointerdown' in chart and 'ctx.setLineDash' in chart and 'formatDateValue' in chart
print('auth UX + chart crosshair source: PASS')

html=(root/'static/index.html').read_text(); js=(root/'static/app.js').read_text(); assert '30 Tage' not in html and '60 Tage' not in html and '90 Tage' not in html; assert 'Januar' in js and 'Dezember' in js and 'dashMonthName' in html and 'txMonthName' in html; print('calendar month UI: PASS')
