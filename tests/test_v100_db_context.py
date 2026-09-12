import sqlite3,sys,types,tempfile
from pathlib import Path
shim=types.ModuleType('sqlcipher3');shim.dbapi2=sqlite3;sys.modules['sqlcipher3']=shim
root=Path(__file__).resolve().parents[1];sys.path.insert(0,str(root))
from app import db
base=Path(tempfile.mkdtemp(prefix='hpctx-'));calls=[]
def plain_connect(key,path=None):
    target=Path(path);calls.append((key,str(target)));c=sqlite3.connect(str(target),check_same_thread=False);c.row_factory=sqlite3.Row;return c
db.close();db._conn=None;db._master_key=None;db.connect=plain_connect
p1=base/'one.db';p2=base/'two.db'
db.activate(p1,'k1');c1=db.db();c1.execute('create table if not exists t(x)');c1.commit()
db.activate(p1,'k2');c2=db.db();assert c2 is not c1 and calls[-1][0]=='k2'
db.activate(p2,'k3');c3=db.db();assert c3 is not c2 and calls[-1][1]==str(p2)
db.clear_context()
print('v0.10.0 DB context path/key isolation: PASS')
