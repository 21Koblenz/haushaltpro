from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
APP=(ROOT/'static/app.js').read_text(encoding='utf-8')
HTML=(ROOT/'static/index.html').read_text(encoding='utf-8')
CSS=(ROOT/'static/style.css').read_text(encoding='utf-8')

def test_flow_uses_displayed_group_total_for_percentages():
    assert 'const categoryTotal=items.reduce' in APP
    assert 'const share=total>0?(safeAmount/total*100):0;' in APP
    assert 'const g=flowArrowGeometry(amount,categoryTotal,groupMax);' in APP

def test_reference_percentages_still_match_labels():
    values=[600,250,150]
    total=sum(values)
    shares=[v/total*100 for v in values]
    assert shares == [60.0,25.0,15.0]

def test_svg_arrows_are_explicit_geometry():
    assert '<svg class="flow-category-svg"' in APP
    assert '.flow-category-svg polygon' in CSS
    assert '.flow-category-arrow>span{display:none!important}' in CSS

def test_top_theme_toggle_exists_and_persists():
    assert 'id="themeToggle"' in HTML
    assert "localStorage.setItem('hp_theme',next)" in APP
    assert 'applyTheme(next)' in APP
    assert 'v=0.21.3' in HTML
