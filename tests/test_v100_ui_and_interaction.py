from pathlib import Path
root=Path(__file__).resolve().parents[1]
html=(root/'static/index.html').read_text()
js=(root/'static/app.js').read_text()
css=(root/'static/style.css').read_text()
main=(root/'app/main.py').read_text()

for needle in ['id="bookSwitcher"','Benutzer & Rechte','Haushaltsbücher','id="dbSize"','id="deleteTxControls"','LÖSCHEN']:
    assert needle in html,needle
for needle in ['/api/books','/membership','/reset-password','/api/admin/storage','/api/admin/transactions-delete-preview','transaction.bulk_delete','BOOKS_DIR']:
    assert needle in main,needle
for needle in ['onpointermove','onpointerdown','donut-legend-row',"classList.toggle('active'",'Passwort zurücksetzen','currentMe','Buchung #','cur.payee','cur.category_name']:
    assert needle in js,needle
assert 'html[data-theme="light"] .topbar nav{background:#f7f9fb' in css
assert 'html[data-theme="light"] .nav{color:#243447' in css

def rgb(h):
    h=h.lstrip('#')
    return tuple(int(h[i:i+2],16)/255 for i in (0,2,4))
def lum(h):
    vals=[]
    for c in rgb(h): vals.append(c/12.92 if c<=.04045 else ((c+.055)/1.055)**2.4)
    return .2126*vals[0]+.7152*vals[1]+.0722*vals[2]
def contrast(a,b):
    x,y=sorted([lum(a),lum(b)],reverse=True)
    return (x+.05)/(y+.05)
assert contrast('#243447','#f7f9fb')>=7,contrast('#243447','#f7f9fb')
assert contrast('#172033','#ffffff')>=12
print('v0.10.0 UI/light-mode/donut/audit source checks: PASS')
