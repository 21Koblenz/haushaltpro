# Testing / Plausibility

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

## v0.21.9-dev.2

Run JavaScript offline-queue tests with Node.js 22 or later:

```bash
npm ci --ignore-scripts --no-audit --no-fund
npm test
```

`tests/test_recurring_occurrence_dates.py` checks independent cent totals after same-month, cross-month and cross-year moves, repeated edits, series version cutoffs, regeneration, reset and cache freshness. `tests/test_occurrence_encrypted_migration.py` upgrades a real encrypted schema-26 database twice and checks preservation and integrity. `tests/test_offline_sync.py` includes concurrent replay with separate connections and wrong-user/book rejection.

Local result: 84 Python scripts, 9 JavaScript tests, 52 static security checks passed. The earlier date-sensitive v0.10.3 regression now fixes its reference date explicitly.

Performance probe (10,000 transactions, 4,000 splits, 8 accounts, 80 series; local SQLite diagnostic without persistent view cache):

| View | SQL before | SQL after | Median before (ms) | Median after (ms) |
|---|---:|---:|---:|---:|
| Monthly planning | 365 | 197 | 83.40 | 65.90 |
| Monthly dashboard | 580 | 540 | 70.49 | 65.87 |
| Annual planning | 533 | 533 | 73.14 | 74.82 |

Timing differences depend on the runner. Query count reduction is deterministic; no cross-request financial calculation cache was added. Interactive browser verification was blocked by local-URL access restrictions in the test environment.

## v0.21.9-dev.3

Use Python 3.12 and Node.js 22.22.2+ (or 24.15.0+) for the current tests. Install Python dependencies with `python -m pip install -r requirements.txt httpx2==2.12.0`, then use the commands above. JavaScript tests now include jsdom interaction checks; they do not launch a browser.

- `test_open_items.py`: independent 200/50/150 EUR balances, cash neutrality when linking/unlinking, payment-direction and allocation bounds, cancellation/deletion, protected edits, concurrent idempotent retries, currency isolation and audit integrity.
- `test_open_items_permissions.py`: real login, CSRF, viewer/editor rights and household isolation for open items and both CSV endpoints.
- `test_csv_exports.py`: exact cent totals, BOM and safe formula handling, pagination-independent filters, split-category exports, shifted monthly/yearly occurrences, and agreement with monthly fixed-cost planning.
- `test_occurrence_encrypted_migration.py`: real SQLCipher schema 26 → 28 upgrade and repeated migration, preserving existing occurrences and new open items.
- `payments-ui.test.cjs`: native collapsed details/summary, visible summary fields, recurring icons, escaped content, read-only actions, overdue partial items, lazy payment loading, actual dialog form submissions, retry pagination and CSV downloads.
- `offline-sync.test.cjs`: lost-reply and single-replay coverage also for new open items and partial payments.

Local result: all 87 Python regression scripts, 16 JavaScript tests and 52 static security checks pass. Python compilation and JavaScript syntax checks pass. npm audit reports zero known vulnerabilities for the test dependencies.

The browser rejected the local test URL with `ERR_BLOCKED_BY_CLIENT`. DOM checks passed, but visual mobile layout and browser-native date/download controls still need the manual checks in the dev.3 release notes.


## v0.21.9-dev.4

`tests/overview-ui.test.cjs` exercises the shipped recurring/account renderers and action bindings in jsdom. It checks collapsed defaults, independently specified account balances, cutoff labels, viewer permissions and escaping.

Chart tests use a mocked canvas context to inspect drawing coordinates at widths of 280, 320, 360, 390, 768 and 1100 CSS pixels, with months of 28–31 days. Every date stays selectable, including first/last days; opening and negative balances remain represented. Tests cover pointer/range input, resize observers, empty/single-point data, yearly selection, analysis bars and the actual i18n script. These are DOM and drawing-command checks, not browser pixel comparisons.

Local result: all 87 Python scripts, 23 JavaScript tests and 52 static security checks passed, with compile/syntax checks. The browser rejected the local URL with `ERR_BLOCKED_BY_CLIENT`; use the release notes' smartphone checklist for visual verification.


## v0.21.9-dev.5

`tests/report-flow-ui.test.cjs` adds seven executable jsdom/SVG checks using the shipped page and renderers: saved/default view selection, reload and month/year changes; independently specified cent totals with surplus/deficit/no income; layout at 240–1280 CSS px; touch/keyboard and resize selection; 60 categories with grouping, tiny/large amounts and escaping; actual i18n; and unavailable preference storage. Group totals and every category remain visible through the appropriate summary/list. The account DOM test now requires the month-end value, including its negative sign, in both collapsed overviews.

All 87 Python regression scripts, 30 JavaScript tests and 52 static security checks passed locally, as did Python compilation, JavaScript syntax and whitespace checks. SVG output was rasterized and inspected at narrow/desktop widths in dark/light themes; a clipped narrow-desktop label was corrected. This verifies SVG output, not full browser CSS layout. Local browser access was previously blocked by `ERR_BLOCKED_BY_CLIENT`; the smartphone checklist is in the dev.5 release notes.

## v0.21.9-dev.6

`tests/privacy-ui.test.cjs` adds nine interaction checks using the shipped privacy module, forms, renderers and language catalogs. Coverage includes signed German/English and compact EUR/percent formats; date/count preservation; saved state and cross-tab events; blocked preference storage; dynamic DOM/SVG text, titles, accessible progress and latest-value restoration; account/transaction/recurring/open-item/investment views; actual form data, validation and explicit reveal; signed-money UI integration; every canvas renderer and hover labels; both cash-flow views; language changes without observer loops; native notices and unmodified CSV contents.

All 87 Python regression scripts, 39 JavaScript tests and 52 static security checks passed locally, with compile, syntax and whitespace checks. The English static-coverage check also includes the new controls. The interrupted local Python environment required dependency reinstallation before the successful complete regression run. Tests inspect DOM behavior and canvas drawing commands; they do not establish browser pixel correctness. The light-mode background uses the existing theme variables with selectors that override generic button styling. See dev.6 release notes for visual smartphone checks.

## v0.21.9 stable

The stable suite contains 89 Python regression scripts, 39 JavaScript tests and 52 static security checks. Compilation, JavaScript syntax, workflow YAML/shell syntax and whitespace checks are included. The project owner confirmed that dev.6 works before stable promotion; no application behavior beyond the version/cache-key change is introduced by the stable packaging.

- `test_stable_release_migration.py` builds a real encrypted database using the exact `app/db.py` snapshot from v0.21.8 (`ff52393d59ada932d2799d8a3ea1434a6065a780`, stored as `tests/fixtures/db_v0218.py`). It upgrades schema 22 directly to 28 twice and verifies account cents, an existing transaction/payee, recurrence identity and interval default, amount exceptions, occurrence history, a month-opening correction, new tables and integrity/foreign-key checks.
- `test_dev_release_channels.py` executes ten event/input combinations from the actual publishing script, including a stable version mirrored onto `dev` and the stable reusable workflow call. Development publication must not move stable tags or create a stable-named prerelease; release jobs depend on CI preparation and Docker/security success.
- `test_release_cleanup.py` creates real local bare/working Git repositories and verifies archive preservation, repeat runs, protected names, changed remote heads and conflicting archive tags. Cleanup uses an atomic push and an exact expected-commit lease.

The stable workflow also waits for CI on the released Main commit, reuses the AMD64/ARM64 Docker publication and four Scout gates, and publishes source archives with SHA-256 checksums. Visual browser checks retain the limitations documented above.
