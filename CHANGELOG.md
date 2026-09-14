# Changelog

## Unreleased

## v0.21.6 - 2026-09-14

Runtime-security maintenance release following v0.21.5. Application logic and database semantics are unchanged; no database migration is required.

### Security / Container

- Removes Python packaging/build tooling (`pip`, `setuptools`, `wheel`, `pkg_resources` and `ensurepip`) from the final runtime filesystem after dependencies have been installed and validated.
- This removes the unnecessary runtime packages that Docker Scout associated with CVE-2026-23949 (`jaraco-context`), CVE-2025-47273 and CVE-2026-59890 (`setuptools`), GHSA-6v7p-g79w-8964 and CVE-2026-57585 (`msgpack`), and CVE-2026-24049 (`wheel`).
- `pip check` still runs before packaging tools are removed.
- A post-removal smoke test verifies FastAPI, Starlette, Uvicorn, Pydantic, Argon2, Cryptography, multipart parsing and SQLCipher 4.
- Existing non-root execution, read-only container hardening, dropped capabilities, SQLCipher, SBOM and provenance controls remain enabled.

### Validation

- Full application regression suite and JavaScript syntax check run before release.
- Static security audit validates the runtime-tooling removal.
- Docker builds and SQLCipher runtime checks run on both `linux/amd64` and `linux/arm64`.
- Docker Scout scans both locally built architecture images for Critical/High findings and blocks the release if any remain.


## v0.21.5 - 2026-09-14

Security-maintenance release following v0.21.4. Application and database semantics are unchanged.

### Security / Dependencies

- Alpine packages are upgraded during the image build with `apk upgrade --no-cache` so fixed `libuuid` / `util-linux` packages replace vulnerable versions from the pinned base snapshot.
- `msgpack` is updated to 1.2.1 in the container build.
- `setuptools` is updated to 78.1.1 in the container build.
- `pip check` now runs during the Docker build and fails on broken Python dependency resolution.
- Existing non-root execution, SQLCipher, SBOM and provenance controls remain enabled.

### Validation

- Full application regression suite and JavaScript syntax check run before publication.
- Static security audit verifies the new remediation controls.
- Docker builds and SQLCipher runtime checks run on both `linux/amd64` and `linux/arm64`.
- Docker Scout reports Critical and High CVEs for the published multi-architecture image.


## v0.21.4 - 2026-09-14

Security-focused Docker release. Application and database semantics are unchanged.

### Security / Container

- Runtime base changed from Debian Bookworm to the smaller official Python 3.12.14 / Alpine 3.24 image, pinned by its multi-architecture SHA-256 index digest.
- `pip` in the runtime image is upgraded to 26.2 to remove Scout findings with an available pip fix.
- Non-root execution with UID/GID 10001 remains enforced.
- Docker Hub publishing includes SBOM and provenance attestations.
- Docker Scout scans the published image for Critical and High CVEs.

### Deployment

- The default `docker-compose.yml` consumes `21koblenz/haushaltpro:latest` from Docker Hub.
- Local source builds remain available through `docker-compose.dev.yml`.
- Standard updates now use `docker compose pull` followed by `docker compose up -d`.

### Validation

- Full application regression suite passed on the security-hardening branch.
- Static security audit passed.
- Docker builds and SQLCipher runtime checks passed on both `linux/amd64` and `linux/arm64`.
- The v0.21.4 release workflow repeats regression, static-security, architecture and SQLCipher checks before publishing.


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
