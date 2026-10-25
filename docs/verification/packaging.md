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

Pending fresh verification. A tag must not be created until the repaired build has
passed the suite, a real stats refresh, unpacked portable-note inspection, all 18
packaged checks, and an ordinary non-debug game with the previously emptied
`%APPDATA%\AramHex\shots` directory unchanged.

These checks do not certify anti-cheat approval or every possible Windows/monitor
configuration. The executable is unsigned. Existing private settings and cached
data are retained; the three old offer captures were deleted at the owner's request.
