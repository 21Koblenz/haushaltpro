from pathlib import Path

# Release-level invariants for the v0.21.1 patch release.
root=Path(__file__).resolve().parents[1]
main=(root/"app/main.py").read_text(encoding="utf-8")
compose=(root/"docker-compose.yml").read_text(encoding="utf-8")
install=(root/"docs/INSTALLATION.md").read_text(encoding="utf-8")
changelog=(root/"CHANGELOG.md").read_text(encoding="utf-8")
assert 'APP_VERSION = "0.21.1"' in main
assert 'image: haushaltpro:' not in compose
assert '# Installation / Deployment - v0.21.1' in install
assert 'docker.io/library/haushaltpro:latest' in install
assert '## v0.21.1 - 2026-09-12' in changelog
assert 'creamowl25@primal.net' in changelog
print('v0.21.1 release metadata + Portainer regression: PASS')
