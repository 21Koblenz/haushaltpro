from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
INDEX = (ROOT / "static" / "index.html").read_text(encoding="utf-8")
APP_JS = (ROOT / "static" / "app.js").read_text(encoding="utf-8")

# Both entry points intentionally remain available: the normal booking dialog can
# be switched to recurring, and the recurring-series tab has its dedicated add
# button for users who manage contracts there.
assert 'id="newTx"' in INDEX
assert 'id="newRecurringTx"' in INDEX
assert "$('newTx').onclick=()=>txDialog()" in APP_JS
assert "$('newRecurringTx').onclick=()=>recDialog(null)" in APP_JS
assert 'Wiederkehrende Zahlung / Einnahme' in APP_JS

print("recurring add entrypoint regression checks: OK")
