# Veröffentlichung / Releasing

## Deutsch

`main` enthält freigegebene Stände, `dev` bleibt für Entwicklung und Tests. Git-Tags und Docker-Tags sind getrennte Namen: Git `v0.21.9`, Docker `21koblenz/haushaltpro:0.21.9`. `:latest` und `:0.21` folgen stabilen Releases, `:dev` dem Testkanal.

1. Auf `dev` entwickeln und testen; `APP_VERSION` und Asset-Cache-Keys erhalten für Testreleases eine Version wie `0.21.10-dev.1`. Der Docker-Workflow veröffentlicht `:dev`, den festen Dev-Tag und ein GitHub-Prerelease. Er verändert keine stabilen Tags.
2. Für die stabile Freigabe `APP_VERSION`, Asset-Keys und Versionsprüfungen auf die stabile Nummer setzen. `CHANGELOG.md`, README, Installationshinweise und `docs/RELEASE-NOTES-vVERSION.md` mit allen Änderungen seit dem vorherigen stabilen Release aktualisieren. Migration, Updateweg und Grenzen dokumentieren.
3. Regression, Syntax und Sicherheitsprüfungen ausführen und den vorbereiteten Stand nach `main` übernehmen. Kein Force-Push und kein Umschreiben bestehender Release-Tags.
4. `stable-release.yml` startet bei einer Versions-/Workflow-Änderung auf `main` oder manuell auf `main`. Es wartet auf einen erfolgreichen `CI`-Push-Lauf für genau diesen Main-Commit, erstellt den unveränderlichen Versionstag und ruft die vorhandene Docker-Veröffentlichung für diesen Tag auf.
5. Erst nach Multiarch-Build, Manifestprüfung und allen vier Scout-Gates werden GitHub-Release, Quellarchive und SHA-256-Prüfsummen veröffentlicht. Anschließend wird `dev` nur dann vorgezogen, wenn dadurch keine neuen Commits verloren gehen. Der stabile Versionsstand auf `dev` aktualisiert nur `:dev`, keine stabilen Tags und kein Prerelease.

Der normale Docker-Workflow und der stabile Release-Aufruf teilen dieselbe Veröffentlichungs-Sperre. Gleichzeitige Image-Veröffentlichungen werden dadurch serialisiert. Der wiederverwendbare Workflow nutzt weiterhin die vorhandenen Docker-Hub-Secrets.

### Git aufräumen

Eine optionale, versionsgebundene Datei `.github/cleanup/vVERSION.json` benennt ausdrücklich die abgelösten Branches und ihre zuvor geprüften Commit-IDs. Nach dem erfolgreichen Release legt die Bereinigung pro Branch einen Tag `archive/vVERSION/BRANCH` an und entfernt den Branch atomar mit Commit-Prüfung. Geänderte Branch-Spitzen, abweichende Archiv-Tags und `main`/`dev` werden nicht gelöscht; offene Pull Requests lassen den Branch bestehen. Ohne eine solche Datei erfolgt keine Branch-Löschung. Release-Tags werden nie bereinigt.

Ein unterbrochener Lauf kann erneut ausgeführt werden. Vorhandene Versionstags müssen auf denselben Commit zeigen. Bei neuen Main-/Dev-Commits wird nicht zurückgesetzt; einen Konflikt vor einer erneuten Veröffentlichung klären.

## English

Develop/test on `dev` with a prerelease version; promote a tested stable version to `main` with complete release notes, changelog, cache keys and upgrade documentation. Git tags use `vVERSION`; Docker image tags use `VERSION`. The stable workflow waits for successful CI on the exact Main commit, creates the version tag, invokes the existing multiarch Docker/Scout workflow, and publishes the GitHub release plus source archives/checksums after all gates pass.

Both publication paths share the Docker concurrency lock. `latest` and the minor alias are stable-only; development versions never move them. After a release, `dev` is fast-forwarded only if it has no new work. A stable version mirrored to `dev` publishes only the moving test image, not a new prerelease or stable version tag.

Optional per-version cleanup manifests explicitly list reviewed retired branch heads. Each is preserved under `archive/vVERSION/BRANCH` before atomic, lease-protected removal. Changed heads, conflicting archive tags, protected branch names and open pull requests are preserved. Release tags and history are retained. No manifest means no branch deletion.
