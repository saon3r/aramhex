# Privacy

AramHex is a personal, screen-reading overlay for League of Legends ARAM: Mayhem. This
document describes the current data behaviour, network scope and verification status.

## No telemetry, identity or remote control

The application does not:

- generate, store or transmit an install ID, usage statistic or account identifier;
- upload logs or diagnostic archives;
- fetch remote configuration, notices, community links, rollout flags or forced settings;
- look up a Riot ID / summoner rank;
- self-update, patch its own files or download OCR models (recognition uses Windows' own
  in-box OCR engine; nothing is downloaded or bundled for it);
- send cookies, identifiers or tracking headers that it creates itself.

Retired settings from older versions (`install_id`, `send_usage`, `logs_sent`,
`logs_tries`, rank fields and removed remote-control fields) are dropped when the local
settings file is loaded and are never written back.

## Local diagnostics only

Settings, logs, caches and optional debug screenshots are stored under `%APPDATA%\AramHex`
(installed build) or the application's `userdata` directory (portable build). They stay on
this machine. Diagnostic screenshots, including augment-offer captures, are produced only
when debug mode is explicitly enabled. They can contain player names or chat, so treat them
as private. Earlier builds also saved up to three offer captures during ordinary runs;
those existing files are not automatically deleted. Nothing in that local data is uploaded
by the application.

## Anonymous stats download

Statistics are downloaded with anonymous GET requests to the fixed stats routes. The
requests carry only a version User-Agent (for example `aramhex/1.1.1`); no install ID,
Cookie, Authorization header or per-player parameter is added. Every downloaded file is
verified against the manifest SHA-256; a failed refresh keeps the last valid cache and the
bundled fallback.

## Approved outbound scope

Runtime downloads are limited to anonymous GET requests for these purposes:

| Host and path | Purpose |
|---|---|
| `aramhex.com/u/data/` | stats manifest and stats payloads |
| `raw.githubusercontent.com/czgreat/aramhex-data/main/` | stats fallback |
| `ddragon.leagueoflegends.com/api/versions.json` and `/cdn/<version>/data/{en_US,en_GB}/{champion,item}.json` | version discovery and English champion/item metadata (the refresher currently requests `en_US`; the policy also admits the equivalent `en_GB` paths) |
| `ddragon.leagueoflegends.com/cdn/<version>/img/champion/…png` and `/img/item/…png` | champion portraits (cached) and on-demand item icons |
| `raw.communitydragon.org/…/global/default/v1/cherry-augments.json` | static augment metadata (name/rarity) only; no icons or splash art |

No other host is permitted by the runtime download policy. There are no POST/PUT requests and no
game-memory, injection or packet-capture access. Metadata and portraits are cached locally;
a failed or malformed refresh keeps the last valid cache and the bundled fallback.

## Migration status - do not overclaim

- Install ID, log upload, usage reporting, remote config/notices/rollout, Riot-ID rank
  lookup, self-update/patching, Korean OCR model download, Tencent static metadata
  (`game.gtimg.cn`, `mlol.qt.qq.com`) and the old fixed jsDelivr stats mirrors have been
  removed. Static metadata now comes from Data Dragon and CommunityDragon as listed above.
- Ordinary background refresh, both warm-cache and fresh bundled-only startup, real fixture
  OCR with three rendered badges, live champion-select/bench recognition and one full
  English-client game have all been verified through the real application entry point,
  including network-denied runs.
- The published v1.1.3 portable executable passed all 18 packaged acceptance checks on
  25 October 2026, including execution without Python on PATH, English UI, fixture OCR,
  three rendered badges, offline warm startup and the missing-recognizer diagnostic.
  A full live game with the packaged application was verified during the packaging
  milestone. See the [packaging verification record](docs/verification/packaging.md).
  A replacement release must pass fresh acceptance, including a normal (non-debug)
  game that creates no diagnostic screenshots, before it is published.

## Attribution and licence boundaries

- Application code: upstream [`czgreat/aramhex`](https://github.com/czgreat/aramhex),
  MIT licence; our changes remain under the same terms. See `LICENSE`.
- Statistics data: [`czgreat/aramhex-data`](https://github.com/czgreat/aramhex-data),
  CC BY-NC 4.0 — personal, non-commercial use with attribution. The stats are collected
  from the Chinese (CN) server and are labelled as such in the application.
- Third-party components and data notices are listed in `NOTICE.md`.
- This is a personal project and is not published; Riot's policy does not approve published
  augment win-rate overlays.
