# Testing / Plausibility - v0.21.0

## Test strategy

HaushaltPro uses script-based regression tests. Each `tests/test_*.py` file runs independently and fails on an assertion error.

Run all tests:

```bash
for t in tests/test_*.py; do
  echo "== $t =="
  python "$t"
done
python tests/security_audit.py
```

## Fixed release demo

`tests/test_v210_release_plausibility.py` creates the following independent reference household:

| Item | Value |
|---|---:|
| Giro opening | 2,000.00 EUR |
| Savings opening | 5,000.00 EUR |
| Cash opening | 200.00 EUR |
| Salary | +3,000.00 EUR |
| Rent | -1,000.00 EUR |
| Electricity | -120.00 EUR |
| Groceries | -400.00 EUR |
| Leisure | -100.00 EUR |
| Internal transfer Giro -> Savings | 500.00 EUR |
| Refund | +50.00 EUR |
| Insurance | -150.00 EUR |

Independent expected results:

```text
Opening wealth = 7,200.00 EUR
Income         = 3,050.00 EUR
Expenses       = 1,770.00 EUR
Surplus        = 1,280.00 EUR
Closing wealth = 8,480.00 EUR
```

Per-account closing balances:

```text
Girokonto  = 2,880.00 EUR
Tagesgeld  = 5,500.00 EUR
Bargeld    =   100.00 EUR
Total      = 8,480.00 EUR
```

The 500 EUR internal transfer must not alter household income, expenses or total wealth.

Constant +1,280 EUR monthly surplus reference:

```text
1 month  =  9,760.00 EUR
3 months = 12,320.00 EUR
6 months = 16,160.00 EUR
12 months = 23,840.00 EUR
```

The release test also verifies German decimal CSV parsing (`1234,56`), exact cent arithmetic and duplicate import detection.

## Covered regression areas

The existing suite covers accounts, transactions, recurring series, month-opening corrections, planning, forecast, liquidity, cashflow warnings, budgets, CSV import, attachments, reconciliation, audit chain, transfers, payee presets, migrations, pagination, year views, UI source checks, light-mode contrast, multi-user auth, multi-book isolation, roles, backups, public-mode hardening, investment layout and mobile responsiveness.

## Limits

Automated tests reduce regression risk but do not prove absence of every possible defect. The internal security audit is not an independent penetration test. Dependency vulnerability scans require external vulnerability databases and are run separately by `scripts/security-scan.sh` / CI where available.
