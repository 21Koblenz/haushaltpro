from pathlib import Path
import re

root = Path(__file__).resolve().parents[1]

main_path = root / 'app' / 'main.py'
main = main_path.read_text(encoding='utf-8')
old = 'APP_VERSION = "0.21.6"'
new = 'APP_VERSION = "0.21.7"'
if old not in main:
    raise SystemExit('APP_VERSION 0.21.6 marker missing')
main_path.write_text(main.replace(old, new, 1), encoding='utf-8')

index_path = root / 'static' / 'index.html'
index = index_path.read_text(encoding='utf-8')
index = re.sub(r'([?&]v=)0\.21\.\d+', r'\g<1>0.21.7', index)
index_path.write_text(index, encoding='utf-8')

changelog_path = root / 'CHANGELOG.md'
changelog = changelog_path.read_text(encoding='utf-8')
section = '''## v0.21.7 - 2026-09-14

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

'''
marker = '## Unreleased\n\n'
if section.splitlines()[0] not in changelog:
    if marker not in changelog:
        raise SystemExit('Unreleased changelog marker missing')
    changelog = changelog.replace(marker, marker + section, 1)
    changelog_path.write_text(changelog, encoding='utf-8')

# Older regression tests intentionally accept a set of later compatible releases.
# Extend those gates without changing the historical assertions themselves.
for path in sorted((root / 'tests').glob('test_*.py')):
    text = path.read_text(encoding='utf-8')
    original = text
    text = text.replace("'0.21.6'}", "'0.21.6','0.21.7'}")
    text = text.replace('"0.21.6"}', '"0.21.6","0.21.7"}')
    text = text.replace("'APP_VERSION = \\\"0.21.6\\\"' in main", "('APP_VERSION = \\\"0.21.6\\\"' in main or 'APP_VERSION = \\\"0.21.7\\\"' in main)")
    text = text.replace("'APP_VERSION = \"0.21.6\"' in main", "('APP_VERSION = \"0.21.6\"' in main or 'APP_VERSION = \"0.21.7\"' in main)")
    text = re.sub(r"assert\s+main\.APP_VERSION\s*==\s*(['\"])0\.21\.6\1", "assert main.APP_VERSION in {'0.21.6','0.21.7'}", text)
    if text != original:
        path.write_text(text, encoding='utf-8')
        print('updated version gate:', path.relative_to(root))

print('v0.21.7 release preparation applied')
