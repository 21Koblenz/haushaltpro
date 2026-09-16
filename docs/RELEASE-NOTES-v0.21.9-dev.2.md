Testrelease für den **dev-Kanal** / prerelease for the **dev channel**.

## Deutsch

- **Einzeltermin verschieben:** Unter Buchungen → Termin anpassen lässt sich das Buchungsdatum frei ändern, z. B. vom 20. September auf den 18. September oder den 1. Oktober. Alle anderen Serientermine behalten ihren Rhythmus. Beträge, Monatsplanung, Fixkosten, Kontostände und Prognosen berücksichtigen die Verschiebung. Auch wiederholtes Bearbeiten und Serienänderungen ab einem Stichtag sind getestet.
- **Offline-Erfassung:** Neue Buchungen, Transfers und Serien werden lokal zwischengespeichert und nach Wiederverbindung einmalig angelegt. Benutzer und Haushaltsbuch sind fest zugeordnet. Verlorene Antworten und parallele Wiederholungsversuche erzeugen keine zusätzlichen Einträge.
- **Verbindungsanzeige:** Server verbunden, keine Verbindung, Synchronisierung, Fehler und wartende Einträge. Anklicken prüft die Verbindung und wiederholt den Sync. Alte Offline-Einträge ohne Benutzerzuordnung erfordern einmalig die Bestätigung ihres Erstellers.
- **Performance:** Im Test mit 10.000 Buchungen sank die Zahl der SQL-Abfragen für die monatliche Planung von 365 auf 197 (−46 %). Die gemessene Medianzeit sank von 83,40 auf 65,90 ms; Zeiten sind vom Rechner abhängig.
- **Datenbank:** Automatische, additive Migration auf Schema 27. Bestehendes Datenvolume beibehalten; ein Backup vor dem Test ermöglicht eine vollständige Rückkehr zum bisherigen Stand.

### Installation

Im bestehenden Compose-/Portainer-Stack nur das Image auf die Testversion setzen:

```yaml
image: 21koblenz/haushaltpro:0.21.9-dev.2
```

Alternativ folgt `21koblenz/haushaltpro:dev` dem jeweils veröffentlichten Teststand.

```bash
docker compose pull
docker compose up -d
```

Das vorhandene Volume `haushaltpro_data` und die übrige Konfiguration beibehalten. Bei einem vorhandenen Override mit `build:` sicherstellen, dass das veröffentlichte Image verwendet wird. Bei einem eigenen Git-Build den Tag `v0.21.9-dev.2` auschecken und wie bisher neu bauen. Im Footer muss danach **0.21.9-dev.2** erscheinen.

### Grenzen / Prüfung

Offline-Erfassung funktioniert in einer vorher online geladenen, angemeldeten App. Ein vollständiger Start ohne Serververbindung sowie Offline-Bearbeiten/Löschen sind noch nicht enthalten. Nur wartende Schreibdaten liegen lokal in IndexedDB; diese sind derzeit nicht zusätzlich verschlüsselt. Nach dem Synchronisieren werden sie entfernt.

84 Python-Testskripte, 9 JavaScript-Tests, 52 statische Sicherheitsprüfungen sowie Syntax-/Compile-Checks bestanden lokal. Die Migration wurde mit SQLCipher 4.12.0 geprüft. Eine interaktive Browserprüfung war wegen des gesperrten lokalen Testzugriffs nicht möglich; [Testanleitung](OFFLINE-DEV.md).

## English

This prerelease adds effective dates for individual recurring occurrences, including moves across months and years. Original occurrence identity prevents duplicate materialization. Journal, planning, fixed costs and forecasts agree on the shifted date.

New offline transactions, transfers and series are persisted before sending and replayed with the same idempotency key. User/book guards, concurrent replay handling, authenticated resumption, server-status validation and reduced read overhead are included. The planning probe uses 197 instead of 365 SQL statements with 10,000 transactions.

Use `21koblenz/haushaltpro:0.21.9-dev.2` for this exact build or `:dev` for the moving test channel, then pull and recreate the existing container while retaining its volume. Source builds can use tag `v0.21.9-dev.2`. Stable image tags are unaffected by this prerelease.

Schema 27 is an additive migration. Offline creation requires a previously loaded/authenticated page; cold start and offline editing/deletion are not included. Pending browser payloads are not yet encrypted. Local checks: 84 Python scripts, 9 JavaScript tests and 52 static security checks passed. Interactive browser verification was blocked by local-URL access restrictions.
