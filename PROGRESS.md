# rimsave-xray progress

SHIPPED 2026-10-12. v1.3.0 is released and published:

- Repo: https://github.com/Booyaka101/rimsave-xray (main, all CI green on
  the tagged commit 0f20054)
- Release with the exe:
  https://github.com/Booyaka101/rimsave-xray/releases/tag/v1.3.0
- PyPI: https://pypi.org/project/rimsavexray/1.3.0/ (verified through
  /simple/ and a fresh-venv install that scanned a fixture)
- Cross-link: https://github.com/Booyaka101/rimbisect/pull/7 (green, left
  open for the owner to merge)

The first push exposed two tests that assumed this machine (a hardcoded
Windows path, and a summary-line test that needed a locally installed
game); both were made environment-independent before tagging. CI was
verified green on the exact tagged commit through the check-runs API.

State: v1.3.0. All 88 tests pass locally, including the 400 MB scale gate. Loops so far: 1.1.0 (span/gzip/cap bug fixes, Patches
attribution, double-click pause), 1.2.0 (component Class measurement,
steam-id folder fallback), 1.3.0 (component-share rule that caught a
1.69 MB trading manager on the first real modded save, determinism test,
verified 1.6 planet layers do not multiply <world> elements, drift checker
auto-discovers the install).

## Verified working (real runs, not unit claims)

- Scan of all three MIT demosave fixtures (1.3 saves): counts and byte
  attribution cross-checked against independent regex counts of the same
  files (Plant 11169, Filth 62, Human 1589091 bytes, world pawns 29/97).
- Scan of the owner's real saves: Autosave-1.rws (1.6.4850, 14 MB) and
  Tribe of Estian.rws (1.5.4297, 42.6 MB, 815 mods, 134 installed) in about
  1.6 s, including mod attribution against D:\SteamLibrary's install;
  15.0 MB attributed to mods, 3.6 MB across 117 defs unattributed (mods
  not installed or defs added by tools the Defs/Patches scan can't see).
- The exe (dist/exe/rimsavexray.exe, 1.1.0) run by bare save name next to
  the fixture: exit 0, report written, SHA-256 of input unchanged.
- Clean-path install: wheel built, installed into a fresh venv, scanned a
  fixture it had never seen.
- 400 MB synthetic save: parses in 17-42 s depending on disk warmth, peak
  process RSS 29 MB. The RSS measurement is real (OpenProcess +
  K32GetProcessMemoryInfo; the naive GetCurrentProcess pseudo-handle
  silently returns 0 on this box, which would have made the test pass
  vacuously).
- Screenshots in docs/ taken by driving Chrome over CDP against the real
  report HTML.

## Decisions worth knowing

- Byte attribution uses xml.parsers.expat directly, not
  ElementTree.iterparse: only expat's CurrentByteIndex gives exact element
  offsets. Start events point at the '<' of the start tag, end events at
  the '<' of the end tag (just past the element when self-closing); a test
  pins this contract. No tree is built; memory stays flat.
- Section spans are a contiguous partition (each section runs to the next
  section's start marker), so every byte lands somewhere and the sums are
  exact; tests assert sum(sections) == xml_bytes == file size.
- The player faction is identified by def-matching scenario/playerFaction/
  factionDef against each faction's loadID (Faction_<loadID> refs). The
  naive "faction def starts with Player" test fails on modded scenarios
  (the 1.3 fixture's player faction is AndroidTiers_PlayerColonyROM).
- modIds/modSteamIds/modNames are parallel lists: the i-th li of each
  belongs to mod i. Assigning by "last appended" silently corrupts every
  mod's name/steam id.
- ticksGame exists per colonist (colonistEvents/vals/li/ticksGame) in 1.5+
  saves; only tickManager's own copy is the game tick.
- Floor items = map things with a DIRECT stackCount child. Things inside
  containers (crates, frames) carry nested stackCounts and must not count.

## Owner's publish steps (from the phone)

1. Create the GitHub repo Booyaka101/rimsave-xray and push
   (git remote add origin ... ; git push -u origin main). CI runs on push.
2. Tag v1.0.0, create a GitHub Release, attach dist/exe/rimsavexray.exe
   (built here; CI also builds it as an artifact).
3. PyPI: py -m pip install build twine; py -m build; twine upload dist/*.
   Verify against /simple/ (the JSON API lags; LESSONS 2026-09-22).
4. Cross-link from rimbisect's README (see the suggested one-liner below).
5. First distribution step: reply in the Steam thread where save bloat
   comes up (600781777414405622) after CI is green, pointing at the exe.

Suggested rimbisect cross-link, one line under its See also / footer:
"rimsave-xray looks inside a save file instead of the running game: bytes
and lag counts per mod, read-only."

## Next steps if this is picked up again

- v2 items from the brief: guided cleanup with automatic backup, save
  folder drift chart across autosaves, opt-in anonymized per-mod footprint
  stats.
- Cache the defName index per mod folder (mtime-keyed) so a cold first run
  on a 200-mod install scans Defs faster; the thread pool already hides
  most of the disk latency.
- The CI scale job runs on ubuntu (tmpfs); if it ever flakes near 60 s,
  drop TARGET_BYTES to 300 MB rather than raising the budget.
