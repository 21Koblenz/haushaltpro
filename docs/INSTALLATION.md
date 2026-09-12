# Installation / Deployment

This guide documents the three intended deployment models for HaushaltPro. Commands that depend on the final v0.21.0 source tree must be verified against the imported application before the release is tagged.

---

# Deutsch

## 1. Voraussetzungen

Für die Docker-basierte Installation werden benötigt:

- Linux-Host oder VM
- Docker Engine
- Docker Compose Plugin (`docker compose`)
- Git
- ausreichend freier Speicher für Anwendung, Datenbank und Backups

Prüfen:

```bash
docker --version
docker compose version
git --version
```

Repository klonen:

```bash
git clone https://github.com/21Koblenz/haushaltpro.git
cd haushaltpro
```

> Die endgültigen Startbefehle, Environment-Variablen und Ports werden mit dem v0.21.0-Quellstand validiert. Bis dieser Quellstand importiert ist, bitte keine Beispielwerte als Produktionskonfiguration übernehmen.

## 2. Lokal / LAN

Empfohlen, wenn HaushaltPro nur im Heimnetz benötigt wird.

Grundprinzip:

1. Anwendung auf dem eigenen Server/der eigenen VM starten.
2. Nur den erforderlichen Anwendungsport im lokalen Netz erreichbar machen.
3. Keine Portweiterleitung im Router einrichten.
4. Datenverzeichnis und Datenbank regelmäßig sichern.

Nach Import des Quellstands wird dieser Abschnitt die exakten `docker compose`-Befehle, Portbelegung und Healthchecks enthalten.

## 3. Zugriff über VPN

Für Zugriff von unterwegs ist VPN gegenüber direkter Internetfreigabe die bevorzugte Variante.

Geeignete Architektur:

```text
Client ── VPN ── Heimnetz/VPS ── HaushaltPro
```

Dabei bleibt HaushaltPro selbst nur lokal bzw. im VPN erreichbar. Möglich sind beispielsweise WireGuard-basierte VPNs. Entscheidend ist, dass der Anwendungsport nicht zusätzlich öffentlich freigegeben wird.

Prüfpunkte:

- VPN-Client erhält eine erreichbare Route zum HaushaltPro-Host.
- Firewall erlaubt den Zugriff nur aus LAN/VPN.
- DNS/Hostname wird intern oder über das VPN aufgelöst.
- Keine Router-Portweiterleitung auf den HaushaltPro-Webport.

## 4. Online / öffentlich erreichbar

Nur verwenden, wenn ein öffentlicher Zugriff wirklich erforderlich ist.

Empfohlene Architektur:

```text
Internet
   │
 HTTPS :443
   │
Reverse Proxy
   │
interner Docker-/Host-Port
   │
HaushaltPro
```

Mindestanforderungen:

- HTTPS/TLS
- gepflegter Reverse Proxy
- starke Authentifizierung
- kein direkter Zugriff auf Datenbank oder interne Verwaltungsports
- Firewall: nur notwendige Ports offen
- regelmäßige Updates
- getestete Backups
- keine Secrets im Git-Repository

Die Anwendung sollte nicht über einen Entwicklungsserver direkt ins Internet gestellt werden.

## 5. Update

Nach Veröffentlichung eines validierten Releases soll ein Update grundsätzlich nach diesem Muster erfolgen:

```bash
git fetch --tags
git checkout <release-tag>
docker compose build --pull
docker compose up -d
```

Vorher Datenbank/Anwendungsdaten sichern. Release-spezifische Migrationshinweise haben Vorrang.

## 6. Backup

Ein Backup muss mindestens alle persistenten Daten enthalten, die nicht aus dem Git-Repository neu erzeugt werden können. Der konkrete v0.21.0-Pfad wird nach Import des Quellstands dokumentiert.

Ein Backup gilt erst dann als belastbar, wenn ein Restore testweise funktioniert hat.

---

# English

## 1. Requirements

For the Docker-based deployment:

- Linux host or VM
- Docker Engine
- Docker Compose plugin (`docker compose`)
- Git
- sufficient storage for application data, database and backups

Check:

```bash
docker --version
docker compose version
git --version
```

Clone:

```bash
git clone https://github.com/21Koblenz/haushaltpro.git
cd haushaltpro
```

The exact ports, environment variables and startup commands must be validated against the imported v0.21.0 source tree before release.

## 2. Local / LAN

Recommended when HaushaltPro is only needed inside the home network. Do not configure router port forwarding. Expose only the required application service inside the trusted LAN and maintain regular backups.

## 3. VPN access

Recommended for remote access without exposing the application directly to the Internet.

```text
Client ── VPN ── private network ── HaushaltPro
```

Allow the application only from LAN/VPN networks and do not expose the same application port publicly.

## 4. Public online deployment

If public access is required, place a maintained HTTPS reverse proxy in front of HaushaltPro.

Minimum requirements:

- TLS/HTTPS
- strong authentication
- minimal firewall exposure
- no public database/admin ports
- regular updates
- tested backups
- no secrets in Git

## 5. Updates

Target workflow after a validated release exists:

```bash
git fetch --tags
git checkout <release-tag>
docker compose build --pull
docker compose up -d
```

Always back up persistent data first and follow release-specific migration notes.
