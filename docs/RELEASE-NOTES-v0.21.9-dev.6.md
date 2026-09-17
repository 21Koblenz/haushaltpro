Testrelease für den **dev-Kanal** / prerelease for the **dev channel**.

## Deutsch

- **Online-Anzeige:** Der Hintergrund passt sich nun auch im Hellmodus an die Oberfläche an. Grüne, rote und blaue Statuspunkte bleiben gut erkennbar.
- **Werte verbergen:** Das neue Auge in der Kopfzeile blendet Eurobeträge und Prozentwerte als `****` aus und wieder ein. Die Auswahl wird im Browser gespeichert und zwischen geöffneten Tabs synchronisiert.
- **Alle Ansichten:** Konten, Buchungen, Serien, offene Zahlungen, Investments und Auswertungen berücksichtigen die Auswahl. Auch Canvas-/SVG-Diagramme, Achsen, Legenden, Prozentanteile, Tooltips und Screenreader-Beschriftungen werden maskiert. Nachgeladene Daten bleiben verborgen.
- **Bearbeitung:** Geldfelder und Textfelder mit Euro-/Prozentangaben zeigen im ausgeblendeten Zustand Sternchen. Das Antippen blendet die Werte bewusst wieder ein. Zusätzlich gibt es ein Auge direkt im Dialog. Native Pflichtfeld-, Grenzwert- und Cent-Prüfungen sowie die tatsächlichen Formularwerte bleiben erhalten.
- **Sprache und Smartphone:** Deutsche und englische Zahlenformate werden unterstützt. Das Auge bleibt auf schmalen Displays als beschriftetes Symbol mit mindestens 44 px Bedienfläche erreichbar.
- Die Funktion ist eine Anzeigeoption: Berechnungen, gespeicherte Werte, CSV-Exporte und Backups behalten die Originaldaten. Die Formen und Größenverhältnisse der Diagramme bleiben erkennbar. Keine zusätzliche Laufzeitbibliothek und keine Datenbankmigration; Schema weiterhin 28.

### Update

Im vorhandenen Compose-/Portainer-Stack `21koblenz/haushaltpro:0.21.9-dev.6` oder `21koblenz/haushaltpro:dev` verwenden und mit demselben Datenvolume neu erstellen:

```bash
docker compose pull
docker compose up -d
```

Der Footer zeigt danach **0.21.9-dev.6**.

### Test auf dem Smartphone

1. Hellmodus wählen und die Online-Anzeige prüfen: heller Hintergrund, lesbarer Text/Statuspunkt. Zwischen Hell- und Dunkelmodus wechseln.
2. Auge antippen: Auf Dashboard, Konten, Buchungen, Serien und offenen Zahlungen müssen Euro-/Prozentwerte als `****` erscheinen, auch beim Aufklappen oder beim Monatswechsel.
3. Auswertungen öffnen, Sure/klassisch umschalten und einen Geldstrom sowie einen Ringdiagramm-Anteil antippen: Auch die Beschriftungen müssen verborgen bleiben.
4. Eine vorhandene Buchung bearbeiten: Betrag zunächst verborgen, nach bewusstem Antippen bearbeitbar. Wieder ausblenden, speichern und anschließend einblenden: Der gespeicherte Wert stimmt.
5. Seite neu laden, einen zweiten Tab öffnen und Deutsch/Englisch wechseln: Auswahl und aktuelle Werte bleiben korrekt. Der CSV-Export enthält weiterhin echte Beträge.

### Prüfung

Alle 87 Python-Regressionsskripte, 39 JavaScript-Tests und 52 statischen Sicherheitsprüfungen sowie Compile-, Syntax- und Whitespace-Prüfungen bestanden lokal.

Neun neue DOM-/Canvas-/SVG-Tests prüfen Zahlenformate, Speicherung, blockierten Browserspeicher, Tab-Synchronisierung, dynamische Aktualisierungen, Wiederherstellung, native Formularwerte und Validierung, signierte Geldfelder, beide Flussdiagramme, alle Canvas-Renderer, echte Sprachumschaltung und unveränderten CSV-Inhalt. Canvas-Tests prüfen Zeichenbefehle, keine Browser-Pixel. Der lokale Browserzugriff war in dieser Umgebung gesperrt; die visuelle Smartphone-Prüfung bleibt anhand der Schritte oben möglich.

## English

The connection indicator now matches the light theme. New eye controls in the header and dialogs hide/show EUR amounts and percentages as `****`, with a saved browser preference and cross-tab synchronization. Cards, dynamic views, chart axes, legends, tooltips and accessible labels follow this preference.

Hidden financial fields can be explicitly revealed for editing. Form values and validation, calculations, saved data, CSV exports and backups remain unchanged. Chart shapes and relative sizes remain visible. Schema remains 28; no extra runtime dependencies.

Use `21koblenz/haushaltpro:0.21.9-dev.6` or `:dev`, keeping the existing volume. Nine new interaction tests extend the suite to 39 JavaScript tests alongside 87 Python scripts and 52 static security checks. Full visual smartphone verification remains a manual check.
