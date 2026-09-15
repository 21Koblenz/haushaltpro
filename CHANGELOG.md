# Changelog

## Unreleased

### Fixed

- The current-month analysis now includes known/planned bookings through month end, including materialized recurring expenses and income. Historical months and yearly analysis remain actual-only.
- Completed the English UI translations for recurring transfer and recurring-series controls.

### Changed

- The dedicated “+ Wiederkehrende Buchung” entry point remains available and now supports saved/free-text payees. The payee is stored on the recurring series and propagated to generated planned transactions.
- Forecast and planning calculations now batch recurring occurrence, override and category lookups instead of issuing SQL queries per due date. A dedicated split-transaction index speeds category reports on larger datasets.

### Added

- Transfers can now repeat with the same calendar interval model as recurring bookings (daily, weekly, monthly, quarterly, half-yearly, yearly or custom). Recurring transfers remain neutral in income/expense analysis while moving the source and destination account forecasts.
- Recurring transactions support quarterly and half-yearly presets plus arbitrary calendar intervals such as every 10 days, 2 weeks, 5 months or 2 years. Existing recurring series keep their previous rhythm with an interval multiplier of 1.

