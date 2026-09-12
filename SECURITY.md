# Security Policy

## Supported version

Until the first validated release is published, security fixes apply to the current `main` branch. After v0.21.0 is released, the latest release line is the supported version unless stated otherwise.

## Reporting a vulnerability

Please avoid publishing a working exploit, credentials, private household data or authentication bypass details in a public issue before a fix exists.

A useful report should include:

- affected version or commit;
- affected component;
- prerequisites;
- minimal reproduction steps;
- expected vs. actual behavior;
- security impact;
- suggested mitigation, if known.

## Deployment principles

- Prefer local or VPN-only access when public exposure is unnecessary.
- Do not expose development servers directly to the Internet.
- Public deployment should use TLS, a maintained reverse proxy, strong authentication and regular backups.
- Never commit `.env` secrets, database dumps containing private data, tokens, API keys or credentials.

## Disclaimer

HaushaltPro is provided without warranty under the terms of the GNU AGPL. Security documentation reduces avoidable risk but is not a guarantee that a deployment is secure.
