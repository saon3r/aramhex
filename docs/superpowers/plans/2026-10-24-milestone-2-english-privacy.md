# Milestone 2: English UI, private downloads and offline operation

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development or superpowers:executing-plans, under the owner rules in AGENTS.md ("Who does what", "Parallel workers"). The architect/controller owns this plan, decisions, review, all git/GitHub actions, the gates and the full suite; `worker` implements and runs only its scoped tests; `explore` answers code-location questions; `reviewer` reviews with fresh context. Worker, explore and reviewer all use `opencode-go/deepseek-v4.1-flash`. Workers never commit, open PRs, close issues, spawn agents or run the full suite.

**Goal:** A runnable English overlay with no telemetry or remote control, narrowly scoped anonymous downloads, and working recognition/badges offline.

**Architecture:** Preserve screen recognition, overlay layering, stats verification and stats-derived ranking. Replace Tencent dependencies with static Data Dragon/CommunityDragon metadata and assets, seed recognition from disk/bundled data, and separate English display names from recognition names. A shared message helper/catalog supplies UI and other rendered text.

**Tech stack:** Existing Python 3.13, PySide6, requests, RapidOCR, OpenCV and pytest; no new runtime dependency.

**Spec:** `docs/superpowers/specs/2026-10-24-aram-mayhem-overlay-design.md`, issue https://github.com/saon3r/aramhex/issues/3, and the owner decisions recorded below. These decisions supersede the original design where it differs.

**Latest execution rulings (apply without restarting the current wave):** Mechanical localisation needs controller review, not a reviewer agent or red-first cycle. Reviewer agents are reserved for network/privacy diffs or combined diffs above roughly 10 files. Future implementation briefs cover one interface and tests, about 10 files maximum; fixes carry only numbered failed criteria. Scratch-only extraction runs in parallel now; one writer still integrates the catalog. Task 8 is deferred to a follow-up issue after #3 closes, so only the strict UI/catalog gates block milestone 2. Controller owns documentation. Environment-dependent failures of the ten physical-pixel/DPI cases may be verified once in isolation and quarantined with a linked issue; deterministic regressions and the real refresh/offline/OCR/three-badge/live-game gates are never waived.

## Global constraints and owner decisions

- Screen pixels only for recognition; no memory reads, injection, packet capture or input synthesis. Local HTTP remains read-only; no new game API integration.
- Remove install ID generation/persistence/transmission, usage reporting, log upload, remote config/control/notices, self-update and Riot-ID rank lookup.
- Allowed outbound traffic: anonymous GET of static champion/augment/item metadata and icons, and stats manifests/payloads. Do not expand the owner's list to spell downloads; retained stats-based summoner advice uses available bundled/cached spell labels/icons and a text fallback.
- No cookies, unique identifiers, tracking headers or per-player requests. No Tencent network dependency. No OCR model download.
- Cut upstream build recommendations and skill order. Preserve stats-pack item/summoner/augment-item advice; those are not the removed upstream build feed.
- Drop Tencent letter tiers and their unsupported fallback. Preserve tiers derived from our own stats and all unrelated scoring math/thresholds.
- Visible evidence ladder: sufficiently supported champion-specific rate; otherwise sufficiently supported all-champion rate explicitly labelled **all champs**; otherwise **?**, no number, and `nodata`. Use existing sample-sufficiency constants, not new arbitrary thresholds.
- English UI defaults to `en_GB`; recognition `game_lang` defaults to `en_US`. Do not conflate them or rewrite existing recognition names.
- Keep Chinese comments/docstrings, recognition tables, aliases and immutable bundled stats. Move runtime display text to the catalog; do not translate checksummed data in place.
- Every fetched asset/metadata family is cached atomically on disk. Failed refresh preserves valid cache and falls back to bundled data. Metadata construction/recognition must not require network.
- Keep upstream MIT and stats CC BY-NC 4.0 attribution; About labels the stats as CN-server data. Personal use, no publication.
- One `english-ui` milestone branch, worked in place; preserve existing changes. The agent/controller handles every git and GitHub action (branch, commit, PR, merge, issue comment/closure) under the owner's standing authorisation, with no owner approval step. Workers do not commit, open PRs, close issues, spawn agents, run the full suite or modify user APPDATA.
- Localisation fan-out follows AGENTS.md "Parallel workers": one worker extracts every key, writes the complete catalog once and lands the architect-reviewed pilot; the catalog is then frozen. Task 7 runs **code-only** waves of up to four workers, one disjoint UI module each, with no catalog writes — so no file is written by two workers at once. Waves never overlap with git, merges or full-suite runs; the controller runs the gates and full suite after each wave and reviews the combined diff. A missing key comes back as a proposal to the single catalog writer in a separate non-parallel phase; no later worker writes the catalog.
- Review each chunk using `git diff --stat` first, then changed hunks; after a wave, review the combined diff. Stop delegating a task after two failed attempts and let the controller take it over or report.
- Live champion-select/bench acceptance stays open until tested. If new portraits fail, restore the previous bundled/cached portrait references; do not ship silent missing badges or re-enable Tencent HTTP.

## Review focus

1. Missing/tiny champion sample, missing global sample and excluded/new augment: honest labelled fallback or `?`, no tier dependency or exception (Task 3).
2. Empty/corrupt metadata cache, partial refresh and cold offline start: bundled recognition tables and portrait references still initialise (Tasks 4–5).
3. Changed portrait bytes: preserve matching thresholds/math and distinguish matcher probes from live bench proof (Task 5).
4. Payload URLs, redirects, cookies and hidden update paths: no request escapes the documented host/path policy (Tasks 2, 4).
5. Text outside `ui/`, f-string fragments and diagnostic strings: strict UI AST gate plus explicit non-UI rendered-text coverage, without corrupting recognition literals (Tasks 6–8).

## Pre-removal evidence and limits

- [x] Read AGENTS.md, linked design and issue #3 before repository reconnaissance.
- [x] Explorer: actual checkout is this directory; initial branch `main` was clean. Harness “not a git repo” metadata is incorrect.
- [x] Worker: production downloader fetched anonymous mirror manifest/pack; five payloads passed SHA-256/size validation. Individual-file and raw-GitHub pack-404 fallback also worked.
- [x] Worker: actual `ui.overlay.run`, QApplication/MainWindow/Tray and `Engine.start` ran in an isolated home; the app's manual refresh downloaded seq 8 rather than bundled seq 7, updated the visible data status and completed without sync errors. Identity generation was intercepted before settings load; prohibited requests were blocked before sending. No identity/cookie headers were sent.
- [ ] Background app refresh outside a match remains unverified: an existing live game caused the normal hold/defer behavior. The earlier instrumented run does not prove identity generation is absent in unchanged source.
- [x] Baseline suite reported by worker: 308 passed.
- [x] Added the verified absolute GitHub CLI path trap to AGENTS.md.
- [ ] Offline app startup, real fixture recognition and rendered card badges remain to be verified after implementation.

## File and interface map

- New `lolhex/messages.py`: `DEFAULT_UI_LANG = "en_GB"`, `set_language(language: str) -> None`, `tr(key: str, **values: object) -> str`. No Qt dependency; importable by data/recommendation/UI code.
- New `lolhex/data/messages.json`: top-level `en_GB` and `zh_CN` maps with identical semantic key sets and identical named-format placeholders. English is the runtime default. Unknown locale falls back to English; missing runtime key returns the key, with a diagnostic warning. Missing keys/placeholders are test failures, not silent Chinese fallback.
- Keep `lolhex/i18n.py` recognition APIs/import paths unchanged. Display names resolve numeric IDs through existing English tables; unknown IDs render `Champion <id>` / `Augment <id>`, never untranslated Chinese or internal stringtable keys.
- New `lolhex/data/metadata.py`: fixed-source static adapters, neutral rarity constants, English display accessors. Preserve existing store/matcher interfaces and Chinese recognition fields.
- Extend `lolhex/data/http.py` with one GET policy boundary used by every surviving download path; reject unapproved URLs before sending. Preserve testability of local HTTP fixture servers through explicit injected test transport, not a production localhost exemption.
- `lolhex/data/store.py`: disk/bundled metadata seeding, schema validation and atomic `static.json` refresh; remove Tencent per-hero fetch dependence.
- `lolhex/data/public.py`: preserve manifests, checksum validation, atomic stats cache, bands and ordinary automatic stats refresh; remove cloud-selected event/rollout/mirror behavior.
- `lolhex/data/icons.py`, `lolhex/vision/portraits.py`: disk cache, safe static URL construction and portrait-source migration only. Preserve `IconBank` feature extraction/thresholds/classification.
- `lolhex/panel.py`, `lolhex/recommend.py`: remove upstream build/skill/tier inputs; preserve own-stats analysis and explicit fallback evidence.
- `lolhex/ui/buildview.py`: narrow rather than delete: retained item/summoner stats share this renderer. Remove build/skill blocks and `skills_line`.
- `lolhex/ui/mainwindow.py`, `overlay.py`, `data_status.py`, `herosearch.py`, `badgepos.py`, `autoshot.py`: module-sized conversion after the pilot. `autostart.py`, `single_instance.py` and empty `__init__.py` need no conversion if the strict AST gate confirms no non-docstring CJK.
- Tests added/extended below; obsolete feature tests replaced by absence/security/regression assertions, not merely removed to obtain green.

## Task 1 — Isolate and record the baseline

**Files:** this plan and AGENTS.md; no product changes.

- [x] Under an explicit controller setup brief, the worker rechecked: `english-ui` already existed at plan commit `bb163cc`; work happens in place on that branch — no new branch, worktree or environment install. `main` had since gained the owner's "Who does what" AGENTS.md section (PR #9); that section was carried onto `english-ui` without discarding it or staging it. The plan's scratch ledger was created at `.superpowers/sdd/2026-10-24-milestone-2-english-privacy/progress.md` (git-ignored) with baseline status, the executed/qualified evidence and the execution rulings.
- [ ] Preserve temp verification evidence under `C:\Users\asaon\AppData\Local\Temp\opencode`; put reproducible methods and concise results in the final repo verification document, not raw logs or personal captures.
- [ ] Architect reviews stat/hunks; owns any commit and why-focused commit message.

## Implementation sequence at a glance

1. Remove identity/telemetry/remote control; migrate `install_id` and `send_usage` through `config.REMOVED`; retain a static About/attribution panel.
2. Remove unsupported builds/skills/Tencent tiers and prove the honest rate/fallback/nodata ladder.
3. Fix fresh-install `game_lang = "en_US"` in code, metadata seeding, bounded downloads and disk-cache/bundled fallback.
4. Migrate portrait sources with matcher regression checks and bundled-reference rollback; leave live bench acceptance open.
5. Add the strict AST CJK-literal test as a real red test; one worker extracts every key and writes the complete catalog once, together with the helper and the architect-reviewed `data_status.py` pilot.
6. Freeze the catalog; convert UI modules in code-only waves of up to four workers, one disjoint module each; the controller runs the gates and full suite after each wave. Then rendered-text coverage outside `ui/`.
7. Verify an ordinary refresh in the unmodified real application after identity removal, then warmed-cache network-blocked startup, real fixture recognition and rendered badges — the agent runs and judges all of it.
8. Record evidence and PR rationale; close #3 only after all definition-of-done checks below, including the owner's live sessions, where the owner plays and the agent evaluates the captured evidence.

## Task 2 — Remove telemetry and remote execution/control

**Status:** Implemented and independently reviewed in `a978662`. Controller full suite: **260 passed**. Fresh-install recognition default was pulled forward to this chunk (`Settings.game_lang = "en_US"`). Release-workflow patch callers and retired `logs_sent` extras were removed after review. Real post-removal application refresh and offline/live acceptance remain open under Task 9; this status does not waive them.

**Files:** delete `lolhex/cloud.py`, `cloudsettings.py`, `logupload.py`, `rank.py`, `update.py`, `patch.py`, `langpack.py`; modify `__main__.py`, `config.py`, `engine.py`, `data/public.py`, `ui/mainwindow.py`, `ui/overlay.py`, relevant tests and privacy documentation. Do not remove RapidOCR itself (milestone 3).

- [ ] Write failing tests that startup/settings load never calls identifier generation; retired config keys are ignored/dropped using the established `REMOVED` migration pattern; no forbidden feature is imported or callable through surviving UI/CLI.
- [ ] Add `install_id` and `send_usage` explicitly to `config.REMOVED`. Test loading an old config containing both, saving it again, and loading it once more: neither key survives or regenerates, no unknown-extra field preserves them, and identifier generation is never invoked.
- [ ] Add request-recording tests proving stats fetch never carries install ID, cookies or Riot ID, and startup never calls config/rank/log/update/model endpoints.
- [ ] Run focused tests and confirm failures exercise the removed behavior.
- [ ] Remove all producers/consumers together, including timers, worker signals, cloud-cache use, usage checkbox, rank card, notices and update UI. Replace remote About content with static attribution. Fixed local scheduling replaces cloud timing without changing match-time holds.
- [ ] Keep a reachable, offline About/attribution panel when notices disappear. Test that it names/links upstream `czgreat/aramhex` (MIT) and `czgreat/aramhex-data` (CC BY-NC 4.0), identifies CN-server stats, and needs no remote content. Preserve the upstream copyright/license notices in the distribution as well; About does not replace the MIT license file.
- [ ] Retain a single supported existing OCR model; remove optional language-model download controls, not recognition heuristics.
- [ ] Preserve stats fetch with anonymous headers and checksum/fallback behavior; remove cloud event configuration rather than invent a replacement event product.
- [ ] Worker runs only its focused tests; the controller runs the full offscreen suite, reports remaining unsupported tests explicitly and reviews stat/hunks before accepting the chunk.

## Task 3 — Cut upstream builds/skills/tiers and prove honest fallback

**Status:** Implemented, controller suite **289 passed**, independent scoped review clear. Unsupported tier/build/skill sources and obsolete prefetch hooks are gone; scan JSON includes basis/rate-label/source evidence. Pure metadata adapters are present but not runtime-integrated: Task 4's schema/filtering acceptance is still mandatory.

**Files:** `data/store.py`, `data/tencent.py`, `panel.py`, `recommend.py`, `data/public.py` as needed, `ui/buildview.py`, `ui/mainwindow.py`, `ui/overlay.py`; `tests/test_recommend.py`, `test_public.py`, `test_augment_items.py`, `test_data_parsers.py`, new `tests/test_advice_fallback.py`.

- [ ] Write `test_champion_rate_precedes_global`, `test_missing_champion_uses_labelled_global`, `test_tiny_champion_uses_labelled_global_or_nodata`, `test_missing_or_tiny_all_rates_has_no_number`, and `test_no_official_tier_dependency`. Assert structured basis/verdict/advice and rendered labels, not only a returned score.
- [ ] Include no-stats, tiny-sample, unknown/new/excluded augment and absent official tier/pick fields. Assert `nodata` and `?` without a fabricated percentage; global fallback contains literal `all champs`; a sufficiently supported champion-specific rate remains preferred.
- [ ] Preserve tests for stats-derived tiers, rarity ranking, smoothing, low-sample suppression, exclusions/provisional rows and band behavior. Remove only assertions that require the deliberately removed official tier source.
- [ ] Confirm tests fail first; remove Tencent build/skill/per-hero tier fetches and the tier-only recommendation branch without changing independent stats math. Missing fields must not raise.
- [ ] Remove build/skill controls/render blocks and unused partner/splash plumbing. Retain stats-based summoner/item/augment-item advice and its metadata/icon rendering.
- [ ] Worker runs focused tests; the controller runs the full suite and verifies the changed recommendation hunks and absence of an implicit tier dependency.

## Task 4 — Static metadata, bounded network and offline seeding

**Complete:** Transport in `9cdc9e5`, source/cache integration and recovery fixes in `42b9276`. Final controller suite **508 passed**. Real ordinary refresh and cold/warm offline starts passed; no Tencent runtime callers remain. See the milestone verification document for observed hosts, cache counts and dataset hashes. No frozen-executable build is claimed.

**Files:** new `data/metadata.py`; `data/http.py`, `data/store.py`, `data/public.py`, `data/icons.py`, `engine.py`, `config.py`, callers; delete remaining `data/tencent.py` once no imports survive. New `tests/test_network_policy.py`, `tests/test_data_cache.py`; extend parser/store tests and AGENTS.md.

- [ ] Write tests for the GET-only boundary: reject unknown host/path, userinfo/ports, traversal, payload-supplied absolute URLs, unsupported methods, identity/cookie headers and redirects before sending. Reject external redirects rather than following and checking after data has already escaped.
- [ ] Define the minimal host/path table in code and AGENTS.md: `aramhex.com/u/data/` for stats; `raw.githubusercontent.com/czgreat/aramhex-data/` for stats fallback; `ddragon.leagueoflegends.com` for versions/champion/item metadata/portraits/item icons; `raw.communitydragon.org` for static augment metadata/icons. CommunityDragon is community-hosted, not a Riot-owned CDN. Remove jsDelivr probes/mirrors if not needed by these two stats routes; any retained additional host requires explicit purpose and policy tests before acceptance.
- [ ] Test static parsing by stable numeric ID, all active bundled IDs resolving English names (current coverage 232 augments/173 champions), six Cherry-path augment IDs not being filtered out, and safe ASCII unknown-ID fallbacks.
- [ ] Before using the adapters at runtime, prove new/PBE flags reach `store.augments` and preserve honest new/nodata/`?` advice; prove arena-only records are excluded while all six Cherry-path Mayhem IDs remain available. Do not replace source mode semantics with universal `modes: []` admission.
- [ ] Preserve English names/aliases and existing Chinese title/alias search across the source swap. Reuse bundled aliases and cached keywords where available; the English fork need not generate Tencent-specific pinyin shortcuts, but recognition titles must not disappear. Pin the intended behavior in search/matcher tests rather than silently dropping coverage.
- [ ] Reject or safely skip unknown source rarity codes before they can create a fictitious fourth ranked rarity group; keep valid bundled/cache metadata when a refreshed record is malformed. Add the parser-to-scorer regression case.
- [ ] Test `DataStore`/`PublicStore`/`Engine` construction without network or `static.json`: populate recognition metadata from verified downloaded dataset or bundled heroes/augments plus existing i18n tables. Preserve Chinese recognition fields; add separate English display accessors. Replace the `roles`-presence refresh sentinel.
- [ ] Set the actual `Settings.game_lang` dataclass default to `"en_US"`, not merely a sample/user config. Add `test_fresh_settings_default_to_english_recognition` and `test_missing_game_lang_config_uses_english_recognition`; with no hand-edited settings, assert the engine's matcher resolves the three English fixture names. Preserve an explicitly selected supported language in an existing config. UI default remains separately `en_GB`.
- [ ] Test invalid/truncated/wrong-schema cache, partial metadata-family failure, interrupted writes, invalid image bytes and missing assets. Valid cache must survive failed refresh; bundled fallback must be immediately usable.
- [ ] Implement Data Dragon metadata/version cache and CommunityDragon augment metadata using fixed templates, validation and atomic disk writes. Cache schema records source/version per family. Normalise Data Dragon `16.21.1` to stats patch `16.21` for display comparisons.
- [ ] Define CLI refresh success as a usable validated downloaded/cache/bundled dataset: return 0 while separately exposing stale/offline refresh errors in status; return nonzero only when no usable dataset exists. Test both outcomes without hiding the network failure.
- [ ] Do not prefetch unused augment icons or splash art. Every asset actually fetched is validated and cached; no unused network dependency is introduced.
- [ ] Worker runs focused tests; the controller runs the full suite, confirms no Tencent host, rank API, hidden model or self-update path survives, and reviews stat/hunks.

## Task 5 — Portrait migration without matcher regression

**Partial evidence:** Public source/client image fixtures and unchanged-classifier baseline tests landed in `a978662`: five Data Dragon references matched five client crops; original bundled-only bank scored 165 correct / 8 abstentions / 0 wrong of 173. Combined-bank coverage is self-match coverage, not independent accuracy. Source migration, offline integration and live bench acceptance are still pending.

**Files:** `vision/portraits.py`, `data/metadata.py`, `engine.py`, `tests/test_portraits.py`, new public-image assets under `tests/fixtures/portraits/` with source/version attribution.

- [ ] Add Data Dragon square/client-icon reference pairs for the five probed champions (Teemo, Ahri, Shaco, Udyr, Hecarim). Pin fixture hashes/source URLs; no player captures.
- [ ] Test Data Dragon-only references against client-icon crops: correct IDs, existing score/margin requirements, no wrong matches, flat images abstain. Add all-hero bundled regression: zero wrong matches and at least the measured 165/173 recognitions with Tencent-only bundled references; separately verify combined fallback coverage.
- [ ] Confirm red tests for current source selection/cache behavior. Change `ensure_icons` to fetch/cache Data Dragon portraits even when an old bundled alias exists; valid disk references take precedence while bundled/client references remain fallback options. Do not change classifier math/constants to make tests pass.
- [ ] Test corrupt/missing downloaded portrait falls back to existing bundled/client reference, including fresh offline startup with all 173 heroes known.
- [ ] Worker runs the portrait tests; the controller runs the full suite, reviews image fixture provenance and changed hunks before any commit. Record automated matcher evidence separately from the still-open live bench/layout check, which only a real session can close — the owner plays it, the agent launches the app and judges the evidence.

## Task 6 — Catalog/helper, complete key extraction and one reviewed pilot

**Pilot accepted by controller:** 201 catalog keys; frozen `tr`/`set_language`/`quantity`/`short_date` API and escaped `data_status_html` pilot. Helper/pilot plus package-resource tests: **49 passed**. The real AST gate remains red for the six unconverted modules, deliberately without exemptions. Complete inventory and module conversion map are in this plan's scratch workspace. Task 8 producers are inventoried but remain deferred.

**Files:** new `lolhex/messages.py`, `lolhex/data/messages.json`, `tests/test_messages.py`, `tests/test_no_cjk_ui.py`; modify only `ui/data_status.py` as the conversion pilot, `config.py`/startup for UI language, its existing assertions in `tests/test_public.py`, resource packaging as required.

- [ ] One worker owns the catalog end to end in this task: extract **every** key needed by every module in scope — every `ui/*.py` module, the Task 8 non-UI rendered text, CLI text and engine snapshot display fields — and write the complete `messages.json` once, with `zh_CN` originals kept for real text. This worker is the sole catalog writer for the whole milestone; Tasks 7–8 convert code against that frozen file.
- [ ] Write helper tests: default English, explicit Chinese, unknown-locale English fallback, missing-key diagnostic/key return, named formatting, locale key/placeholder parity and no CJK in English catalog values. Catalog loading must work from source and existing package-resource mechanisms.
- [ ] Write the AST gate: parse every `lolhex/ui/*.py`, flag CJK `ast.Constant` strings including f-string fragments, skip actual module/class/function docstrings by node identity. Comments are naturally excluded. Do not exempt UI log calls or whole files. Test the gate itself on miniature source strings so it cannot silently miss f-strings/nested functions.
- [ ] Run gate and record the real failing modules. Keep the full gate red during conversion; do not hide debt with xfail/allowlists. Focused per-module checks establish each worker's result until the final gate can pass.
- [ ] Implement `tr` and convert only `data_status_html(d)` as the pilot. English uses readable games/date units, escaped HTML substitutions and clear CN-source/staleness labels. Preserve `zh_CN` catalog values.
- [ ] Worker runs the helper/pilot tests only. The controller runs the gates and reviews stat/hunks, catalog shape, completeness of the extracted key set, escaping and resource loading, then accepts the pilot on its own review — the pilot is self-reviewed by the architect, not approved by the owner. No other UI conversion starts until that acceptance, and after it the catalog is **frozen**: no later task writes it.

## Task 7 — Code-only waves, one UI module per worker, catalog frozen

**Complete:** Both four-worker waves reviewed by the controller; UI conversions landed in `03f7a5c` and `9066d1d`. All UI AST gates are green. No catalog amendment or DPI quarantine was needed. Pentakill placeholder collision fixed with a regression in `0e543d9`; real fixture-to-badge acceptance landed in `ab7d954`.

**Files:** each worker owns exactly one of `ui/badgepos.py`, `herosearch.py`, `buildview.py`, `autoshot.py`, `overlay.py`, `mainwindow.py`, plus its own disjoint tests. `data_status.py` is already converted. All share the Task 6 helper contract and the frozen catalog; nobody writes `messages.json`.

- [ ] Wave 1: `badgepos.py`, `herosearch.py`, `buildview.py`, `autoshot.py`. Wave 2: `overlay.py`, `mainwindow.py`, plus bounded module-verification workers for `autostart.py` and `single_instance.py` (already free of UI CJK; no gratuitous edits). Dispatch each wave's four workers together in the background, wait for all of them, then run the gates. Do not pull deferred Task 8 into the second wave merely to fill seats.
- [ ] Code only. Each worker converts its one module and its own tests and returns proposals for any key the frozen catalog lacks. No worker edits the catalog; the single Task 6 catalog writer applies accepted proposals in a separate, non-parallel phase before the next wave starts.
- [ ] For each module: write/update English rendering assertions and run the per-module AST check to show its red state; convert all non-docstring CJK literals, preserving Chinese originals in catalog entries for real text. Use ASCII internal identifiers and screenshot phase filenames; migrate their references/tests rather than cataloguing machine keys.
- [ ] Resolve hero/augment display names through Task 4 English accessors. Do not show Chinese aliases/nicknames as English autocomplete text, alter matching tables, translate arbitrary JSON payloads in place or display internal augment stringtable keys.
- [ ] Workers run only their own scoped tests — never the full suite, never git, never another agent. They report pass/fail conclusions and remaining expected red gates, not raw output.
- [ ] The controller runs the whole strict UI AST gate and the full offscreen suite after each wave and reviews that wave's combined diff before the next wave starts. Two failed attempts on one module stop the delegation for it.
- [ ] Once all modules are converted, require the entire strict UI AST gate to pass, including logging strings in UI modules; verify retained item/summoner stats rendering and static About attribution in the real window, launched and read by the agent.

## Task 8 — Rendered text outside UI and coverage boundaries

**DEFERRED by owner:** Do not execute this task for milestone 2. Keep its inventory as scratch/planned follow-up; create the follow-up issue after #3 closes. The requirements below describe that later polish, not milestone-2 blockers. Core fallback behavior from Task 3 and the existing source/recognition safeguards remain required.

**Files:** `recommend.py`, `panel.py`, `data/public.py`, `data/metadata.py`, `config.py`, `__main__.py`, `engine.py` only where rendered data requires it; `tests/test_no_cjk_ui.py`, `test_messages.py`, new `tests/test_display_localisation.py`. Code only: the catalog was extracted complete in Task 6 and is frozen, so any key found missing here becomes a proposal to the single catalog writer, applied in a separate non-parallel phase.

- [ ] Explicitly test `win_text`, `display_name`, `pentakill_text`, advice/fallback/nodata notes, dataset/band/speed/language labels and CLI text. Route them through the shared catalog; preserve recommendation machine codes and calculations. Localise recommendation reasons exposed in scan JSON too, avoiding a second ambiguous display/diagnostic exception.
- [ ] Extend AST checks to non-UI display-producing modules with narrowly identified recognition/data-literal exclusions where genuinely necessary, never a blanket file exemption. Keep `lolhex/i18n.py` recognition strings and immutable stats/aliases outside the UI-literal gate.
- [ ] Record exact coverage: strict UI literals; explicitly checked non-UI rendered functions/modules; engine's non-rendered diagnostics and vision/recognition data remain outside the display gate. Snapshot tests verify engine snapshots consumed by UI have English display fields.
- [ ] Worker runs its scoped display tests; the controller runs the full AST/catalog/placeholder checks and the full suite. No claim of “no CJK anywhere in repo”: documented comments/docstrings, recognition data and fixtures remain intentionally Chinese.

## Task 9 — Real warm-cache/offline acceptance, documentation and handoff

**Files:** new `tests/test_offline_startup.py`, extend `tests/test_full_scan_badge_bounds.py` as needed; new `docs/superpowers/verification/2026-10-24-milestone-2.md`; AGENTS.md, privacy/README/About documentation, this checklist.

- [ ] Automated tests block all external transport including session/fetch paths, not just `requests.get`; explicit test-server transport remains isolated. Prove construction/startup, failed refresh, corrupt-cache fallback, fixture recognition and real badge rendering still work.
- [ ] Add an integration case using actual OCR on `tests/fixtures/real-mayhem-augment-screen.png`: recognise Juiced (2016), Adaptive Ward (2138), Snowday (2088); feed the resulting offer into the engine and render `BadgeLayer`; assert three badge rectangles and existing title/bounds invariants. Do not replace OCR or the offer with mocks and call it fixture recognition.
- [ ] After tests pass, the controller performs one real allowed-network startup/refresh in isolated `ARAMHEX_HOME`, records anonymous request host/path/header evidence and disk caches, then closes the process. This runs alone, never in parallel with other runs. Do not write user's APPDATA or interfere with an existing match/overlay; coordinate if single-instance/live-match holds block the check.
- [ ] Relaunch from the same warmed directory with all external connections denied before startup, not success-mocked. Verify actual UI starts with cached dataset, actual fixture scan succeeds, and card badges render. Record exact commands, cache origin/revision, request-denial mechanism, recognised IDs and badge count. Also test empty-home bundled startup so offline recognition seeding is not left broken.
- [ ] Verify real anonymous background refresh outside a live match separately from the pre-removal manual-refresh evidence. Normal holds during a match are not a network failure.
- [ ] Mandatory post-removal real-build check: launch the committed product code with ordinary settings loading and the normal application entry point, then complete one ordinary scheduled/background stats refresh outside a match. Do not intercept identifier generation, patch cloud/header/settings methods, invoke the downloader directly, or substitute a manual-refresh-only path for this check. Record application completion state, dataset origin/revision, checksum validation, and independently observed requests/headers showing no identity. A controlled HTTP recorder may observe real requests without changing application logic. Confirm config has neither retired key. If match holds, single-instance contention or unavailable network block this check, leave it open and do not close #3.
- [ ] Exercise missing/tiny champion sample through rendered advice: labelled `all champs` or `?` without number and without crash. Include its evidence in the verification document.
- [ ] Controller runs the full offscreen suite: `$env:QT_QPA_PLATFORM='offscreen'; .venv\Scripts\python.exe -m pytest -q`. Record actual new totals; deletions of obsolete feature tests mean 308 is not a required final count. Record fixture CLI JSON rather than pipeline exit status.
- [ ] Architect reviews `git diff --stat`, changed hunks, test evidence, network inventory and limitations. Author small why-focused commits only after review; workers never commit.
- [ ] PR description explicitly explains Tencent build/skill/letter-tier removal: unsupported CN letters are not evidence; stats-derived tiers remain; visible fallback is champion rate → labelled all-champs rate → `?`. Include outbound hosts, offline evidence, source-change matcher evidence and pending live checks. Use `& "C:\Program Files\GitHub CLI\gh.exe" pr create --repo saon3r/aramhex` when integration is authorised.
- [ ] Live acceptance: the owner plays champion select/bench and one full game in English; the agent launches and manages the app, reads the logs, screenshots and scan output, and decides pass/fail. The owner is not asked to verify anything. If Data Dragon bench references fail, the agent restores proven previous bundled/cached references and retests; the bench check is not closed on the basis of the five-image probe.
- [ ] Only after that, the agent comments on issue #3 with evidence and limitations and closes it, under the standing owner authorisation — no further approval step. Until then leave live/full-game checkboxes open and do not claim milestone completion.

## Definition of done — permission to close issue #3

Every item below must have evidence linked from the issue/PR; a blocked or pending item means #3 stays open. The real-refresh and offline/cold-start gates are never waived on partial or pre-removal evidence.

- [ ] English catalog and strict AST test pass for every `lolhex/ui/*.py` string literal except actual docstrings; catalog key/placeholder checks pass. Non-UI rendered-text polish/gates are explicitly deferred to Task 8's follow-up, not silently described as complete. Intentional recognition/data/diagnostic exclusions are documented precisely.
- [ ] A fresh config uses English UI and `game_lang == "en_US"` without manual editing, and recognises the real English fixture.
- [ ] Old configs cannot resurrect `install_id` or `send_usage`; generation, persistence and transmission are gone, along with every prohibited remote feature and Tencent request.
- [ ] Static About/upstream MIT notices and stats CC BY-NC 4.0 attribution remain available offline.
- [ ] The real application completes an ordinary stats refresh after identity removal with no identity interception or data-fetch substitution; record its requests and successful verified dataset state. Pre-removal instrumented evidence does not satisfy this checkbox.
- [ ] All remaining outbound hosts/purposes and bounded GET paths are documented in AGENTS.md and tested; only the approved anonymous static assets/metadata and stats are fetched and cached.
- [ ] After one successful online run, network-blocked app startup, real fixture OCR/matching and three rendered card badges pass from disk cache; empty-home bundled metadata also seeds recognition successfully.
- [ ] Missing/tiny champion samples render a supported rate labelled `all champs` or `?` with no number, never an unsupported tier; no verdict/advice crash, own-stats tiers preserved.
- [ ] Full automated suite passes, and PR description explains the intentional upstream tier/build/skill differences and records offline/source-migration evidence.
- [ ] Live session evidence exists: the owner plays champion select/bench and a full game in English while the agent launches and manages the app, captures logs/screenshots/scan JSON and decides pass/fail — the owner judges nothing. A failed new portrait source is rolled back to the previous bundled/cached references and retested, not waived on probe evidence.
- [ ] Issue #3 receives the final evidence comment before closure; no unchecked acceptance requirement is described as completed.

## Execution contract

Each worker brief repeats exact owned paths, goal, interface/dependency decisions, global non-negotiables, tests and done criteria. Ask for conclusions, not raw outputs. Report tests actually run, remaining expected red gates and any blocked checks. The architect settles implementation details; stop for the owner only when scope, trustworthy behavior or acceptance materially changes.

Parallel work follows AGENTS.md "Parallel workers": disjoint files only, no parallel git/merge/suite runs, one catalog writer with the catalog frozen after Task 6, workers scoped-tests-only and unable to spawn agents, and the controller owning the gates, the full suite, `git diff --check`, the combined-diff review and every git/GitHub action. These owner rules override the delegation skill's generic defaults — its ban on parallel agents, its model tiers and its "every worker runs the suite" contract. Worker, explore and reviewer all use `opencode-go/deepseek-v4.1-flash`.
