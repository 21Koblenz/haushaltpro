from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
APP_JS = (ROOT / "static" / "app.js").read_text(encoding="utf-8")
ENHANCEMENTS_JS = (ROOT / "static" / "ui-enhancements.js").read_text(encoding="utf-8")

# The transaction dialog still exposes the saved payees through its datalist.
# ui-enhancements.js converts that browser-dependent datalist into a native
# select while keeping the free-text payee input as the submitted form value.
assert 'name="payee" list="payeeSuggestions"' in APP_JS
assert "function enhancePayeePicker" in ENHANCEMENTS_JS
assert "input.removeAttribute('list')" in ENHANCEMENTS_JS
assert "select.className='payee-preset-select'" in ENHANCEMENTS_JS
assert "select.addEventListener('change'" in ENHANCEMENTS_JS
assert "input.value=select.value" in ENHANCEMENTS_JS
assert "input.before(select)" in ENHANCEMENTS_JS

print("payee picker UI regression checks: OK")
