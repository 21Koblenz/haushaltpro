Testrelease für den **dev-Kanal** / prerelease for the **dev channel**.

## Deutsch

- **Wiederkehrende Buchungen:** Standardmäßig eingeklappte Karten wie bei den einzelnen Buchungen, einschließlich Transfer-Serien. Name, Wiederholungssymbol, nächster Termin, Konto und Betrag bleiben sichtbar. Details und Aktionen lassen sich aufklappen.
- **Konten:** Dashboard und Kontenverwaltung verwenden ebenfalls eingeklappte Karten. Geschlossen sichtbar: Name, Kontostand und Stichtag. Geöffnet: übersichtliche Zeilen für Monatsanfang, Bis heute/Bis Stichtag und Monatsende sowie die Kontenaktionen.
- **Dashboard auf Smartphones:** Monats- und Jahresgrafik nutzen die echte verfügbare Breite. Größere Achsenbeschriftung und weniger Beschriftungen bei wenig Platz; alle Werte bleiben auswählbar. Datum und genauer Betrag stehen unterhalb der Grafik.
- **Bedienung:** Antippen, Fingerbewegung oder Tages-/Monatsregler mit Tastaturbedienung. Größen-, Ausrichtungs- und Theme-Wechsel zeichnen die Grafik ohne erneute Datenabfragen. Auch die Analyse-Grafik passt sich schmalen Ansichten an.
- **Darstellungsschutz:** Lange Namen werden umgebrochen, negative Beträge bleiben erkennbar, Leseberechtigte sehen keine Bearbeitungsaktionen. Sprachwechsel und leere Daten führen nicht zu wiederholtem Neuzeichnen oder veralteten Wertanzeigen.

### Update und Test

Im bestehenden Compose-/Portainer-Stack:

```yaml
image: 21koblenz/haushaltpro:0.21.9-dev.4
```

Alternativ `21koblenz/haushaltpro:dev` verwenden. Image neu ziehen und den vorhandenen Container mit demselben Datenvolume neu erstellen:

```bash
docker compose pull
docker compose up -d
```

Im Footer muss **0.21.9-dev.4** stehen. Schema bleibt 28; dieses Update ändert die Darstellung und benötigt keine zusätzliche Datenbankmigration.

Zum Testen auf dem Smartphone:

1. Serienliste sowie Konten im Dashboard und in der Kontenverwaltung öffnen: Alle Karten starten geschlossen. Eine Karte antippen und die Details/Aktionen prüfen.
2. Bei einem Konto Monatsanfang, Bis heute/Bis Stichtag und Monatsende vergleichen. Auch einen anderen Monat auswählen.
3. In der Dashboard-Grafik den ersten und letzten Tag sowie einen Tag mit einer Buchung auswählen. Regler und Antippen müssen dasselbe Datum und denselben Betrag liefern.
4. Zwischen Monaten mit 28/29/30/31 Tagen, Monats-/Jahresansicht und Hoch-/Querformat wechseln. Helle und dunkle Darstellung prüfen.

### Prüfung

87 Python-Regressionsskripte, 23 JavaScript-Tests und 52 statische Sicherheitsprüfungen bestanden lokal; Compile- und Syntaxprüfungen ebenfalls. Neue DOM-/Zeichenprüfungen decken Kartenaktionen, Rechte, Stichtage, 280–1100 px Diagrammbreite, alle Monatslängen, Touch-/Reglerauswahl, Größenänderungen, leere Daten und die echte Sprachumschaltung ab.

Der Browser blockierte den lokalen Testzugriff mit `ERR_BLOCKED_BY_CLIENT`. Die automatisierten DOM- und Zeichenprüfungen ersetzen keine visuelle Prüfung auf einem echten Smartphone.

## English

Recurring bookings, transfer series and both account overviews now use collapsed cards. Account details show separate opening, cutoff and month-end balances.

Dashboard charts adapt to their actual container width, retain all data points, and show the selected date and full amount below the plot. Touch, range-slider and keyboard selection are supported. Resizing and theme changes redraw locally without fetching financial data again.

Use `21koblenz/haushaltpro:0.21.9-dev.4` or `:dev` and recreate the existing container while retaining its volume. Schema remains 28. Automated tests passed as listed above; visual mobile verification was blocked by the environment.
