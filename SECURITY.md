# Security policy

## Supported versions

Only the latest released version receives security fixes.

## Reporting a vulnerability

Please **do not open a public issue**. Report it privately through
[GitHub Security Advisories](https://github.com/lore2601/tper-cli/security/advisories/new).
Include steps to reproduce and the impact. You should get an answer within 7 days.

## Scope and threat model

`tper` acts on your behalf towards TPER and Trenitalia, from your computer. Most of it only
reads public information. The main risks are:

- **Personal data exposure.** The complaint profile (name, codice fiscale, address, email) is
  stored in `~/.config/tper-cli/profile.toml` with mode `0600`. No command prints it in full
  (previews and `profile show` mask values), and it is only sent to TPER's own complaint form.
  The complaint history stores a hash, the line and the date, never the text or the details.
  Leaks of these values, in output, logs or errors, are in scope.
- **Complaints filed by mistake or by manipulation.** An agent might file, repeat or alter a
  complaint, or be steered by text in a news item. Mitigations are mandatory `--yes`,
  `--dry-run`, duplicate detection, read-only mode, and `profile init` being interactive-only.
  Bypasses of these controls are in scope.
- **Prompt injection through third-party text.** News, notices and stop names are written by
  others. The CLI returns them as data and the agent skill tells agents never to follow
  instructions found in them. Terminal escape sequences are stripped from tables.
- **Injection and SSRF through arguments** (stop codes, lines, places, dates) into URLs or form
  fields, and redirects to other hosts. Arguments are validated, and the HTTP layer only talks
  to a fixed allowlist of hosts, including across redirects.
- **Hostile XML** in feeds (entity expansion). Feeds are parsed with `defusedxml`.

Out of scope: vulnerabilities in the TPER or Trenitalia services themselves, and a compromised
local user account.
