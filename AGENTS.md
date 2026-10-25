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

## Relationship to upstream — this fork has diverged

This is not a tracked fork that can merge upstream again. It was forked to personalise, and the
divergence is structural, not cosmetic:

- telemetry, cloud identity, log upload, self-update, remote config and the Riot-ID rank lookup
  are **deleted** (upstream modules and their callers are gone);
- Tencent metadata, portraits and build/skill feeds are **replaced** with Data Dragon and
  CommunityDragon, and runtime HTTP is restricted to four documented host families;
- RapidOCR and its ONNX models are **gone**, replaced by Windows.Media.Ocr;
- the UI is English through a message catalog (upstream is Chinese), including text produced
  outside `lolhex/ui`;
- packaging (`packaging/lolhex.spec`, `build.ps1`) was changed for the new dependencies.

So **do not plan an upstream merge**; adding the `upstream` remote's `main` would produce a
conflict set larger than the feature anyone wanted, and would silently reintroduce telemetry if
resolved carelessly. Upstream commits are cherry-picks at best, and usually not even that: the
files they touch often no longer exist here. If a specific upstream fix matters, read that diff,
port the *intent* by hand into this codebase, and prove it with this suite plus the relevant
acceptance (fixture, and a live game for recognition changes).

The remote is kept only to read upstream history and to attribute code.

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

The owner may ask to be walked through GitHub for learning. That is optional and never a
dependency — do the work either way.

Two consequences worth spelling out:

- **Report conclusions, not output.** The agent reads the logs, JSON, screenshots and test
  results, decides pass or fail, and tells the owner what happened in plain English. The
  owner is never handed evidence to weigh.
- **Git and GitHub writes are pre-authorised.** Branches, commits, PRs, merges into `main`,
  issue comments and closures need no owner approval. Ask only when scope, risk or
  acceptance materially changes — never for a technical choice, a diff or a test result.

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

- **All milestones closed.** #2/#3/#4/#6 verified (#4 is milestone 3, #6 is milestone 5);
  #11/#12 follow-ups done. **#5 (client API) was rejected as not planned** — the champion
  offer is not in the champ-select session, recorded in the design doc so it is not
  re-proposed. **#22 (1080p recognition)** is closed: the live 1920×1080 window never failed
  (the report was a downscaled still), but the full scan did feed the OCR different pixels
  per resolution and lost cards at 1366; it now normalises to a fixed 1600 px. Evidence:
  `docs/superpowers/verification/2026-10-25-issue-22-1080p.md`. The only open issue is
  **#18 (low priority)**: make "cards on screen, nothing recognised" visible instead of
  silent, because the layout constants are measured against today's augment screen and a
  Riot restyle would look like a broken app.
- **Milestone 1 — verified.** Upstream runs unmodified on this client. The augment screen
  is proven against `tests/fixtures/real-mayhem-augment-screen.png`; the app launches.
  Champion select was the one unchecked item and was verified live in milestone 2.
- **Milestone 5 — verified (issue #6).** One-folder PyInstaller build plus the portable ZIP
  (75 MB); `scripts/accept_packaged.py` runs the frozen app with no Python on PATH and passes
  **18/18**, including "no module loaded from outside the install", fixture OCR to three
  badges, English chrome, the crash dialog and the missing-recognizer message; the
  packaged EXE also played one full live game (champion select, 17 offers, three
  badges, zero errors). Evidence:
  `docs/superpowers/verification/2026-10-25-milestone-5-packaging.md`.
- **Milestone 3 — verified (issue #4).** OCR is now Windows.Media.Ocr: 3.4-4.2 ms per
  three-card tick and 57-63 ms per 4K full scan (RapidOCR: 32-34 ms and 758-953 ms), 75 MB
  of dependencies removed. Fixture reads 2016/2138/2088 with three badges; one live
  `--debug` game had zero errors, 16 English offers, and the champion-select height
  heuristic did not invert. Evidence:
  `docs/superpowers/verification/2026-10-25-milestone-3-windows-ocr.md`.
- **Milestone 2 — verified (issue #3).** English UI/catalog gates and the full suite pass
  (521 tests after the follow-up). Real ordinary refresh, cold/warm offline startup, fixture
  OCR, three badges, live bench recognition and one full English-client ARAM: Mayhem game are
  all verified. The advice/panel Chinese the first game exposed was fixed in PR #13 (#11):
  producers now render through the catalogue and use `name_en`. Evidence:
  `docs/superpowers/verification/2026-10-24-milestone-2.md`.

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
| `lolhex/vision/ocr.py` | OCR entry point (`get_ocr`), `TextLine`; backend is `ocr_win.py` |
| `lolhex/vision/ocr_win.py` | Windows.Media.Ocr backend: SoftwareBitmap from raw pixels, completion-handler wait |
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
  `-Encoding UTF8` or the `read` tool. The same mangling applies to `git show` output piped
  into a PowerShell string comparison: an em dash comes back as `-`, so an identical section
  looks changed. Compare with Python or `git diff` before believing a "not identical" result.
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
- **The UI gate only covers `lolhex/ui/*.py` literals.** Advice, badge lines, provenance and
  the panel table are assembled by `recommend.py`, `data/public.py` and `panel.py`, so they can
  be Chinese while the AST gate is green — that is exactly what happened, and the owner saw it
  in a game. `tests/test_render_localisation.py` covers the producer output; put any new
  player-visible string through the catalogue and that gate, not just `tr()` in the UI.
- **Display names are `name_en`, never `name`.** The Chinese `name` in `store.augments`/
  `store.heroes` is what the OCR matcher scores against; using it for display leaks Chinese
  into the panel. `recommend.augment_label()` is the display accessor.
- **Acceptance runs need `--debug`.** Auto screenshots are debug-only, so a normal
  (`--minimized`) run leaves no captures to review afterwards — the log still records what was
  published, but the visual proof is gone. Launch acceptance games with `--debug`.
- **Offscreen Qt has no usable fonts here.** `QT_QPA_PLATFORM=offscreen` renders text as boxes
  and positions `BadgeLayer` painting in logical pixels, so a badge render looks like a
  different, broken layout. Render with the windows platform and `layer.grab()`.
- **OCR is Windows.Media.Ocr and needs the client language's recognizer pack.** `get_ocr()`
  raises `OcrUnavailable` for a language Windows does not have (this machine: only `en-GB`),
  because an English engine reading Chinese card faces returns nothing and looks like "OCR is
  broken". Install the pack in Windows settings; the log names what is missing.
- **RapidOCR has been removed** — see the milestone-3 record. OCR is `get_ocr()` on
  Windows.Media.Ocr; there is no bundled model and no fallback backend.
- **PowerShell 5.1 needs a UTF-8 BOM to read a `.ps1` with Chinese.** There is no `pwsh` on
  this machine, and a BOM-less script is decoded as ANSI, which fails to parse (`Unexpected
  token`). `packaging/build.ps1` keeps a BOM for that reason; add one to any new script with
  non-ASCII text and say so in its header.
- **Wait on WinRT without asyncio.** An asyncio loop creates a loopback socketpair on
  Windows, which the offline acceptance test's no-socket guard reports as a connection. Use
  the completion handler + `threading.Event` (see `ocr_win._wait`).
- **WinRT line boxes are per word.** `line.words[0].bounding_rect` is the first word only;
  union all word rectangles or `pick_my_hero`'s text-height heuristic (and card x-extents)
  get the wrong numbers.
- **The League client does not reliably accept a scripted window resize.** `SetWindowPos`
  changed the window frame but the client kept painting its old surface: a 1920×1080 window
  showing a 1600×900 UI, or a 2880×1620 window with the old 1920×1080 UI clipped and a white
  band. That is what "the client looks weird" was. Sending `WM_ENTERSIZEMOVE` (0x0231) and
  `WM_EXITSIZEMOVE` (0x0232) around the resize makes it reflow — but even then it sometimes
  refuses, so always verify: the content's non-black extent must equal the window, and if it
  does not, put the original size back. On this 4K/150%-scale machine the client's honest
  size is 1600×900 physical; 1920×1080 physical renders clipped. Do not script client
  resizes during a live acceptance unless the owner accepts the risk.
- **`game.cfg` `Width`/`Height` in windowed mode are the window size, not the client area.**
  `WindowMode=1, Width=1920, Height=1080` produced a 1904×993 client area (16 px borders,
  39 px title bar). For an exact 1920×1080 render, `SetWindowPos` the game window to the
  client size plus the measured frame, then check `vision.window.client_rect` before
  capturing; games do re-render on resize.
- **League has no custom FPS cap.** `FrameCapType` is a fixed enum (3=25, 4=30, 5=60, 6=80,
  7=120, 8=144, 9=200, 2=240, 10=uncapped). There is no 320 and no numeric field; a 320 cap
  would have to be a driver-level setting.
- **`scripts/accept_packaged.py` needs no other instance running.** Its warm-start and
  missing-recogniser checks launch the frozen app; if a dev `python -m lolhex` (or another
  packaged copy) is alive, the frozen app exits silently on the single-instance guard and the
  run scores 14/18 without a product fault. Stop every instance first.

## How we work

- One branch per milestone (`english-ui`, `winrt-ocr`, …), merged by pull request.
  `main` always runs.
- Commit messages say **why**. Small commits beat tidy ones.
- Finish a milestone by commenting on its issue with **evidence** (command output, numbers,
  what was checked), then closing it. If something did not work, that goes in the comment
  too.
- When you discover a trap, add it to the list above. This file is how the next agent
  avoids repeating this session.
