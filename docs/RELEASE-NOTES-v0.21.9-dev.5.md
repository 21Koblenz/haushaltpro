Testrelease für den **dev-Kanal** / prerelease for the **dev channel**.

## Deutsch

- **Kontenkarten:** Auf dem Dashboard und unter Konten bleiben nun sowohl der aktuelle/Stichtagsstand als auch der Monatsendstand im eingeklappten Zustand sichtbar. Beide Werte sind beschriftet, negative Beträge gekennzeichnet. Die Werte stammen unverändert aus der bestehenden Monatsberechnung.
- **Geldfluss:** Unter Auswertung ist die neue verbundene Sankey-Darstellung im Sure-Stil der Standard. Proportionale Bänder verbinden Einnahmen mit Ausgaben, Sparen und dem verbleibenden Überschuss. Bei einem Minus zeigt ein gesonderter Fehlbetrag die Differenz; er zählt nicht als zusätzliche Einnahme.
- **Ansicht wählen:** „HaushaltPro · Klassisch“ bietet das bisherige Pfeildiagramm. Die Auswahl wird im Browser gespeichert und bleibt beim Monats-/Jahreswechsel erhalten. Ein Ansichtswechsel lädt keine Finanzdaten erneut.
- **Smartphones:** Unter 640 px Diagrammbreite läuft der Geldfluss von oben nach unten und zeigt die zusammengefassten Gruppen mit vollständigen Beträgen. „Alle Kategorien und Beträge“ enthält sämtliche Kategorien. Auf großen Bildschirmen werden bei vielen Kategorien kleinere Positionen grafisch zusammengefasst, bleiben aber in der Liste einzeln verfügbar.
- **Bedienung:** Antippen oder Tastaturauswahl hebt einen Geldstrom hervor und zeigt den genauen Betrag sowie den Anteil an seiner Gruppe. Lange Kategorienamen bleiben in der Liste vollständig lesbar. Sprachwechsel, leere Daten und Größenänderungen werden berücksichtigt.
- Die Sure-Gestaltungsvorlage ist in [THIRD-PARTY-NOTICES.md](THIRD-PARTY-NOTICES.md) dokumentiert; es wurden keine zusätzlichen Laufzeitbibliotheken benötigt.

### Update

Im vorhandenen Compose-/Portainer-Stack `21koblenz/haushaltpro:0.21.9-dev.5` oder `21koblenz/haushaltpro:dev` verwenden und mit demselben Datenvolume neu erstellen:

```bash
docker compose pull
docker compose up -d
```

Der Footer zeigt danach **0.21.9-dev.5**. Datenbankschema: weiterhin 28; keine zusätzliche Migration.

### Test auf dem Smartphone

1. Dashboard und Konten öffnen: Aktueller/Stichtagsstand und Monatsendstand müssen bereits auf geschlossenen Karten stehen. Einen anderen Monat sowie ein Konto mit negativem Monatsendstand prüfen.
2. Auswertung öffnen: Ohne gespeicherte Auswahl erscheint „Sankey · Sure-Stil“. Zu „HaushaltPro · Klassisch“ wechseln, den Monat ändern und die Seite neu laden: Die Auswahl bleibt erhalten.
3. Ein- und Ausgaben mit Sparen/Überschuss sowie einen Monat mit Fehlbetrag vergleichen. Die Beträge müssen mit den Kennzahlen oberhalb übereinstimmen.
4. Kategorienliste aufklappen, einen kleinen Betrag auswählen und anschließend das Smartphone drehen. Keine Kategorien oder Beträge dürfen verschwinden.
5. Helle/dunkle Ansicht, Deutsch/Englisch und Tastaturbedienung prüfen.

### Prüfung

87 Python-Regressionsskripte, 30 JavaScript-Tests und 52 statische Sicherheitsprüfungen bestanden lokal; Compile-, Syntax- und Whitespace-Prüfungen ebenfalls.

Die neuen DOM-/SVG-Tests prüfen Ansichtswechsel und Speicherung, centgenaue Flussgleichheit, Fehlbeträge, keine Einnahmen, 240–1280 px, 60 Kategorien, kleine/große Beträge, Text-Escaping, Auswahl, Größenänderungen, leere Daten und die echte Sprachumschaltung. SVG-Ansichten werden zusätzlich als Bilder geprüft. Diese Prüfung ersetzt keinen vollständigen Browsertest auf einem Smartphone; der lokale Browserzugriff war in dieser Umgebung gesperrt.

## English

Collapsed account cards now show both cutoff/current and month-end balances. Reports default to a connected Sankey view inspired by Sure, with the previous HaushaltPro diagram available as a second option. The browser remembers the choice.

Desktop bands display categories; narrow screens use a vertical group overview with exact amounts. Every category remains available in the expandable list. Surplus and deficit are represented separately; a deficit is not treated as additional income. Touch/keyboard selection, resizing, language changes and empty reports are supported without extra financial-data requests.

Use `21koblenz/haushaltpro:0.21.9-dev.5` or `:dev`, retaining the existing volume. Schema remains 28. DOM/SVG checks and rendered SVG inspection cover the new behavior; full visual browser verification remains a manual check.
