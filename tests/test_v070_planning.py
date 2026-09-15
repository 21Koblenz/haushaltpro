import sqlite3,sys,types,tempfile
from pathlib import Path
from datetime import date
shim=types.ModuleType('sqlcipher3'); shim.dbapi2=sqlite3; sys.modules['sqlcipher3']=shim
root=Path(__file__).resolve().parents[1]
Path('/app').mkdir(exist_ok=True); static=Path('/app/static')
if not static.exists(): static.symlink_to(root/'static',target_is_directory=True)
sys.path.insert(0,str(root))
from app import db
fd,tmp=tempfile.mkstemp(suffix='.db'); Path(tmp).unlink(missing_ok=True)
c=sqlite3.connect(tmp,check_same_thread=False); c.row_factory=sqlite3.Row; c.execute('PRAGMA foreign_keys=ON'); db._conn=c; db.DB_PATH=Path(tmp); db.init_schema(c); db.migrate_schema(c)
from app import main
class FrozenDate(date):
    @classmethod
    def today(cls): return cls(2026,9,11)
main.date=FrozenDate
main.db._conn=c; main.session=lambda request,write=False:('test',1,'csrf',0)
main.require_book_owner=lambda request: None; main.require_system_admin=lambda request: None
from fastapi.testclient import TestClient
client=TestClient(main.app)
def ok(r): assert r.status_code<300,(r.status_code,r.text); return r.json()
assert main.date.today().isoformat()=='2026-09-11'
acc=ok(client.post('/api/accounts',json={'name':'C24','type':'checking','opening_balance':5000,'currency':'EUR','start_date':'2026-01-01'}))
inc=ok(client.post('/api/categories',json={'name':'Gehalt','direction':'income'}))
exp=ok(client.post('/api/categories',json={'name':'Miete','direction':'expense'}))
sav=ok(client.post('/api/categories',json={'name':'ETF','direction':'savings'}))
for payload in [
 {'category_id':inc['id'],'name':'Gehalt','amount':2500,'next_date':'2026-09-25','kind':'income','confidence':'likely','fixed_cost':False},
 {'category_id':exp['id'],'name':'Miete','amount':1000,'next_date':'2026-09-01','kind':'direct_debit','confidence':'fixed','fixed_cost':True},
 {'category_id':sav['id'],'name':'ETF','amount':500,'next_date':'2026-09-05','kind':'direct_debit','confidence':'fixed','fixed_cost':False},
]:
 ok(client.post('/api/recurring',json={'account_id':acc['id'],'frequency':'monthly','active':True,'valid_until':None,'max_amount':None,**payload}))
p=ok(client.get('/api/planning/overview?month=2026-10'))
assert p['plan_actual']['planned']['income']==2500,p
assert p['plan_actual']['planned']['expense']==1000,p
assert p['plan_actual']['planned']['savings']==500,p
assert p['fixed_costs']==1000 and p['fixed_cost_ratio_pct']==40.0,p
assert p['free_money']==1000,p
assert len(p['forecast']['12'])==12,p['forecast']['12']
assert p['forecast']['conservative'][-1]['end_balance'] < p['forecast']['optimistic'][-1]['end_balance'],p['forecast']
r=ok(client.post('/api/accounts/%s/reconcile'%acc['id'],json={'actual_balance':5100,'checked_at':'2026-09-11','note':'Test'}))
assert r['actual']==5100 and isinstance(r['difference'],float),r
tx=ok(client.post('/api/transactions',json={'account_id':acc['id'],'amount':12.34,'booking_date':'2026-09-11','category_id':exp['id'],'payee':'Belegtest','status':'executed','tags':[],'splits':[]}))
up=ok(client.post(f"/api/transactions/{tx['id']}/attachments",files={'file':('rechnung.pdf',b'%PDF-1.4 test','application/pdf')}))
lst=ok(client.get(f"/api/transactions/{tx['id']}/attachments"))
assert len(lst)==1 and lst[0]['filename']=='rechnung.pdf',lst
raw=client.get(f"/api/attachments/{up['id']}")
assert raw.status_code==200 and raw.content.startswith(b'%PDF'),raw.status_code
h=ok(client.get('/api/history'))
assert len(h['recurring'])>=3,h
assert tuple(map(int,main.APP_VERSION.split('-',1)[0].split('.'))) >= (0,7,0)
print('v0.7.0 planning/documentation plausibility: PASS')
c.close(); Path(tmp).unlink(missing_ok=True)
