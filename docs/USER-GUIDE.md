# HaushaltPro – Benutzerhandbuch

## Zweck
HaushaltPro soll gleichzeitig Haushaltsdokumentation und Liquiditätsprognose sein. Echte Buchungen dokumentieren die Vergangenheit; zukünftige Buchungen und wiederkehrende Serien bilden die Planung.

## Konten
Ein Konto benötigt ein Startdatum und einen Startsaldo. Der Monatsanfang eines Folgemonats entspricht dem Monatsendstand des Vormonats. Manuelle Monatskorrekturen überschreiben nur die Berechnungsbasis des gewählten Monats, nicht die historischen Buchungen.

## Buchungen
Jede Buchung kann enthalten:
- Name
- Empfänger
- Kategorie
- Datum
- Betrag
- Tags
- Notiz
- Prognose-Sicherheit
- Fixkosten-Kennzeichnung
- optionale Wiederholung

Der Name ist die primäre Bezeichnung, z. B. „KFZ-Versicherung“. Der Empfänger kann z. B. „HUK24“ sein.

Die Buchungsliste startet eingeklappt. Name, Wiederholungssymbol, Datum, Betrag und Konto bleiben sichtbar. Antippen oder per Tastatur Öffnen zeigt Kategorie, Empfänger, Notizen, Belege und Bearbeitungsaktionen. Bei verschobenen Serienterminen steht der ursprüngliche Termin in den Details.

## Offene Zahlungen

Unter **Offene Zahlungen → + Offener Posten** eine Verbindlichkeit („ich muss bezahlen“) oder Forderung („ich bekomme Geld“) anlegen. Bezeichnung, Gegenpartei und Gesamtbetrag sind Pflicht; Fälligkeit und Notiz sind optional. Die Übersicht zeigt Restbeträge, Status und überfällige Posten. Der Status ergibt sich aus den zugeordneten Zahlungen; erledigte und stornierte Posten sind über den Filter erreichbar.

Über **Zahlung erfassen** entweder eine bereits gebuchte Zahlung zuordnen oder eine neue Kontobuchung erstellen. Nur den tatsächlich gezahlten Teilbetrag angeben. Beispiel: Eine Forderung über 200 EUR mit einer Rückzahlung von 50 EUR bleibt mit 150 EUR offen. Die ursprüngliche Auszahlung muss als eigene Kontobuchung vorliegen; das Anlegen der Forderung bucht kein Geld.

Vorhandene Buchungen lassen sich mit ihrem freien Betrag auf mehrere Posten verteilen. Die Zuordnung verändert keinen Kontostand. Eine neue Zahlung erzeugt genau eine Kontobuchung. Zuordnungen können gelöst werden, ohne die Buchung zu löschen. Storno oder Löschung einer verknüpften Buchung erhöht den offenen Rest wieder. Änderungen, die bestehende Zahlungen unterschreiten oder die Zahlungsrichtung umkehren, werden abgewiesen.

Die Posten werden in EUR geführt. Sie verändern allein weder Kontostände noch Prognosen. Die Fälligkeit dient der Übersicht; für zukünftige Kontobewegungen wie bisher eine geplante Buchung nutzen und diese nach der tatsächlichen Zahlung zuordnen. Leseberechtigte können Posten und Zahlungen sehen, aber nicht verändern. Alle Daten gehören zum aktiven Haushaltsbuch.

## CSV-Export

**Buchungen → CSV-Export** exportiert alle passenden Buchungen nach Zeitraum, Konto, Kategorie, Status und Suchtext. Die aktuelle Listen-Seite begrenzt den Export nicht. Stornierte Buchungen werden ausgeschlossen. Split-Buchungen haben eine Zeile je Teilbetrag; mit Kategorie-Filter werden ausschließlich die passenden Teilbeträge exportiert. Ein Export ist auf 100.000 Zeilen begrenzt; bei größeren Beständen den Zeitraum eingrenzen.

**Planung & Prognose → Fixkosten als CSV exportieren** liefert den Jahresplan mit zwölf Monatsspalten und einer Jahressumme. Jahreszahlungen stehen vollständig im Fälligkeitsmonat. Verschobene Einzeltermine, Serienversionen und Betragsausnahmen werden berücksichtigt. Der Export zeigt Planwerte, nicht den Nachweis tatsächlich geleisteter Zahlungen.

Die Dateien verwenden UTF-8 mit BOM, Semikolon und Dezimalkomma. Text, den Tabellenprogramme als Formel interpretieren könnten, erhält ein führendes Apostroph. CSV-Dateien enthalten lesbare Finanzdaten.

## Kategorien
Die Kategorie bestimmt die Art:
- Einnahme
- Ausgabe
- Sparen

Eine Sparbuchung reduziert das Konto, wird aber getrennt von Konsumausgaben ausgewertet.

## Wiederkehrende Buchungen
Wiederholungen können täglich, wöchentlich, monatlich oder jährlich laufen und optional ein Enddatum haben. Änderungen können ab einem Stichtag als neue Serienversion gelten.

## Planung & Prognose
Die Monatsansicht zeigt Monatsanfang, Stichtagsstand und Monatsendprognose. Die langfristige Prognose zeigt Monatsendstände für 3/6/12 Monate. Die Jahresübersicht zeigt Plan/Ist und Monatsendstand für alle zwölf Monate.

## Finanz-Check
Der Finanz-Check sollte nach größeren Imports, Korrekturen oder Restore-Vorgängen ausgeführt werden. Er kontrolliert Rechenlogik und Integrität.

## Kontenabgleich
Vergleiche regelmäßig den errechneten Stand mit dem echten Bankstand. Eine Korrekturbuchung wird nur nach ausdrücklicher Bestätigung erzeugt.

## Belege
Belege werden nie automatisch importiert. Nur explizit hochgeladene Dateien werden dauerhaft in der SQLCipher-Datenbank gespeichert.

## Backups
- `.hpb` herunterladen: externes, passwortgeschütztes Backup.
- internes Backup: lokale Snapshot-Rotation im Docker-Volume.
- ein internes Backup schützt nicht vor Verlust des gesamten Hosts; externe Sicherung bleibt notwendig.


## Monat / Jahr
Dashboard und Planung & Prognose besitzen einen Umschalter zwischen Monats- und Jahresansicht. Die Jahresansicht verwendet dieselbe Berechnungslogik wie die Monatsprognose und zeigt zwölf Monatsendstände.

## Änderungsverlauf
Der Reiter **Änderungsverlauf** zeigt eine Timeline wichtiger Änderungen. Angezeigt werden Benutzer, Aktion und Zeitpunkt. Die Zeit wird intern in UTC protokolliert und im Browser in lokaler Zeit dargestellt. Die Hashkette wird zusätzlich vom Finanz-Check geprüft.


## Änderungsverlauf
Unter **Einstellungen → Änderungsverlauf** befindet sich die Audit-Timeline. Sie zeigt für neue protokollierte Änderungen:
- Benutzername
- Aktion
- betroffenen Datensatz
- Datum und lokale Uhrzeit
- Audit-ID und Hash-Status

Die Timeline wird in der verschlüsselten SQLCipher-Datenbank gespeichert. Sie ist kein Docker- oder Systemlog. Ältere Änderungen aus der Zeit vor Einführung des Audit-Journals können teilweise keine Benutzerzuordnung enthalten.


## Gespeicherte Empfänger
Beim Erfassen einer normalen Buchung kannst du **„Empfänger für spätere Vorauswahl merken“** aktivieren. Nur dann wird der Empfänger als Vorschlag gespeichert. Ohne Opt-in bleibt der Text ausschließlich Bestandteil der Buchung. Unter **Einstellungen → Gespeicherte Empfänger** kannst du die Vorschlagsliste pflegen. Umbenennen oder Löschen eines Vorschlags ändert keine historischen Buchungen.

## Interne Transfers
Nutze **Buchungen → Transfer**, wenn Geld nur zwischen deinen eigenen Konten verschoben wird, z. B. Girokonto → Bargeld nach einer Bargeldabhebung. HaushaltPro bucht den Betrag auf dem Quellkonto ab und auf dem Zielkonto zu. Der Gesamtbestand des Haushalts bleibt dadurch gleich. Transfers zählen weder als Haushaltseinnahme noch als Haushaltsausgabe und werden aus Budget-, Sparquoten- und Kategorieauswertungen ausgeschlossen.

## Buchungslisten
Im Bereich Buchungen kannst du zwischen **Alle Buchungen** und **Wiederkehrende Buchungen** wechseln. Die normale Liste unterstützt weiterhin Monat, Jahr oder den gesamten Zeitraum sowie 10/25/50/100/Alle Einträge pro Seite.

## Kategorieauswertung
Unter **Auswertung** zeigen zwei Donutdiagramme die Verteilung der Ausgaben und Einnahmen nach Kategorie. Die Legende enthält Betrag und Anteil in Prozent. Der gewählte Zeitraum kann Monat oder Jahr sein. Interne Transfers erscheinen dort nicht.

## Änderungsverlauf
Unter **Einstellungen → Änderungsverlauf** steht zu jeder protokollierten Änderung der Benutzer, Zeitstempel und eindeutig betroffene Datensatz. Geänderte Felder erscheinen als Alt → Neu; unveränderte relevante Felder stehen darunter als **Aktueller Stand**. Die Audit-Daten werden in der SQLCipher-Datenbank gespeichert und über eine Hashkette auf nachträgliche Manipulation geprüft.


## Mehrere Haushaltsbücher und Benutzerrechte
Unter Einstellungen können Eigentümer Benutzer anlegen, Rechte ändern und Passwörter zurücksetzen. Rechte gelten immer nur für das aktuell ausgewählte Haushaltsbuch. Ein Benutzer kann mehreren Haushaltsbüchern zugeordnet sein.

- Eigentümer: vollständige Verwaltung des Haushaltsbuchs.
- Bearbeiter: laufende Finanzdaten bearbeiten.
- Nur Lesen: reine Ansicht.

Jedes Haushaltsbuch ist eine eigene SQLCipher-Datenbank. Dadurch können z. B. ein gemeinsamer Haushalt und ein Kinder-Haushaltsbuch parallel betrieben werden, ohne dass Buchungen oder Auswertungen vermischt werden.

## Speicher & Datenpflege
Die Einstellungen zeigen die aktuelle Datenbankgröße und den Belegspeicher. Für Massenlöschungen muss zuerst der Zeitraum geprüft und anschließend exakt `LÖSCHEN` eingegeben werden. Der Audit-Verlauf bleibt als manipulationsgeschützte Historie erhalten.

## Änderungsverlauf verwalten
Unter **Einstellungen → Änderungsverlauf** kann die Timeline durchsucht und seitenweise angezeigt werden. Bei Löschvorgängen zeigt sie den letzten bekannten Stand des gelöschten Objekts. Eigentümer dürfen einzelne Logeinträge bewusst löschen; HaushaltPro fordert dazu `LÖSCHEN` als zweite Bestätigung an und baut anschließend die Hashkette neu auf.

## Haushaltsbücher verwalten
Unter **Einstellungen → Haushaltsbücher** können berechtigte Benutzer Bücher öffnen und umbenennen. Ein nicht aktives Haushaltsbuch kann endgültig gelöscht werden. Vor dem Löschen muss sein Name exakt bestätigt werden. Das aktuell geöffnete und das letzte verbliebene Haushaltsbuch sind geschützt.

## Benutzer löschen
Nur der System-Administrator kann ein globales Benutzerkonto endgültig entfernen. Ist der Benutzer alleiniger Eigentümer eines Haushaltsbuchs, muss zuerst ein weiterer Eigentümer festgelegt werden. Historische Audit-Einträge behalten den alten Benutzernamen.


## Performance und Datenbankwachstum (v0.10.2)
HaushaltPro berechnet Monatscharts gebündelt und hält häufig gelesene Dashboard-/Planungsdaten kurz im Arbeitsspeicher. Schreibvorgänge verwerfen diese Caches sofort. Finanzdaten werden dafür nicht in LocalStorage oder SessionStorage abgelegt.

SQLCipher/SQLite wächst automatisch mit den Daten. Eine Datenbank muss nicht vorab vergrößert oder wegen ihrer Größe neu angelegt werden. Entscheidend ist ausreichend freier Speicher auf dem Datenträger.

## Benutzerrechte über mehrere Haushaltsbücher
Unter Einstellungen → Benutzer & Rechte kann pro Benutzer zuerst das Haushaltsbuch und danach die Rolle gewählt werden. Die Freigabe ist damit unabhängig vom aktuell geöffneten Haushaltsbuch.
