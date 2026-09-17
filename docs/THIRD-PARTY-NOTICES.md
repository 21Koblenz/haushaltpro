# Design references / Gestaltungsvorlagen

## Sure cash-flow Sankey

Die verbundene Geldflussansicht in HaushaltPro orientiert sich an der Sankey-Darstellung von [we-promise/sure](https://github.com/we-promise/sure), einem AGPL-3.0-Projekt aus der Maybe-Finance-Community. Geprüfte Referenz: [Sankey-Controller, Commit 42836cc](https://github.com/we-promise/sure/blob/42836ccaccbb4c72ba15e155a0a6ee71f24a90fc/app/javascript/controllers/sankey_chart_controller.js), einschließlich proportionaler Verbindungen, Farbverläufe und Betragsbeschriftungen.

HaushaltPro implementiert diese Darstellung selbst in `static/report-flow.js` für die vorhandenen Auswertungsdaten. Auf Smartphones zeigt eine vertikale Ansicht die Gruppen; die vollständige Kategorienliste bleibt erreichbar. Kein Sure-, Maybe-, D3- oder Stimulus-Code und keine zusätzlichen Bibliotheken wurden übernommen. Es besteht keine Verbindung zu oder Unterstützung durch die Sure-/Maybe-Projekte.

The connected cash-flow view is visually inspired by Sure's Sankey chart, referenced above. It is an original HaushaltPro implementation using existing report data, with a vertical group overview for phones and a complete accessible category list. No Sure/Maybe implementation or D3/Stimulus dependency is bundled. HaushaltPro is not affiliated with or endorsed by these projects.
