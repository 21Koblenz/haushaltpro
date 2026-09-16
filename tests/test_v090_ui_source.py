from pathlib import Path
root=Path(__file__).resolve().parents[1]
main=(root/'app/main.py').read_text(); db=(root/'app/db.py').read_text(); html=(root/'static/index.html').read_text(); js=(root/'static/app.js').read_text(); css=(root/'static/style.css').read_text()
assert ('APP_VERSION = "0.9.0"' in main) or (('APP_VERSION = "0.10.0"' in main) or (('APP_VERSION = "0.10.1"' in main) or (('APP_VERSION = "0.10.2"' in main) or ('APP_VERSION = "0.10.3"' in main)))) or ('APP_VERSION = "0.10.4"' in main) or (('APP_VERSION = "0.10.5"' in main) or (('APP_VERSION = "0.11.1"' in main) or (('APP_VERSION = "0.21.0"' in main or 'APP_VERSION = "0.21.2"' in main or ('APP_VERSION = "0.21.3"' in main or ('APP_VERSION = "0.21.4"' in main or ('APP_VERSION = "0.21.5"' in main or ('APP_VERSION = "0.21.6"' in main or ('APP_VERSION = "0.21.8"' in main or 'APP_VERSION = "0.21.9-dev.3"' in main)))))))))
for needle in ['id="newTransfer"','id="txTabAll"','id="txTabRecurring"','id="expenseDonut"','id="incomeDonut"','id="payeePresetList"']:
    assert needle in html,needle
for needle in ['/api/transfers','/api/payees','remember_payee','function drawDonut','Aktueller Stand','Buchung #']:
    assert needle in js or needle in main,needle
assert 'GZipMiddleware' in main
assert 'serialize_transaction_rows' in main
assert 'idx_tx_category_date' in db and 'idx_tags_tag_tx' in db
assert 'html[data-theme="light"]' in css and '--text:#142033' in css
assert 'report-donut-grid' in css and 'segmented-tabs' in css
print('v0.9.0 UI/source requirements: PASS')
