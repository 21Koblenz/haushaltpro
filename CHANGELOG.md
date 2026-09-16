# Changelog

## v0.21.9-dev.3 - 2026-09-16 (prerelease)

### Deutsch

- Offene Zahlungen, Verbindlichkeiten und Forderungen mit Fälligkeit, Überfälligkeit, Status und Teilzahlungen. Vorhandene Buchungen zuordnen oder eine neue Zahlung atomar erstellen; keine doppelte Kontobewegung.
- Schutz vor Überzahlung und widersprüchlichen Buchungsänderungen. Storno/Löschung öffnet zugeordnete Restbeträge wieder. Haushaltsbuch-/Benutzerrechte und idempotente Offline-Wiederholung gelten auch für die neuen Einträge.
- CSV-Export nach Zeitraum, Konto, Kategorie, Status und Suche, mit centgenauen Split-Zeilen sowie sicher behandelten Textfeldern. Fixkosten-Jahresplan mit Monatsspalten, Fälligkeiten und verschobenen Serienterminen.
- Eingeklappte Buchungskarten mit Name, Wiederholungssymbol, Datum, Betrag und Konto; Details und Aktionen per Antippen oder Tastatur öffnen.
- Additive SQLCipher-Migration auf Schema 28; bisherige Daten bleiben erhalten.

### English

- Payables, receivables, partial payments and overdue highlighting. Link existing bookings or create a single payment atomically with allocation guards, permissions and safe offline replay.
- Filtered CSV exports, cent-exact split rows and monthly/yearly fixed-cost plans respecting effective recurring dates.
- Collapsed mobile booking cards with keyboard-accessible details and actions. Additive schema 28 migration.

### Validation and scope

- 87 Python regression scripts, 16 JavaScript tests and 52 static security checks passed locally, plus compile/syntax checks. npm audit reports no known vulnerabilities.
- Real encrypted migration and DOM interaction tests included. Interactive visual browser checks were blocked by local-URL access restrictions.
- Open items are EUR-only and affect cash/projections through their account bookings. Fixed-cost exports are plan values. See [dev.3 release notes](docs/RELEASE-NOTES-v0.21.9-dev.3.md) for update and manual checks.

## v0.21.9-dev.2 - 2026-09-16 (prerelease)

### Deutsch

- Einzelne wiederkehrende Buchungen lassen sich auf ein anderes Datum verschieben, auch über Monats- und Jahresgrenzen. Die ursprüngliche Serienzuordnung verhindert doppelte Termine; Planung, Fixkosten, Prognose und Journal folgen dem tatsächlichen Buchungsdatum.
- Offline-Einträge werden vor dem Senden dauerhaft gespeichert. Verlorene Antworten, parallele Wiederholungen, abgelaufene Sitzungen und Benutzer-/Haushaltsbuchwechsel sind abgesichert. Offline-Speichern schließt den Dialog direkt, ohne nachfolgende Serverabfragen abzuwarten.
- Serverstatus wird anhand einer echten Antwort geprüft; Fehlerseiten gelten nicht als erfolgreiche Verbindung. Alte Warteschlangen ohne Benutzerzuordnung werden erst nach ausdrücklicher Zuordnung synchronisiert.
- Wiederholte Berechnungen innerhalb einer Leseanfrage werden wiederverwendet; die monatliche Planung benötigt im 10.000-Buchungen-Test 197 statt 365 SQL-Abfragen.
- Additive SQLCipher-Schemamigration 26 → 27; vorhandene Buchungen und Betragsausnahmen bleiben erhalten.

### English

- Reschedule a single recurring occurrence across month/year boundaries while retaining its original schedule identity. Journal, planning, fixed costs and forecasts use the effective booking date.
- Persist new offline writes before sending. Retry safely after lost replies, concurrent requests and expired sessions; isolate queued writes by user and book, including cross-tab switches.
- Validate server reachability, avoid redundant IndexedDB reads, and reuse calculations within a GET request. Monthly planning uses 197 rather than 365 SQL statements in the 10,000-transaction probe.
- Additive schema 26 → 27 migration tested with the actual SQLCipher runtime.

### Validation and scope

- 84 Python regression scripts, 9 JavaScript queue tests and 52 static security checks passed locally; Python compile and JavaScript syntax checks passed.
- Offline mode covers new transactions, transfers and recurring series after the app has been loaded online. Full offline cold start and offline edits/deletes are not included. Pending payloads remain unencrypted in the browser's IndexedDB.
- Dev tags publish `:dev` and the explicit prerelease version; they do not update stable `:latest` or `:0.21`.
- Browser UI validation could not run in this environment because the browser blocked the local test URL. See the manual checklist in `docs/OFFLINE-DEV.md`.

## Earlier changes included in v0.21.9-dev.2

### Fixed

- The current-month analysis now includes known/planned bookings through month end, including materialized recurring expenses and income. Historical months and yearly analysis remain actual-only.
- Offline queue for new bookings, transfers and recurring series: entries are stored locally when the server is unreachable and synchronized automatically after reconnecting.
- Client-generated idempotency keys prevent duplicate financial entries when a request reached the server but the response was lost.

### Changed

- The dedicated “+ Wiederkehrende Buchung” entry point remains available and now supports saved/free-text payees. The payee is stored on the recurring series and propagated to generated planned transactions.

- The top bar now shows live server reachability, pending offline entries and synchronization state; clicking the indicator triggers an immediate connectivity/sync check.

### Added

- Transfers can now repeat with the same calendar interval model as recurring bookings (daily, weekly, monthly, quarterly, half-yearly, yearly or custom). Recurring transfers remain neutral in income/expense analysis while moving the source and destination account forecasts.

- Recurring transactions support quarterly and half-yearly presets plus arbitrary calendar intervals such as every 10 days, 2 weeks, 5 months or 2 years. Existing recurring series keep their previous rhythm with an interval multiplier of 1.


## v0.21.8 - 2026-09-14

Bugfix and deployment-channel release. No database migration is required.

### Fixed

- Saved payees in the transaction dialog now use a real native selection control instead of relying on browser-dependent `datalist` behaviour.
- Selecting a saved payee fills the normal payee field used to save the transaction; free-text entry remains available for new payees.
- Added a dedicated regression guard for the saved-payee selector.

### Deployment

- Every push to `main` publishes `21koblenz/haushaltpro:dev` for `linux/amd64` and `linux/arm64`, providing a separate test channel for Portainer and other Docker deployments.
- Stable `latest` remains reserved for releases; development builds cannot overwrite the stable release tag.
- Removed obsolete preview-by-preview notes from the README; historical implementation details remain in this changelog.

### Validation

- Full regression suite passes, including the saved-payee selector regression.
- JavaScript syntax checks and the static security audit pass.
- Docker builds and SQLCipher runtime checks pass on both `linux/amd64` and `linux/arm64`.
- Published release images remain protected by Docker Scout Critical/High gates on both architectures and PyPI Medium+ gates.

## v0.21.7 - 2026-09-14

Role-boundary and responsive-UI maintenance release. No database migration is required.

### Fixed

- Users created or reset with a temporary password can now change their own password regardless of their household role. Temporary passwords are marked as requiring a change, and the UI guides the user directly to the self-service password form.
- Self-service password changes are protected by authentication and CSRF checks but are no longer incorrectly tied to household write permissions.
- Editors no longer see or access the audit timeline, storage/data-maintenance tools, bulk transaction deletion, or user/rights administration. The corresponding API endpoints are owner/admin protected as well.
- Editors cannot rename or delete household books.
- Editors may request a new household book. An owner of the current household must approve or reject the request; after approval the approver is owner and the requester remains editor.
- The bookings table no longer relies on horizontal scrolling: wide screens use a wrapped fixed layout, while smaller devices automatically switch to responsive booking cards.
- Asset cache keys are bumped so browsers load the new JavaScript and CSS immediately after updating.

### Validation

- Added an integration regression covering temporary-password change, editor permission boundaries, household-book approval and delete/rename denial.
- Full regression suite and static security audit run before release.
- Docker builds and SQLCipher runtime checks run on both `linux/amd64` and `linux/arm64`.
- Docker Hub publishing remains protected by Scout Critical/High gates on both architectures and PyPI Medium+ gates.

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
