# Milestone 2: English UI, private downloads and offline operation

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development or superpowers:executing-plans. Follow the owner's execution method: architect owns this plan, decisions and review; `worker` implements/tests and `explore` answers code-location questions. Both use `opencode-go/deepseek-v4.1-flash`. No worker commits.

**Goal:** A runnable English overlay with no telemetry or remote control, narrowly scoped anonymous downloads, and working recognition/badges offline.

**Architecture:** Preserve screen recognition, overlay layering, stats verification and stats-derived ranking. Replace Tencent dependencies with static Data Dragon/CommunityDragon metadata and assets, seed recognition from disk/bundled data, and separate English display names from recognition names. A shared message helper/catalog supplies UI and other rendered text.

**Tech stack:** Existing Python 3.13, PySide6, requests, RapidOCR, OpenCV and pytest; no new runtime dependency.

**Spec:** `docs/superpowers/specs/2026-10-24-aram-mayhem-overlay-design.md`, issue https://github.com/saon3r/aramhex/issues/3, and the owner decisions recorded below. These decisions supersede the original design where it differs.

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
- One `english-ui` milestone branch; preserve existing changes. Workers do not commit, open PRs, close issues or modify user APPDATA.
- One worker per UI module after the reviewed pilot. Catalog writes are serialized. Parallel workers only if all edited files, including tests/catalog, are disjoint; sequential is the default.
- Review each chunk using `git diff --stat` first, then changed hunks. Stop delegating a task after two failed attempts.
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

- [ ] Have a worker recheck branch/status and create `english-ui` without discarding changes; carry the architect's two-line AGENTS.md edit and this plan forward. If state differs, report before changing branches.
- [ ] Preserve temp verification evidence under `C:\Users\asaon\AppData\Local\Temp\opencode`; put reproducible methods and concise results in the final repo verification document, not raw logs or personal captures.
- [ ] Architect reviews stat/hunks; owns any commit and why-focused commit message.

## Implementation sequence at a glance

1. Remove identity/telemetry/remote control; migrate `install_id` and `send_usage` through `config.REMOVED`; retain a static About/attribution panel.
2. Remove unsupported builds/skills/Tencent tiers and prove the honest rate/fallback/nodata ladder.
3. Fix fresh-install `game_lang = "en_US"` in code, metadata seeding, bounded downloads and disk-cache/bundled fallback.
4. Migrate portrait sources with matcher regression checks and bundled-reference rollback; leave live bench acceptance open.
5. Add the strict AST CJK-literal test as a real red test; implement catalog/helper plus the reviewed `data_status.py` pilot.
6. Convert one UI module per worker, serializing catalog writes; finish the AST gate and rendered-text coverage outside `ui/`.
7. Verify an ordinary refresh in the unmodified real application after identity removal, then warmed-cache network-blocked startup, real fixture recognition and rendered badges.
8. Record evidence and PR rationale; close #3 only after all definition-of-done checks below, including owner live acceptance.

## Task 2 — Remove telemetry and remote execution/control

**Files:** delete `lolhex/cloud.py`, `cloudsettings.py`, `logupload.py`, `rank.py`, `update.py`, `patch.py`, `langpack.py`; modify `__main__.py`, `config.py`, `engine.py`, `data/public.py`, `ui/mainwindow.py`, `ui/overlay.py`, relevant tests and privacy documentation. Do not remove RapidOCR itself (milestone 3).

- [ ] Write failing tests that startup/settings load never calls identifier generation; retired config keys are ignored/dropped using the established `REMOVED` migration pattern; no forbidden feature is imported or callable through surviving UI/CLI.
- [ ] Add `install_id` and `send_usage` explicitly to `config.REMOVED`. Test loading an old config containing both, saving it again, and loading it once more: neither key survives or regenerates, no unknown-extra field preserves them, and identifier generation is never invoked.
- [ ] Add request-recording tests proving stats fetch never carries install ID, cookies or Riot ID, and startup never calls config/rank/log/update/model endpoints.
- [ ] Run focused tests and confirm failures exercise the removed behavior.
- [ ] Remove all producers/consumers together, including timers, worker signals, cloud-cache use, usage checkbox, rank card, notices and update UI. Replace remote About content with static attribution. Fixed local scheduling replaces cloud timing without changing match-time holds.
- [ ] Keep a reachable, offline About/attribution panel when notices disappear. Test that it names/links upstream `czgreat/aramhex` (MIT) and `czgreat/aramhex-data` (CC BY-NC 4.0), identifies CN-server stats, and needs no remote content. Preserve the upstream copyright/license notices in the distribution as well; About does not replace the MIT license file.
- [ ] Retain a single supported existing OCR model; remove optional language-model download controls, not recognition heuristics.
- [ ] Preserve stats fetch with anonymous headers and checksum/fallback behavior; remove cloud event configuration rather than invent a replacement event product.
- [ ] Run focused tests and full offscreen suite; report remaining unsupported tests explicitly. Architect reviews stat/hunks before accepting the chunk.

## Task 3 — Cut upstream builds/skills/tiers and prove honest fallback

**Files:** `data/store.py`, `data/tencent.py`, `panel.py`, `recommend.py`, `data/public.py` as needed, `ui/buildview.py`, `ui/mainwindow.py`, `ui/overlay.py`; `tests/test_recommend.py`, `test_public.py`, `test_augment_items.py`, `test_data_parsers.py`, new `tests/test_advice_fallback.py`.

- [ ] Write `test_champion_rate_precedes_global`, `test_missing_champion_uses_labelled_global`, `test_tiny_champion_uses_labelled_global_or_nodata`, `test_missing_or_tiny_all_rates_has_no_number`, and `test_no_official_tier_dependency`. Assert structured basis/verdict/advice and rendered labels, not only a returned score.
- [ ] Include no-stats, tiny-sample, unknown/new/excluded augment and absent official tier/pick fields. Assert `nodata` and `?` without a fabricated percentage; global fallback contains literal `all champs`; a sufficiently supported champion-specific rate remains preferred.
- [ ] Preserve tests for stats-derived tiers, rarity ranking, smoothing, low-sample suppression, exclusions/provisional rows and band behavior. Remove only assertions that require the deliberately removed official tier source.
- [ ] Confirm tests fail first; remove Tencent build/skill/per-hero tier fetches and the tier-only recommendation branch without changing independent stats math. Missing fields must not raise.
- [ ] Remove build/skill controls/render blocks and unused partner/splash plumbing. Retain stats-based summoner/item/augment-item advice and its metadata/icon rendering.
- [ ] Run focused tests and full suite; architect verifies the changed recommendation hunks and absence of implicit tier dependency.

## Task 4 — Static metadata, bounded network and offline seeding

**Files:** new `data/metadata.py`; `data/http.py`, `data/store.py`, `data/public.py`, `data/icons.py`, `engine.py`, `config.py`, callers; delete remaining `data/tencent.py` once no imports survive. New `tests/test_network_policy.py`, `tests/test_data_cache.py`; extend parser/store tests and AGENTS.md.

- [ ] Write tests for the GET-only boundary: reject unknown host/path, userinfo/ports, traversal, payload-supplied absolute URLs, unsupported methods, identity/cookie headers and redirects before sending. Reject external redirects rather than following and checking after data has already escaped.
- [ ] Define the minimal host/path table in code and AGENTS.md: `aramhex.com/u/data/` for stats; `raw.githubusercontent.com/czgreat/aramhex-data/` for stats fallback; `ddragon.leagueoflegends.com` for versions/champion/item metadata/portraits/item icons; `raw.communitydragon.org` for static augment metadata/icons. CommunityDragon is community-hosted, not a Riot-owned CDN. Remove jsDelivr probes/mirrors if not needed by these two stats routes; any retained additional host requires explicit purpose and policy tests before acceptance.
- [ ] Test static parsing by stable numeric ID, all active bundled IDs resolving English names (current coverage 232 augments/173 champions), six Cherry-path augment IDs not being filtered out, and safe ASCII unknown-ID fallbacks.
- [ ] Test `DataStore`/`PublicStore`/`Engine` construction without network or `static.json`: populate recognition metadata from verified downloaded dataset or bundled heroes/augments plus existing i18n tables. Preserve Chinese recognition fields; add separate English display accessors. Replace the `roles`-presence refresh sentinel.
- [ ] Set the actual `Settings.game_lang` dataclass default to `"en_US"`, not merely a sample/user config. Add `test_fresh_settings_default_to_english_recognition` and `test_missing_game_lang_config_uses_english_recognition`; with no hand-edited settings, assert the engine's matcher resolves the three English fixture names. Preserve an explicitly selected supported language in an existing config. UI default remains separately `en_GB`.
- [ ] Test invalid/truncated/wrong-schema cache, partial metadata-family failure, interrupted writes, invalid image bytes and missing assets. Valid cache must survive failed refresh; bundled fallback must be immediately usable.
- [ ] Implement Data Dragon metadata/version cache and CommunityDragon augment metadata using fixed templates, validation and atomic disk writes. Cache schema records source/version per family. Normalise Data Dragon `16.21.1` to stats patch `16.21` for display comparisons.
- [ ] Define CLI refresh success as a usable validated downloaded/cache/bundled dataset: return 0 while separately exposing stale/offline refresh errors in status; return nonzero only when no usable dataset exists. Test both outcomes without hiding the network failure.
- [ ] Do not prefetch unused augment icons or splash art. Every asset actually fetched is validated and cached; no unused network dependency is introduced.
- [ ] Run focused tests/full suite and confirm no Tencent host, rank API, hidden model or self-update path survives. Architect reviews stat/hunks.

## Task 5 — Portrait migration without matcher regression

**Files:** `vision/portraits.py`, `data/metadata.py`, `engine.py`, `tests/test_portraits.py`, new public-image assets under `tests/fixtures/portraits/` with source/version attribution.

- [ ] Add Data Dragon square/client-icon reference pairs for the five probed champions (Teemo, Ahri, Shaco, Udyr, Hecarim). Pin fixture hashes/source URLs; no player captures.
- [ ] Test Data Dragon-only references against client-icon crops: correct IDs, existing score/margin requirements, no wrong matches, flat images abstain. Add all-hero bundled regression: zero wrong matches and at least the measured 165/173 recognitions with Tencent-only bundled references; separately verify combined fallback coverage.
- [ ] Confirm red tests for current source selection/cache behavior. Change `ensure_icons` to fetch/cache Data Dragon portraits even when an old bundled alias exists; valid disk references take precedence while bundled/client references remain fallback options. Do not change classifier math/constants to make tests pass.
- [ ] Test corrupt/missing downloaded portrait falls back to existing bundled/client reference, including fresh offline startup with all 173 heroes known.
- [ ] Run portrait and full tests. Record automated matcher evidence separately from the still-open live bench/layout check. Architect reviews image fixture provenance and changed hunks before any commit.

## Task 6 — Catalog/helper and one reviewed localisation pilot

**Files:** new `lolhex/messages.py`, `lolhex/data/messages.json`, `tests/test_messages.py`, `tests/test_no_cjk_ui.py`; modify only `ui/data_status.py` as the conversion pilot, `config.py`/startup for UI language, its existing assertions in `tests/test_public.py`, resource packaging as required.

- [ ] Write helper tests: default English, explicit Chinese, unknown-locale English fallback, missing-key diagnostic/key return, named formatting, locale key/placeholder parity and no CJK in English catalog values. Catalog loading must work from source and existing package-resource mechanisms.
- [ ] Write the AST gate: parse every `lolhex/ui/*.py`, flag CJK `ast.Constant` strings including f-string fragments, skip actual module/class/function docstrings by node identity. Comments are naturally excluded. Do not exempt UI log calls or whole files. Test the gate itself on miniature source strings so it cannot silently miss f-strings/nested functions.
- [ ] Run gate and record the real failing modules. Keep the full gate red during conversion; do not hide debt with xfail/allowlists. Focused per-module checks establish each worker's result until the final gate can pass.
- [ ] Implement `tr` and convert only `data_status_html(d)` as the pilot. English uses readable games/date units, escaped HTML substitutions and clear CN-source/staleness labels. Preserve `zh_CN` catalog values.
- [ ] Run helper/pilot tests, then architect reviews stat/hunks, catalog shape, escaping and resource loading. No other UI conversion starts until this pattern is accepted.

## Task 7 — One worker per UI module, serialized catalog integration

**Files:** each worker owns exactly one of `ui/badgepos.py`, `herosearch.py`, `buildview.py`, `autoshot.py`, `overlay.py`, `mainwindow.py`, with disjoint relevant tests. `data_status.py` is already converted. All share the Task 6 helper contract.

- [ ] Default to sequential module workers in the order above; each may edit the catalog only while it is the sole catalog writer. If parallelism is worthwhile, workers submit key proposals in separate temporary fragments and a single integration worker merges/validates them serially before tests; never concurrent `messages.json` edits.
- [ ] For each module: write/update English rendering assertions and run the per-module AST check to show its red state; convert all non-docstring CJK literals, preserving Chinese originals in catalog entries for real text. Use ASCII internal identifiers and screenshot phase filenames; migrate their references/tests rather than cataloguing machine keys.
- [ ] Resolve hero/augment display names through Task 4 English accessors. Do not show Chinese aliases/nicknames as English autocomplete text, alter matching tables, translate arbitrary JSON payloads in place or display internal augment stringtable keys.
- [ ] Each worker runs its focused tests and full suite, reporting expected remaining full-AST failures separately from regressions. Architect reviews stat/hunks after each module before the next catalog writer starts.
- [ ] Once all modules are converted, require the entire strict UI AST gate to pass, including logging strings in UI modules; verify retained item/summoner stats rendering and static About attribution in the real window.

## Task 8 — Rendered text outside UI and coverage boundaries

**Files:** `recommend.py`, `panel.py`, `data/public.py`, `data/metadata.py`, `config.py`, `__main__.py`, `engine.py` only where rendered data requires it; catalog and `tests/test_no_cjk_ui.py`, `test_messages.py`, new `tests/test_display_localisation.py`.

- [ ] Explicitly test `win_text`, `display_name`, `pentakill_text`, advice/fallback/nodata notes, dataset/band/speed/language labels and CLI text. Route them through the shared catalog; preserve recommendation machine codes and calculations. Localise recommendation reasons exposed in scan JSON too, avoiding a second ambiguous display/diagnostic exception.
- [ ] Extend AST checks to non-UI display-producing modules with narrowly identified recognition/data-literal exclusions where genuinely necessary, never a blanket file exemption. Keep `lolhex/i18n.py` recognition strings and immutable stats/aliases outside the UI-literal gate.
- [ ] Record exact coverage: strict UI literals; explicitly checked non-UI rendered functions/modules; engine's non-rendered diagnostics and vision/recognition data remain outside the display gate. Snapshot tests verify engine snapshots consumed by UI have English display fields.
- [ ] Run full AST/catalog/placeholder checks and full suite. No claim of “no CJK anywhere in repo”: documented comments/docstrings, recognition data and fixtures remain intentionally Chinese.

## Task 9 — Real warm-cache/offline acceptance, documentation and handoff

**Files:** new `tests/test_offline_startup.py`, extend `tests/test_full_scan_badge_bounds.py` as needed; new `docs/superpowers/verification/2026-10-24-milestone-2.md`; AGENTS.md, privacy/README/About documentation, this checklist.

- [ ] Automated tests block all external transport including session/fetch paths, not just `requests.get`; explicit test-server transport remains isolated. Prove construction/startup, failed refresh, corrupt-cache fallback, fixture recognition and real badge rendering still work.
- [ ] Add an integration case using actual OCR on `tests/fixtures/real-mayhem-augment-screen.png`: recognise Juiced (2016), Adaptive Ward (2138), Snowday (2088); feed the resulting offer into the engine and render `BadgeLayer`; assert three badge rectangles and existing title/bounds invariants. Do not replace OCR or the offer with mocks and call it fixture recognition.
- [ ] After tests pass, worker performs one real allowed-network startup/refresh in isolated `ARAMHEX_HOME`, records anonymous request host/path/header evidence and disk caches, then closes the process. Do not write user's APPDATA or interfere with an existing match/overlay; coordinate if single-instance/live-match holds block the check.
- [ ] Relaunch from the same warmed directory with all external connections denied before startup, not success-mocked. Verify actual UI starts with cached dataset, actual fixture scan succeeds, and card badges render. Record exact commands, cache origin/revision, request-denial mechanism, recognised IDs and badge count. Also test empty-home bundled startup so offline recognition seeding is not left broken.
- [ ] Verify real anonymous background refresh outside a live match separately from the pre-removal manual-refresh evidence. Normal holds during a match are not a network failure.
- [ ] Mandatory post-removal real-build check: launch the committed product code with ordinary settings loading and the normal application entry point, then complete one ordinary scheduled/background stats refresh outside a match. Do not intercept identifier generation, patch cloud/header/settings methods, invoke the downloader directly, or substitute a manual-refresh-only path for this check. Record application completion state, dataset origin/revision, checksum validation, and independently observed requests/headers showing no identity. A controlled HTTP recorder may observe real requests without changing application logic. Confirm config has neither retired key. If match holds, single-instance contention or unavailable network block this check, leave it open and do not close #3.
- [ ] Exercise missing/tiny champion sample through rendered advice: labelled `all champs` or `?` without number and without crash. Include its evidence in the verification document.
- [ ] Full offscreen suite: `$env:QT_QPA_PLATFORM='offscreen'; .venv\Scripts\python.exe -m pytest -q`. Record actual new totals; deletions of obsolete feature tests mean 308 is not a required final count. Record fixture CLI JSON rather than pipeline exit status.
- [ ] Architect reviews `git diff --stat`, changed hunks, test evidence, network inventory and limitations. Author small why-focused commits only after review; workers never commit.
- [ ] PR description explicitly explains Tencent build/skill/letter-tier removal: unsupported CN letters are not evidence; stats-derived tiers remain; visible fallback is champion rate → labelled all-champs rate → `?`. Include outbound hosts, offline evidence, source-change matcher evidence and pending live checks. Use `& "C:\Program Files\GitHub CLI\gh.exe" pr create --repo saon3r/aramhex` when integration is authorised.
- [ ] Owner live acceptance: champion select/bench recognition and one full game in English. If Data Dragon bench references fail, restore proven previous bundled/cached references and retest; do not close the bench check on the basis of the five-image probe.
- [ ] Only after acceptance, comment on issue #3 with evidence and limitations and close it. Until then leave live/full-game checkboxes open and do not claim milestone completion.

## Definition of done — permission to close issue #3

Every item below must have evidence linked from the issue/PR; a blocked or pending item means #3 stays open.

- [ ] English catalog and strict AST test pass for every `lolhex/ui/*.py` string literal except actual docstrings; catalog key/placeholder checks and named non-UI rendered-text tests pass. Intentional recognition/data/diagnostic exclusions are documented precisely.
- [ ] A fresh config uses English UI and `game_lang == "en_US"` without manual editing, and recognises the real English fixture.
- [ ] Old configs cannot resurrect `install_id` or `send_usage`; generation, persistence and transmission are gone, along with every prohibited remote feature and Tencent request.
- [ ] Static About/upstream MIT notices and stats CC BY-NC 4.0 attribution remain available offline.
- [ ] The real application completes an ordinary stats refresh after identity removal with no identity interception or data-fetch substitution; record its requests and successful verified dataset state. Pre-removal instrumented evidence does not satisfy this checkbox.
- [ ] All remaining outbound hosts/purposes and bounded GET paths are documented in AGENTS.md and tested; only the approved anonymous static assets/metadata and stats are fetched and cached.
- [ ] After one successful online run, network-blocked app startup, real fixture OCR/matching and three rendered card badges pass from disk cache; empty-home bundled metadata also seeds recognition successfully.
- [ ] Missing/tiny champion samples render a supported rate labelled `all champs` or `?` with no number, never an unsupported tier; no verdict/advice crash, own-stats tiers preserved.
- [ ] Full automated suite passes, and PR description explains the intentional upstream tier/build/skill differences and records offline/source-migration evidence.
- [ ] Owner verifies live champion-select/bench behavior and a full game in English. A failed new portrait source is rolled back to the previous bundled/cached references and retested, not waived on probe evidence.
- [ ] Issue #3 receives the final evidence comment before closure; no unchecked acceptance requirement is described as completed.

## Execution contract

Each worker brief repeats exact owned paths, goal, interface/dependency decisions, global non-negotiables, tests and done criteria. Ask for conclusions, not raw outputs. Report tests actually run, remaining expected red gates and any blocked checks. The architect settles implementation details; stop for the owner only when scope, trustworthy behavior or acceptance materially changes.
