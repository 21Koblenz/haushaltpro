from pathlib import Path

root = Path(__file__).resolve().parents[1]
main = (root / "app/main.py").read_text()
dockerfile = (root / "Dockerfile").read_text()
compose = (root / "docker-compose.yml").read_text()
changelog = (root / "CHANGELOG.md").read_text()

assert 'APP_VERSION = "0.21.4"' in main
assert 'python:3.12.14-alpine3.24@sha256:' in dockerfile
assert 'pip==26.2' in dockerfile
assert 'python:3.12-slim-bookworm' not in dockerfile
assert 'image: 21koblenz/haushaltpro:latest' in compose
assert '## v0.21.4 - 2026-09-14' in changelog
print("v0.21.4 security-release invariants: PASS")
