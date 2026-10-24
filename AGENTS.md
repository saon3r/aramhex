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

## Current status

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

# tests — 308 passing, ~57 s, needs offscreen Qt
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
| `lolhex/data/public.py` | Stats download/cache |
| `lolhex/data/*.json`, `lolhex/data/bundled/` | Bundled names, aliases, stats |
| `tests/` | 308 tests; `tests/fixtures/` holds the redacted real capture |

Comments and docstrings are Chinese and are the real documentation — keep them.

## Traps we have already hit

- **`game_lang` defaults to `zh_CN`.** English card text matches nothing until it is set
  to `en_US`. This looked like "OCR is broken" for a whole debugging round.
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

## How we work

- One branch per milestone (`english-ui`, `winrt-ocr`, …), merged by pull request.
  `main` always runs.
- Commit messages say **why**. Small commits beat tidy ones.
- Finish a milestone by commenting on its issue with **evidence** (command output, numbers,
  what was checked), then closing it. If something did not work, that goes in the comment
  too.
- When you discover a trap, add it to the list above. This file is how the next agent
  avoids repeating this session.
