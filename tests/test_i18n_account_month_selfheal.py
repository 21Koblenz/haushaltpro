from pathlib import Path
import re

root = Path(__file__).resolve().parents[1]
js = (root / "static" / "app.js").read_text(encoding="utf-8")
html = (root / "static" / "index.html").read_text(encoding="utf-8")

assert "const MONTH_CONTROL_PAIRS=" in js
assert "function ensureMonthControls(" in js
assert "sel.options.length===12" in js
assert "function monthValue(monthId,yearId){return ensureMonthControls(" in js
assert "const month=ensureMonthControls('accountMonthName','accountYear',selectedMonth)" in js
assert "setMonthControls('accountMonthName','accountYear',body.start_date.slice(0,7))" in js
assert "function refreshLocalizedMonthControls()" in js
assert "for(const [monthId,yearId] of MONTH_CONTROL_PAIRS)" in js
for asset in ("style.css", "ui-enhancements.css", "i18n.js", "app.js", "ui-enhancements.js"):
    assert re.search(rf'/assets/{re.escape(asset)}\?v=[^"\']+', html), asset

print("i18n account/month self-heal + cache busting: PASS")
