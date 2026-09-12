# Vibe Coding / AI-assisted development

HaushaltPro is explicitly developed as a **Vibe Coding / AI-assisted project**.

AI may assist with architecture, implementation, refactoring, tests, documentation and review. AI output is treated as a proposal, never as proof of correctness.

## Project rules

1. Financial calculations require deterministic tests or independently calculated reference values.
2. Security-sensitive changes require explicit review of authentication, authorization, secrets, uploads and exposed network surfaces.
3. Changes must remain reviewable in Git history.
4. Real household data, bank exports, credentials, secrets and private backups must never be committed.
5. A release may only claim tests that were actually executed against the exact release source state.
6. Contributors remain responsible for reviewing AI-assisted code they submit.

## Deutsch

KI-gestützter Code gilt nicht automatisch als korrekt. Relevante Berechnungen, Migrationen und Sicherheitsfunktionen sollen reproduzierbar getestet und nachvollziehbar dokumentiert werden.
