# Release Test Report - HaushaltPro v0.21.0

Date: 2026-09-12

## Source baseline

The supplied `haushaltpro-v0.11.2` package was used as the application baseline. No functional change was made before its existing test suite was executed.

## Baseline result

- Existing automated test files: **50/50 PASS**.
- Static security audit: **45/45 PASS**.
- Syntax/compile check: PASS.

The baseline suite includes the v0.11.2 mobile transaction layout test and v0.11.0 public security runtime test.

## v0.21.0 release changes

The application version was changed to `0.21.0`; release/open-source documentation, AGPL notice, source link and CI files were added. A fixed-data release plausibility test was added as `tests/test_v210_release_plausibility.py`.

## Release demo result

`tests/test_v210_release_plausibility.py`: **PASS**.

Verified expected values:

- opening wealth: 7,200.00 EUR;
- income: 3,050.00 EUR;
- expenses: 1,770.00 EUR;
- surplus: 1,280.00 EUR;
- closing wealth: 8,480.00 EUR;
- account balances: 2,880.00 / 5,500.00 / 100.00 EUR;
- internal 500 EUR transfer remains neutral to household totals;
- 12-month cumulative +1,280 EUR/month scenario difference: 15,360.00 EUR;
- independent 12-month reference balance: 23,840.00 EUR;
- German CSV decimal import and duplicate detection: PASS.

## Final v0.21.0 result

After the version, documentation, UI source-link and release-test changes were applied, the complete application suite was executed again:

- Application test files: **51/51 PASS**.
- Static security audit: **45/45 PASS**.
- Python syntax/compile check: **PASS**.

Three intermediate failures during release preparation were caused by old tests/documentation assertions that still whitelisted earlier version numbers or required exact README compatibility phrases. The application calculation/runtime logic was not changed to make those checks pass; the release metadata/test assumptions were updated to the new version.

## Environment note

The local execution environment used for this preparation did not provide a Docker daemon. Docker image build and exact pinned dependency installation are therefore delegated to the repository CI workflow after push. Local tests use the project's existing sqlite test shim where the test suite intentionally isolates application logic from SQLCipher runtime packaging.

## Security scope

`tests/security_audit.py` is an internal static/code/configuration audit. It is not an external penetration test or security certification.
