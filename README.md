# HaushaltPro

> **Version target:** v0.21.0  
> **License:** GNU AGPL-3.0-or-later  
> **Development note:** Vibe Coding / AI-assisted development

HaushaltPro is a self-hosted household-finance application intended to keep financial data under the user's own control.

**Important:** This repository has just been created. The previously developed application source has not yet been imported into this repository. Therefore v0.21.0 is currently a **release candidate target, not a validated release**. No test result is claimed until the exact application source is present and the regression/plausibility suite has been executed against it.

## Deutsch

### Ziel

HaushaltPro soll Einnahmen, Ausgaben, Konten, Buchungen sowie Planung und Prognosen nachvollziehbar und selbst gehostet verwalten. Das Projekt wird offen entwickelt und soll ohne Abhängigkeit von einem zentralen Cloud-Anbieter betrieben werden können.

### Open Source / Copyleft

Dieses Projekt steht unter **GNU Affero General Public License v3.0 oder neuer (AGPL-3.0-or-later)**.

Das bedeutet insbesondere:

- Quellcode darf genutzt, untersucht und verändert werden.
- Weitergegebene abgeleitete Versionen müssen unter derselben Lizenz stehen.
- Wer eine veränderte Version als Netzwerkdienst bereitstellt, muss den Nutzern dieser Version den korrespondierenden Quellcode zugänglich machen.
- Lizenz- und Copyright-Hinweise müssen erhalten bleiben.

Reine private Nutzung einer unveränderten lokalen Installation erzeugt keine Pflicht, die Installation öffentlich auf GitHub zu stellen.

### Vibe Coding

HaushaltPro ist ausdrücklich als **Vibe-Coding / AI-assisted project** gekennzeichnet. KI-gestützter Code wird nicht allein deshalb als korrekt betrachtet: Änderungen sollen nachvollziehbar geprüft, getestet und reviewbar committed werden.

Siehe [VIBE_CODING.md](VIBE_CODING.md).

### Installation

Die Installationsvarianten werden getrennt dokumentiert:

- lokal / LAN
- Zugriff über VPN
- öffentlich erreichbarer Online-Betrieb

Siehe [docs/INSTALLATION.md](docs/INSTALLATION.md).

### Tests

Für v0.21.0 ist ein reproduzierbarer Demo- und Plausibilitätstest vorgesehen. Erwartete Ergebnisse werden vor dem Release festgeschrieben und anschließend mit der Anwendung verglichen.

Siehe [docs/TESTING.md](docs/TESTING.md).

### Sicherheit

Sicherheitsprobleme bitte nicht als öffentliche Exploit-Anleitung veröffentlichen. Siehe [SECURITY.md](SECURITY.md).

---

## English

### Goal

HaushaltPro is intended to manage household income, expenses, accounts, transactions, planning and forecasts in a transparent, self-hosted setup while keeping financial data under the user's control.

### Open source / copyleft

This project is licensed under the **GNU Affero General Public License v3.0 or later (AGPL-3.0-or-later)**.

In particular:

- the source code may be used, studied and modified;
- distributed derivative versions must remain under the same license;
- operators of modified network-accessible versions must offer the corresponding source code to users of that version;
- copyright and license notices must be preserved.

Purely private use of an unmodified local installation does not require publishing the installation on GitHub.

### Vibe Coding

HaushaltPro is explicitly marked as a **Vibe Coding / AI-assisted development project**. AI-generated code is not treated as correct by default. Changes should remain reviewable and must be validated with reproducible tests.

See [VIBE_CODING.md](VIBE_CODING.md).

### Installation

Deployment documentation is separated into:

- local / LAN
- VPN access
- public online deployment

See [docs/INSTALLATION.md](docs/INSTALLATION.md).

### Testing

v0.21.0 is intended to include a reproducible demo-data and plausibility test. Expected values are fixed independently and compared with application output before release.

See [docs/TESTING.md](docs/TESTING.md).

## Project status

The repository structure is being prepared for the first public release. The exact application source from the previous development session must be imported before v0.21.0 can honestly be tagged as tested and released.
