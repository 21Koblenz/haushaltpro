# Offline-Sync – Dev-Test

Diese Funktion ist für den `:dev`-Kanal vorgesehen und noch kein stabiles Release.

## Unterstützt

Nach einer erfolgreichen Anmeldung kann HaushaltPro bei einem Verbindungsabbruch neue JSON-basierte Einträge lokal puffern und nach Wiederherstellung der Serververbindung automatisch synchronisieren.

Aktuell offline puffern lassen sich:

- neue Buchungen,
- neue Transfers,
- neue wiederkehrende Buchungsserien,
- neue offene Posten und Zahlungen zu bestehenden Posten (Zahlungsdialog vorher online öffnen).

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

## v0.21.9-dev.6 testen

Die vollständigen Update-Schritte stehen in den [Release Notes](RELEASE-NOTES-v0.21.9-dev.6.md). `main` bezeichnet Quellcode, `:dev` ein Docker-Image. Erst Pull/Neuerstellung des Containers installiert ein Update. Dieses Testrelease besitzt zusätzlich den festen Image-Tag `:0.21.9-dev.6` und den Git-Tag `v0.21.9-dev.6` auf dem Testbranch `dev`.

Zusätzliche Prüfungen:

1. Eine Monatsserie mit 100 EUR am 20. September, Oktober und November anlegen. Nur September auf den 1. Oktober verschieben. September enthält für diese Serie 0 EUR, Oktober 200 EUR, November 100 EUR.
2. Den verschobenen Termin erneut bearbeiten. Sein ursprünglicher Termin bleibt der 20. September. Der Oktober-Termin am 20. bleibt separat erhalten.
3. Eine Einzelbuchung vom Dezember in den Januar verschieben. Jahres- und Monatsansichten vergleichen.
4. Bei geöffnetem Buch Serververbindung trennen, mehrere Einträge erfassen, wieder verbinden: Warteschlange geht auf null, jeder Eintrag erscheint einmal. Offline-Einträge stehen bis zum Sync in der Warteschlange, noch nicht in den serverseitigen Summen.
5. Nach Offline-Erfassung abmelden und mit einem anderen Benutzer anmelden: Einträge des ursprünglichen Benutzers werden nicht übertragen. Zum Übertragen wieder mit dem ursprünglichen Benutzer das passende Haushaltsbuch öffnen.
6. Bei einem Sitzungsablauf erneut anmelden. Bei einem Sync-Fehler Anzeige anklicken und Fehlertext prüfen; ein dauerhaft abgewiesener Eintrag bleibt erhalten und stoppt die Warteschlange bis zur Behebung.

Die Warteschlange wird erst nach erfolgreichem IndexedDB-Transaktionsabschluss als gespeichert bestätigt. Bei bekanntem Verbindungsabbruch wird direkt lokal gespeichert. Unsichere Serverantworten werden mit derselben ID erneut geprüft. Bereits wartende Einträge aus der ersten Dev-Version bleiben erhalten; mangels früherer Benutzerzuordnung werden sie nur nach ausdrücklicher Bestätigung per Klick auf die Statusanzeige übernommen.

## English test summary

Load and sign in online before testing offline creation. Create new transactions/transfers/series during an outage, reconnect, and verify that each entry is created exactly once. Pending entries are not included in server-side totals until synchronization. User/book switches must not replay another user's queue. Move one 100 EUR monthly September occurrence to October 1: September contributes 0 EUR, October 200 EUR, November 100 EUR. Test another edit and a December-to-January move. Full offline cold start and offline edits/deletes are outside this prerelease; pending IndexedDB payloads remain unencrypted.
