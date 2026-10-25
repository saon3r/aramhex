# Packaged application verification

## Previously verified builds

The v1.1.1 portable build was verified on Windows on 25 October 2026. The frozen
application passed all 18 checks in `scripts/accept_packaged.py`, then completed
one live ARAM: Mayhem game. Champion select and 17 augment offers were recognised;
three badges rendered, with no module errors. That live run used debug mode.

The published v1.1.3 portable ZIP was downloaded and checked again on 25 October
2026: its SHA-256 matched the published checksums, and all 18 packaged acceptance
checks passed. Its portable note still pointed to upstream; do not use that build
as the repaired v1.1.4 artifact.

The packaged checks cover:

- execution without Python on PATH and no modules loaded from the source checkout;
- Windows OCR and English application chrome;
- the real redacted fixture recognising IDs `2016`, `2138`, `2088` and rendering
  three ordered badges inside the game bounds;
- warmed-cache startup, no TCP connections with updates disabled, and cached data;
- the English startup crash dialog and missing-recognizer diagnostic.

## v1.1.4 release gate

Code candidate `1ba49e6`, rebuilt and checked on 25 October 2026:

| Gate | Result |
|---|---|
| Complete offscreen test suite | 622 passed |
| Traversal rejection and nested manifest filenames | Regression tests pass, including `..\..\evil.json` and `patches/16.21/normal/heroes.json` |
| Ordinary stats refresh | Pass; fresh-home run downloaded the real 16.21 pack, revision `d745511cb712`, 5,141,715 matches |
| Native Windows source fixture/self-test | Pass; English UI, correct three cards and three ordered in-bounds badges |
| Fresh local v1.1.4 portable build | Pass; unzipped note is English, points to this fork, and says to copy `userdata` into the new folder before deleting the old folder |
| Fresh v1.1.4 frozen acceptance | 18/18 passed, without Python on PATH |
| Independent security/privacy review | Approved; scoped re-review confirms safe portable upgrades, Windows OCR-pack notice and both-folder screenshot gate |
| Ordinary non-debug live game; `shots/` and `screenshots/` unchanged | Pending; snapshot names, sizes and modification times in both folders before launch and after the game; verify no `debug.txt` in the application or data directory |

This is not yet a release approval. No tag may be created until the remaining gates
pass on the final candidate. A revised candidate must be rebuilt and rechecked.

Local ZIP SHA-256:
`911fb2c60aa254871f2fb1d2e5ff740e0bd099a1737f276eb1351a60437a1c55`.
The frozen acceptance was rerun after the final code/portable-note corrections;
the earlier candidate's acceptance is not being reused.

These checks do not certify anti-cheat approval or every possible Windows/monitor
configuration. The executable is unsigned. Installed upgrades retain private settings
and cached data. For portable upgrades, extract the new ZIP beside the old folder,
copy the old `userdata` folder into the new one, then remove the old application folder.
The three old offer captures were deleted at the owner's request; older debug captures
in the separate `screenshots/` folder remain private and are not deleted by this repair.
