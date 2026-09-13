import sqlite3, sys, tempfile, types
from datetime import date as real_date
from pathlib import Path
shim=types.ModuleType('sqlcipher3'); shim.dbapi2=sqlite3; sys.modules['sqlcipher3']=shim
root=Path(__file__).resolve().parents[1]
Path('/app').mkdir(exist_ok=True)
sm=Path('/app/static')
if sm.is_symlink() and sm.resolve() != (root/'static').resolve(): sm.unlink()
if not sm.exists(): sm.symlink_to(root/'static', target_is_directory=True)
sys.path.insert(0,str(root))
from app import db
fd,tmp=tempfile.mkstemp(suffix='.db'); Path(tmp).unlink(missing_ok=True)
c=sqlite3.connect(tmp,check_same_thread=False); c.row_factory=sqlite3.Row; c.execute('PRAGMA foreign_keys=ON')
db._conn=c; db.DB_PATH=Path(tmp); db.init_schema(c)
from app import main
main.db._conn=c; main.session=lambda request,write=False:('test',1,'csrf',0)
class FixedDate(real_date):
    @classmethod
    def today(cls): return cls(2026,9,20)
main.date=FixedDate
from fastapi.testclient import TestClient
client=TestClient(main.app)
r=client.post('/api/accounts',json={'name':'Dispo ab Monatsmitte','type':'checking','opening_balance':'-1234.56','currency':'EUR','start_date':'2026-09-12'})
assert r.status_code==200,(r.status_code,r.text)
aid=r.json()['id']
series=main.monthly_account_series(c,aid,'2026-09'); by={x['date']:x['balance'] for x in series}
assert by['2026-09-11']==0.0 and by['2026-09-12']==-1234.56 and by['2026-09-30']==-1234.56
D=client.get('/api/dashboard?month=2026-09').json(); assert D['total_balance']==-1234.56 and D['month_end_balance']==-1234.56
print('v0.21.2 mid-month negative dashboard preview regression: PASS')
c.close(); Path(tmp).unlink(missing_ok=True)
