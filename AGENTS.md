# AGENTS.md — read this before changing anything

Personal, English-localised fork of [`czgreat/aramhex`](https://github.com/czgreat/aramhex):
an ARAM: Mayhem companion overlay for League of Legends. Screen-reading only, no game
integration. Built for one player on EUW with an `en_GB` client.

- **Our repo:** https://github.com/saon3r/aramhex (remote `origin`)
- **Upstream:** https://github.com/czgreat/aramhex (remote `upstream`)
- **Design / rationale:** [`docs/superpowers/specs/2026-10-24-aram-mayhem-overlay-design.md`](docs/superpowers/specs/2026-10-24-aram-mayhem-overlay-design.md)
- **Work plan:** the open [issues](https://github.com/saon3r/aramhex/issues) — one per milestone

Read the design doc before proposing anything. It records what was measured, what was
rejected and why. Most "obvious improvements" were already considered there.

## Who does what — read this twice

**The owner is not a programmer. Treat them as the client, not as a pair.**

The agent does every technical thing: reading code, editing, running commands and tests,
git, GitHub (branches, pull requests, merges, issue comments), environment setup,
verification, and documentation. Never ask the owner to run a command, read a diff,
interpret output, click through a GUI, or judge code quality.

Code review is the agent's job. For a second opinion, dispatch a reviewer subagent with
fresh context. Never ask the owner to review a diff.

The owner does exactly two things:

1. **Plays a game when asked**, for live acceptance. They interpret nothing. The agent
   launches and manages the app, and afterwards reads the logs, screenshots and scan
   output itself.
2. **Answers questions of preference.** Ask in plain language, give a recommendation, and
   say what each option costs. Never ask them to choose between technical alternatives —
   make that call yourself and record it.

If a step seems to need the owner, first ask whether it can be automated or verified
another way. It usually can.

Two consequences worth spelling out:

- **Report conclusions, not output.** The agent reads the logs, JSON, screenshots and test
  results, decides pass or fail, and tells the owner what happened in plain English. The
  owner is never handed evidence to weigh.
- **Git and GitHub writes are pre-authorised.** Branches, commits, PRs, merges into `main`,
  issue comments and closures need no owner approval. Ask only when scope, risk or
  acceptance materially changes — never for a technical choice, a diff or a test result.

The owner may ask to be walked through GitHub for learning. That is optional and never a
dependency — do the work either way.

## Parallel workers

Fanning out is allowed; shared state is not.

- **Disjoint files only.** No two workers edit one file in a wave. No parallel `git`
  commands, no parallel merges, no parallel full-suite runs — ever.
- **One catalog writer.** One worker extracts every key and writes the complete catalog
  once; after that the catalog is frozen and one worker per UI module changes code only.
  A worker that finds a missing key returns a proposal; the single catalog writer applies
  it in a separate, non-parallel phase. No later worker writes the catalog.
- **Where parallelism pays:** up to 4 concurrent workers while localising UI modules, 1–2
  elsewhere. Dispatch a wave together in the background, then wait for all of it.
- **Workers** cannot spawn agents, run the full suite, or touch git unless explicitly
  assigned; they run only the scoped tests for their own files.
- **The controller** runs the gates, the full suite and `git diff --check` after each wave,
  and reviews the combined diff — not each fragment in isolation. What the controller runs
  is the acceptance signal.
- **Two failed attempts on one task stop the delegation** for it; the controller takes it
  over or reports.
- The owner's rules here override the delegation skill's generic defaults — its ban on
  parallel agents, its model tiers, and its "every worker runs the suite" contract.
  Worker, explore and reviewer agents all use the plan's cheap flash model.

## Current status

### Milestone 2 execution rulings

- Finish the current wave; do not restart or re-plan it. Implementation briefs cover one
  interface plus tests, at most roughly 10 files. Keep transport/seeding serial; use
  separate disjoint briefs for portraits, CLI and other follow-ups. Fix briefs contain
  only failed items and their criterion numbers, not the full original contract.
- Independent reviewer agents are required only for network-policy/privacy-boundary
  changes or diffs larger than roughly 10 files. The controller reviews mechanical
  localisation directly. Mechanical extraction/string conversion needs no red-first
  cycle; behaviour changes still do.
- Localisation waves target four workers. Scratch-only key extraction can run alongside
  the current wave: no product edits and no catalog writes. The single catalog-writer
  rule remains in force when that inventory is integrated.
- Task 8 (non-UI rendered-text polish) is deferred to a new issue after milestone 2 closes.
  Its wider display-text gate does not block milestone 2's strict `lolhex/ui/*.py` gate.
- If the ten `test_badges_follow_physical_pixels_at_current_qt_scale` cases fail because
  of environment/DPI, verify once in isolation, quarantine with a skip and linked issue,
  then stop iterating. Do not quarantine deterministic product regressions.
- The controller writes AGENTS.md and PRIVACY.md directly; no documentation worker is
  needed. Stop repeated fix delegations: take over or split remaining work, never send a
  fourth attempt.
- Unwaived acceptance: real post-removal app refresh, offline startup, fixture OCR and
  three rendered badges, live bench recognition, and one full English-game session.

- **Milestone 1 — verified.** Upstream runs unmodified on this client. The augment screen
  is proven against `tests/fixtures/real-mayhem-augment-screen.png`; the app launches.
  *Still unchecked:* champion select, which needs a live client in a queue.
- **Next:** milestone 2 — English UI and telemetry removal (issue #3).

## Environment (already set up on this machine)

| | |
|---|---|
| Python | 3.13.15 — `C:\Users\asaon\AppData\Local\Programs\Python\Python313\python.exe` |
| Virtualenv | `.venv` in the repo root (gitignored). Use `.venv\Scripts\python.exe` |
| Dependencies | `requirements.txt`, installed |
| Settings | `%APPDATA%\AramHex\config.json` — **`game_lang` must be `"en_US"`** |
| Logs | `%APPDATA%\AramHex\aramhex.log` |
| Data cache | `%APPDATA%\AramHex\data\` |

On a fresh machine: `py -3.13 -m venv .venv`, then
`.venv\Scripts\python.exe -m pip install -r requirements.txt`.

## Commands

```powershell
# the app (tray icon, overlay; close via the tray menu)
.venv\Scripts\python.exe -m lolhex

# tests — use offscreen Qt; current results are recorded in the milestone evidence
$env:QT_QPA_PLATFORM = 'offscreen'; .venv\Scripts\python.exe -m pytest -q

# recognition only, against a still image. The fastest way to check a change.
.venv\Scripts\python.exe -m lolhex --scan-image tests\fixtures\real-mayhem-augment-screen.png

# with a champion, to get per-champion advice instead of all-champion averages
.venv\Scripts\python.exe -m lolhex --scan-image <png> --hero Ahri

# background worker only, no UI
.venv\Scripts\python.exe -m lolhex --headless

# refresh the stats and print their status
.venv\Scripts\python.exe -m lolhex --refresh
```

`--scan-image` prints JSON. If you pipe the output through `Select-String` or `findstr`,
**ignore the shell's reported exit code** and read the JSON — the exit code reflects the
pipeline, not the app.

## Non-negotiables

These are the reason the fork exists. Do not trade them away:

- **No game memory reads, no injection, no packet capture, no input synthesis.**
  Screen pixels and advisory click-through windows only.
- **Local HTTP is read-only.** The League client API and `127.0.0.1:2999` are allowed to
  read; nothing may be written or triggered through them.
- **No telemetry of any kind** (milestone 2 removes what upstream has).
- **Attribution stays.** Code is MIT (upstream), stats are CC BY-NC 4.0
  ([`czgreat/aramhex-data`](https://github.com/czgreat/aramhex-data)). Personal use only —
  this is not to be published, and Riot's policy bars published augment win-rate overlays.

## Code map

| Path | What lives there |
|---|---|
| `lolhex/__main__.py` | CLI entry, flags, logging |
| `lolhex/engine.py` | Coordinator: data thread, observer thread, vision thread, state |
| `lolhex/vision/window.py` | Win32 window discovery (`RiotWindowClass`, `RCLIENT`), DPI awareness |
| `lolhex/vision/detector.py` | Finds the three cards, calibrates the layout |
| `lolhex/vision/ocr.py` | **RapidOCR wrapper — the piece milestone 3 replaces** |
| `lolhex/vision/champselect.py` | Champion-select layout, fractions of the window |
| `lolhex/vision/cardframe.py` | Pixel evidence for card rarity (silver/gold) |
| `lolhex/vision/matcher.py` | Fuzzy name matching against the augment list |
| `lolhex/ui/overlay.py` | In-game layers, badges, click-through window |
| `lolhex/ui/mainwindow.py` | Main window + tray |
| `lolhex/data/public.py` | Stats download/cache; dataset seeding |
| `lolhex/data/metadata.py` | Data Dragon / CommunityDragon parsers, English display helpers |
| `lolhex/data/store.py` | Offline static seed, per-family refresh, atomic `static.json` cache |
| `lolhex/data/static_fallback.json` | Pinned offline fallback (id→Data Dragon alias, augment rarity, spell names) with source hashes |
| `lolhex/data/*.json`, `lolhex/data/bundled/` | Bundled names, aliases, stats |
| `tests/` | Automated suite; `tests/fixtures/` holds the redacted real capture |

Comments and docstrings are Chinese and are the real documentation — keep them.

## Runtime network hosts

All runtime HTTP goes through `lolhex/data/http.py`; it refuses anything not on this list
before sending. All four are anonymous HTTPS GET only, no cookies/credentials/referer.
The policy also permits the equivalent `en_GB` Data Dragon metadata paths; the current
metadata refresher uses `en_US` names.

| Host and path | Exact purpose |
|---|---|
| `aramhex.com/u/data/` | stats manifest and stats payloads (primary) |
| `raw.githubusercontent.com/czgreat/aramhex-data/main/` | stats manifest and payloads (fallback) |
| `ddragon.leagueoflegends.com/api/versions.json` + `/cdn/<version>/data/en_US/{champion,item}.json` + `/cdn/<version>/img/{champion,item}/…png` | version discovery; en_US champion/item metadata; champion portraits and on-demand item icons |
| `raw.communitydragon.org/…/global/default/v1/cherry-augments.json` | English augment metadata only (name/rarity); no icons/splash |

No Tencent host (`game.gtimg.cn`, `mlol.qt.qq.com`) and no jsDelivr mirror is contacted by
the shipped app. Maintenance scripts under `scripts/` are not runtime code and may read wider
CommunityDragon paths to regenerate bundled tables; they never import Tencent endpoints.

## Traps we have already hit

- **`game_lang` must match the client language.** Upstream defaulted to `zh_CN`; this fork's
  `Settings` default is `en_US` (pinned by tests, and old config files without the key load
  as `en_US`). Wrong language = card names match nothing and looks like "OCR is broken".
- **Do not derive portrait filenames from display names.** Data Dragon aliases differ from
  English names and from the old Tencent spellings (`Nunu`, `MonkeyKing`, `Renata`,
  `Khazix`, `Fiddlesticks` vs `FiddleSticks`). Use `static_fallback.json`; a case-insensitive
  fallback covers old bundled bytes.
- **Files are UTF-8 without BOM.** Windows PowerShell 5.1 `Get-Content` mangles them; use
  `-Encoding UTF8` or the `read` tool.
- **Capture resolution varies.** The fixture is 2560×1440; an earlier session logged
  3840×2160. Never hardcode pixels — upstream stores layout as fractions for this reason.
- **The overlay must not read itself.** Upstream's layers are excluded from capture.
- **Forks arrive with GitHub Issues disabled**, and `gh pr create` defaults to opening the
  PR against *upstream*. Use `gh pr create --repo saon3r/aramhex`.
- **GitHub CLI is not on PATH in a fresh shell.** Use
  `& "C:\Program Files\GitHub CLI\gh.exe"` in PowerShell.
- **The raw capture is not committed.** `screenshots/` is gitignored because it contains
  other players' Riot IDs. `tests/fixtures/real-mayhem-augment-screen.png` is the redacted
  version — use it, and keep future fixtures redacted too.
- **`bash` on PATH is a broken WSL shim.** The SDD scripts need
  `& "C:\Program Files\Git\bin\bash.exe" ...`; plain `bash` fails with
  `execvpe(/bin/bash)`. The `sdd-workspace` script works fine under Git Bash.
- **`git checkout <branch> -- <file>` stages the file.** When an uncommitted carry is the
  point (e.g. bringing a later `main` doc onto a milestone branch), use
  `git restore --source=<branch> --worktree -- <file>` instead.
- **Deleted modules can still have non-Python callers.** Check release workflows and
  packaging scripts too; the release workflow used to invoke `python -m lolhex.patch`.
- **Retired settings can hide in `Settings.extra`.** Add keys written there (such as
  `logs_sent`) to `REMOVED`, not just the deleted dataclass fields.
- **Policy tests must use the shipped manifest's paths.** Stats live under
  `patches/<patch>/normal` (including `normal.pack.xz`); mode-less test-server paths
  once hid a policy that blocked every real stats payload despite a green suite.

## How we work

- One branch per milestone (`english-ui`, `winrt-ocr`, …), merged by pull request.
  `main` always runs.
- Commit messages say **why**. Small commits beat tidy ones.
- Finish a milestone by commenting on its issue with **evidence** (command output, numbers,
  what was checked), then closing it. If something did not work, that goes in the comment
  too.
- When you discover a trap, add it to the list above. This file is how the next agent
  avoids repeating this session.
