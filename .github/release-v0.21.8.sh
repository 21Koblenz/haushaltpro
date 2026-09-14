#!/usr/bin/env bash
set -euo pipefail

VERSION="0.21.8"
TAG="v${VERSION}"
DATE="2026-09-14"

if git rev-parse -q --verify "refs/tags/${TAG}" >/dev/null; then
  echo "Tag ${TAG} already exists; refusing to overwrite it."
  exit 1
fi

python - <<'PY'
from pathlib import Path

replacements = {
    Path("app/main.py"): [('APP_VERSION = "0.21.7"', 'APP_VERSION = "0.21.8"')],
    Path("README.md"): [("# HaushaltPro v0.21.7", "# HaushaltPro v0.21.8")],
    Path("static/index.html"): [("?v=0.21.7", "?v=0.21.8")],
    Path("tests/test_i18n_account_month_selfheal.py"): [("?v=0.21.7", "?v=0.21.8")],
    Path("tests/test_preview14_flow_style_cache.py"): [("v=0.21.7", "v=0.21.8")],
}
for path, pairs in replacements.items():
    text = path.read_text(encoding="utf-8")
    for old, new in pairs:
        if old not in text:
            raise SystemExit(f"Expected release marker not found in {path}: {old}")
        text = text.replace(old, new)
    path.write_text(text, encoding="utf-8")

# Historical regression files intentionally allow all known application versions.
# Add this release to every one-line APP_VERSION allowlist instead of maintaining
# a growing hand-written list of files in the release process.
for path in Path("tests").glob("test_*.py"):
    text = path.read_text(encoding="utf-8")
    lines = text.splitlines(keepends=True)
    changed = False
    result = []
    for line in lines:
        if "main.APP_VERSION in {" in line and "'0.21.8'" not in line:
            if "}" not in line:
                raise SystemExit(f"Unsupported multi-line APP_VERSION allowlist: {path}")
            line = line.replace("}", ",'0.21.8'}", 1)
            changed = True
        result.append(line)
    if changed:
        path.write_text("".join(result), encoding="utf-8")

changelog = Path("CHANGELOG.md")
text = changelog.read_text(encoding="utf-8")
heading = "## v0.21.8 - 2026-09-14"
if heading in text:
    raise SystemExit("v0.21.8 already exists in CHANGELOG.md")
marker = "## Unreleased\n"
if marker not in text:
    raise SystemExit("Unreleased marker missing from CHANGELOG.md")
entry = r'''

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
'''
changelog.write_text(text.replace(marker, marker + entry, 1), encoding="utf-8")
PY

grep -F 'APP_VERSION = "0.21.8"' app/main.py
grep -F '# HaushaltPro v0.21.8' README.md
grep -F '## v0.21.8 - 2026-09-14' CHANGELOG.md
test "$(grep -o 'v=0.21.8' static/index.html | wc -l)" -ge 5
grep -F '?v=0.21.8' tests/test_i18n_account_month_selfheal.py
grep -F 'v=0.21.8' tests/test_preview14_flow_style_cache.py

# Every legacy APP_VERSION allowlist must now accept this release.
python - <<'PY'
from pathlib import Path
for path in Path("tests").glob("test_*.py"):
    for line in path.read_text(encoding="utf-8").splitlines():
        if "main.APP_VERSION in {" in line and "'0.21.8'" not in line:
            raise SystemExit(f"Missing 0.21.8 in APP_VERSION guard: {path}")
PY

git diff --check
python -m compileall -q app tests
sudo install -d -o "$(id -u)" -g "$(id -g)" /app
for test_file in tests/test_*.py; do
  echo "== ${test_file} =="
  python "${test_file}"
done
node --check static/app.js
node --check static/i18n.js
node --check static/ui-enhancements.js
python tests/security_audit.py

git config user.name "github-actions[bot]"
git config user.email "41898282+github-actions[bot]@users.noreply.github.com"
git add app/main.py README.md CHANGELOG.md static/index.html tests/test_*.py
git commit -m "release: v0.21.8"
RELEASE_SHA="$(git rev-parse HEAD)"
git push origin HEAD:main

mkdir -p dist
git archive --format=tar --prefix="haushaltpro-${TAG}/" "${RELEASE_SHA}" | gzip -9 > "dist/haushaltpro-${TAG}.tar.gz"
git archive --format=zip --prefix="haushaltpro-${TAG}/" -o "dist/haushaltpro-${TAG}.zip" "${RELEASE_SHA}"
(
  cd dist
  sha256sum "haushaltpro-${TAG}.tar.gz" "haushaltpro-${TAG}.zip" > "SHA256SUMS-${TAG}.txt"
)

cat > /tmp/release-notes.md <<'EOF'
Bugfix and deployment-channel release. **No database migration is required.**

### Fixed
- Saved payees in the transaction dialog now use a reliable native selection control; choosing one fills the transaction's normal payee field.
- Free-text payee entry remains available for new recipients.
- Added a regression guard for the saved-payee selector.

### Deployment
- `21koblenz/haushaltpro:dev` is now the automatic test channel for every push to `main` on amd64 and arm64.
- `latest` remains release-only.
- Obsolete Preview sections were removed from the README; history remains in `CHANGELOG.md`.

### Validation
- Full regression suite and static security audit passed before tagging.
- JavaScript syntax checks passed.
- Release Docker images are built multi-arch with SBOM/provenance and protected by Docker Scout gates.
EOF

git tag -a "${TAG}" "${RELEASE_SHA}" -m "HaushaltPro ${TAG}"
git push origin "${TAG}"

gh release create "${TAG}" \
  --target "${RELEASE_SHA}" \
  --title "HaushaltPro ${TAG}" \
  --notes-file /tmp/release-notes.md \
  "dist/haushaltpro-${TAG}.tar.gz" \
  "dist/haushaltpro-${TAG}.zip" \
  "dist/SHA256SUMS-${TAG}.txt"

gh workflow run docker-publish.yml -f version="${VERSION}"

echo "Released ${TAG} from ${RELEASE_SHA} and dispatched Docker publication."
