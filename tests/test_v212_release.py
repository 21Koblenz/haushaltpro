from pathlib import Path

root = Path(__file__).resolve().parents[1]
main = (root / "app/main.py").read_text(encoding="utf-8")
changelog = (root / "CHANGELOG.md").read_text(encoding="utf-8")
install = (root / "docs/INSTALLATION.md").read_text(encoding="utf-8")
compose = (root / "docker-compose.yml").read_text(encoding="utf-8")

assert 'APP_VERSION = "0.21.2"' in main
assert '## v0.21.2 - 2026-09-13' in changelog
assert 'opening balance exactly on the account start date' in changelog
assert 'Month-opening corrections remain authoritative' in changelog
assert '# Installation / Deployment - v0.21.2' in install
assert 'image: haushaltpro:' not in compose

print('v0.21.2 release metadata + dashboard opening-balance regression: PASS')
