from pathlib import Path
css=(Path(__file__).resolve().parents[1]/'static/style.css').read_text()

def rgb(h):
    h=h.lstrip('#'); return tuple(int(h[i:i+2],16)/255 for i in (0,2,4))
def lum(h):
    vals=[]
    for c in rgb(h): vals.append(c/12.92 if c<=.04045 else ((c+.055)/1.055)**2.4)
    return .2126*vals[0]+.7152*vals[1]+.0722*vals[2]
def ratio(a,b):
    x,y=sorted((lum(a),lum(b)),reverse=True); return (x+.05)/(y+.05)

pairs={
    'main text':('#142033','#ffffff',7.0),
    'muted text':('#536477','#ffffff',4.5),
    'nav text':('#43546a','#ffffff',4.5),
    'negative amount':('#a61b28','#ffffff',4.5),
    'button text':('#ffffff','#17263a',7.0),
}
for name,(fg,bg,minimum) in pairs.items():
    assert fg in css and bg in css,(name,fg,bg)
    r=ratio(fg,bg)
    assert r>=minimum,(name,r,minimum)
    print(f'{name}: {r:.2f}:1')
print('v0.9.0 light-mode contrast checks: PASS')
