# Changelog

## 1.4.1 - 2026-10-13

Review loop over 1.4.0.

- Byte-identity proof: the HTML report and terminal summary for a 1.6-and-
  older save are now verified byte-for-byte identical to the 1.3.0 output
  (the report template restructure had left one stray blank line; fixed).
- The structural record now covers every depth, not just the section level:
  across the 1.3-1.6 corpus (seven real saves) versus the two 1.7 fixtures,
  the only genuinely new serialized field anywhere is wakeUpIfColonistClose
  (a CompCanBeDormant field, absent from the 1.6 assembly); the four other
  new-to-the-corpus names are transient pawn state the 1.6 engine already
  had. Nothing structural changed at any depth.
- The 1.7 structural vocabulary is re-measured against all seven pre-1.7
  saves (three 1.3 demosaves, three real 1.6 autosaves, one real 1.5 save
  with 815 mods): the union is exactly the shipped known-set, both ways.
- New tests: the unmapped-block report surfaces (summary line, HTML table,
  biggest-first ordering, absence for clean saves) and scan determinism on
  both 1.7 fixtures.
- save-drift-check.py states its budget line as a growth budget, so a save
  that shrank reads "within budget (XML -18.85% vs a 5% growth budget)"
  instead of the ambiguous old wording.

## 1.4.0 - 2026-10-13

RimWorld 1.7 (Waylith) save support.

- 1.7 saves scan natively. Two real fixtures from the 1.7 unstable install
  (build 1.7.4976) now pin this in the test suite: a brand-new colony saved
  in 1.7, and the owner's actual 1.6 save loaded into 1.7 and re-saved there
  (with two of its mods failing on 1.7, the migration path players hit).
  Both parse with exact byte partitioning and no version errors.
- The structural record, measured on those fixtures: 1.7 writes the same XML
  shape as 1.6 - same root, same meta fields, the same 35 game sections,
  same line-ending and layout conventions. No save-format changes to map.
- Any structural block a future 1.7 build adds outside the vocabulary
  measured on real saves back to 1.3 is now surfaced in the summary, report
  and --json as "new in 1.7 - not yet mapped" with its element name and byte
  weight, instead of being silently dropped. Saves from 1.6 and older are
  reported exactly as before; nothing about their output changes.
- Install discovery accepts the Waylith exe name (RimWorld.exe) alongside
  RimWorldWin64.exe, so mod attribution keeps working on 1.7 installs.

## 1.3.0 - 2026-10-12

Third review loop.

- New rule: one component Class holding over 3% of the save bytes names the
  component and its share ("Component VanillaTradingExpanded.TradingManager
  holds 1.6 MB (3.8% of the save)"). On the first real modded save it ran
  against, this caught a trading manager nobody could see in the thing
  counters.
- Scans are now pinned deterministic by a test: two passes over one file
  produce identical results.
- Verified RimWorld 1.6 planet layers live in a layers dict under game, not
  as extra <world> elements, so section attribution stays exact on Odyssey
  saves.
- examples/save-drift-check.py finds the install through Steam like the main
  CLI when --game is not given, and attributes mod drift without being
  asked twice.

## 1.2.0 - 2026-10-12

Second review loop.

- Game, world and map components are now measured: count and exact bytes per
  Class, in the report and in --json. This is where a mod's save data hides
  when it is not things (on a real 815-mod save it surfaced a 1.69 MB
  trading manager nobody could see before).
- Mods whose About.xml packageId no longer matches the save's modId (renamed
  or forked mods) attribute again when their folder is named for the
  Workshop id, which is how Steam lays them out.
- The report's mod table shows one collapsed row for the save's not-installed
  mods instead of hiding them, with the "(unattributed: mod folder not
  found)" wording.
- examples/save-drift-check.py gained a components-movers section (it caught
  a co-op mod's overseer component growing 732 bytes a day on a real save)
  and lost a dead variable and a docstring lie about an exit code.

## 1.1.0 - 2026-10-12

Review pass over 1.0.0.

- Defs a mod inserts or rewrites through Patches/*.xml now attribute to that
  mod (a PatchOperationAdd's `<value>` holding a `<defName>` defines it);
  xpath selectors quoting `defName="X"` were and stay references, not defs.
- The terminal summary names the top three mods by bytes and the count of
  defs no installed mod defines.
- The double-clicked exe now holds its window open ("Press Enter to close")
  after scanning or failing; launches with arguments exit as before.
- examples/save-drift-check.py: compare two saves of one colony (sections,
  counters, biggest def movers, per-mod drift) with a growth budget for
  use as a playtest/CI gate while building mods.
- A gzip save cut off mid-stream is now a message ("truncated or corrupt,
  try the previous autosave") instead of an EOFError traceback.
- Text capture inside one leaf is capped by total length, not by callback
  count, so a pathological value cannot balloon memory past the cap.

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
