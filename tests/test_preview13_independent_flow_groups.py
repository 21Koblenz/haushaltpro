from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
js=(ROOT/'static/app.js').read_text(encoding='utf-8')
assert 'const categoryTotal=items.reduce' in js
assert 'flowArrowGeometry(amount,categoryTotal,groupMax)' in js
assert 'data-flow-group="${cls}"' in js
def shares(values):
 total=sum(values)
 return [round(v/total*100,1) for v in values]
assert shares([3000,1000]) == [75.0,25.0]
assert shares([600,300,100]) == [60.0,30.0,10.0]
assert shares([800,200]) == [80.0,20.0]
