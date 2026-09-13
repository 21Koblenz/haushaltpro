import json
import re
from html.parser import HTMLParser
from pathlib import Path

root=Path(__file__).resolve().parents[1]
static=root/'static'
manifest=json.loads((static/'i18n/languages.json').read_text(encoding='utf-8'))
assert manifest['default']=='de'
codes={x['code'] for x in manifest['languages']}
assert {'de','en'} <= codes

de=json.loads((static/'i18n/de.json').read_text(encoding='utf-8'))
en=json.loads((static/'i18n/en.json').read_text(encoding='utf-8'))
tpl=json.loads((static/'i18n/_template.json').read_text(encoding='utf-8'))
assert set(de['messages']) == set(en['messages']) == set(tpl['messages'])
assert all(en['messages'][k].strip() for k in en['messages'])
assert len(en['legacy']) >= 450
assert en['legacy']['Aktueller Kontostand']=='Current account balance'

index=(static/'index.html').read_text(encoding='utf-8')
assert '/assets/i18n.js' in index
assert '/assets/ui-enhancements.js' in index
assert 'data-i18n="dashboard.currentBalance"' in index
assert 'creamowl25@primal.net' in index
assert (static/'lightning-qr-black.svg').stat().st_size > 1000

i18n=(static/'i18n.js').read_text(encoding='utf-8')
assert 'HaushaltProI18n' in i18n and 'MutationObserver' in i18n
assert 'function audit()' in i18n

app=(static/'app.js').read_text(encoding='utf-8')
assert "const hpLocale=" in app
assert "new Intl.NumberFormat(hpLocale()" in app
assert ".toLocaleDateString(hpLocale()" in app
assert "new Intl.NumberFormat('de-DE'" not in app


# Regression coverage for language-aware month selectors and controls.
assert "const MONTHS_DE=" in app and "const MONTHS_EN=" in app
assert "const monthNames=()=>" in app
assert "monthNames().map" in app
assert "const MONTHS=new Proxy" not in app
assert not re.search(r"\bMONTHS\[", app), "stale MONTHS[] reference would break month/account views"
assert "enhanceDateInput" in i18n and "date.placeholder" in i18n
assert "enhanceFileInput" in i18n and "file.choose" in i18n
assert "canonicalDeleteConfirmation" in app and "'DELETE'?'LÖSCHEN'" in app
for source, translated in {
    'Wohnen':'Housing',
    'Lebensmittel':'Groceries',
    'Freizeit':'Leisure',
    'Einkommen':'Income',
    'Sparen & Rücklagen':'Savings & reserves',
    'Einstellung geändert':'Setting changed',
    'Zur Bestätigung exakt LÖSCHEN eingeben:':'Enter DELETE exactly to confirm:',
}.items():
    assert en['legacy'].get(source)==translated, (source,en['legacy'].get(source))
for key in [
    'budget.strategy.hybrid.description','budget.strategy.zeroBased.description',
    'budget.strategy.envelope.description','budget.strategy.503020.description',
    'budget.strategy.pyf.description','budget.metric.needs','budget.metric.wants',
    'budget.metric.savings','date.placeholder','file.choose','file.none'
]:
    assert en['messages'].get(key), key

# All built-in DB category names must have an English display translation.
db_source=(root/'app/db.py').read_text(encoding='utf-8')
seed_categories=re.findall(r"INSERT OR IGNORE INTO categories\(id,parent_id,name,direction\) VALUES\(\d+,NULL,'([^']+)'", db_source)
assert seed_categories, 'default category seed list not found'
for name in seed_categories:
    assert en['legacy'].get(name), f'missing default category translation: {name}'

# Dynamic form examples/placeholders must be covered too.
for placeholder in re.findall(r"placeholder=[\"']([^\"']+)[\"']", app):
    assert en['legacy'].get(placeholder), f'missing dynamic placeholder translation: {placeholder}'

# Audit action labels are user-facing history entries and must be translated.
audit_block=re.search(r"const AUDIT_ACTION_LABELS=\{(.*?)\};", app, re.S)
assert audit_block
for label in re.findall(r":'([^']+)'", audit_block.group(1)):
    assert label in en['legacy'], f'missing audit action translation: {label}'

assert "budget.metric.needs" in app and "budget.metric.wants" in app and "budget.metric.savings" in app
assert "formatDateTimeValue" in app and "formatMonthValue" in app
assert "start.querySelectorAll?.('input,select,textarea').forEach(el=>el.lang=currentCode)" in i18n

class CoverageParser(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.stack=[]; self.missing=[]; self.skip=0
    def handle_starttag(self, tag, attrs):
        a=dict(attrs); self.stack.append((tag,a))
        if tag in {'script','style','code','pre'}: self.skip += 1
        for attr,marker in [('placeholder','data-i18n-placeholder'),('title','data-i18n-title'),('aria-label','data-i18n-aria-label'),('alt','data-i18n-alt')]:
            v=a.get(attr)
            if v and marker not in a and v not in en['legacy']:
                self.missing.append(f'{attr}:{v}')
    def handle_endtag(self, tag):
        if tag in {'script','style','code','pre'} and self.skip: self.skip -= 1
        if self.stack: self.stack.pop()
    def handle_data(self, data):
        if self.skip: return
        text=' '.join(data.split())
        if not text or text in {'HaushaltPro','html','⚡ creamowl25@primal.net'}: return
        if re.fullmatch(r'[-–—+±‹›«»·↔↗↻\d\s.,:%/€()#]+',text): return
        attrs=self.stack[-1][1] if self.stack else {}
        if 'data-i18n' in attrs: return
        if text.startswith('cp .env.example '): return
        if text not in en['legacy']: self.missing.append(text)

cp=CoverageParser(); cp.feed(index)
assert not cp.missing, cp.missing
print('i18n preview structure + static English coverage: PASS')
