# Offline-Sync – Dev-Test

Diese Funktion ist für den `:dev`-Kanal vorgesehen und noch kein stabiles Release.

## Unterstützt

Nach einer erfolgreichen Anmeldung kann HaushaltPro bei einem Verbindungsabbruch neue JSON-basierte Einträge lokal puffern und nach Wiederherstellung der Serververbindung automatisch synchronisieren.

Aktuell offline puffern lassen sich:

- neue Buchungen,
- neue Transfers,
- neue wiederkehrende Buchungsserien.

Oben in der Oberfläche zeigt HaushaltPro den Verbindungs- und Sync-Status sowie die Zahl wartender Änderungen. Ein Klick auf die Anzeige stößt eine erneute Serverprüfung bzw. Synchronisierung an.

Jede gepufferte Aktion besitzt eine eindeutige Client-ID. Der Server speichert erfolgreiche IDs und liefert bei einem Wiederholungsversuch die bereits erzeugte Antwort zurück. Dadurch führt ein Verbindungsabbruch unmittelbar nach dem Speichern nicht zu Doppelbuchungen.

Die Warteschlange ist an das aktive Haushaltsbuch gebunden und wird in Reihenfolge abgearbeitet. Bei einer abgelaufenen Anmeldung bleibt sie erhalten, bis sich der Benutzer erneut authentifiziert.

## Grenzen der ersten Dev-Version

Dies ist noch kein vollständiger Cold-Start-PWA-Modus. Die App muss vor dem Verbindungsabbruch bereits geladen und angemeldet gewesen sein. Wird Browser/App geschlossen und anschließend ohne erreichbaren Server neu geöffnet, stehen Konten, Kategorien und Empfänger noch nicht vollständig offline zur Verfügung.

Aus Datenschutzgründen wird bewusst kein vollständiger unverschlüsselter Finanzdatenbestand über einen Service-Worker-Cache gespiegelt. Die noch nicht synchronisierten Request-Payloads liegen in dieser Dev-Version im Same-Origin-IndexedDB des Browsers. Vor einem stabilen vollständigen Offline-Modus sollte dieser lokale Bestand zusätzlich verschlüsselt werden.

## Testablauf

1. `21koblenz/haushaltpro:dev` starten und normal anmelden.
2. Die App geöffnet lassen und anschließend die Serververbindung unterbrechen bzw. den Container stoppen.
3. Prüfen, dass die Statusanzeige auf Offline wechselt.
4. Eine Buchung, einen Transfer und optional eine wiederkehrende Buchung anlegen.
5. Prüfen, dass die Zahl wartender Änderungen angezeigt wird.
6. Server/Netzwerk wieder herstellen.
7. Auf die automatische Synchronisierung warten oder die Statusanzeige anklicken.
8. Seite neu laden und prüfen, dass jeder Eintrag genau einmal vorhanden ist.

Nicht offline gepuffert werden in dieser ersten Version unter anderem Datei-Uploads, Benutzer-/Rechteverwaltung, Backups/Restore sowie Bearbeiten/Löschen bestehender Datensätze.
