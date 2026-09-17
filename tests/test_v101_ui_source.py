from pathlib import Path
root=Path(__file__).resolve().parents[1]
h=(root/'static/index.html').read_text();j=(root/'static/app.js').read_text();c=(root/'static/style.css').read_text();m=(root/'app/main.py').read_text()
assert 'id="auditSearch"' in h and 'id="auditPageSize"' in h and 'id="auditPageInfo"' in h
assert 'data-audit-delete' in j and '/api/audit/' in j
assert 'data-rename-book' in j and 'data-delete-book' in j
assert 'data-delete-user' in j
cards=(root/'static/overview-cards.js').read_text()
assert 'recurringCards(rows,transferRows)' in j and 'recurring-future-change' in cards
assert '.recurring-name-cell b{display:block' in c
assert '@app.put("/api/books/{book_id}")' in m and '@app.delete("/api/books/{book_id}")' in m
assert '@app.delete("/api/users/{username}")' in m
assert '@app.delete("/api/audit/{audit_id}")' in m
assert 'deleted_items' in m and 'audit_rebuild_chain' in m
print('v0.10.1 UI/admin/audit source checks: PASS')
