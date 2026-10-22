# Filing a complaint (reclamo)

`tper claim` sends a complaint through [TPER's own web form](https://solweb.tper.it/web/communications/complaints.aspx), the same one you would fill in a browser, but from the terminal and without a browser: each step is a plain HTTP form post.

> **Experimental.** `tper claim check` verifies against the live site that the form is reachable and has the fields the CLI fills (and runs weekly in CI). Steps 2 and 3 of the wizard only appear after you submit real personal data, and the last one files a real complaint, so they cannot be exercised automatically. They are tested against a simulation of the three-step page. If TPER rejects a step, the error says what the page showed; if a control disappears, you get `formChanged` instead of a guess.

Complain with moderation, be polite and give the facts needed to resolve the problem. The form is for legitimate complaints only.

## 1. Store your details once

```bash
tper claim profile init     # interactive, in a terminal
tper claim profile show     # which fields are set; values are masked
```

The details go to `~/.config/tper-cli/profile.toml` with `0600` permissions and are never printed in full, by any command. `init` refuses to run without a terminal, so an agent can never type your personal data for you. The codice fiscale is validated (format and check character), so is the email, CAP and phone.

The countries, province and municipality must be written as the form lists them (for example `ITALIA`, `BOLOGNA`); `tper claim file` tells you the valid options when one does not match.

## 2. Preview

```bash
tper claim file \
  --category "Corsa non effettuata" --basin Bologna --line 20 \
  --direction "Pilastro" --date yesterday --time 09:11 --place "fermata 4476" \
  --text-file complaint.txt --dry-run
```

`--dry-run` validates everything and prints the claim and a masked copy of your profile. Nothing is sent. The text must be 20 to 3000 characters. `--date` accepts `DD/MM/YYYY`, `YYYY-MM-DD`, `yesterday`, `-2d`; a future date is refused.

| Option | Meaning |
|---|---|
| `--service` (default `Servizio bus`), `--kind` (default `Servizio`) | The first two choices of the form |
| `--category` | e.g. `Corsa non effettuata`, `Frequenza o orario non rispettato` |
| `--basin`, `--line` | `Bologna` or `Ferrara`, and the line |
| `--direction`, `--vehicle`, `--driver` | Optional details |
| `--date`, `--time`, `--place` | When and where |
| `--text` / `--text-file FILE\|-` | The complaint |
| `--no-compensation` | Do not ask for an indemnity (*indennizzo*), which is requested by default |

## 3. Send

```bash
tper claim file … --yes          # or answer the prompt on a terminal
```

Without `--yes` and without a terminal, the command stops with exit code `4` (`confirmationRequired`). On success TPER's confirmation text is printed, and the claim is recorded in `~/.local/state/tper-cli/claims.jsonl` (a fingerprint, the line and the date, never the text or your details). Sending the same complaint again is refused (`duplicateClaim`, exit `4`) unless you pass `--allow-duplicate`. `tper claim history` lists what was sent.

`TPER_READ_ONLY=1` blocks sending altogether.

## For agents

Never write the complaint for the user without showing it, and never send it without their explicit approval of the exact text. Never ask for or handle their personal details: the profile is theirs to create. See [agents.md](agents.md).
