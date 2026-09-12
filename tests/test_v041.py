from pathlib import Path
import ast
root=Path(__file__).resolve().parents[1]
ast.parse((root/'app/main.py').read_text())
js=(root/'static/app.js').read_text()
main=(root/'app/main.py').read_text()
assert 'APP_VERSION = "' in main
assert 'opening_balance' in main and 'def monthly_account_series' in main and 'GROUP BY booking_date' in main
assert 'type="month" required value="${month}"' in js
assert '/corrections' in js and "month-opening/'+encodeURIComponent" in js
print('v0.5.0 chart full-month + arbitrary month correction source: PASS')
