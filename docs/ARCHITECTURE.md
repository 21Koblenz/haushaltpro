# HaushaltPro v0.21.0 – Architektur

## Identitäten und Haushaltsbücher

`/data/auth.json` enthält globale Benutzeridentitäten, öffentliche Schlüssel, passwortverschlüsselte private Benutzerschlüssel sowie die Mitgliedschaften der Haushaltsbücher. Datenbank-Masterkeys liegen dort ausschließlich mit dem öffentlichen Schlüssel des jeweiligen Mitglieds verschlüsselt vor.

Das bisherige Haushaltsbuch bleibt `/data/haushaltpro.db`. Zusätzliche Haushaltsbücher liegen als eigene SQLCipher-Dateien unter `/data/books/<id>.db`.

## Rollen

- `owner`: lesen/schreiben, Benutzerverwaltung, Backup, Datenpflege.
- `editor`: lesen/schreiben der laufenden Haushaltsdaten.
- `viewer`: nur lesen.

Die Rolle ist eine Mitgliedschaftseigenschaft des jeweiligen Haushaltsbuchs, nicht global.

## Sitzungen

Authentifizierte Sitzungen liegen nur im Arbeitsspeicher. Eine Sitzung hält den entschlüsselten privaten Benutzerschlüssel sowie den Masterkey des aktuell gewählten Haushaltsbuchs. Nach einem App-Neustart ist eine erneute Anmeldung erforderlich.

Pro Request aktiviert `app/db.py` über ContextVars den Pfad und Schlüssel des ausgewählten Haushaltsbuchs. Dadurch können unterschiedliche Benutzer gleichzeitig mit unterschiedlichen SQLCipher-Datenbanken arbeiten.

## Backups

Interne Rotationsbackups liegen getrennt unter `/data/backups/<book-id>/...`. Portable HPB4-Backups enthalten genau ein Haushaltsbuch und die zur Verifikation nötigen Schlüsselmetadaten des exportierenden Benutzers.

## Audit

Jedes Haushaltsbuch besitzt sein eigenes `audit_log`. Änderungen an Benutzermitgliedschaften werden in dem Haushaltsbuch protokolliert, in dem sie vorgenommen wurden. Die Hashkette dient der Manipulationserkennung.
