# ARAM Mayhem Companion — Design

**Date:** 2026-10-24
**Status:** draft for approval
**Shape:** a fork of [`czgreat/aramhex`](https://github.com/czgreat/aramhex) (MIT), improved for an EUW / English client
**Supersedes:** the C#/WPF design written earlier the same day. Its verified findings are carried into §8 rather than lost.

---

## 1. Intent

Two moments in ARAM: Mayhem where a player decides with no information:

1. **Champion select** — a pool of champions and a bench, ~30 seconds, and which of them is
   actually strong is knowledge, not skill.
2. **Augment selection** — three cards, four times a game, each ranked differently *per
   champion*. Seconds to decide, and the card tells you nothing about win rate.

The overlay answers both at a glance, over the game, without taking mouse or keyboard.

## 2. Decision: fork, don't rebuild

Upstream already ships both features, plus recommended builds and skill order. It is
MIT-licensed, 131 files, ~5,000 lines of Python, with a real test suite and unusually
careful comments — the vision code documents *why* each heuristic exists.

The two genuinely hard problems are already solved there:

- **Finding the three cards** at any resolution: layouts are stored as fractions of the
  game window, not pixel coordinates.
- **Knowing which champion you are** in champion select: it reads the champion *title*
  text under the card ("Card Master" → Twisted Fate) rather than matching skin portraits,
  because teammates' skins don't match base art.

What we give up by forking: a single small native `.exe`. We inherit Python + PySide6
(≈90–120 MB once packaged at best) and their Chinese-first UI.

**Why this still beats building fresh:** we would spend the first two milestones
rediscovering exactly the traps their code documents — window-relative fractions, title
text vs portraits, CPU contention with the game. Forking buys that for free and lets us
spend the effort on the parts that are wrong for us.

## 3. What we keep unchanged

- `lolhex/vision/` — window discovery (Win32, `RiotWindowClass` / `RCLIENT`), capture,
  card layout fractions, portrait bank, title OCR, card-frame pixel evidence for rarity.
- The overlay architecture: separate click-through layers (`WindowTransparentForInput`,
  `WA_ShowWithoutActivating`), per-layer DPI scaling by game-window height, the small
  button that expands into a details panel, focus returned to the game after a click.
- The data store, scoring, and tier logic.
- The test suite, which is our safety net for every change below.

## 4. What we change

### 4.1 English

The UI strings are hardcoded Chinese across the source. Measured: **1,297 lines contain
CJK**, of which roughly 350 are user-facing strings (the rest are comments and docstrings,
which we keep — they are the documentation).

- Introduce a message catalog (`lolhex/i18n/messages.json`) and a `tr("key")` helper.
- Default language from the client locale; `en_GB` first.
- Rename nothing in the vision pipeline; only user-visible text.
- Keep upstream's Chinese strings in the catalog as `zh_CN` so future upstream diffs stay
  readable.

This is the largest single chunk of work in the fork, and it is mechanical.

### 4.2 Remove telemetry and remote control

Upstream carries an anonymous install id, remote notices/community/rollout config, and a
log-upload path that can send up to 512 KB on request. All of it is disclosed and
switchable — and none of it belongs in a personal tool.

- Delete `logupload.py`, `cloudsettings.py`, and the install-id/send-usage path.
- Keep the data-update fetch (it is how stats arrive) but strip the identity.
- Replace remote notices with a static About panel.

### 4.3 Defaults for us

- Game language `en_GB`; no Tencent build/skill-order fetch if it cannot be shown in
  English — builds are a nice-to-have, the two core screens are not.
- Attribution for upstream (MIT) and the stats (CC BY-NC 4.0) in About.

## 5. What we improve

### 5.1 Replace RapidOCR with Windows' own OCR

Upstream uses RapidOCR (PaddleOCR models on ONNX). Its own docstring explains the
consequence: it hogs cores, so they force ONNX to a single thread, and a title strip costs
**~70 ms** (a full scan ~1 s).

Windows ships an OCR engine. Measured on the user's actual card screen:

| | RapidOCR (upstream) | Windows.Media.Ocr |
|---|---|---|
| Per title strip | ~70 ms | **7–8 ms** |
| All three in one band | — | **6 ms** |
| Model download | PaddleOCR models bundled | none, in-box |
| Extra runtime | ONNX Runtime + models | none |

Tenfold faster, and it removes `rapidocr`, `onnxruntime` and the model files from the
bundle. It also removes the reason they had to throttle to one thread — the OS does the
work outside our process, so the game keeps its cores.

Planned behind a small `Ocr` interface so the existing RapidOCR path can be restored if a
card style defeats the in-box engine.

**Risk:** Python WinRT bindings (`winrt-runtime` + the `winrt-Windows.*` projections) must
install and work on Python 3.13. `winrt-runtime` publishes wheels for 3.11–3.15, so this is
expected to work; it is the first thing verified in step 3.

### 5.2 Add a client-API fast path for champion select

Upstream's stated principle is to never touch the client: no LCU, no in-game 2999 API.
That is a deliberate trust position for a public tool, and it costs them accuracy — the
champion-select code has to infer *which* champion is yours by comparing font heights
(`pick_my_hero` treats the largest text as the local player's).

For a personal tool the trade is different. The LCU, read from `lockfile`, hands over
exact champion ids, the bench, and `localPlayerCellId` — no guessing.

- Add an **optional** LCU reader used when available.
- Keep the existing screen reading as the fallback, so the app still works if the client
  is closed, elevated, or the API shape changes.
- Scope: champion select only. The in-game overlay stays screen-only; the augment offer
  exists in no API.

This is additive and reversible, and it does not weaken the "no memory, no injection,
no input synthesis" position.

**Rejected after measuring, 25 October 2026.** A read-only probe during a real ARAM:
Mayhem champion select (queueId 2400) settled the question the plan assumed away: the
champion offer is not in the API. When the client showed three champion cards (157, 32,
350) the session payload contained none of them — 0 occurrences of each id — and
`benchChampions` held two different champions (127, 42). Only after the player locked did
`myTeam[4].championId` become 157; the unchosen 32 and 350 then reappeared in
`benchChampions`. `theirTeam` was all zeros for the whole champion select, so even the enemy
team is not exposed. What the API gives exactly is `localPlayerCellId`, per-player
`championId` once locked, `benchChampions` (with `isPriority`), pick `actions`,
`spell1Id`/`spell2Id` and `queueId`.

So the only gain would be making exact what screen reading already gets right — the owner's
champion (Talon, then Yi in two live games) and the bench (7/7) — at the cost of a new
"reads the client API" trust claim, lockfile/token handling, breakage when the client runs
elevated, and rewrites of README, PRIVACY, AGENTS and About. Rejected; screen reading stays
the only input.

### 5.3 Smaller bundle

After 5.1, the ONNX runtime and PaddleOCR models are gone. Expected packaged size falls
by roughly a third. Further reduction (e.g. reducing OpenCV to the few operations used) is
optional and later.

### 5.4 Robustness

- Detect exclusive fullscreen and say so, rather than silently drawing nothing.
- Verify the layout fractions at 4K/150 % with the mixed-DPI portrait second monitor.
- A calibration dump (already partly present as a debug screenshot) that saves what the
  reader saw and what it returned, so a patch-day break is diagnosable in one screenshot.

## 6. Constraints and policy

- **Code:** upstream MIT — keep the copyright notice and licence; our changes stay under
  the same terms.
- **Stats:** `czgreat/aramhex-data`, CC BY-NC 4.0 — personal use, attribution required,
  no commercial distribution.
- **Behaviour:** no memory reads, no injection, no input synthesis. Screen pixels and local
  read-only HTTP only.
- **Distribution:** personal, not published. Riot's developer policy explicitly lists
  augment win-rate overlays as unapproved for published products.
- **Upstream:** work stays on our own branch with `upstream` as a remote, so their fixes
  can be merged and our changes read as a diff.

## 7. Risks

| Risk | Mitigation |
|---|---|
| Upstream moves fast (8 days old, daily commits) | Keep `upstream` remote; rebase our patch series; isolate changes in new modules plus thin edits |
| WinRT bindings fail on Python 3.13 | First check in step 3; `Ocr` interface keeps RapidOCR as fallback |
| Their layout constants were measured on the CN client | Calibration dump + our own capture; fractions already handle 1080p→4K |
| Localization misses strings | A grep gate in CI: no CJK outside the catalog and comments |
| LCU unavailable (client elevated, API change) | Screen reading remains the fallback path |
| Their data is Chinese-server | Accepted and labelled; §8.3 quantifies the gap |

## 8. Verified findings carried over

### 8.1 The augment offer is not in any API
Riot returns **403 for queue 2400** in match-v5 (developer-relations issue #1109, closed as
"is working"), and an open request asks them to publish it without win/loss. Screen reading
is the only route. Confirmed live: `gameMode == "KIWI"`, and no augment field exists
anywhere in `/liveclientdata/allgamedata`.

### 8.2 Windows OCR reads the real cards
Measured on the user's capture at 2560×1440: `Juiced`, `Adaptive Ward`, `Snowday` — all
three, first attempt, 6–8 ms. Each card also prints a category tag (`General`,
`Resilience`, `Utility`) inside the same strip; the classifier must take the largest line
and discard the rest.

### 8.3 The stats are Chinese-server, and how much that matters
`aramhex-data` pools seven CN regions on the live patch: 5,141,715 valid matches. Compared
against an independent sample across 16 champions: **mean gap 1.8 points, worst 5.4**
(Hecarim). Champion strength drifts by region; augment strength is a balance number and
travels better — which is the half that matters most here.

### 8.4 Data joins directly
CommunityDragon's `cherry-augments.json` (594 rows: id, `nameTRA`, rarity, icon) and
aramhex share numeric augment ids — all 232 aramhex augments resolve. No name bridge.
`queues.json` lists nine Mayhem queue ids, so queue gating must match names, not ids.

## 9. Milestones

1. **Run it.** Python 3.13, venv, launch upstream unmodified, confirm it reads our client
   in English. No code changes. If this fails, the whole plan is wrong and we learn it cheaply.
2. **Make it ours.** English catalog, telemetry removed, EUW defaults. A usable English
   tool exists at the end of this step.
3. **Make it fast.** WinRT OCR behind an interface; verify the bundle shrinks and the CPU
   cost drops.
4. ~~**Make it precise.**~~ LCU fast path for champion select — **rejected**, see §5.2:
   the offer is not in the API.
5. **Package.** Single portable build, About/attribution, calibration dump.

Each milestone ends with something runnable.

## 10. Left to the builder

- Message-catalog format and how keys are named.
- Whether builds/skill order survive the English pivot or get cut from v1.
- Exact `Ocr` interface boundary and whether the RapidOCR path is kept compiled in.
- How much of `ui/mainwindow.py` is rewritten versus patched for English.
- Packaging: PyInstaller one-folder vs one-file, and the icon/name.

## 11. Deliberate calls made for the owner

- **Fork over rebuild**, accepting Python and a larger binary in exchange for a working
  vision pipeline today.
- **English-only UI**, matching the client.
- **No telemetry, no remote control** of any kind.
- **Chinese stats accepted and labelled**, because no EUW source exists (§8.1, §8.3).
- **Client API rejected** (§5.2) after a live probe: the champion offer is not in the
  session, so the API would only make exact what screen reading already got right, in
  exchange for a new trust claim and token handling. An earlier draft of this list allowed
  it; the probe reversed that.
