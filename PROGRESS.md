# rimsave-xray progress

## 1.4.1 review loop, same day: what the loop found and fixed

Review findings, all verified by measurement:

- BYTE-IDENTITY (bug, fixed): the 1.4.0 report-template insertion left one
  stray blank line in the HTML of every save, including 1.6 and older. The
  template now yields byte-for-byte the 1.3.0 HTML and summary for old
  saves, proven by building both from git HEAD and the tree on the demosave
  fixture and comparing (the byteidentity script in .scratch/ui).
- ALL-DEPTHS STRUCTURAL DIFF (record extended): the depth-2/3 identity proof
  covered section names only. Re-running the element-name diff at EVERY
  depth across the old corpus (three 1.3 demosaves, Autosave-1/2, and the
  1.5 815-mod save) versus the two 1.7 fixtures: only five names appear
  solely in 1.7, and four of them (attackTarget, curPathJobIsStale,
  selectedTarget, sourcePawn) are transient pawn/job fields the 1.6
  assembly already declares (content variance, not format change). The
  fifth, wakeUpIfColonistClose, is genuinely new (a CompCanBeDormant field,
  absent from the 1.6 assembly) and lives inside a thing, where the
  scanner measures it with its thing. Nothing structural changed at any
  depth; the 776 old-only names are all mod data from the modded corpus.
- VOCABULARY RE-MEASURED: the KNOWN set now proven against all seven
  pre-1.7 saves available locally - the union is exactly the shipped set,
  nothing outside it, nothing in it unobserved.
- MIGRATION DRIFT, MEASURED WITH OUR OWN TOOL (worth keeping): running
  save-drift-check.py on the original 1.6 Autosave-1 versus the migrated
  1.7 fixture shows the migration shed 18.85% of the save (2.66 MB), 6,747
  map things, dominated by Plant_Grass (-900 KB), Filth_RubbleRock
  (-386 KB) and Plant_TallGrass (-316 KB), consistent with the
  "Collection was modified" map-save exception the game logged during the
  migration re-save. That is the real cost players pay migrating a modded
  save while their mods fail on 1.7.
- Missing test coverage added: the unmapped-block surfaces (summary line,
  HTML table, ordering, absence for clean saves) and determinism on both
  1.7 fixtures. drift-check budget line reworded for shrinkage.

## 1.4.0 shipped 2026-10-13: RimWorld 1.7 (Waylith) save support

State: complete. 104 tests pass locally (including the 400 MB scale gate and
nine new fixture-driven 1.7 tests). The wheel installs into a clean venv and
scans the 1.7 fixtures. The repo working tree holds the release changes,
uncommitted (the owner commits and tags from the phone, as with 1.3.0).

What shipped:

- The two real 1.7 fixtures, made on this machine from the unstable-branch
  install (build 1.7.4976 rev1043):
  `tests/fixtures/waylith new colony.rws.gz` (fresh colony generated and
  saved in 1.7, vanilla loadout, 41,267 map things) and
  `tests/fixtures/waylith migrated save.rws.gz` (the owner's real 1.6.4850
  Autosave-1 loaded into 1.7 and re-saved; ticks 660013 and the 8-mod loadout
  carried over; Harmony and Convergence both failed to initialize on 1.7
  during that load, which is the migration path players actually hit).
- The structural record, measured with a whole-file element walk:
  1.6 Autosave-1, 1.7 new, and 1.7 migrated have IDENTICAL structure - same
  root with no attributes, same meta fields (gameVersion, modIds,
  modSteamIds, modNames), the same 35 children of <game>, the same tail
  element order, line endings and indentation. Waylith 1.7 changed the save
  format NOT AT ALL; the only difference is the gameVersion value. This
  matches Ludeon's "1.6 saves load on 1.7 and vice versa" claim.
- Version-gated unmapped-block surfacing: for 1.7+ saves, any structural
  block outside the vocabulary measured on real saves back to 1.3 is
  reported ("new in 1.7 - not yet mapped", element name, count, byte weight)
  in the summary, HTML report and --json. 1.6-and-older output is unchanged
  byte for byte (test-pinned).
- discover.py accepts the Waylith exe name (RimWorld.exe) alongside
  RimWorldWin64.exe; without this, mod attribution could not find the 1.7
  install.

How the fixtures were actually made (the whole trail, for whoever comes
back to this): the Steam client was signed in behind its Family View
startup PIN (owner unlocked it over TeamViewer mid-session; see the session
log). Two agents were using this machine's game at once, and RimWorld kills
the older instance when a second launches, so interactive menu driving kept
dying. The working path was fully headless: a temporary mod
(xrayfixtures, source in .scratch/xrayfixtures, deployed to the game's Mods
folder and removed afterward) whose watcher thread saves the game through
GameDataSaveLoader.SaveGame and quits via Root.Shutdown, combined with two
engine features read off the decompiled 1.7 assemblies: `-quicktest`
(generates a new colony without any UI) and dev mode's autostart save
(a save named "autostart" in the Saves folder is loaded automatically at
startup). Each fixture capture took under 20 seconds. Facts worth keeping:
two RimWorld instances starting together leave the younger one with a 0x0
resolution AccessViolation and a per-frame error loop that wrote a 10 GB
Player.log before it was killed; the game must be launched exclusively.

Machine state left behind: Steam running, signed in, RimWorld on the
unstable branch (the owner switched it deliberately; switch back via
RimWorld Properties -> Betas when 1.7 hits main). The temporary
xrayfixtures mod is removed from the install. The owner's real
Autosave-1.rws is untouched (hash-checked). The .scratch/w17c sandbox holds
the fixture originals plus autostart.rws. Chrome tabs were restored.
Backups (appmanifest, ModsConfig, Prefs) remain in the temp backup folder.

Left for the owner (their voice, not mine): the release post. This one has
a natural first step: a reply in the same Steam thread used for 1.3.0
(steamcommunity.com/app/294100/discussions/0/600781777414405622), noting
1.7 saves scan as of today's unstable build.

## Verified working (real runs, not unit claims)

- rimsavexray on both 1.7 fixtures: full summary, exact byte partition
  (sum(sections) == xml_bytes == gunzipped size), read-only SHA-256 before
  and after identical, exit 0. Output pasted in the session log.
- rimsavexray on demosave 1 (1.3): identical numbers to the 1.3.0 release
  output (135 mods, 15535 things, 126 world pawns, Human 1,589,091 bytes).
- Clean venv wheel install: rimsavexray 1.4.0 --version, scans the
  migrated fixture.
- 104/104 tests green (`py -m pytest`).

## Next steps if this is picked up again

- When 1.7 stabilizes toward main, re-run the structural diff against a
  newer build: if anything new appears, it lands in the unmapped-block
  report automatically; promote real block names into the vocabulary only
  after measuring what they hold.
- v2 items from the original brief are still open: guided cleanup with
  automatic backup, save folder drift chart, opt-in anonymized per-mod
  footprint stats.

## Earlier releases

SHIPPED 2026-10-12. v1.3.0 is released and published:

- Repo: https://github.com/Booyaka101/rimsave-xray (main, all CI green on
  the tagged commit 0f20054 and on every commit since; topics set:
  rimworld, rimworld-mod, save-file, performance, profiler, save-bloat)
- Release with the exe:
  https://github.com/Booyaka101/rimsave-xray/releases/tag/v1.3.0
- PyPI: https://pypi.org/project/rimsavexray/1.3.0/ (verified through
  /simple/ and a fresh-venv install that scanned a fixture)
- Cross-link: rimbisect PR #7 merged (squash, 14ebc3a); both repos now
  point at each other

Loops so far: 1.1.0 (span/gzip/cap bug fixes, Patches attribution,
double-click pause), 1.2.0 (component Class measurement, steam-id folder
fallback), 1.3.0 (component-share rule that caught a 1.69 MB trading
manager on the first real modded save, determinism test, verified 1.6
planet layers do not multiply <world> elements, drift checker
auto-discovers the install), 1.4.0 (1.7 Waylith support above).
