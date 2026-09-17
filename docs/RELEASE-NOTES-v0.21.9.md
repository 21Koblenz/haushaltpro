# HaushaltPro v0.21.9

Stabiles Release mit allen Änderungen seit **v0.21.8**, einschließlich der getesteten Entwicklungsversionen bis **v0.21.9-dev.6**. / Stable release containing all changes since **v0.21.8**, including the tested development versions through **v0.21.9-dev.6**.

## Deutsch

### Offline-Erfassung und Verbindungsstatus

- Neue Buchungen, interne Transfers, wiederkehrende Buchungsserien, offene Posten und Zahlungen können bei unterbrochener Serververbindung lokal vorgemerkt werden. Sobald die Verbindung wieder besteht, werden sie automatisch angelegt.
- Jeder Eintrag wird vor dem Senden dauerhaft in der Browser-Warteschlange gespeichert. Dieselbe Vorgangs-ID verhindert Doppelbuchungen bei verlorenen Antworten, parallelen Tabs und wiederholten Übertragungsversuchen.
- Die Warteschlange gehört zum ursprünglichen Benutzer und Haushaltsbuch. Ein Wechsel oder eine abgelaufene Sitzung führt nicht zur Übertragung in ein anderes Buch. Nach erneuter Anmeldung lässt sich die Synchronisierung fortsetzen.
- Die Kopfzeile zeigt Serververbindung, Synchronisierung, Fehler und die Anzahl wartender Einträge. Antippen startet eine neue Prüfung. Eine Fehlerseite des Servers zählt nicht als erfolgreiche Verbindung.
- Die Online-Anzeige hat im Hellmodus einen passenden hellen Hintergrund und erkennbare Statusfarben.

### Wiederkehrende Buchungen und Transfers

- Einzelne Serientermine lassen sich unabhängig verschieben, auch in den nächsten Monat oder ins nächste Jahr. Der ursprüngliche Termin bleibt als Serienzuordnung erhalten und verhindert eine zweite automatische Anlage.
- Beispiel: Die September-Buchung vom 20. auf den 1. Oktober verschieben. September enthält diesen Betrag nicht mehr; im Oktober stehen sowohl die verschobene September-Buchung als auch der reguläre Oktober-Termin.
- Journal, Fixkostenplan, Monats-/Jahresauswertung und Prognose verwenden das tatsächliche Buchungsdatum. Erneutes Bearbeiten, Zurücksetzen, Betragsausnahmen und Änderungen einer Serie ab einem Stichtag werden berücksichtigt.
- Vierteljährliche und halbjährliche Voreinstellungen sowie freie Kalenderintervalle, etwa alle 10 Tage, 2 Wochen, 5 Monate oder 2 Jahre. Bestehende Serien behalten ihren Rhythmus.
- Interne Transfers können ebenfalls wiederkehren. Sie verschieben Geld zwischen Konten und bleiben in der Einnahmen-/Ausgabenanalyse neutral.
- Wiederkehrende Buchungen unterstützen gespeicherte und frei eingegebene Empfänger; diese werden in die erzeugten Buchungen übernommen. Der eigene Einstieg zum Anlegen einer Serie bleibt vorhanden.

### Offene Zahlungen, Schulden und Forderungen

- Verbindlichkeiten und Forderungen mit Bezeichnung, Betrag, Empfänger/Gegenpartei, Fälligkeit, Notiz und Status. Überfällige Posten werden hervorgehoben; erledigte und stornierte Posten bleiben über Filter erreichbar.
- Teilzahlungen: 200 EUR verliehen und 50 EUR zurückbekommen ergeben 150 EUR Restforderung. Der Status folgt den zugeordneten Zahlungen.
- Eine vorhandene Buchung zuordnen oder beim Bezahlen genau eine neue Kontobuchung erstellen. Freie Buchungsbeträge können auf mehrere Posten verteilt werden; Überzahlungen und widersprüchliche Änderungen werden verhindert.
- Eine Zuordnung lösen lässt die Kontobuchung bestehen. Storno oder Löschung der Buchung öffnet den zugehörigen Restbetrag wieder. Benutzerrechte, Haushaltsbuchtrennung und Schutz vor doppelter Offline-Übertragung gelten auch hier.

### CSV-Export und Fixkosten

- Buchungen nach Zeitraum, Konto, Kategorie, Status und Suchtext exportieren. Der Export enthält alle passenden Ergebnisse, unabhängig von der geöffneten Listen-Seite.
- Split-Buchungen erhalten getrennte Zeilen ohne doppelte Gesamtsummen. Kategorie-Filter exportieren nur passende Split-Anteile.
- Fixkosten-Jahresplan mit zwölf Monatsspalten und Jahressumme. Jahreszahlungen stehen im Fälligkeitsmonat; verschobene Serientermine und Serienversionen werden berücksichtigt.
- UTF-8 mit BOM, Semikolon, Dezimalkomma und Schutz gegen die Ausführung von Formeln aus Textfeldern in Tabellenprogrammen.

### Übersicht und Smartphone-Bedienung

- Buchungen, wiederkehrende Buchungen und Transferserien starten als eingeklappte Karten. Name, Wiederholungssymbol, Datum/nächster Termin, Betrag und Konto bleiben sichtbar. Antippen oder Tastaturbedienung öffnet Details und Aktionen.
- Kontenkarten auf Dashboard und Kontenseite starten ebenfalls eingeklappt und zeigen bereits den aktuellen/Stichtagsstand **und** den Monatsendstand. Geöffnet stehen Monatsanfang, Bis heute/Bis Stichtag und Monatsende übersichtlich untereinander.
- Dashboard-Grafiken nutzen die verfügbare Breite. Auf schmalen Displays erscheinen weniger Achsenbeschriftungen; jeder Tages-/Monatswert bleibt per Antippen oder Regler erreichbar. Der genaue Betrag steht unter der Grafik.
- Größenänderungen, Hell-/Dunkelmodus, unterschiedliche Monatslängen, leere Daten und Sprachwechsel werden berücksichtigt. Für das Neuzeichnen werden keine Finanzdaten erneut geladen.

### Geldfluss und Werte ausblenden

- Verbundenes Sankey im Sure-Stil als Standard: proportionale Bänder verbinden Einnahmen, Ausgaben, Sparen und Überschuss. Ein Fehlbetrag wird getrennt dargestellt und nicht als zusätzliche Einnahme gezählt.
- Das bisherige HaushaltPro-Pfeildiagramm bleibt als zweite Ansicht verfügbar. Der Browser merkt sich die Auswahl.
- Smartphones erhalten eine vertikale Gruppenansicht. Alle Kategorien und Beträge bleiben in einer aufklappbaren Liste erhalten; Auswahl zeigt den Betrag und Gruppenanteil. Centgenaue Flussgleichheit, kleine Beträge, viele Kategorien und lange Namen werden berücksichtigt. [Gestaltungsnachweis](THIRD-PARTY-NOTICES.md).
- Das Auge in Kopfzeile und Dialogen blendet Eurobeträge und Prozentwerte als `****` aus und wieder ein. Die Auswahl bleibt gespeichert und wird zwischen Tabs übernommen.
- Maskierung umfasst Karten, nachgeladene Daten, Diagrammachsen, Legenden, Tooltips, Screenreader-Texte und Geldfelder. Verborgene Eingabefelder lassen sich bewusst zum Bearbeiten einblenden. Berechnungen, gespeicherte Werte, CSV und Backups behalten ihre Originaldaten.

### Korrekturen, Performance und Veröffentlichung

- Die aktuelle Monatsanalyse berücksichtigt bekannte/geplante Buchungen bis Monatsende einschließlich bereits angelegter Serientermine. Vergangene Monate und die Jahresanalyse bleiben bei den tatsächlich gebuchten Werten.
- Gebündelte Abfragen für Serientermine, Ausnahmen und Kategorien sowie ein zusätzlicher Index für Split-Buchungen reduzieren wiederholte Datenbankarbeit. Berechnungen werden innerhalb einer Leseanfrage wiederverwendet.
- In der dokumentierten weiteren Optimierungsrunde mit 10.000 Buchungen sank die Zahl der SQL-Abfragen für die monatliche Planung von 365 auf 197; die lokale Medianzeit von 83,40 auf 65,90 ms. Laufzeiten hängen vom System ab; [Messung und Tests](TESTING.md).
- Englische Übersetzungen, automatisierte Plausibilitäts-/Berechtigungsprüfungen und Tests für verschlüsselte Migrationen, Offline-Wiederholung und Oberfläche wurden erweitert.
- Die stabile Veröffentlichung wartet auf die CI-Prüfung des exakten Commits und verwendet die bestehende Multiarch-Docker-Pipeline mit vier Scout-Sicherheitsprüfungen. Quellarchive und SHA-256-Prüfsummen gehören zum Release.
- Veraltete Patch-/Release-Einmalskripte wurden entfernt. Abgelöste Arbeitsbranches werden erst nach erfolgreichem Release anhand ihrer geprüften Commit-IDs archiviert und entfernt; neue Branch-Arbeit wird dabei nicht überschrieben. Die bisherige Release-Historie bleibt erhalten.

### Update und Datenbank

Vor dem Update ein externes Backup erstellen. Im bestehenden Compose-/Portainer-Stack `21koblenz/haushaltpro:latest` oder den festen Tag `21koblenz/haushaltpro:0.21.9` verwenden. Zum Wechsel vom Testkanal die bisherige `:dev`-Angabe ersetzen.

```bash
docker compose pull
docker compose up -d
```

Bestehendes Datenvolume und Konfiguration beibehalten. Der Footer zeigt anschließend **0.21.9**. Datenbanken aus **v0.21.8 (Schema 22)** werden automatisch und additiv auf **Schema 28** aktualisiert; der direkte Weg wurde mit echter SQLCipher-Verschlüsselung geprüft. Wer bereits dev.3–dev.6 verwendet, hat Schema 28 und benötigt keine weitere Migration. Für einen Rückwechsel auf v0.21.8 das Backup von vor dem Update wiederherstellen. [Installation lokal, im LAN, per VPN und über HTTPS](INSTALLATION.md).

### Funktionsumfang

Offline-Erfassung benötigt eine zuvor online geladene, angemeldete App. Für Zahlungen zu offenen Posten den Dialog zuvor online öffnen. Vollständiger Offline-Neustart, Offline-Bearbeiten/Löschen, Datei-Uploads und Administration sind nicht enthalten. Wartende Browser-Daten sind nicht zusätzlich verschlüsselt und zählen erst nach Synchronisierung in Serversummen.

Offene Posten werden in EUR geführt und verändern allein keine Kontostände oder Prognosen; entscheidend sind die zugehörigen Kontobuchungen. Der Fixkostenexport enthält Planwerte. Ein Buchungsexport umfasst höchstens 100.000 Zeilen. Die Sternchenoption ist eine Anzeigeoption; Diagrammformen und Größenverhältnisse bleiben sichtbar.

## English

### Everything included since v0.21.8

- **Offline creation:** Queue new bookings, transfers, recurring booking series, open items and payments during a connection outage. Entries are persisted before sending and replayed automatically with the same operation ID. Lost responses and concurrent retries do not create duplicate financial entries. The queue is bound to the original user and household book; expired sessions resume after login.
- **Connection status:** Live server reachability, synchronization, errors and pending-entry count, with a manual retry action. Server error pages are not accepted as successful probes. The light theme now has a matching indicator background and readable status colors.
- **Recurring dates:** Move one occurrence independently, including across month/year boundaries. The original due-date identity prevents duplicate generation. Journal, reports, fixed costs and forecasts use the effective date; repeated edits, reset, amount exceptions and future series versions are supported.
- **Flexible recurrence:** Quarterly/half-yearly presets and custom calendar intervals such as every 10 days, 2 weeks or 5 months. Existing schedules keep their rhythm. Transfers may also recur while remaining neutral to household income/expense totals. Saved or free-text payees propagate from recurring series to generated bookings.
- **Payables and receivables:** Manage title, counterparty, total, due date, note and derived status, with overdue highlighting. Partial payments are supported: a 200 EUR receivable with 50 EUR repaid leaves 150 EUR open.
- **Payment allocation:** Link an existing booking without a second cash movement or create exactly one new booking. Distribute available amounts across items, with overpayment and conflicting-edit guards. Unlinking retains the booking; cancelling/deleting it reopens the allocated balance. Permissions, book isolation and idempotent offline replay apply.
- **CSV reports:** Export all matching bookings by date, account, category, status and search text, across pagination. Split rows avoid double-counting. Export annual fixed costs with twelve month columns and annual totals, respecting actual due months, shifted occurrences and series versions. UTF-8 BOM, semicolons, decimal commas and formula-safe text are included.
- **Collapsed mobile cards:** Bookings, recurring bookings and transfer series start closed, keeping name, recurrence icon, date, amount and account visible. Account cards on both dashboard and account management show cutoff/current **and** month-end balances while closed. Expanded cards show opening, cutoff and month-end values separately.
- **Responsive charts:** Dashboard day/year charts fit their containers, retain every data point and support touch, keyboard/range selection and exact readouts. Resize, themes, different month lengths, empty data and language changes do not require additional financial-data requests.
- **Cash flow:** Sure-inspired connected Sankey is the default; the previous arrow chart remains selectable with a saved preference. Mobile uses a vertical group overview and a complete expandable category list. Surplus/deficit are separate, flows balance in exact cents, and selecting a stream reveals its amount and share. [Design credits](THIRD-PARTY-NOTICES.md).
- **Hide values:** Eye controls in the header and dialogs mask EUR amounts and percentages as `****`, including charts, legends, tooltips, accessible labels, dynamic views and financial fields. Preferences persist across reloads and tabs. Fields can be explicitly revealed for editing; calculations, saved data and exports remain original.
- **Analysis correction:** The current month includes known/planned bookings through month end, including materialized recurring items. Historical months and annual analysis remain actual-only.
- **Performance:** Batch recurring-occurrence, exception and category lookups, index split transactions and reuse calculations within a read request. A documented additional optimization reduced monthly-planning SQL statements from 365 to 197 with 10,000 bookings; local median time changed from 83.40 to 65.90 ms. Timings depend on the system.
- **Quality and delivery:** Expanded German/English, plausibility, permission, migration, offline and UI tests. Stable publication waits for CI on the released commit, uses multiarch Docker builds and four Scout security gates, then publishes source archives with SHA-256 checksums. Obsolete one-shot scripts are removed; reviewed retired branches are preserved as archive tags before removal. Existing release history is retained.

### Updating and scope

Back up first. Use `21koblenz/haushaltpro:latest` or pin `:0.21.9`; replace `:dev` in the stack when leaving the test channel. Pull and recreate the container with its existing data volume. Footer: **0.21.9**. Direct encrypted migration from v0.21.8/schema 22 to schema 28 is tested. Dev.3–dev.6 already use schema 28. Downgrading to v0.21.8 requires restoring the pre-update backup.

Offline creation requires a previously loaded/authenticated page; open payment dialogs online first. Full offline cold start, editing/deletion, uploads and administration are outside this release. Pending IndexedDB data is not additionally encrypted and enters server totals only after synchronization. Open items are EUR-only and affect cash through their account bookings; fixed-cost exports are plans. Booking exports are limited to 100,000 rows. Masking is a display preference; chart shapes and proportions remain visible.

### Verification / Prüfung

The release suite contains **89 Python regression scripts, 39 JavaScript tests and 52 static security checks**, plus Python compilation, JavaScript/shell syntax checks, direct encrypted stable-version migration and branch-cleanup tests using real local Git repositories. Docker CI verifies SQLCipher on AMD64 and ARM64. The dev.6 behavior was confirmed by the project owner; automated DOM/canvas checks are not a complete visual browser test.

Full history: [CHANGELOG.md](../CHANGELOG.md) · Upgrade: [INSTALLATION.md](INSTALLATION.md) · Tests: [TESTING.md](TESTING.md) · Source comparison: [v0.21.8…v0.21.9](https://github.com/21Koblenz/haushaltpro/compare/v0.21.8...v0.21.9).
