import sqlite3, sys, types, tempfile
from datetime import date, timedelta
from pathlib import Path

shim=types.ModuleType("sqlcipher3"); shim.dbapi2=sqlite3; sys.modules["sqlcipher3"]=shim
root=Path(__file__).resolve().parents[1]
Path("/app").mkdir(exist_ok=True)
static=Path("/app/static")
if not static.exists(): static.symlink_to(root/"static", target_is_directory=True)
sys.path.insert(0,str(root))
from app import db
fd,tmp=tempfile.mkstemp(suffix=".db"); Path(tmp).unlink(missing_ok=True)
c=sqlite3.connect(tmp,check_same_thread=False); c.row_factory=sqlite3.Row; c.execute("PRAGMA foreign_keys=ON")
db._conn=c; db.DB_PATH=Path(tmp); db.init_schema(c)
from app import main
main.db._conn=c
main.session=lambda request,write=False:("test",1,"csrf",0)
from fastapi.testclient import TestClient
client=TestClient(main.app)

def ok(r):
    assert r.status_code < 300,(r.status_code,r.text)
    return r.json()

acc=ok(client.post("/api/accounts",json={"name":"Testkonto","type":"checking","opening_balance":1000,"currency":"EUR","start_date":date.today().isoformat()}))
cat=ok(client.post("/api/categories",json={"name":"Vertrag","direction":"expense"}))
due=date.today()+timedelta(days=1)
payload={"account_id":acc["id"],"category_id":cat["id"],"name":"Stromabschlag","payee":"Stadtwerke Test","amount":"42.00","next_date":due.isoformat(),"frequency":"monthly","interval_count":1,"kind":"direct_debit","active":True,"valid_until":due.isoformat(),"confidence":"fixed","fixed_cost":True}
created=ok(client.post("/api/recurring",json=payload))
r=c.execute("SELECT payee FROM recurring WHERE id=?",(created["id"],)).fetchone(); assert r["payee"]=="Stadtwerke Test",r
tx=c.execute("SELECT payee,status FROM transactions WHERE recurring_id=? AND booking_date=?",(created["id"],due.isoformat())).fetchone(); assert tx and tx["payee"]=="Stadtwerke Test" and tx["status"]=="planned",tx
rows=ok(client.get("/api/recurring")); row=next(x for x in rows if x["id"]==created["id"]); assert row["payee"]=="Stadtwerke Test",row
payload["payee"]="Neuer Stadtwerke Name"; payload["effective_from"]=due.isoformat()
ok(client.put(f"/api/recurring/{created['id']}",json=payload))
r=c.execute("SELECT payee FROM recurring WHERE id=?",(created["id"],)).fetchone(); assert r["payee"]=="Neuer Stadtwerke Name",r
tx=c.execute("SELECT payee FROM transactions WHERE recurring_id=? AND booking_date=? AND status='planned'",(created["id"],due.isoformat())).fetchone(); assert tx and tx["payee"]=="Neuer Stadtwerke Name",tx
index=(root/"static/index.html").read_text(encoding="utf-8"); appjs=(root/"static/app.js").read_text(encoding="utf-8")
assert 'id="newTx"' in index
assert 'id="newRecurringTx"' not in index
assert "$('newRecurringTx').onclick" not in appjs
assert 'Wiederkehrende Zahlung / Einnahme' in appjs
assert 'name="payee" list="payeeSuggestions"' in appjs
print("recurring payee + unified add entrypoint: PASS")
