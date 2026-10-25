# Milestone 5 — packaged portable build verification

**Status: verified on this machine.** Issue #6. Branch `packaging`, merged after this record.

## What was built

One-folder PyInstaller build (`packaging/lolhex.spec`, `exclude_binaries=True` + `COLLECT`) and
the portable ZIP that `packaging/build.ps1 -PortableOnly` produces. One-folder, not one-file:
one-file unpacks to `%TEMP%` on every launch, which is slower and trips antivirus scanners.

| Artefact | Size |
|---|---|
| `build/dist/AramHex/` (one folder, exe + `_internal`) | ~200 MB |
| `AramHex-Portable-1.1.1.zip` | 75 MB |
| `SHA256SUMS.txt` | checksums for the zip |

No installer was built (Inno Setup is not installed here); `-PortableOnly` is the supported
path. The spec no longer collects ONNX models or the ONNX runtime and declares the WinRT
projections the OCR backend imports.

## Acceptance (the bar the owner set)

Run by `scripts/accept_packaged.py`, which launches the frozen app with **PATH reduced to
`System32;C:\Windows`** so no Python can be found:

| Check | Result |
|---|---|
| Frozen build exists, one folder | pass |
| Self-test passes inside the frozen app | pass (exit 0) |
| `sys.frozen` true | pass |
| Package loaded from inside the install dir | `…\AramHex\_internal\lolhex` |
| **No module loaded from outside the install** | pass — the report lists every loaded `lolhex` module whose file is outside the exe's folder; the list is empty |
| No `python.exe` on PATH | pass |
| Interpreter is `AramHex.exe` | pass |
| OCR works in the frozen app | `AramHex 2026`, score 1.0 |
| UI chrome is English | title + tab labels, zero CJK |
| Fixture reads the three cards | `2016 / 2138 / 2088` |
| Three badges render | 3, in order, inside the window |
| Warmed-cache start stays up | pass |
| Warmed-cache start opens no TCP connections | pass (updates disabled; this is not a blocked-network run) |
| Warmed-cache start reads the cached dataset | pass — icon bank built from cached `static.json` (173) |
| Crash dialog appears | pass |
| Crash dialog is English | pass — "AramHex could not start…" + log path |
| Missing recognizer is reported | pass — `OcrUnavailable: no Windows OCR recognizer for 'zh_CN'; installed: ['en-GB']` |

Full run: **18/18 passed**.

## Defects this acceptance found (all fixed)

1. **Startup crash without `USERNAME`.** `getpass.getuser()` raises when the environment has
   no `USERNAME`/`LOGNAME` (scheduler or a launcher that scrubs the environment), and the app
   died before the tray appeared — the crash dialog was the only thing that showed. The
   single-instance name now falls back; test: `tests/test_instance_user.py`.
2. **My own regression while fixing (1).** The helper was inserted at module level *inside*
   `run()`, which silently truncated the function body: the app started, logged one line and
   exited. Caught by this acceptance, fixed, and pinned by a structural test that `run()`
   still contains its event loop.
3. **`packaging/build.ps1` would not parse on PowerShell 5.1.** No `pwsh` on this machine and
   the script was UTF-8 without BOM, so 5.1 decoded its Chinese as ANSI. BOM added (honoured by
   both 5.1 and 7); recorded in AGENTS.md.

## SmartScreen

The exe is unsigned, so Windows will show "Windows protected your PC" on other machines or on
a fresh download: **More info → Run anyway**. The portable ZIP itself is not blocked locally
because it was not downloaded from the internet. This is noted, not worked around — disabling
SmartScreen or self-signing would misrepresent the binary's provenance.

## Not covered

- No installer (Inno Setup absent); only the portable ZIP.
- Built and accepted on one machine, one Windows version, one monitor layout.
- The warmed start proves the app needs no network to run from cache; it does not re-prove the
  blocked-network path (that is covered by the in-process offline acceptance for the same code).
- The 4K badges were checked through the fixture and the earlier live game, not in a fresh
  packaged live game.
