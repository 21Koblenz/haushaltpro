import sqlite3, sys, types, tempfile
from pathlib import Path
shim=types.ModuleType('sqlcipher3'); shim.dbapi2=sqlite3; sys.modules['sqlcipher3']=shim
root=Path(__file__).resolve().parents[1]
Path('/app').mkdir(exist_ok=True)
static=Path('/app/static')
if static.is_symlink() or static.exists():
    try:
        if static.resolve()!= (root/'static').resolve(): static.unlink()
    except Exception: pass
if not static.exists(): static.symlink_to(root/'static', target_is_directory=True)
sys.path.insert(0,str(root))
from app import db
fd,tmp=tempfile.mkstemp(suffix='.db'); Path(tmp).unlink(missing_ok=True)
c=sqlite3.connect(tmp,check_same_thread=False); c.row_factory=sqlite3.Row; c.execute('PRAGMA foreign_keys=ON'); db._conn=c; db.DB_PATH=Path(tmp); db.init_schema(c)
from app import main
main.db._conn=c; main.session=lambda request,write=False:('test',1,'csrf',0)
main.require_book_owner=lambda request: None; main.require_system_admin=lambda request: None
from fastapi.testclient import TestClient
client=TestClient(main.app)
def ok(r):
    assert r.status_code<300,(r.status_code,r.text)
    return r.json()
acc=ok(client.post('/api/accounts',json={'name':'Giro','type':'checking','opening_balance':1000,'currency':'EUR','start_date':'2026-01-01'}))
rec=ok(client.post('/api/recurring',json={'account_id':acc['id'],'name':'Gehalt','amount':2000,'next_date':'2026-09-10','frequency':'monthly','kind':'income','active':True}))
c.execute("UPDATE recurring SET created_at='2026-09-01T00:00:00+00:00' WHERE id=?",(rec['id'],)); c.commit()
# One monthly override must not mutate the series amount.
ok(client.put(f"/api/recurring/{rec['id']}/override",json={'due_date':'2026-10-10','amount':2450,'note':'Überstunden'}))
row=c.execute('SELECT amount FROM recurring WHERE id=?',(rec['id'],)).fetchone(); assert row['amount']==200000
ov=c.execute('SELECT amount,note FROM recurring_overrides WHERE series_id=? AND due_date=?',(rec['id'],'2026-10-10')).fetchone(); assert ov['amount']==245000 and ov['note']=='Überstunden'
# Future recurring dates are materialised immediately as planned transactions.
# The October override updates only October; the base series remains unchanged.
rows=c.execute("SELECT booking_date,amount,status FROM transactions WHERE recurring_id=? AND booking_date BETWEEN '2026-09-01' AND '2026-11-30' ORDER BY booking_date",(rec['id'],)).fetchall()
vals={r['booking_date']:r['amount'] for r in rows}
assert '2026-09-10' not in vals  # created after this mistyped/past due date
assert vals['2026-10-10']==245000
assert vals['2026-11-10']==200000
assert all(r['status']=='planned' for r in rows)
# Executing/accessing the overridden occurrence reuses the already-materialised row.
from datetime import date as real_date
class DueDate(real_date):
    @classmethod
    def today(cls): return cls(2026,10,10)
main.date=DueDate
booked=ok(client.post(f"/api/recurring/{rec['id']}/execute"))
tx=c.execute('SELECT amount FROM transactions WHERE id=?',(booked['transaction_id'],)).fetchone(); assert tx['amount']==245000
html=(root/'static/index.html').read_text(); js=(root/'static/app.js').read_text(); css=(root/'static/style.css').read_text()
assert 'id="appVersion"' in html and 'id="themeMode"' in html
assert 'data-roverride' in js and "localStorage.setItem('hp_theme'" in js
assert 'html[data-theme="light"]' in css
assert tuple(map(int,main.APP_VERSION.split('.'))) >= (0,6,0)
print('v0.4.0 monthly recurring override + theme + footer version: PASS')
