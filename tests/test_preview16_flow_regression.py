from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
HTML=(ROOT/'static/index.html').read_text(encoding='utf-8')
JS=(ROOT/'static/app.js').read_text(encoding='utf-8')
CSS=(ROOT/'static/style.css').read_text(encoding='utf-8')
def test_release_cache_key_is_used(): assert 'v=0.21.3' in HTML
def test_flow_is_constrained_to_panel_width():
 assert '.report-flow-panel{margin-top:20px;overflow:hidden;max-width:100%}' in CSS
 assert 'max-width:100%' in CSS
def test_each_category_arrow_head_is_attached_to_its_body():
 assert '<svg class="flow-category-svg"' in JS
 assert '<polygon points="${g.points}">' in JS
 assert 'const points=`0,${top} ${neckX},${top} ${endX},${centerY} ${neckX},${bottom} 0,${bottom}`;' in JS
def test_all_category_groups_remain_present():
 for element_id in ('reportFlowIncomeCategories','reportFlowExpenseCategories','reportFlowSavingsCategories'):
  assert f'id="{element_id}"' in HTML
