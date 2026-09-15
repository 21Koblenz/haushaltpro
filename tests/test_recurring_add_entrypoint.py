from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
INDEX = (ROOT / "static" / "index.html").read_text(encoding="utf-8")
APP_JS = (ROOT / "static" / "app.js").read_text(encoding="utf-8")

assert 'id="newTx"' in INDEX
assert 'id="newRecurringTx"' not in INDEX
assert "$('newTx').onclick=()=>txDialog()" in APP_JS
assert "$('newRecurringTx').onclick" not in APP_JS
assert 'Wiederkehrende Zahlung / Einnahme' in APP_JS
assert 'Neue Serien legst du über „+ Buchung“ an' in INDEX

print("recurring add entrypoint regression checks: OK")
