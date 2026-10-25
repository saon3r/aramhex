# Milestone 3 — Windows OCR verification

**Status: verified.** Issue #4. Branch `winrt-ocr`, merged after this record.

Plan/rationale: [design §5.1](../specs/2026-10-24-aram-mayhem-overlay-design.md).

## What changed

RapidOCR (PaddleOCR models on ONNX) is gone. `lolhex/vision/ocr.py` is now the OCR entry
point (`get_ocr`, `TextLine`); the backend is `lolhex/vision/ocr_win.py`, built on
**Windows.Media.Ocr**, which ships with Windows. Nothing OCR-related is downloaded or
bundled.

The interface did not change: `detect(img)` returns text lines with boxes, `recognize(img)`
returns `(text, score)`. The detector, matcher, calibration and champion-select code are
unchanged apart from asking `get_ocr()` for the backend.

## Measured

Through `AugmentDetector` (the app's own path), on the committed fixture and on real
3840×2160 game captures. Every run printed the ids and per-column text it read, so a fast
number cannot be an empty result. Reproduce with `scripts/bench_ocr.py`; the 4K captures
contain other players' names and stay local (`--captures <dir>`).

| | Windows OCR | RapidOCR | |
|---|---|---|---|
| Title strip, 3 cards (per tick) | **3.4–4.2 ms** | 32–34 ms | ~9× |
| One card, `recognize` | **0.8–1.1 ms** | 10.6–11.4 ms | ~10× |
| Full-frame scan, 4K | **57–63 ms** | 758–953 ms | ~13× |
| Fixture (2560×1440), full scan | 48.5 ms | 778–790 ms | ~16× |
| Installed size | — | −75 MB measured after uninstall | `rapidocr` 33 MB + `onnxruntime` 46 MB |

The live game produced the same picture from the app's own counters:

| Game | Title strips | Full scans | Title-strip OCR calls |
|---|---|---|---|
| milestone 2 (RapidOCR) | 2033 × **33 ms** (CPU 33) | 37 × **524 ms** (CPU 517) | 5736 |
| milestone 3 (Windows OCR) | 2507 × **4 ms** (CPU 3) | 39 × **66 ms** (CPU 24) | 6960 |

Same work, roughly a tenth of the time and CPU, with 50 % more strip reads in the same
game length.

## Acceptance

- **Fixture through the engine**: `tests/fixtures/real-mayhem-augment-screen.png` reads
  `2016 / 2138 / 2088` (`Juiced / Adaptive Ward / Snowday`), evaluation runs, and three
  badges render. Run both as the committed acceptance test (with its no-socket guard) and
  against the downloaded cache: zero socket attempts, zero HTTP dispatch.
- **Live game, 25 Oct, `--debug`**: 7,488 log lines, **zero errors and zero warnings**;
  16 offers published (23 distinct augments); every offer in English; match ended cleanly.
  Three badges rendered on the live captures, e.g. `Snowday –5.3 · 50.0% win rate ·
  Silver win-rate #33/38` (Consider reroll), `Goredrink +1.8` (Viable),
  `Escape Plan +2.6 · 58.4% win rate · Silver win-rate #1/38` (Best).
- **Champion select, re-checked because the height heuristic could invert**: the app read
  `PICK YOUR CHAMPION`, resolved the player's champion (Yi) and attributed every offer to
  him. On the milestone-2 champion-select capture both engines agree on bench (6), team (5)
  and "you are Talon"; Windows OCR additionally resolved the height pick that RapidOCR left
  ambiguous (`_champ_select_ocr` returned `None` with RapidOCR, `91` with Windows OCR).

## Fuzzy matcher on hard names

The easy names are not the test. Rendering the awkward ones at card size and reading them
with the shipped engine, then matching against the real 262-name table:

| Card text | Windows OCR read | Matched | Score |
|---|---|---|---|
| `Transmute: Prismatic` | exact | 1238 | 100 |
| `Quest: Steel Your Heart` | exact | 1152 (`Steel Your Heart`) | 84.8 |
| `BEES!!!` | `BEES ! ! !` / exact | 3086 | 100 |
| `BONK!` | exact | 2111 | 100 |

Confusions checked: `Transmute: Gold` → 1237 (not 1238), `Transmute: Chaos` → 1243,
`BEES`/`BEES!!` → 3086 or nothing, `BONK`/`BONK!!` → 2111 or nothing, `Get Jinxed` → 3004
and `Get Excited!` → 1322 are never interchanged. **No threshold was changed** — the
existing 72 / min-margin 6 rules were adequate on real output, so there was nothing to tune.
These cases are pinned in `tests/test_hard_augment_names.py`.

## Deliberate trade-off

Windows OCR needs the client language's recognizer pack. On this machine only `en-GB` is
installed, so a Chinese or Japanese client would get `OcrUnavailable` and no badges rather
than silently wrong ones; the log names the missing language. This replaces RapidOCR's
bundled Chinese models, which is the point of the swap, and is recorded in the README.

## Not covered

- No frozen executable was built; the PyInstaller spec now declares the WinRT projections
  and no longer collects ONNX data, but that is milestone 5's acceptance.
- Bench timings are wall-clock on one machine; the strip numbers exclude the rarity frame
  classifier, identically for both engines.
- The champion-select capture used for the cross-engine comparison is not committed (it
  contains other players' names).
