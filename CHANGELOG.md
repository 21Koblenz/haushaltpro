# Changelog

## Unreleased

## v0.21.3 - 2026-09-13

Stable release of the tested v0.21.x preview line.

### Added

- German and English user interface with local translation catalogs and locale-aware number/date/currency formatting.
- Complete recurring-contract schedule materialization in Bookings, including finite schedules, rolling horizon for open-ended contracts, one-occurrence overrides and series changes from an effective date.
- New money-flow visualization for monthly and yearly analysis with category → group flows for income, expenses and savings.
- Fast light/dark theme switch in the top bar.

### Changed

- Money-flow category arrows now use explicit SVG geometry. Their direction, length and thickness follow the real category share and cannot be flattened by CSS.
- Category names remain fully visible above their arrows.
- Income, expense and savings groups scale independently to their own 100% total.
- Monthly analysis now also shows savings rate and average savings per day; yearly analysis keeps average savings per month.
- Account/month selectors self-heal if browser state or stale assets leave invalid options behind.

### Fixed

- Correct arrow direction for the money-flow card.
- Correct proportional arrow sizing for very small and very large categories.
- Forecast double counting of already materialized recurring transactions.
- Monthly recurring overrides now update the materialized booking and revert cleanly.
- Existing v0.21.2 mid-month opening-balance and negative-balance fixes remain included.

### Validation

- Preview 24 was manually confirmed in the target environment before release.
- Full application regression suite re-run for the v0.21.3 release candidate.
- Static security audit re-run for the v0.21.3 release candidate.
- Python and JavaScript syntax checks re-run for the v0.21.3 release candidate.

## v0.21.2 - 2026-09-13

### Fixed

- Accounts that begin after the first day of a month now contribute their opening balance exactly on the account start date. This fixes Dashboard `Aktueller Kontostand` and `Prognose Monatsende` showing `0,00 €` for newly created mid-month accounts, including negative opening balances.
- Month-opening corrections remain authoritative and are not combined with the original account opening balance.

## v0.21.1 - 2026-09-12

### Fixed

- New accounts now accept negative opening balances reliably, including on mobile devices. Signed-money fields accept decimal comma or decimal point and include an explicit `±` control.
- Added a regression test that verifies `-1234.56` is stored as `-123456` cents and remains negative across account balance calculations.
- Portainer documentation now explains why `haushaltpro:latest` must not be re-pulled from Docker Hub for a locally built Git stack.
- Removed the local `image: haushaltpro:0.21.0` declaration from the repository Compose file so build-based deployments do not accidentally look like registry-pull deployments.
- Docker/Portainer builds support both `linux/amd64` and `linux/arm64` by using `sqlcipher3==0.6.2`.
- CI builds the Docker image for both architectures and verifies that SQLCipher 4 starts successfully inside each image.

### Added

- Value-for-Value footer with the Lightning address `creamowl25@primal.net`.
- Theme-aware local Lightning QR code for dark and light mode.

## v0.21.0 - 2026-09-12

First public open-source release prepared for `21Koblenz/haushaltpro`.

### Included

- complete existing HaushaltPro application state through the previous v0.11.2 feature set;
- responsive mobile transaction/recurring layouts;
- local/LAN, VPN and public HTTPS deployment documentation in German and English;
- AGPL-3.0-or-later copyleft licensing;
- explicit Vibe Coding / AI-assisted development disclosure;
- GitHub Actions CI for regression tests, security checks and Docker build;
- v0.21.0 fixed-data release plausibility test;
- source-code link and AGPL notice in the application footer.

### Validation

- 50/50 pre-existing automated test files passed before the version bump.
- 45/45 static security audit checks passed before the version bump.
- v0.21.0 release demo/plausibility test passed after the version bump.
- Full post-change regression results are recorded in `docs/TEST-REPORT-v0.21.0.md`.
