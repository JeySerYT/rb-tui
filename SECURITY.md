# Security Policy

## Supported Versions

Fixes are released for the latest release. The version can be checked with
`rb-tui --version`.

## Reporting a Vulnerability

Do not open a public Issue: it is visible to everyone, including those who have
not updated yet.

Private report: <https://github.com/JeySerYT/rb-tui/security/advisories/new>

Include in the report:

- version and OS (`rb-tui --diag`);
- what happens and how to reproduce it;
- potential impact;
- contact information for a response.

Do not attach API keys, tokens, or the full `opencode.json`. Replace secrets
with `***` if they are needed for demonstration.

## In Scope

- binaries and installers: sha256 verification, download source;
- reading and writing the OpenCode config, key file permissions;
- dashboard: binding to loopback and behavior on an external host;
- crash reports: secret sanitizer;
- self-update: checksum and atomic replacement;
- guard: bypass of daily budget, cooldown, and rotation.

## Out of Scope

- vulnerabilities in the ReformBoss API and OpenCode itself — report them to their authors;
- local access to the user's machine and stolen keys;
- social engineering and phishing links.

## Timeline

I acknowledge receipt within 3 business days, assessment and plan — within 10,
fix — within 30. If the case is more complex, I will let you know in advance.
