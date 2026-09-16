# HaushaltPro

Stable: **v0.21.8** · Testversion / prerelease: **v0.21.9-dev.2**

[Testversion und Grenzen / Dev setup and limitations](docs/OFFLINE-DEV.md) · [Release notes](docs/RELEASE-NOTES-v0.21.9-dev.2.md)

[![License: AGPL v3+](https://img.shields.io/badge/License-AGPL_v3%2B-blue.svg)](LICENSE)
[![Vibe Coding](https://img.shields.io/badge/development-Vibe%20Coding-orange.svg)](VIBE_CODING.md)

**Self-hosted Haushaltsbuch für Dokumentation, Planung und Prognose.**  
**Self-hosted household finance tracker for records, planning and forecasting.**

HaushaltPro verwaltet Finanzdaten auf dem eigenen Server. Konten, Buchungen, interne Transfers, Budgets, wiederkehrende Zahlungen, Prognosen, Bank-CSV-Import, Audit-Historie, Backups, Mehrbenutzer und mehrere getrennte Haushaltsbücher sind in einer Weboberfläche zusammengeführt.

> **Vibe Coding / AI-assisted development:** Dieses Projekt wurde in erheblichem Umfang KI-gestützt entwickelt. KI-Ausgaben gelten nicht automatisch als korrekt; relevante Berechnungen werden mit reproduzierbaren Tests und festen Sollwerten gegengeprüft.

## Deutsch

### Hauptfunktionen

- Konten mit Startsaldo, Monatsanfang, Stichtags- und Monatsendstand
- Einnahmen, Ausgaben, Sparen und interne Transfers
- Buchungen mit Kategorien, Empfängern, Tags, Notizen, Splits und Belegen
- wiederkehrende Buchungen mit Serienversionen und Stichtagsänderungen
- Budgets und Plan/Ist-Vergleich
- 3/6/12-Monats-Prognosen, Jahresansicht und What-if-Szenarien
- CSV-Bankimport mit Decimal-Verarbeitung und Dublettenprüfung
- Kontenabgleich und Korrekturbuchungen
- Finanz-Check und Audit-Hashkette
- mehrere Benutzer mit Eigentümer-/Bearbeiter-/Leserechten
- mehrere getrennte Haushaltsbücher mit eigener SQLCipher-Datenbank
- optionale Investment-Übersicht
- verschlüsselte portable Backups und interne Snapshot-Rotation
- responsive Smartphone-Ansicht

### Weitere Hinweise

CSV-Importdateien werden nicht dauerhaft gespeichert; importiert werden nur die daraus erzeugten Buchungen und lokalen Dublettenmerkmale.

Die Jahresübersicht in Planung & Prognose und Dashboard als echte einspaltige Finanztabelle bleibt auch in der responsiven Darstellung erreichbar.

### Datenschutz und Sicherheit

Finanzdaten liegen in SQLCipher-Datenbanken. Benutzerpasswörter werden mit Argon2id verarbeitet. Der Container läuft non-root, mit read-only Root-Dateisystem, ohne Linux-Capabilities und standardmäßig nur auf `127.0.0.1:8080`.

Für private Nutzung wird **LAN oder VPN** empfohlen. Für öffentlichen Betrieb ist ein HTTPS-Reverse-Proxy vorgesehen; Port 8080 darf nicht direkt ins Internet weitergeleitet werden.

Details: [Security Audit](docs/SECURITY-AUDIT.md) und [Public Deployment](docs/PUBLIC-DEPLOYMENT.md).

Published Docker images are built for `linux/amd64` and `linux/arm64`, include SBOM/provenance attestations and are analyzed with Docker Scout.

### Installation

```bash
git clone https://github.com/21Koblenz/haushaltpro.git
cd haushaltpro
cp .env.example .env
docker compose pull
docker compose up -d
docker compose ps
```

Der sichere Standard bindet die Anwendung nur an `127.0.0.1:8080`.

Für LAN-Zugriff wird in `.env` `HAUSHALTPRO_BIND_IP=0.0.0.0` gesetzt. Für **lokal/LAN, VPN und öffentlichen HTTPS-Betrieb** siehe [docs/INSTALLATION.md](docs/INSTALLATION.md).

### Update

Vor einem Update ein externes Backup erzeugen. Danach:

```bash
git fetch --tags
docker compose pull
docker compose up -d
```

Das Docker-Volume **nicht löschen**, wenn bestehende Daten erhalten bleiben sollen.

### Tests / Plausibilität

v0.21.0 wurde gegen die gesamte vorhandene Regression-Suite geprüft. Zusätzlich enthält `tests/test_v210_release_plausibility.py` einen festen Demohaushalt mit unabhängig berechneten Sollwerten.

Referenzfall:

| Kennzahl | Sollwert |
|---|---:|
| Anfangsvermögen | 7.200,00 € |
| Einnahmen | 3.050,00 € |
| Ausgaben | 1.770,00 € |
| Monatsüberschuss | 1.280,00 € |
| Endvermögen | 8.480,00 € |
| nach 3 Monaten bei +1.280 €/Monat | 12.320,00 € |
| nach 6 Monaten | 16.160,00 € |
| nach 12 Monaten | 23.840,00 € |

Ein interner Transfer von 500 € verändert dabei weder Einnahmen/Ausgaben noch das Gesamtvermögen.

Details: [Testplan](docs/TESTING.md) und [Release-Testbericht](docs/TEST-REPORT-v0.21.0.md).

### Lizenz

HaushaltPro steht unter **GNU Affero General Public License v3.0 oder neuer (AGPL-3.0-or-later)**.

Wer eine veränderte Fassung weitergibt, muss den korrespondierenden Quellcode unter den Lizenzbedingungen bereitstellen. Wer eine veränderte Fassung als Netzwerkdienst betreibt, muss den Nutzern dieses Dienstes den korrespondierenden Quellcode anbieten. Reine private Nutzung einer unveränderten lokalen Installation erzeugt keine Pflicht, sie öffentlich auf GitHub zu stellen.

Siehe [LICENSE](LICENSE).

---

## English

### Features

HaushaltPro combines accounts, transactions, internal transfers, categories, recurring payments, budgets, forecasts, bank CSV import, reconciliation, audit history, backups, multi-user permissions, multiple isolated household books and optional investment tracking in a self-hosted web application.

Financial data is stored in SQLCipher databases. The container is hardened and binds to `127.0.0.1:8080` by default. LAN/VPN access is preferred; public access should only be provided through an HTTPS reverse proxy.

### Install

```bash
git clone https://github.com/21Koblenz/haushaltpro.git
cd haushaltpro
cp .env.example .env
docker compose pull
docker compose up -d
```

See [docs/INSTALLATION.md](docs/INSTALLATION.md) for **local/LAN, VPN and public HTTPS deployment**.

### Verification

v0.21.0 includes the historical regression suite plus a release-specific fixed-data plausibility test. The reference household starts at €7,200, receives €3,050 income, spends €1,770, ends at €8,480 and has a €1,280 monthly surplus. Internal transfers remain neutral to household income/expense totals.

See [docs/TEST-REPORT-v0.21.0.md](docs/TEST-REPORT-v0.21.0.md).

### License

Licensed under **GNU AGPL-3.0-or-later**. Modified distributed versions remain under the same copyleft terms, and operators of modified network-accessible versions must offer the corresponding source code to their users.

## Project links

- Source: https://github.com/21Koblenz/haushaltpro
- Changelog: [CHANGELOG.md](CHANGELOG.md)
- Issues: https://github.com/21Koblenz/haushaltpro/issues
- License: [AGPL-3.0-or-later](LICENSE)
- Contribution guide: [CONTRIBUTING.md](CONTRIBUTING.md)
- Security policy: [SECURITY.md](SECURITY.md)
