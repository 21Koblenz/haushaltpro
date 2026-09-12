from pathlib import Path
root=Path(__file__).resolve().parents[1]
main=(root/'app/main.py').read_text(); js=(root/'static/app.js').read_text(); css=(root/'static/style.css').read_text()
assert 'audit_changes' in main and '"changes"' in main
assert 'auditChangeRows' in js and '<s>' in js
assert 'AUDIT_FIELD_LABELS' in js and 'AUDIT_MONEY_FIELDS' in js
assert '.audit-change-row' in css and 'text-decoration-color:var(--danger)' in css
assert ('APP_VERSION = "0.8.4"' in main) or (('APP_VERSION = "0.8.5"' in main) or (('APP_VERSION = "0.8.6"' in main) or (('APP_VERSION = "0.8.7"' in main) or (('APP_VERSION = "0.9.0"' in main) or (('APP_VERSION = "0.10.0"' in main) or (('APP_VERSION = "0.10.1"' in main) or (('APP_VERSION = "0.10.2"' in main) or ('APP_VERSION = "0.10.3"' in main)))))))) or ('APP_VERSION = "0.10.4"' in main) or (('APP_VERSION = "0.10.5"' in main) or (('APP_VERSION = "0.11.1"' in main) or (('APP_VERSION = "0.21.0"' in main or ('APP_VERSION = "0.21.1"' in main or 'APP_VERSION = "0.21.2"' in main)))))
print('v0.8.4 detailed audit source/UI: PASS')
