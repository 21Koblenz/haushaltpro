from pathlib import Path

root = Path(__file__).resolve().parents[1]
main = (root / "app/main.py").read_text()
dockerfile = (root / "Dockerfile").read_text()
changelog = (root / "CHANGELOG.md").read_text()

assert ('APP_VERSION = "0.21.6"' in main or ('APP_VERSION = "0.21.8"' in main or 'APP_VERSION = "0.21.9-dev.3"' in main))
assert 'python -m pip check' in dockerfile
assert '/usr/local/lib/python3.12/site-packages/pip' in dockerfile
assert '/usr/local/lib/python3.12/site-packages/setuptools' in dockerfile
assert '/usr/local/lib/python3.12/site-packages/wheel' in dockerfile
assert '/usr/local/lib/python3.12/ensurepip' in dockerfile
assert 'import fastapi,starlette,uvicorn,pydantic,argon2,cryptography,multipart' in dockerfile
assert 'PRAGMA cipher_version' in dockerfile
assert '## v0.21.6 - 2026-09-14' in changelog
for cve in (
    'CVE-2026-23949',
    'CVE-2025-47273',
    'GHSA-6v7p-g79w-8964',
    'CVE-2026-57585',
    'CVE-2026-24049',
    'CVE-2026-59890',
):
    assert cve in changelog
print("v0.21.6 runtime-security invariants: PASS")
