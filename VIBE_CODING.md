# Vibe Coding / AI-assisted development

HaushaltPro is developed with substantial AI assistance. The project therefore explicitly identifies itself as **Vibe Coding / AI-assisted development**.

## What this means

AI may be used for architecture drafts, implementation, refactoring, tests, documentation and review assistance. AI output is treated as a proposal, not as proof of correctness.

## Requirements for contributions

1. Changes must remain reviewable in Git history.
2. Non-trivial calculation changes should include deterministic tests.
3. Financial calculations should use fixed demo data with independently calculated expected values.
4. Security-sensitive changes require an explicit review of authentication, authorization, secrets, input validation and exposed network surfaces.
5. Generated dependencies, binaries, credentials and private household data must not be committed.
6. A release must not claim a passed test that was not actually executed against that exact source state.

## Kennzeichnung auf Deutsch

HaushaltPro ist ein **Vibe-Coding-/KI-unterstütztes Projekt**. KI-generierter Code gilt nicht automatisch als korrekt. Relevante Berechnungen und Änderungen sollen mit reproduzierbaren Tests und nachvollziehbaren Commits abgesichert werden.
