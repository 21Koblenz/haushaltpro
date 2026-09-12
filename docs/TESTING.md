# v0.21.0 Demo- und Plausibilitätstest

## Status

**Noch nicht gegen den v0.21.0-Anwendungscode ausgeführt.** Der Quellstand aus der vorherigen Entwicklungssitzung ist in diesem neuen Repository noch nicht vorhanden. Dieses Dokument definiert deshalb die reproduzierbare Prüfmethode und die unabhängigen Sollwerte, ohne ein bestandenes Ergebnis vorzutäuschen.

---

# Deutsch

## Testprinzip

Für Finanzsoftware reicht es nicht, dass die Oberfläche plausibel aussieht. Jeder relevante Rechenweg soll mit festen Demo-Daten geprüft werden:

1. Eingabedaten festlegen.
2. Erwartungswert unabhängig von der Anwendung berechnen.
3. Datensatz in HaushaltPro eingeben/importieren.
4. Anzeige, Summen, Salden, Planung und Prognose vergleichen.
5. Abweichung dokumentieren.
6. Randfälle getrennt testen.

## Referenz-Demohaushalt

### Anfangsstände

| Konto | Anfangsstand |
|---|---:|
| Girokonto | 2.000,00 € |
| Tagesgeld | 5.000,00 € |
| Bargeld | 200,00 € |
| **Gesamt** | **7.200,00 €** |

### Buchungen Monat 1

| Nr. | Typ | Konto | Kategorie | Betrag |
|---:|---|---|---|---:|
| 1 | Einnahme | Girokonto | Gehalt | +3.000,00 € |
| 2 | Ausgabe | Girokonto | Miete | -1.000,00 € |
| 3 | Ausgabe | Girokonto | Strom | -120,00 € |
| 4 | Ausgabe | Girokonto | Lebensmittel | -400,00 € |
| 5 | Ausgabe | Bargeld | Freizeit | -100,00 € |
| 6 | Transfer | Girokonto → Tagesgeld | Umbuchung | 500,00 € |
| 7 | Einnahme | Girokonto | Erstattung | +50,00 € |
| 8 | Ausgabe | Girokonto | Versicherung | -150,00 € |

### Unabhängig berechnete Sollwerte

**Einnahmen:**

```text
3.000 + 50 = 3.050,00 €
```

**Ausgaben ohne Transfers:**

```text
1.000 + 120 + 400 + 100 + 150 = 1.770,00 €
```

**Monatlicher Überschuss:**

```text
3.050 - 1.770 = 1.280,00 €
```

**Kontostände nach allen Buchungen:**

Girokonto:

```text
2.000 + 3.000 - 1.000 - 120 - 400 - 500 + 50 - 150 = 2.880,00 €
```

Tagesgeld:

```text
5.000 + 500 = 5.500,00 €
```

Bargeld:

```text
200 - 100 = 100,00 €
```

Gesamtvermögen:

```text
2.880 + 5.500 + 100 = 8.480,00 €
```

Kontrollrechnung:

```text
7.200 + 3.050 - 1.770 = 8.480,00 €
```

**Wichtig:** Die interne Umbuchung von 500 € darf weder Einkommen noch Ausgabe des Gesamthaushalts verändern.

## Testfälle

### A. Buchungen

Zu prüfen:

- positive Einnahme;
- normale Ausgabe;
- Betrag mit Cent;
- Nullbetrag, falls erlaubt/verboten;
- sehr großer Betrag;
- negative Eingabe an falscher Stelle;
- heutiges Datum;
- vergangenes Datum;
- Zukunftsdatum entsprechend Anwendungsregel;
- Bearbeiten;
- Löschen;
- Mehrfachanlage/Dubletten;
- Sortierung bei gleichem Datum;
- Filter und Suche;
- Kategorien;
- Notizen/Sonderzeichen/Umlaute;
- mobile Darstellung ohne rechts abgeschnittene Pflichtfelder.

### B. Transfers

- Giro → Tagesgeld;
- Gegenrichtung;
- vollständiger Transfer;
- Transfer mit Cent;
- Bearbeiten/Löschen;
- keine doppelte Berücksichtigung in Einnahmen/Ausgaben;
- Gesamtvermögen bleibt durch Transfer unverändert.

### C. CSV-Import

Bekannter Importpfad berücksichtigt unter anderem Datums-/Betragsfelder wie `Buchungstag`, `Datum`, `Booking Date`, `Betrag`, `Umsatz` und `Amount`. Der endgültige Test muss gegen den tatsächlichen v0.21.0-Parser erfolgen.

Zu prüfen:

- deutsches Zahlenformat `1.234,56`;
- negatives deutsches Zahlenformat;
- ISO-Datum;
- deutsches Datum;
- leere Zeilen;
- ungültiger Betrag;
- fehlendes Datum;
- fehlende Kontozuordnung;
- Dublette derselben Bankzeile;
- zwei echte verschiedene Buchungen mit gleichem Betrag/Datum;
- Umlaute und Sonderzeichen;
- CSV mit zusätzlicher unbekannter Spalte;
- erneuter Import derselben Datei.

### D. Planung und Prognose

Nach Import des exakten Quellstands werden alle im Programm vorhandenen Planungsarten einzeln erfasst und mit festen Sollwerten getestet.

Basisfall für wiederkehrende Monatswerte:

```text
Startvermögen:           8.480 €
monatliche Einnahmen:    3.050 €
monatliche Ausgaben:     1.770 €
Monatsüberschuss:        1.280 €
```

Ohne Zinsen und zusätzliche Ereignisse:

| Horizont | Soll-Endbestand |
|---|---:|
| 1 Monat | 9.760,00 € |
| 3 Monate | 12.320,00 € |
| 6 Monate | 16.160,00 € |
| 12 Monate | 23.840,00 € |

Formel:

```text
Endbestand = 8.480 + Monate × 1.280
```

Zu prüfen sind zusätzlich alle tatsächlich implementierten Varianten wie einmalige Planwerte, wiederkehrende Planwerte, Start-/Enddatum, Änderungen und Löschungen, sobald der Source importiert ist.

### E. Monats-/Jahressummen

Bei zwölf identischen Monaten:

```text
Jahreseinnahmen = 12 × 3.050 = 36.600 €
Jahresausgaben  = 12 × 1.770 = 21.240 €
Jahresüberschuss = 15.360 €
```

### F. Rundung

Testwerte:

```text
0,01 €
0,10 €
10,01 €
1.234,56 €
```

Es darf keine sichtbare Gleitkomma-Ausgabe wie `10.009999999` entstehen. Finanzwerte müssen entsprechend der Anwendungslogik centgenau bleiben.

### G. Responsive/mobile UI

Mindestens folgende Breiten prüfen:

- 320 px
- 360 px
- 390 px
- 412 px
- 768 px
- Desktop

Besonders die Buchungstabelle darf auf Mobilgeräten nicht so abgeschnitten werden, dass Daten oder Bedienaktionen unerreichbar sind. Zulässig sind je nach Design responsives Umbrechen, Kartenlayout oder bewusstes horizontales Scrollen mit erreichbaren Controls.

### H. Fehlerfälle

- leere Datenbank;
- nur Einnahmen;
- nur Ausgaben;
- Konto exakt 0,00 €;
- negatives Konto, sofern erlaubt;
- Löschen der letzten Buchung;
- Import einer leeren CSV;
- beschädigte CSV;
- Neustart des Containers;
- Anwendung nach Backup/Restore;
- fehlende optionale Konfiguration;
- ungültige Konfiguration.

## Release-Gate v0.21.0

v0.21.0 darf erst als geprüft markiert werden, wenn:

- der exakte Release-Commit feststeht;
- automatisierte Tests erfolgreich sind;
- alle vorhandenen Funktionsbereiche in eine Testmatrix aufgenommen wurden;
- die Demo-Sollwerte mit der Anwendung übereinstimmen;
- mobile Ansichten geprüft wurden;
- Neuinstallation geprüft wurde;
- Upgrade/Restart und Datenpersistenz geprüft wurden;
- Backup/Restore mindestens einmal erfolgreich getestet wurde;
- keine bekannten kritischen Fehler offen sind.

---

# English

The v0.21.0 release must be validated against fixed demo data and independently calculated expected values. Transfers must not change household income/expense totals, balances must reconcile, forecasts must match their documented formulas and mobile layouts must keep all relevant data/actions reachable.

The reference dataset above yields:

- opening net balance: **€7,200.00**;
- income: **€3,050.00**;
- expenses excluding transfers: **€1,770.00**;
- monthly surplus: **€1,280.00**;
- closing net balance: **€8,480.00**;
- 12-month projected balance with a constant €1,280 monthly surplus and no other effects: **€23,840.00**.

This file becomes a test report only after the exact release source has been imported and each case has been executed. Until then it is intentionally a test specification, not evidence of a passed release.
