# Changelog

## 1.0.0 - 2026-10-12

First release.

- One streaming pass over a `.rws` / `.rws.gz` save (stdlib expat, no tree):
  exact byte attribution per section (meta / game / world / maps), per map and
  per def, with every byte landing in exactly one section.
- Counters: things by def and by `Class`, thing comps by `Class`, floor items,
  filth, corpses, designations by def, world pawns split alive/dead and by
  faction, apparel and inventory items on world pawns.
- Mod attribution: the save's own load order drives a Defs scan of every
  installed mod it lists (Steam library discovery as the game does it);
  redefined defs go to the last writer; the six official content packs group
  as Vanilla.
- Six seed rules with counted numbers: world pawns over 800, floor items over
  20000, filth over 5000, apparel on dead pawns over 2000, any mod over 15% of
  save bytes, file over 150 MB.
- Terminal summary plus a self-contained HTML report (no scripts, no external
  assets) with the Top 25 defs by bytes, per-mod byte bars and the ranked fix
  list.
- Read-only proof: SHA-256 of the input printed before and after every run.
- `--json` emitting the same numbers as the HTML, `--out` to place the report,
  `--game` to point at the install, `--list` to list saves, and a
  double-click mode that asks which save to scan.
- A 400 MB synthetic save parses in ~17 s with peak RSS around 40 MB.
