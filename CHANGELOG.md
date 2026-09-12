# Changelog

## Unreleased

### Fixed

- Docker/Portainer builds now support both `linux/amd64` and `linux/arm64` by switching from the x86-only `sqlcipher3-binary==0.6.0` package to `sqlcipher3==0.6.2`.
- CI now builds the Docker image for both architectures and verifies that SQLCipher 4 starts successfully inside each image.
- New and corrected account balances can now be entered reliably as negative values on mobile devices; signed balance fields support decimal comma/point input and an explicit `±` control.

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
