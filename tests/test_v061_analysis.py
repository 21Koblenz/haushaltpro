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

today=date.today(); month=today.strftime('%Y-%m'); last=main.month_bounds(month)[1]
acc=ok(client.post('/api/accounts',json={'name':'Analyse','type':'checking','opening_balance':1000,'currency':'EUR','start_date':today.replace(day=1).isoformat()}))
inc=ok(client.post('/api/categories',json={'name':'Lohn','direction':'income'}))
exp=ok(client.post('/api/categories',json={'name':'Alltag','direction':'expense'}))
sav=ok(client.post('/api/categories',json={'name':'ETF','direction':'savings'}))
# Actual expense through today's cutoff: account balance should be 900, while movement net is -100.
ok(client.post('/api/transactions',json={'account_id':acc['id'],'amount':100,'booking_date':today.isoformat(),'payee':'Heute Ausgabe','category_id':exp['id'],'tags':[],'splits':[]}))
# Future entries inside the same month must influence projected per-day averages immediately.
future_day=min(last.day,max(today.day+1,20))
if future_day<=today.day: future_day=last.day
fdate=today.replace(day=future_day)
ok(client.post('/api/transactions',json={'account_id':acc['id'],'amount':900,'booking_date':fdate.isoformat(),'payee':'Zukunft Lohn','category_id':inc['id'],'tags':[],'splits':[]}))
ok(client.post('/api/transactions',json={'account_id':acc['id'],'amount':200,'booking_date':fdate.isoformat(),'payee':'Zukunft Ausgabe','category_id':exp['id'],'tags':[],'splits':[]}))
ok(client.post('/api/transactions',json={'account_id':acc['id'],'amount':100,'booking_date':fdate.isoformat(),'payee':'Zukunft Sparen','category_id':sav['id'],'tags':[],'splits':[]}))
d=ok(client.get('/api/dashboard?month='+month)); a=d['analysis']
assert a['balance_to_cutoff']==900.0,a
assert a['booked_net']==-100.0,a
assert a['planned_income']==900.0,a
assert a['planned_expense']==300.0,a
assert a['planned_savings']==100.0,a
expected_income=round(900/last.day,2); expected_expense=round(300/last.day,2); expected_savings=round(100/last.day,2)
assert a['average_daily_income']==expected_income,(a['average_daily_income'],expected_income)
assert a['average_daily_expense']==expected_expense,(a['average_daily_expense'],expected_expense)
assert a['average_daily_savings']==expected_savings,(a['average_daily_savings'],expected_savings)
html=(root/'static/index.html').read_text(); js=(root/'static/app.js').read_text()
assert 'Kontostand bis heute' in html and 'Einnahmen bis heute' in html and 'Monatsprognose inkl. geplanter Einnahmen' in html
assert 'fmt(a.balance_to_cutoff)' in js
assert tuple(map(int,main.APP_VERSION.split('-',1)[0].split('.'))) >= (0,6,1)
print('v0.6.1 cutoff balance + projected daily averages + cent rounding: PASS')
c.close(); Path(tmp).unlink(missing_ok=True)
