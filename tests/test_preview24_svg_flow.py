from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
APP=(ROOT/'static/app.js').read_text(encoding='utf-8')
CSS=(ROOT/'static/style.css').read_text(encoding='utf-8')
HTML=(ROOT/'static/index.html').read_text(encoding='utf-8')

def geom(amount,total,max_amount):
    share=amount/total*100 if total else 0
    relative=amount/max_amount if max_amount else 0
    end=max(12,min(100,share))
    thickness=round(4+max(0,min(1,relative))*56,1)
    return share,end,thickness

def test_percentages_are_from_displayed_group_total():
    vals=[600,250,150]
    total=sum(vals)
    shares=[geom(x,total,max(vals))[0] for x in vals]
    assert shares == [60.0,25.0,15.0]
    assert round(sum(shares),10)==100.0
    assert 'const categoryTotal=items.reduce' in APP

def test_thickness_is_visually_distinct_by_amount():
    vals=[600,250,150]
    total=sum(vals); mx=max(vals)
    thickness=[geom(x,total,mx)[2] for x in vals]
    assert thickness == [60.0,27.3,18.0]
    assert thickness[0] > thickness[1] > thickness[2]
    assert thickness[0]-thickness[1] > 30
    assert 'const relative=maxAmount>0?' in APP

def test_svg_geometry_is_used_instead_of_css_span():
    assert '<svg class="flow-category-svg"' in APP
    assert '<polygon points="${g.points}">' in APP
    assert '.flow-category-svg polygon' in CSS
    assert '.flow-category-arrow>span{display:none!important}' in CSS

def test_preview24_cache_key():
    assert 'v=0.21.3' in HTML
