# HaushaltPro – Security Audit v0.21.0

**Status:** interner Code-, Regressions- und Konfigurationsaudit. Kein externes Zertifikat und kein Ersatz für einen unabhängigen Penetrationstest.

## Verschlüsselung
- SQLCipher 4 wird zur Laufzeit erzwungen.
- PBKDF2-HMAC-SHA512, 256.000 KDF-Iterationen, 4096-Byte-Seiten, HMAC-SHA512.
- `cipher_integrity_check` ist Bestandteil des Finanz-/Security-Checks.
- Benutzerpasswörter: Argon2id.
- Mehrbenutzer: zufälliger DB-Master-Key, pro Benutzer separat mit dessen RSA-Schlüssel verpackt; privater Benutzerschlüssel ist passwortverschlüsselt.

## Connection- und Transaktionsmodell
- Produktionsbetrieb nutzt keine einzelne globale SQLite-Verbindung für alle Worker-Threads.
- Leseverbindungen sind worker-thread-lokal.
- Schreibtransaktionen öffnen eine eigene SQLCipher-Verbindung, verwenden `BEGIN IMMEDIATE`, Commit/Rollback und schließen garantiert.
- `busy_timeout`, WAL, `synchronous=NORMAL`, Foreign Keys und WAL-Checkpointing bleiben aktiv.
- `REKEY` schließt alte Verbindungen, bevor mit dem neuen Schlüssel weitergearbeitet wird.

## Geldarithmetik
- Eingehende Geldwerte werden als `Decimal` validiert.
- Speicherung des Haushaltsbuchs erfolgt in Integer-Cents.
- Rundung: `ROUND_HALF_UP`.
- CSV-Geldwerte werden über `Decimal` geparst.
- Investment-Geldwerte werden ab Schema v20 zusätzlich als Integer-Cents gespeichert.

## Authentifizierung / Web
- HttpOnly Session-Cookie.
- SameSite=Strict.
- Secure + `__Host-` bei `SECURE_COOKIES=true`.
- CSRF-Token auf schreibenden Requests.
- Login-Rate-Limit: 5 Fehlversuche / 5 Minuten -> 15 Minuten Block. Im Public-Modus zusätzlich IP-weites Login-Limit.
- serverseitiger Autolock.
- CSP, X-Frame-Options, nosniff, Referrer-Policy, Permissions-Policy, COOP/CORP und Cache-Control für sensible Antworten.
- Public-Modus: Trusted Host Allowlist, HTTPS-Erzwingung, HSTS, `__Host-`-Cookie, Selbstregistrierung standardmäßig deaktiviert und Setup-Token für die Ersteinrichtung.
- Request-Body-Limit greift vor Multipart-/Form-Parsing.

## Uploads
- Uploadlimit pro Beleg: standardmäßig 5 MB.
- maximal 10 Belege je Buchung.
- Gesamtlimit: standardmäßig 100 MB.
- Prüfung echter Dateisignaturen/Magic Bytes; Content-Type allein wird nicht vertraut.
- Dateien werden nicht aus einem öffentlichen Upload-Verzeichnis ausgeliefert, sondern als BLOB in SQLCipher gespeichert.

## Audit-Journal
- zentrale Änderungen erzeugen append-only Audit-Einträge.
- jeder Eintrag enthält den Hash des Vorgängers und einen SHA-256-Hash über den aktuellen Datensatz.
- der Finanz-Check validiert die Hashkette.
- Die Hashkette ist Manipulationserkennung, kein Schutz gegen einen Angreifer, der vollständige DB- und Anwendungskontrolle besitzt und die gesamte Kette bewusst neu berechnet.

## Backups
- Download-Backup: AES-256-GCM + PBKDF2-HMAC-SHA512 (600.000 Iterationen).
- Restore prüft AEAD, DB-Key, DB-Magic und SQLCipher-Integrität.
- interne SQLCipher-Snapshots: 7 täglich, 4 wöchentlich, 12 monatlich.
- Gesamtlimit interner Backups: 2 GB; älteste Dateien werden bei Überschreitung bereinigt.
- letzter interner Snapshot kann ohne Produktiv-Restore verifiziert werden.

## Container
- non-root.
- read-only Root-Dateisystem.
- `cap_drop: ALL`.
- `no-new-privileges`.
- tmpfs mit `noexec,nosuid,nodev`.
- PID-, RAM- und CPU-Limit.
- Standard-Bind nur `127.0.0.1`.
- Base-Image-Digest gepinnt.

## Ergebnis
`tests/security_audit.py`: **45/45 statische Sicherheitschecks PASS**.

Zusätzlich wurden für v0.21.0 **51/51 Anwendungstests** erfolgreich ausgeführt, einschließlich Mehrbenutzer-/Mehrbuch-Isolation, Public-Modus, Mobile-Layout und Release-Plausibilität.

## Restpunkte
1. Für externe Erreichbarkeit ist HTTPS über einen Reverse Proxy Pflicht; dann `SECURE_COOKIES=true`.
2. Kein unabhängiger Penetrationstest.
3. `scripts/security-scan.sh` integriert `pip-audit` und Trivy; die Scans müssen in einer Umgebung mit Internetzugriff und für den Image-Scan mit gebautem Container ausgeführt werden.
4. Open Banking benötigt vor Produktivbetrieb einen separaten Threat Model-/OAuth-/Token-Audit.
