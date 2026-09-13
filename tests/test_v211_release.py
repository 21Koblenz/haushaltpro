from pathlib import Path

# Historical v0.21.1 invariants must remain true in later releases.
root=Path(__file__).resolve().parents[1]
main=(root/"app/main.py").read_text(encoding="utf-8")
compose=(root/"docker-compose.yml").read_text(encoding="utf-8")
changelog=(root/"CHANGELOG.md").read_text(encoding="utf-8")
assert 'APP_VERSION = "0.21.3"' in main
assert 'image: haushaltpro:' not in compose
assert '## v0.21.1 - 2026-09-12' in changelog
assert 'creamowl25@primal.net' in changelog
print('v0.21.1 historical release invariants: PASS')
