# HaushaltPro translations / Übersetzungen

This preview introduces a translation layer without moving financial logic into language-specific code.

## Deutsch: Eine neue Sprache hinzufügen

1. Kopiere `static/i18n/_template.json` nach `static/i18n/<code>.json`, z. B. `fr.json`.
2. Trage unter `meta` Sprachcode, Anzeigename, nativen Namen und Browser-Locale ein.
3. Übersetze unter `messages` die stabilen Schlüssel. Diese Schlüssel werden bevorzugt für Dashboard, Navigation und neue UI verwendet.
4. Übersetze unter `legacy` die vorhandenen deutschen Quelltexte. Diese Kompatibilitätsschicht hält die heute noch direkt in `app.js` erzeugten Dialoge und Hinweise übersetzbar, ohne die Finanzlogik umzubauen.
5. Übersetze bei Bedarf die `patterns`. Sie decken dynamische Texte mit Datum, Anzahl oder Betrag ab. `$1`, `$2` usw. müssen erhalten bleiben.
6. Ergänze die Sprache in `static/i18n/languages.json`. Danach erscheint sie automatisch im Sprachmenü.
7. Öffne die Browser-Konsole und führe `HaushaltProI18n.audit()` aus. Die zurückgegebenen Texte sind noch nicht abgedeckte UI-Texte der aktuell geöffneten Ansicht.

Neue UI sollte möglichst **nicht** mit festem deutschem Text verdrahtet werden. Bevorzugt:

```html
<span data-i18n="dashboard.currentBalance">Aktueller Kontostand</span>
```

oder für JavaScript:

```js
const text = HaushaltProI18n.t('dashboard.currentBalance', 'Aktueller Kontostand');
```

Attribute werden ebenfalls unterstützt:

```html
<input data-i18n-placeholder="search.placeholder" placeholder="Suchen …">
<button data-i18n-title="common.refresh" title="Aktualisieren">…</button>
```

Unterstützte Attribute sind `data-i18n`, `data-i18n-placeholder`, `data-i18n-title`, `data-i18n-aria-label` und `data-i18n-alt`.

## English: Adding another language

1. Copy `static/i18n/_template.json` to `static/i18n/<code>.json`, for example `fr.json`.
2. Fill in the language code, display name, native name and browser locale under `meta`.
3. Translate the stable keys under `messages`. These are preferred for the Dashboard, navigation and all new UI.
4. Translate the German source strings under `legacy`. This compatibility bridge keeps dialogs and notices currently generated directly by `app.js` translatable without touching finance logic.
5. Translate `patterns` where needed. They cover dynamic text containing dates, counts or amounts. Keep `$1`, `$2`, etc. unchanged.
6. Add the new language to `static/i18n/languages.json`. It will automatically appear in the language selector.
7. Open the browser console and run `HaushaltProI18n.audit()`. The returned strings are UI text in the current view that is not yet covered.

For new UI, prefer stable translation keys using `data-i18n` or `HaushaltProI18n.t()` rather than hard-coded language-specific strings.

## Design

- German (`de`) is the fallback/source language.
- English (`en`) is included in this preview.
- The selected language is stored only in browser `localStorage` as `hp_lang`; it is not sent to a cloud service.
- No translation service, CDN or external API is used.
- Number/date formatting reads the selected locale, so English also changes `1.234,56 €`/German dates to an English locale format.
- Missing strings fall back to German instead of breaking the UI.

## Locale-sensitive form controls / Sprachabhängige Formulare

HaushaltPro keeps API/database values language-neutral while localizing what the user sees:

- dates are submitted as ISO `YYYY-MM-DD`, but the visible editor follows the selected language (`TT.MM.JJJJ` for German, `DD/MM/YYYY` for English);
- date/time/month output uses the locale declared in `static/i18n/languages.json`;
- native file inputs are visually replaced by localized controls, because browser captions otherwise follow the operating-system language;
- the six built-in categories use stable `category.default.*` message keys. User-created category names are data and are never automatically translated.

When adding a language, choose its `locale` deliberately (for example `fr-FR` or `en-GB`). This controls number, currency, date and time formatting without changing stored values.

## Stable keys versus legacy bridge / Stabile Schlüssel vs. Legacy-Brücke

New code should use `messages` keys whenever possible. The `legacy` map remains a compatibility layer for older UI text generated directly by `app.js`. `patterns` are only for dynamic sentences that contain values. This lets contributors add a translation without touching account, booking or forecast logic.
