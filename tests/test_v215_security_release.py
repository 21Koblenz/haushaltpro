from pathlib import Path

root = Path(__file__).resolve().parents[1]
main = (root / "app/main.py").read_text()
dockerfile = (root / "Dockerfile").read_text()
compose = (root / "docker-compose.yml").read_text()
changelog = (root / "CHANGELOG.md").read_text()

assert ('APP_VERSION = "0.21.5"' in main or ('APP_VERSION = "0.21.6"' in main or 'APP_VERSION = "0.21.8"' in main))
assert 'python:3.12.14-alpine3.24@sha256:' in dockerfile
assert 'apk upgrade --no-cache' in dockerfile
assert 'pip==26.2' in dockerfile
# v0.21.5 originally pinned these packages to remediate Scout findings.
# Later hardening may remove the packaging toolchain entirely from runtime,
# which is stronger than keeping the patched but unnecessary packages present.
assert ('msgpack==1.2.1' in dockerfile) or ('/usr/local/lib/python3.12/site-packages/pip' in dockerfile)
assert ('setuptools==78.1.1' in dockerfile) or ('/usr/local/lib/python3.12/site-packages/setuptools' in dockerfile)
assert 'pip check' in dockerfile
assert 'image: 21koblenz/haushaltpro:latest' in compose
assert '## v0.21.5 - 2026-09-14' in changelog
print("v0.21.5 security-release invariants: PASS")
