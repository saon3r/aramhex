# Augment item suggestions (1.1.1)

`hero_augment_items.json` is an optional data file. It must be listed in the public data
manifest's `files` with its SHA-256 and size. If the file is missing, the current champion has
no entry, or the entry is invalid, the panel is not shown at all — a generic item build is
never substituted in its place.

It is currently enabled for the three offered cards of **Sword of Blossoming Dawn** (3081).
The suggestion sits above the win-rate label rather than overlapping it, and only appears
while that card is on screen. It does not assume the player has built anything, and it does
not remember whether the card was taken. Suggestions use the all-ranks sample so that the
numbers are not thinned further by score bands.

The shape is `champion ID → augment ID → config`:

```json
{
  "17": {
    "3081": {
      "source": "community",
      "show_winrate": false,
      "items": [
        {"item": "4645"},
        {"item": "3135"}
      ]
    }
  }
}
```

This is a format example only. It is not a real recommendation for Teemo and must not be
shipped as live data.

- `source` is required: `stats` (derived from statistics), `community` (community
  recommendation) or `manual` (hand-written). The file is data, so it can be maintained and
  shipped with a routine data update without touching the program.
- `items` are displayed in the given order, up to three. Duplicate items are skipped. The
  client never re-sorts them by an unstable small-sample win rate.
- `item` is an item ID, including mode-specific IDs. Names and icons come from Riot's item
  metadata (Data Dragon, with CommunityDragon filling gaps). For an item that metadata does
  not know, you can supply `name`; it may then render as text only for a while.
- Each entry may carry integer `games` and `wins`, from which the client computes a win rate.
  Those samples must come from games where the champion held Sword of Blossoming Dawn — they
  must not be mixed with ordinary build statistics. End-of-game items cannot prove purchase
  order, so publish the methodology alongside the numbers.
- Win rates are optional. `show_winrate: false` on the config hides all of them; the same key
  on a single item hides just that one. With no win/loss data, show the items and invent
  nothing.
- Icons reuse the existing item cache and download in the background. The new panel region is
  registered in the capture-blocking list so the app cannot read its own text.

Online updates follow the existing path: the site's `.pack.xz`, then per-file fallback, with
every file in the manifest verified individually. Older clients download and verify the new
JSON, then ignore it, so it does not affect them. Nothing about the wire format or the server
changes here.
