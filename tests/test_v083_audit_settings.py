from pathlib import Path
root=Path(__file__).resolve().parents[1]
h=(root/'static/index.html').read_text(); j=(root/'static/app.js').read_text(); m=(root/'app/main.py').read_text(); d=(root/'Dockerfile').read_text()
assert 'planningHistoryLog' not in h
assert 'data-view="audit"' not in h
assert 'id="view-audit"' not in h
assert 'settings-audit-card' in h and 'id="auditTimeline"' in h
assert 'Änderungsverlauf' in h and 'Audit-Timeline' in h
assert 'Audit-Timeline' in h and 'Hashkette' in h
assert 'formatAuditTimestamp' in j
assert "Benutzer: <b>" not in j  # new stronger user badge instead
assert 'audit-user' in j and 'x.username' in j
assert "loadAuditTimeline(true)" in j and "async function loadSettings()" in j
assert '/api/audit/timeline' in m
assert 'INSERT INTO audit_log' in m
assert '--no-access-log' in d
# Audit append writes to DB and does not call print/logger/system logging.
a=m[m.index('def audit_append'):m.index('def audit_verify')]
assert 'c.execute' in a and 'print(' not in a and 'logger.' not in a and 'logging.' not in a
print('v0.8.3 audit moved to settings/readable timestamp/log privacy: PASS')
