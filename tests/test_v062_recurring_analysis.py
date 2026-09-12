import sqlite3,sys,types,tempfile
from pathlib import Path
from datetime import date
shim=types.ModuleType('sqlcipher3'); shim.dbapi2=sqlite3; sys.modules['sqlcipher3']=shim
root=Path(__file__).resolve().parents[1]
Path('/app').mkdir(exist_ok=True); static=Path('/app/static')
if static.is_symlink() or static.exists():
    try:
        if static.resolve()!=(root/'static').resolve(): static.unlink()
    except Exception: pass
if not static.exists(): static.symlink_to(root/'static',target_is_directory=True)
sys.path.insert(0,str(root))
from app import db
fd,tmp=tempfile.mkstemp(suffix='.db'); Path(tmp).unlink(missing_ok=True)
c=sqlite3.connect(tmp,check_same_thread=False); c.row_factory=sqlite3.Row; c.execute('PRAGMA foreign_keys=ON'); db._conn=c; db.DB_PATH=Path(tmp); db.init_schema(c); db.migrate_schema(c)
from app import main
main.db._conn=c; main.session=lambda request,write=False:('test',1,'csrf',0)
main.require_book_owner=lambda request: None; main.require_system_admin=lambda request: None
from fastapi.testclient import TestClient
client=TestClient(main.app)
def ok(r): assert r.status_code<300,(r.status_code,r.text); return r.json()

today=date.today(); month=today.strftime('%Y-%m'); first=today.replace(day=1); month_end=main.month_bounds(month)[1]
acc=ok(client.post('/api/accounts',json={'name':'Serientest','type':'checking','opening_balance':1000,'currency':'EUR','start_date':first.isoformat()}))
inc=ok(client.post('/api/categories',json={'name':'Gehalt Serie','direction':'income'}))
exp=ok(client.post('/api/categories',json={'name':'Miete Serie','direction':'expense'}))
# Direct recurring rows simulate an existing plan whose due date was the 1st and
# has not been manually marked executed. They must still flow into "bis heute".
rin=ok(client.post('/api/recurring',json={'account_id':acc['id'],'category_id':inc['id'],'name':'Gehalt','amount':2000,'next_date':first.isoformat(),'frequency':'monthly','kind':'income','active':True}))
rout=ok(client.post('/api/recurring',json={'account_id':acc['id'],'category_id':exp['id'],'name':'Miete','amount':500,'next_date':first.isoformat(),'frequency':'monthly','kind':'direct_debit','active':True}))
d=ok(client.get('/api/dashboard?month='+month)); a=d['analysis']
assert a['booked_income']==2000.0,a
assert a['booked_expense']==500.0,a
assert a['balance_to_cutoff']==2500.0,a  # 1000 + 2000 - 500
assert d['accounts'][0]['month_start_balance']==1000.0,d['accounts'][0]
assert d['accounts'][0]['balance']==2500.0,d['accounts'][0]
# Full-month averages include planned/current recurring values, cent rounded.
assert a['average_daily_income']==round(2000/month_end.day,2),a
assert a['average_daily_expense']==round(500/month_end.day,2),a
# A future manual income must affect projected daily income immediately.
future_day=min(month_end.day,max(today.day+1,20))
if future_day>today.day:
    fdate=today.replace(day=future_day)
    ok(client.post('/api/transactions',json={'account_id':acc['id'],'amount':100,'booking_date':fdate.isoformat(),'payee':'Bonus','category_id':inc['id'],'tags':[],'splits':[]}))
    d2=ok(client.get('/api/dashboard?month='+month)); a2=d2['analysis']
    assert a2['average_daily_income']==round(2100/month_end.day,2),a2
# Frontend must turn structured FastAPI details into readable messages.
js=(root/'static/app.js').read_text()
assert "Array.isArray(detail)" in js and "x?.msg" in js
html=(root/'static/index.html').read_text()
assert 'Kennzahlen bis heute im ausgewählten Monat' in html
assert tuple(map(int,main.APP_VERSION.split('.'))) >= (0,6,2)
print('v0.6.2 recurring due-on-first + cutoff balance + averages + readable errors: PASS')
c.close(); Path(tmp).unlink(missing_ok=True)
