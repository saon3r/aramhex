# Portrait source fixtures

Pinned public artwork used by `tests/test_portrait_sources.py` to prove that
`lolhex.vision.portraits.IconBank`, unchanged, matches **DataDragon** square portraits
against the **real client icons** the app already ships from CommunityDragon/CDragon.

This is a fixture/provenance baseline, not live acceptance. It does not prove champion
select or the live bench; no game screen is captured here.

## Layout

| Path | What it is |
|---|---|
| `source/<Alias>.png` | DataDragon 16.21.1 square champion portrait, downloaded once, verbatim |
| `client/<hero_id>_<Alias>.png` | The bundled CDragon 64×64 client icon, decoded verbatim from `lolhex/data/client_icons.json` and re-encoded as PNG |
| `manifest.json` | Exact URLs, versions, sizes, SHA-256 hashes, and the measured scores at bench 64/56 |

Hero IDs and English names come from bundled metadata (`lolhex/data/i18n.json` and the
`hero_icons.json` alias list): 17 Teemo, 103 Ahri, 35 Shaco, 77 Udyr, 120 Hecarim.

## Sources and attribution

- DataDragon: `https://ddragon.leagueoflegends.com/cdn/16.21.1/img/champion/<alias>.png`
  — anonymous plain GET on 2026-10-24, no cookies, no redirects, exact HTTPS host check.
- Client icons: `lolhex/data/client_icons.json`, itself built from
  `https://raw.communitydragon.org/latest/plugins/rcp-be-lol-game-data/global/default/v1/champion-icons`
  (shipped 2026-10-19). These are the game's own assets, not regenerated art.
- All images are Riot Games game assets. Personal, non-commercial use only; this
  repository is not published as an augment win-rate overlay.

No Tencent hosts were contacted for this fixture; no user data, settings, config or
gameplay capture is involved.

## What the tests measure

With an `IconBank` built from **only** the five `source/` squares:

- every `client/` crop is classified as its own hero at bench sizes 64 and 56;
- scores are 0.976–0.994 and lead the runner-up by 0.48–0.71 (well over
  `MIN_SCORE` 0.75 and `MIN_MARGIN` 0.10);
- a flat/blank slot abstains.

With `IconBank` built from the bundled Tencent references (`hero_icons()`) and probed with
the bundled client icons (`client_icons()`), all 173 heroes: 165 correct, 8 abstain,
**0 wrong** — the cross-source regression recon measured. This is the independent result;
the combined Tencent+client bank's 173/173 is self-match fallback coverage and is
labelled as such, not as accuracy.

## Regenerating

Re-download the five URLs above with a fresh anonymous session, no redirects, and verify
the host is exactly `ddragon.leagueoflegends.com`. Re-decode the client crops from the
current `client_icons.json`. Then update every hash and measured score in `manifest.json`.
Fixture drift is meant to fail the provenance test loudly.
