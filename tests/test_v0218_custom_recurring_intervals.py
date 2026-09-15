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
    def today(cls): return cls(2026,9,15)
main.date=FrozenDate; main.db._conn=c; main.session=lambda request,write=False:('test',1,'csrf',0)
main.require_book_owner=lambda request: None; main.require_system_admin=lambda request: None
from fastapi.testclient import TestClient
client=TestClient(main.app)
def ok(r): assert r.status_code<300,(r.status_code,r.text); return r.json()
acc=ok(client.post('/api/accounts',json={'name':'Interval Test','type':'checking','opening_balance':10000,'currency':'EUR','start_date':'2026-01-01'}))
cat=ok(client.post('/api/categories',json={'name':'Vertrag','direction':'expense'}))
def create(name,start,end,frequency,interval):
    return ok(client.post('/api/recurring',json={'account_id':acc['id'],'category_id':cat['id'],'name':name,'amount':100,'next_date':start,'frequency':frequency,'interval_count':interval,'kind':'direct_debit','active':True,'valid_until':end,'confidence':'fixed','fixed_cost':True}))
def dates(rid):
    return [r[0] for r in c.execute("SELECT booking_date FROM transactions WHERE recurring_id=? ORDER BY booking_date",(rid,)).fetchall()]
q=create('Quartal','2026-10-31','2027-10-31','monthly',3)
assert dates(q['id'])==['2026-10-31','2027-01-31','2027-04-30','2027-07-31','2027-10-31'],dates(q['id'])
h=create('Halbjahr','2026-11-30','2027-11-30','monthly',6)
assert dates(h['id'])==['2026-11-30','2027-05-30','2027-11-30'],dates(h['id'])
w=create('Alle zwei Wochen','2026-09-21','2026-11-02','weekly',2)
assert dates(w['id'])==['2026-09-21','2026-10-05','2026-10-19','2026-11-02'],dates(w['id'])
d=create('Alle zehn Tage','2026-09-20','2026-10-20','daily',10)
assert dates(d['id'])==['2026-09-20','2026-09-30','2026-10-10','2026-10-20'],dates(d['id'])
y=create('Alle zwei Jahre','2026-12-31','2030-12-31','yearly',2)
assert dates(y['id'])==['2026-12-31','2028-12-31','2030-12-31'],dates(y['id'])
m=create('Monat Standard','2026-10-15','2027-01-15','monthly',1)
assert dates(m['id'])==['2026-10-15','2026-11-15','2026-12-15','2027-01-15'],dates(m['id'])
rows=ok(client.get('/api/recurring'))
by_name={r['name']:r for r in rows}
assert by_name['Quartal']['interval_count']==3,by_name['Quartal']
assert by_name['Halbjahr']['interval_count']==6,by_name['Halbjahr']
assert by_name['Alle zwei Wochen']['interval_count']==2,by_name['Alle zwei Wochen']
bad=client.post('/api/recurring',json={'account_id':acc['id'],'category_id':cat['id'],'name':'Bad','amount':1,'next_date':'2026-10-01','frequency':'monthly','interval_count':0,'kind':'direct_debit','active':True})
assert bad.status_code==422,bad.text
# Transaction dialog path uses the same multiplier and persists it on the series.
tx=ok(client.post('/api/transactions',json={'account_id':acc['id'],'amount':50,'booking_date':'2026-10-20','category_id':cat['id'],'name':'Tx Quartal','payee':'Test','status':'executed','tags':[],'splits':[],'recurring':True,'recurring_frequency':'monthly','recurring_interval_count':3,'recurring_until':'2027-04-20','confidence':'fixed','fixed_cost':True}))
rr=c.execute('SELECT interval_count,frequency FROM recurring WHERE id=(SELECT recurring_id FROM transactions WHERE id=?)',(tx['id'],)).fetchone()
assert rr and rr['frequency']=='monthly' and rr['interval_count']==3,rr
source=(root/'static/app.js').read_text(encoding='utf-8')
for needle in ['Quartalsweise','Halbjährlich','recurring_interval_count','interval_count','recurrenceLabel']:
    assert needle in source,needle
print('custom recurring intervals plausibility: PASS')
c.close(); Path(tmp).unlink(missing_ok=True)
