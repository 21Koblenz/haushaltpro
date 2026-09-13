from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
APP=(ROOT/'static/app.js').read_text(encoding='utf-8')
CSS=(ROOT/'static/style.css').read_text(encoding='utf-8')
HTML=(ROOT/'static/index.html').read_text(encoding='utf-8')

def test_flow_renderer_uses_current_svg_geometry():
    # Preview 24 supersedes the old Preview-23 CSS span geometry.
    assert 'function flowArrowGeometry(' in APP
    assert '<svg class="flow-category-svg"' in APP
    assert 'const thickness=Number((4+relative*56).toFixed(1));' in APP

def test_flow_lane_stays_fixed_height():
    assert 'height:64px!important' in CSS
    assert 'min-height:64px!important' in CSS
    assert 'max-height:64px!important' in CSS

def test_header_dimensions_do_not_depend_on_theme():
    assert 'html[data-theme="light"] .topbar' in CSS
    assert 'padding:0!important' in CSS
    assert 'flex-wrap:nowrap!important' in CSS
    assert 'width:194px!important' in CSS
    assert 'v=0.21.3' in HTML
