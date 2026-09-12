# Security Policy

## Supported release

The latest tagged release is the supported release line unless stated otherwise.

## Reporting

Please do not publish credentials, private household data, working authentication bypasses or destructive exploit instructions in a public issue before a fix is available.

A useful report contains the affected version/commit, component, prerequisites, minimal reproduction steps, expected/actual behavior and impact.

## Deployment guidance

Prefer local or VPN-only access when public exposure is unnecessary. Public installations must use HTTPS through a maintained reverse proxy. Do not expose the database or internal administrative services. Never commit `.env`, keys, tokens, database files or backups.

See `docs/PUBLIC-DEPLOYMENT.md` and `docs/SECURITY-AUDIT.md`.
