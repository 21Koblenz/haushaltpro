from pathlib import Path

# Small, temporary release-helper. It is removed by the apply workflow together
# with apply_offline_sync.py after the complete regression suite succeeds.

index = Path("static/index.html")
s = index.read_text(encoding="utf-8")
s = s.replace('<span id="connectionText">Server prüfen …</span>', '<span id="connectionText"></span>', 1)
s = s.replace("0.21.9-offline1", "0.21.8-offline1")
index.write_text(s, encoding="utf-8")

offline_test = Path("tests/test_offline_sync.py")
if offline_test.exists():
    s = offline_test.read_text(encoding="utf-8").replace("0.21.9-offline1", "0.21.8-offline1")
    offline_test.write_text(s, encoding="utf-8")

matrix = Path("tests/test_v0219_plausibility_matrix.py")
s = matrix.read_text(encoding="utf-8")
if "assert schema=='25',schema" in s:
    s = s.replace("assert schema=='25',schema", "assert schema=='26',schema", 1)
matrix.write_text(s, encoding="utf-8")

# Current-month reports intentionally combine actuals through today with the
# already-known remainder through month end. Historical month/year reports stay
# actual-only.
v071 = Path("tests/test_v071_full_plausibility.py")
s = v071.read_text(encoding="utf-8")
old = (
    "assert rep['income']==0.0 and rep['expense']==1000.0 and rep['savings']==0.0,rep\n"
    "assert rep['net']==-1000.0 and rep['total_saved']==0.0 and rep['savings_rate_pct']==0.0,rep"
)
new = (
    "assert rep['mode']=='forecast' and rep['includes_planned'] is True,rep\n"
    "assert rep['income']==2000.0 and rep['expense']==1000.0 and rep['savings']==500.0,rep\n"
    "assert rep['net']==500.0 and rep['total_saved']==1000.0 and rep['savings_rate_pct']==50.0,rep"
)
if old in s:
    s = s.replace(old, new, 1)
v071.write_text(s, encoding="utf-8")

v086 = Path("tests/test_v086_deep_plausibility.py")
s = v086.read_text(encoding="utf-8")
old = (
    "# Documentary reports exclude future-dated manual entries (car on Sep20) until their date arrives.\n"
    "rep=ok(client.get('/api/reports/categories?period=month&anchor=2026-09-01'))\n"
    "eq(rep['actual_through'],'2026-09-11','report actual cutoff')\n"
    "eq(rep['income'],0.0,'Sep report income actual only')\n"
    "eq(rep['expense'],1851.0,'Sep report expense actual only')\n"
    "eq(rep['savings'],0.0,'Sep report savings actual only')"
)
new = (
    "# Current-month report combines actuals through today with known/planned remainder through month end.\n"
    "rep=ok(client.get('/api/reports/categories?period=month&anchor=2026-09-01'))\n"
    "eq(rep['actual_through'],'2026-09-11','report actual cutoff')\n"
    "eq(rep['mode'],'forecast','Sep report mode')\n"
    "eq(rep['includes_planned'],True,'Sep report includes planned')\n"
    "eq(rep['income'],3000.0,'Sep report forecast income')\n"
    "eq(rep['expense'],2526.0,'Sep report forecast expense')\n"
    "eq(rep['savings'],500.0,'Sep report forecast savings')"
)
if old in s:
    s = s.replace(old, new, 1)
v086.write_text(s, encoding="utf-8")

# Historical tests used a numeric-only version string. Development builds carry
# the -dev suffix, so normalize comparisons without weakening release assertions.
old_version = "tuple(map(int,main.APP_VERSION.split('.')))"
new_version = "tuple(map(int,main.APP_VERSION.split('-',1)[0].split('.')))"
source_old = '\'APP_VERSION = "0.21.8"\' in main'
source_new = '(\'APP_VERSION = "0.21.8"\' in main or \'APP_VERSION = "0.21.9-dev"\' in main)'
changed = []
for test in Path("tests").glob("test_*.py"):
    text = test.read_text(encoding="utf-8")
    original = text
    text = text.replace(old_version, new_version)
    if "assert main.APP_VERSION in {" in text and "'0.21.9-dev'" not in text:
        text = text.replace("'0.21.8'}", "'0.21.8','0.21.9-dev'}")
    if source_old in text and "0.21.9-dev" not in text:
        text = text.replace(source_old, source_new)
    if text != original:
        test.write_text(text, encoding="utf-8")
        changed.append(test.name)
print("prerelease-aware version checks:", changed)

# Remove a stale changelog line from the short-lived idea of removing the
# dedicated recurring button. The user chose to keep it with payee support.
changelog = Path("CHANGELOG.md")
s = changelog.read_text(encoding="utf-8")
stale = "- Removed the duplicate “+ Wiederkehrende Buchung” creation button from the recurring-series tab. New recurring series are created through the normal “+ Buchung” dialog, while existing series remain manageable in the recurring tab.\n"
s = s.replace(stale, "", 1)
changelog.write_text(s, encoding="utf-8")
