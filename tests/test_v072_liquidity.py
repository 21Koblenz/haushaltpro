import sqlite3,sys,types,tempfile
from pathlib import Path
from datetime import date
shim=types.ModuleType('sqlcipher3'); shim.dbapi2=sqlite3; sys.modules['sqlcipher3']=shim
root=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(root))
from app import db
fd,tmp=tempfile.mkstemp(suffix='.db'); Path(tmp).unlink(missing_ok=True)
c=sqlite3.connect(tmp,check_same_thread=False); c.row_factory=sqlite3.Row; c.execute('PRAGMA foreign_keys=ON')
db._conn=c; db.DB_PATH=Path(tmp); db.init_schema(c); db.migrate_schema(c)
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

# Konto A: viel angespartes Guthaben. Monatliche Ausgaben > Einnahmen, aber 12 Monate lang nie negativ.
a=ok(client.post('/api/accounts',json={'name':'Rücklagenkonto','type':'checking','opening_balance':10000,'currency':'EUR','start_date':'2026-09-01'}))
inc=ok(client.post('/api/categories',json={'name':'Einkommen A','direction':'income'}))['id']
exp=ok(client.post('/api/categories',json={'name':'Fixkosten A','direction':'expense'}))['id']
# monatlich +1000 / -1500 => -500 pro Monat, aus 10k Rücklage bleibt nach 12 Monaten positiv
for payload in [
 {'category_id':inc,'name':'Einkommen A','amount':1000,'next_date':'2026-09-25','kind':'income','confidence':'fixed','fixed_cost':False},
 {'category_id':exp,'name':'Fixkosten A','amount':1500,'next_date':'2026-09-20','kind':'direct_debit','confidence':'fixed','fixed_cost':True},
]:
 ok(client.post('/api/recurring',json={'account_id':a['id'],'frequency':'monthly','active':True,'valid_until':None,'max_amount':None,**payload}))

plan=ok(client.get('/api/planning/overview?month=2026-09'))
warn_names={w['account'] for w in plan['liquidity_warnings']}
assert 'Rücklagenkonto' not in warn_names, plan['liquidity_warnings']

# Konto B: wenig Guthaben, echte Unterdeckung soll gewarnt werden.
b=ok(client.post('/api/accounts',json={'name':'Knappes Konto','type':'checking','opening_balance':200,'currency':'EUR','start_date':'2026-09-01'}))
exp2=ok(client.post('/api/categories',json={'name':'Fixkosten B','direction':'expense'}))['id']
ok(client.post('/api/recurring',json={'account_id':b['id'],'category_id':exp2,'name':'Große Abbuchung','amount':500,'next_date':'2026-09-20','frequency':'monthly','kind':'direct_debit','max_amount':None,'active':True,'valid_until':None,'confidence':'fixed','fixed_cost':True}))
plan2=ok(client.get('/api/planning/overview?month=2026-09'))
warn={w['account']:w for w in plan2['liquidity_warnings']}
assert 'Knappes Konto' in warn and warn['Knappes Konto']['date']=='2026-09-20',warn
assert warn['Knappes Konto']['balance']==-300.0,warn

# Monatsanfang bleibt Vormonatsende/Startsaldo und Tag-1-Bewegung wird erst danach gerechnet.
assert main._month_opening_balance(c,a['id'],date(2026,9,1))==1000000
assert main.projected_account_balance(c,a['id'],date(2026,9,1))==1000000

print('v0.7.2 liquidity plausibility: PASS')
c.close(); Path(tmp).unlink(missing_ok=True)
