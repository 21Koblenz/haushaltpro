Testrelease für den **dev-Kanal** / prerelease for the **dev channel**.

## Deutsch

- **Offene Zahlungen und Schulden:** Verbindlichkeiten und Forderungen mit Empfänger/Gegenpartei, Gesamtbetrag, Fälligkeit, Notiz und Status. Überfällige Posten werden hervorgehoben.
- **Teilzahlungen:** Beispielsweise 200 EUR verliehen, 50 EUR zurückbekommen → 150 EUR offen. Vorhandene Buchung zuordnen oder genau eine neue Kontobuchung erstellen. Freie Buchungsbeträge können auf mehrere Posten verteilt werden; Überzahlungen werden verhindert.
- **Korrekturen:** Eine Zuordnung lösen lässt die Kontobuchung bestehen. Storno/Löschung der Buchung öffnet den Restbetrag wieder. Widersprüchliche Betrags- oder Richtungsänderungen sind geschützt. Eigentümer/Bearbeiter dürfen ändern, Leseberechtigte nur ansehen und exportieren.
- **CSV-Export:** Buchungen nach Zeitraum, Konto, Kategorie, Status und Suchtext – über alle Ergebnisse. Split-Buchungen werden ohne doppelte Gesamtsummen exportiert. UTF-8/BOM, Semikolon, Dezimalkomma und Schutz gegen Formeln in Textfeldern.
- **Fixkostenübersicht:** CSV-Jahresplan mit zwölf Monatsspalten und Jahressumme. Jahreszahlungen erscheinen im Fälligkeitsmonat; verschobene Einzeltermine und Serienänderungen werden berücksichtigt.
- **Mobile Buchungskarten:** Standardmäßig eingeklappt; Name, Wiederholungssymbol, Datum, Betrag und Konto bleiben sichtbar. Antippen öffnet Details und Aktionen. Tastaturbedienung, große Schaltflächen und schmale Ansichten werden unterstützt.
- **Integration:** Bestehende Offline-Warteschlange auch für neue Posten und Teilzahlungen; Schutz vor Doppelbuchungen bei verlorenen Antworten. Additive Datenbankmigration 27 → 28, auch von Schema 26 getestet.

### Update

Im vorhandenen Compose-/Portainer-Stack das Image setzen und den Container aktualisieren:

```yaml
image: 21koblenz/haushaltpro:0.21.9-dev.3
```

```bash
docker compose pull
docker compose up -d
```

Alternativ den beweglichen Testtag `21koblenz/haushaltpro:dev` verwenden. Bestehendes Datenvolume und Konfiguration beibehalten; vorher ein externes Backup anlegen. Bei eigenem Quellcode-Build den Tag `v0.21.9-dev.3` auschecken. Im Footer muss **0.21.9-dev.3** stehen.

### Zum Testen

1. Forderung „Privatdarlehen“, 200 EUR, Fälligkeit gestern anlegen. 50 EUR als neue Rückzahlung buchen: Status „Teilweise bezahlt“, 150 EUR offen.
2. Eine vorhandene passende Buchung zuordnen: Der Kontostand bleibt unverändert. Zuordnung wieder lösen, Buchung anschließend stornieren und Restbeträge vergleichen.
3. Buchungen auf einem Smartphone öffnen: Karten anfangs geschlossen; wiederkehrende Zahlung erkennbar; Datum einer einzelnen Serie in den Details bearbeiten.
4. CSV-Export mit Datum, Konto und Kategorie prüfen, einschließlich Split-Buchung. Fixkosten-Jahresplan mit einer jährlichen Zahlung und einem verschobenen Monatsbetrag vergleichen.
5. Nach Online-Öffnen des Zahlungsdialogs die Verbindung trennen, Zahlung speichern und wieder verbinden: Die Zahlung darf genau einmal erscheinen.

### Grenzen und Prüfung

Offene Posten werden in EUR geführt und verändern allein keine Kontostände oder Prognosen. Für zukünftige Kontobewegungen geplante Buchungen verwenden; nach Ausführung zuordnen. Fixkostenexport ist ein Plan, kein Zahlungsnachweis. Buchungsexport enthält höchstens 100.000 Zeilen pro Download.

Offline-Zahlungserfassung benötigt einen zuvor online geöffneten Dialog zu einem bereits gespeicherten Posten. Neu offline angelegte Posten sind erst nach Synchronisierung zuordenbar. Full-Offline-Start und Offline-Bearbeiten/Löschen bleiben außerhalb dieses Releases; wartende IndexedDB-Payloads sind nicht zusätzlich verschlüsselt.

87 Python-Regressionsskripte, 16 JavaScript-Tests, 52 statische Sicherheitsprüfungen sowie Compile-/Syntax-Prüfungen bestanden lokal. Die Migration ist mit echter SQLCipher-Verschlüsselung geprüft. npm audit: keine bekannten Schwachstellen. Der lokale Browserzugriff war blockiert; automatisierte DOM-Interaktionen ersetzen keine visuelle Smartphone-Prüfung.

## English

This dev release adds payables, receivables and partial payments. Link existing cash bookings without double counting or create one new booking atomically. Derived balances, overdue highlighting, allocation guards, cancellation handling, permissions, household isolation and offline retry protection are included.

Export filtered bookings across all pages, with one row per split, or a fixed-cost plan with monthly and annual totals using effective recurring dates. Bookings now use collapsed, keyboard-accessible cards showing name, recurring icon, date, amount and account.

Use `21koblenz/haushaltpro:0.21.9-dev.3` or `:dev`, pull and recreate the existing container while retaining its data volume. Schema 28 is additive. Items are EUR-only and do not themselves change cash balances or forecasts; the fixed-cost CSV represents a plan. Automated checks passed as listed above; visual browser checks were blocked by the environment.
