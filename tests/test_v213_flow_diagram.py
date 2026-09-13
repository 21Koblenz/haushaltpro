from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_flow_renderer_exists_and_is_called():
    js = (ROOT / "static" / "app.js").read_text(encoding="utf-8")
    assert "function renderReportFlow(" in js
    assert "renderFlowCategoryStack('reportFlowIncomeCategories'" in js
    assert "renderFlowCategoryStack('reportFlowExpenseCategories'" in js
    assert "renderFlowCategoryStack('reportFlowSavingsCategories'" in js
    assert "renderReportFlow(r, period, anchorLabel)" in js


def test_all_three_category_stacks_exist():
    html = (ROOT / "static" / "index.html").read_text(encoding="utf-8")
    assert 'id="reportFlowIncomeCategories"' in html
    assert 'id="reportFlowExpenseCategories"' in html
    assert 'id="reportFlowSavingsCategories"' in html


def test_category_arrow_thickness_uses_own_group_share():
    js = (ROOT / "static" / "app.js").read_text(encoding="utf-8")
    assert "const shareRatio=Math.max(0,Math.min(1,share/100))" in js
    assert "const categoryTotal=items.reduce" in js
    assert "const share=categoryTotal>0?(amount/categoryTotal*100):0" in js
    assert "const width=Number(Math.max(8,share).toFixed(1))" in js
    assert "const thick=Number((3+shareRatio*37).toFixed(1))" in js
    assert "--flow-thickness:${thick}px" in js
    assert 'height:${thick}px!important' in js
    assert 'width:${width}%!important' in js
    assert "--flow-head:${head}px" in js


def test_arrow_heads_scale_with_shaft():
    css = (ROOT / "static" / "style.css").read_text(encoding="utf-8")
    assert "border-top:var(--flow-head,6px) solid transparent" in css
    assert "calc(var(--flow-head,6px)*1.5)" in css
