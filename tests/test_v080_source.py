from pathlib import Path
root=Path(__file__).resolve().parents[1]
main=(root/'app/main.py').read_text(); db=(root/'app/db.py').read_text(); js=(root/'static/app.js').read_text(); html=(root/'static/index.html').read_text(); compose=(root/'docker-compose.yml').read_text()
assert any(f'APP_VERSION = \"{v}.' in main for v in ['0.8','0.9','0.10','0.11','0.21'])
assert '_thread_local' in db and 'def transaction()' in db and 'current_key()' in db and 'active_path()' in db
assert 'amount: Decimal' in main and 'def money_decimal' in main
for x in ['view-finance-check','planningVarianceTable','runwayMonths','scenarioResult','contractsList','variabilityStats']:
    assert x in html,x
for x in ['/api/finance-check','/api/planning/what-if','/api/planning/runway','/api/planning/variance','/api/contracts','detect_attachment_type','audit_verify','rotate_internal_backups']:
    assert x in main,x
assert 'HAUSHALTPRO_BIND_IP:-127.0.0.1' in compose
assert 'mem_limit: 512m' in compose and 'cpus: 1.0' in compose
assert "actual_balance:String(f.get('actual_balance'))" in js
assert "opening_balance:String(f.get('opening_balance'))" in js
print('v0.8.0 source/UX hardening: PASS')
