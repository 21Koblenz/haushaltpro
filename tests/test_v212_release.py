from pathlib import Path

# Historical v0.21.2 dashboard opening-balance fix must remain documented in later releases.
root = Path(__file__).resolve().parents[1]
main = (root / "app/main.py").read_text(encoding="utf-8")
changelog = (root / "CHANGELOG.md").read_text(encoding="utf-8")
compose = (root / "docker-compose.yml").read_text(encoding="utf-8")
assert ('APP_VERSION = "0.21.3"' in main or ('APP_VERSION = "0.21.4"' in main or ('APP_VERSION = "0.21.5"' in main or ('APP_VERSION = "0.21.6"' in main or ('APP_VERSION = "0.21.8"' in main or 'APP_VERSION = "0.21.9-dev.3"' in main)))))
assert '## v0.21.2 - 2026-09-13' in changelog
assert 'opening balance exactly on the account start date' in changelog
assert 'Month-opening corrections remain authoritative' in changelog
assert 'image: haushaltpro:' not in compose
print('v0.21.2 historical release invariants: PASS')
