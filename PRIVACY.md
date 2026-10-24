# Privacy

AramHex is a personal, screen-reading overlay for League of Legends ARAM: Mayhem. This
document describes the current data behaviour and the final intended network scope. It is
deliberately explicit about what is **not yet migrated**.

## No telemetry, identity or remote control

The application does not:

- generate, store or transmit an install ID, usage statistic or account identifier;
- upload logs or diagnostic archives;
- fetch remote configuration, notices, community links, rollout flags or forced settings;
- look up a Riot ID / summoner rank;
- self-update, patch its own files or download OCR language models;
- send cookies, identifiers or tracking headers that it creates itself.

Retired settings from older versions (`install_id`, `send_usage`, `logs_sent`,
`logs_tries`, rank fields and removed remote-control fields) are dropped when the local
settings file is loaded and are never written back.

## Local diagnostics only

Settings, logs, caches and optional debug screenshots are stored under `%APPDATA%\AramHex`
(installed build) or the application's `userdata` directory (portable build). They stay on
this machine. Debug screenshots are produced only when debug mode is explicitly enabled.
Nothing in that local data is uploaded by the application.

## Anonymous stats download

Statistics are downloaded with anonymous GET requests to the fixed stats routes. The
requests carry only a version User-Agent (for example `aramhex/1.1.1`); no install ID,
Cookie, Authorization header or per-player parameter is added. Every downloaded file is
verified against the manifest SHA-256; a failed refresh keeps the last valid cache and the
bundled fallback.

## Final intended outbound scope

Only anonymous GET requests for the following purposes are intended to remain:

| Host | Purpose |
|---|---|
| `aramhex.com/u/data/` | stats manifest and stats payloads |
| `raw.githubusercontent.com/czgreat/aramhex-data/` | stats fallback |
| `ddragon.leagueoflegends.com` | champion/item metadata and icons |
| `raw.communitydragon.org` | static augment metadata and icons |

No other host is intended to be contacted by the final build. There are no POST/PUT
requests and no game-memory, injection or packet-capture access.

## Migration status — do not overclaim

- Install ID, log upload, usage reporting, remote config/notices/rollout, Riot-ID rank
  lookup, self-update/patching and Korean OCR model download have been removed.
- **Still present temporarily:** Tencent static metadata fetches
  (`game.gtimg.cn`, `mlol.qt.qq.com`) and fixed jsDelivr stats mirrors. Those are being
  removed/reviewed in the ongoing Tasks 3–4; this document describes the final target, not
  a claim that every host above is already the only one contacted.
- Offline and network-blocked startup have **not** yet been verified in the real build; that
  acceptance remains open in Task 9.

## Attribution and licence boundaries

- Application code: upstream [`czgreat/aramhex`](https://github.com/czgreat/aramhex),
  MIT licence; our changes remain under the same terms. See `LICENSE`.
- Statistics data: [`czgreat/aramhex-data`](https://github.com/czgreat/aramhex-data),
  CC BY-NC 4.0 — personal, non-commercial use with attribution. The stats are collected
  from the Chinese (CN) server and are labelled as such in the application.
- Third-party components and data notices are listed in `NOTICE.md`.
- This is a personal project and is not published; Riot's policy does not approve published
  augment win-rate overlays.
