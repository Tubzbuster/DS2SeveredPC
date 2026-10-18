# In-game progress

A working list of how far Severed plays on PC, area by area, filled in as we
play through it together. Each test run updates it.

Status: **works**, **partial** (playable, with problems listed),
**broken** (blocks progress), **fix pending** (a fix is pushed and waiting
for a test), **untested**.

Section names are the level's stream folders
(`pdlc1_ch01_mng\pdlc1_ch01_mng\<area>\<section>`). The order follows the
scene and audio numbering (`igc_01_xx` = chapter 1, `igc_02_xx` = chapter 2)
and is corrected as we play.

## Summary (2026-10-18, v0.8.5, first full release)

**Where we are:** Severed is fully playable on PC, start to finish: all of
chapter 1 and chapter 2, the final fight, the last stand, the ending video,
the end screens and the credits (first full play-through, probe 50 log).
What is left are minor issues, listed under Open bugs; none blocks the game.

**Fixed so far** (confirmed in game unless marked):
- Severed in Episode Select; intro terminal, RIG call scene, hand-over
- level geometry, collision, lighting; quarry colour grading (black screen)
- Necromorph AI (navmesh checksums)
- dialogue, audio logs, videos, 5.1 cutscene audio; music and ambience
  streams play
- saving and loading
- Gabe's Pulse Rifle upgrades
- the quarry door drawn solid black
- suit packs removed from the stores (choosing one crashed)
- crash at the docking station (gunship vertex buffer index)
- black screen after the gunship scene (chapter 2 opening)
- gunship hull textures (built from the PC game's own mesh)
- crash entering the decompression room (looping sounds split)
- the gift shop's strobing lights (calmed)
- black shapes and slabs across the hospital, and the zero-oxygen hallway's
  black box and beige windows (vertex positions, FINDINGS 59)
- the installer app: converts, installs the hook, removes everything again

**Tests waiting on you:**
1. Release hook (56, the slimmed-down DLL in v0.8.5): Severed in the
   episode select, the Pulse Rifle upgrades on a new game, and the ending
   going straight back to the main menu with no New Game+ popup or New
   Unlocks screen (log: `end of game: Severed - back to the main menu`).

**Reported in the replay (new game):**
- ~~Gabe floats above the gunship after the docking transition (again,
  from the dock checkpoint)~~ fixed and confirmed: the landing waits for
  its voice stream, which never loaded when the gunship was killed during
  Gabe's second radio log; the cutscene audio is now preloaded with the
  next radio log instead (`gunship_audio.ok`, FINDINGS 52). Earlier:
  caused by the chapter 16 numbering (FINDINGS 52). Chapters stay 1 and 2
  for good. Saves made with the chapter 16 build need `player_set_chapter_1`
  sent once with F7 (`severed_send.txt`), confirmed working.
- hanging fight drop: releasing the hanging state early (`hang_drop2.ok`)
  flipped Gabe upright and the drop animation took him into the ceiling.
  Back to the console's flow (`hang_console.ok`); the fall is now looked
  for in the animation (FINDINGS 48)
- black stretched shapes in several hospital rooms: the hallway's box is
  the scratched-metal wall panels shaded black (lightmap-shader material);
  probe 46 trace pending.
  Seen again in the operating theatre (`surgery_pit_z01`): a large dark
  slab in front of a pickup. Material links, vertex colour and table data
  checked and ruled out (FINDINGS 58); the probe trace can be taken there
  as well as in the hallway.
  **Fixed and confirmed** across the whole hospital: found by comparing
  with the base game's own hallway: vertex positions left half-converted
  (some words read as text), 173 words in 17 meshes, most in the hospital
  (FINDINGS 59). Step `mesh_positions.ok`.
- ~~bodies in the drill tunnel move during the opening scene~~ fixed and
  confirmed: both get "Freeze on limp" (`corpse_freeze.ok`, FINDINGS 56).
  They stay put through the scene and react to shots and stomps. (No body
  is on a spike, on the console either.)
- ~~the clinic overlook room's reflections are sideways~~ not a bug: the
  base game's chapter 1 clinic window (same glass files) looks the same on
  PC (FINDINGS 57).

**Open bugs** (strike out any that are no longer bugs):
- ~~crash entering the decompression room~~ fixed (looping sound split)
- ~~black shape and flat beige windows in the zero-oxygen hallway~~ fixed
  and confirmed: vertices thrown far off by half-converted positions
  (`mesh_positions.ok`, FINDINGS 59); the windows look right since too
- ~~Gabe does not drop to the floor after the hanging fight~~ fixed and
  confirmed (consistent over several runs): gravity on during the drop, hanging
  spot moved 0.35 m, the door started 2 s after the drop (FINDINGS 48)
- ~~thump in the opening scene~~ fixed and confirmed: gone since the
  drill tunnel's two bodies hold still (`corpse_freeze`, FINDINGS 56)
- ~~final fight sometimes does not end~~ fixed and confirmed: the Oracle
  corpses hold their pose for the Infectors (`oracle_corpses.ok`,
  FINDINGS 62)
- ~~end screens show their texts at once, overlaid~~ fixed and confirmed
  (`vfx_headers.ok`, FINDINGS 63)
- a pale see-through sheet under the Oracle corpses (still there with the
  PC game's Oracle mesh)
- ~~Gabe's legs come back for the last seconds after the four fuses~~
  not a bug: the console footage shows his legs in that shot too
  (FINDINGS 63)
- ~~after the ending video the room shows for about 3 s~~ fixed and
  confirmed: the camera moves into the RIG screen and fades to black
- the end-of-game "save for New Game+" message and the New Unlocks
  screen: Severed has no New Game+ (console footage goes straight to the
  main menu); probe 55 skips both (FINDINGS 65)
- save station lock-up: happens when the terminal is used again during
  its closing animation
- Twitchers stunlocking Gabe (not reproduced since)
- frame drops near some lights in the drill tunnel

**No longer bugs** (confirmed by the user): the stretched slabs after the
intro terminal, the alt-tab hang, the gunship hull textures. The Pulse
Rifle grip (a misread on screen, the rifle is held properly).

**For the full release** (not bugs): Severed saves still show the base
game's "Chapter 1"/"Chapter 2" titles and pictures, as decided: giving
them their own broke more than it was worth (the chapter 16 numbering,
FINDINGS 52). To try again with the release hook (see To do for a
release).

**To double-check sometime** (notes, not counted as bugs):
- quarry Twitchers seemed not to take hits while climbing out of their
  vents (shots went through). May be normal: their character files
  (model, `twitcher.rcb`, `slashersecurity.hkx`, animation banks) are the
  PC game's own, and enemies may not be hittable mid-climb in the base
  game either. When convenient: can they be hit once they have landed,
  and can the base game's Twitchers (Government Sector) be shot while
  climbing out of a vent? The vents are VentMarker objects in
  `pdlc1_ch01_mng.str`.

## Start-up

| Step | Status | Notes |
|---|---|---|
| Building the test archive (`Make-SeveredTest.bat`) | works | |
| Severed in Single Player > New Game > Episode Select | works | via the probe DLL |
| Level loads (no black void, no crash) | works | |
| Intro terminal ("Primary mission assets", RIG call video, dialogue) | works | |
| Gabe on the ground, RIG call scene, getting up | works | since probe 23 stopped loading a second copy of the level data |
| Control handed back after the scene | works | no F8 needed |

## Chapter 1: the mines

| Area / sections | Status | Notes |
|---|---|---|
| drill_tunnel: drill_tunnel_01, drill_tunnel_02 | works | the thump in the opening scene is gone since the two bodies hold still ("Freeze on limp", `corpse_freeze`, FINDINGS 56); confirmed by the user |
| drill_tunnel: drill_cavern_01 | partial | Flamethrower picked up without a crash once the PC game's own assets were used |
| drill_tunnel: drill_saferoom | works | door, bench, store, save station (second use of the save station locked up in an earlier run: recheck) |
| bomb_run: grinder_hall_z01/z02, grinder_room | works | |
| bomb_run: quarry_entrance, quarry_z01/z02, escape_hall | works | loads and plays (probe 31, and no `D3D GUARD` lines since the LUT fix). Price's scene and attack, the override switch, the door encounter and the cargo lift all work. The black screen when the quarry door opened is fixed (colour-grading LUTs, FINDINGS 45). The door that drew as a solid black slab (`door_inner_01_am`) is fixed and confirmed (20-byte UV streams, FINDINGS 46) |
| mining_camp: mining_camp_hall, mining_camp01/02, mining_camp_z01 | works | played through to the docking station. The upside-down tentacle grab after the lift plays; pressing stomp during it put Gabe inside the ceiling (he got out once the animation ended). The quarantine lockdown with 3 override terminals starts. Died there: Twitchers sometimes repeat the same attack and stunlock Gabe in a damage loop |
| elevator: elevator_hall, elevator_z01-z03, elevator_shaft_04-12 | works | played through on the way to the docking station, elevator crash scenes included (`ses_player_01_02`, `01_03`) |
| docking_station: docking_airlock_01, docking_station_z01/z02 | works | the gunship fight, destroying it and boarding work (FINDINGS 47). The smeared hull textures: Severed's `exterior_black_win` is the base game's gunship hull with another window material; it is now built from the PC game's own `exterior.dae` with that material (`pcassets.DERIVED`, step `gunship_hull.ok`, FINDINGS 51); confirmed |
| chapter 1 -> 2 transition (emergency_arrival) | works | confirmed: the crash-landing scene, its dialogue and the Chapter 2 title play (FINDINGS 49). A side-by-side screenshot with console footage at the psych ward line matches |
| emergency / psych ward: Tormentor fight, airless hallway | works | the Tormentor boss fight works; the flat black shape in the zero-oxygen hallway is fixed and confirmed (vertex positions, `mesh_positions.ok`, FINDINGS 59) |
| decompression room | works | confirmed passed in two runs. Was: crashed on entering (doors open, light supports destroyed): audio thread, exe 0x515F0F, the sample decoder (0x515EE0) read a block through a null pointer (voice +0x34). Severed's sound banks are the only XAS bank samples the PC plays (its own banks are all EALayer3). Probe 39 dumps the voice and the sample header at this crash |

## Chapter 2: the hospital

| Area / sections | Status | Notes |
|---|---|---|
| emergency: emergency_arrival_z01, emergency_arrival_hall_z01, storage_z01, hacking_room_z01 | works | crash landing, Tormentor fight |
| emergency: decompression_z01, decom_hall_z01, airless_hall_z01, vista_sprawl_z01/z03 | works | decompression crash fixed; gift shop lights calmed (confirmed); the zero-oxygen hallway's black box and beige windows fixed and confirmed (FINDINGS 59) |
| trauma: elevator_morgue_z01, morgue_z01, morgue_hall_z01-z03, triage_z01, triage_hall_z01 | works | passed; the black shapes are fixed and confirmed (FINDINGS 59) |
| hospital_entrance: lower_lobby_z01/z02, upper_lobby_z01/z02, reception_z01 | works | passed; the black shapes are fixed and confirmed |
| upper_corridors: patient_hall_z02-z05, patient_z01/z02, store_room_z01, surgery_lobby_z01 | works | passed; the black shapes are fixed and confirmed |
| surgery_ward: decontamination_z01, surgery_z01, surgery_hall_z01, surgery_observation_z01, surgery_pit_z01, elev_surg_pit_z01 | works | passed; black slabs fixed and confirmed; the slanted reflections in the clinic overlook window match the base game on PC |
| recreation: elevator_recreation_hall, recreation_hall_z01-z03, recreation_z01/z02, elevator_rec_z01/z02 | works | passed |
| observation: observation_z01, observation_hall_z01, psycho_development_z01 | works | passed; scene `igc_02_01` (Lexine, the Oracle, the captain) plays |
| psych_ward: psych_hall_z01/z03/z04, chase_hall_saferoom_z01 | works | passed |
| security: security_z01, security_hall_z01; psych_ward: isaacs_cell_z01 | works | passed |
| chase_hall: chase_hall_z01/z02; psych_ward: psych_arrival_hall_z01 | works | passed |
| psych_ward: landing_bay_psycho_z01/z02 | works | the final battle, the final cutscene (camera, FINDINGS 60), the Infectors and Oracle Twitchers fight (crash fixed, FINDINGS 61; corpses held for the Infectors, FINDINGS 62), the final hack, Bartlett's grenade, the last stand and the four fuses, the decompression and the ending video all play. Open: legs back after the fuses, the room after the video, a pale sheet under the corpses |
| Also in the DLC: entry_hall, pre_moonquake | works | played in chapter 1 (mining camp to the docking station) |
| End of the DLC (end screens, credits) | works, issues | the credits play and the game returns to the main menu. End screens fixed (FINDINGS 63); no New Game+ popup or unlocks, as on the console (probe 55, FINDINGS 65) | |

## Systems

| System | Status | Notes |
|---|---|---|
| Level geometry, lighting, collision | works | up to the final boss; the hospital's black shapes fixed (FINDINGS 59) |
| Gabe (security suit) | works | |
| HUD, menus, inventory screen | works | |
| Subtitles | works | |
| Dialogue and audio logs (stereo streams) | works | |
| Cutscene audio (5.1 streams) | works | stereo downmix |
| RIG health spine | works | since the PC game's own RIG bar meshes are used |
| Starting equipment (`equip_command_player_initial`) | works | Pulse Rifle, Seeker Rifle, ammo; 50,000 credits (to compare with the console) |
| Gabe's Pulse Rifle upgrades | works | probe 34: `10 node(s) set, 0 missing`; the user confirmed the upgraded rifle in game. RIG upgrades not looked at yet |
| Twitchers | not reproduced since | parked by the user; previously: one Twitcher alone keeps Gabe in his flinch: each slash lands before the flinch ends (Normal and Casual; no grab). Their `Zombie` settings differ from the slashers' in an authored way (pain interrupt delays 4/2 s, dodge 0.9, turn speeds doubled, 8 damage per hit), nothing that looks like a conversion error. Next: A/B against the base game's own Twitchers (Government Sector) on the same PC, and a 60 fps cap test (the user plays at 75 fps with external V-Sync) |
| Scripted hang after the cargo lift | works | Gabe drops to the grate, gets up and runs through the door (two runs, a third to come): gravity on during `ses_player_01_03`, hanging spot moved 0.35 m, the door's sequence started 2 s after the drop (FINDINGS 48) |
| Weapons: Flamethrower pickup | works | |
| Weapons, kinesis | works | |
| Weapon in Gabe's hands | works | the Pulse Rifle looked off once; the user confirmed it was a misread, all weapons are held properly |
| Necromorph AI | works | navmesh checksums recomputed (the game had rejected every converted navmesh) |
| Crash in the quarry | works | fixed by the LUT conversion; probe 31 stays as a safety net |
| Save stations | partial | saving and loading a save work; using the terminal again during its closing animation locks it up; saves are listed as "Chapter 1" and so get chapter 1's picture in the load menu (the PC picks it from a `ch01`-`ch15` table by chapter number). On console the load menu shows "Severed, chapter N" with its own picture (Gabe in a corridor, from footage); Severed's files hold only the two 64x64 Xbox dashboard icons (`weller1_ch1/ch2.png`), so that picture is probably in a front-end file still to find |
| Stores, benches | works | confirmed: no suits in the store on a new save (saves made before the rebuild keep them). Severed's store lists held Gabe versions of the suit packs (Advanced, Quick Draw, EarthGov, Brushed Aluminium, Bloody, ...); choosing one crashed the game (a suit model part not loaded). The converter now leaves those 10 suits out of the stores (`simgroup.STORE_HIDDEN`, step `store_suits.ok`); Gabe's starting suit stays |
| Performance near some lights | partial | frame drops in the drill tunnel |
| Overall brightness | works | confirmed by the user after the LUT fix: the darkness was only the quarry's colour grading (FINDINGS 45). Lighting data audit in FINDINGS 44 |
| Gabe's pain sounds | works | Isaac's grunts and damage lines, as on console (the DLC reuses them) |
| First view after the terminal | works | the stretched slabs are gone (confirmed) |
| Menu text (localised episode name) | partial | English placeholder via the probe |

## Test tools

- F7: sends the messages listed in `severed_send.txt` (ignored with Alt,
  Ctrl or Shift held). Probe 49 keeps only F7: F8 (intro hand-over), F9
  (start sections, episode list) and F10/F11 (scans) are retired, their
  jobs confirmed working; F3-F6 went in probe 48. Wrong surfaces are now
  looked into by comparing with the base game's own files for the area
  (`tools/research/extract_base_sections.py`, FINDINGS 59), not with draw
  hooks.
- Crash reports name the meshes near the crash (probe 21+).
- Probe 26+: heap checks every 2 s (`HEAP ... CORRUPT` lines). Probe 35: off unless `severed_heapcheck.on` is in the game folder (suspected of the alt-tab hang).
- Probe 36: `SES` lines: each scripted sequence's name hash, settings flags and origin once; sequences with SSEQFL_NEGATE_CHAR_PROXY_OFFSET every 250 ms with the hanging proxy offset they subtract (FINDINGS 48).
- Probe 37: the scripted sequence hook retries for 10 s (it missed about half of the runs before).
- Probe 39: at a crash in the sample decoder (exe+0x115F0F), dumps the voice and the sample's EA header.
- Probe 38: `SES` lines only when a sequence's anchor or offset changes (probe 37 hit the 600-line cap in the opening scene).
- Probe 30+: `severed_novtf.on` (empty file in the game folder) unbinds
  vertex textures before dynamic-geometry draws; an experiment for the
  quarry crash.
- Probe 33+: `MSG <hash>` lines: the first 3 sends of each level message,
  flagged when nobody listens (dropped). Hashes are sdbm of the message
  name.
- Probe 27+: Direct3D guard (`D3D GUARD` lines); crash reports list the
  bound textures and who set them.

## To do for a release

- **Installer app:** a small window that asks for:
  - A) the Xbox 360 Severed add-on file, or the unpacked add-on folder;
  - B) the Dead Space 2 PC folder (retail or Steam).

  Each box has a Browse button. The app then runs the conversion that
  `Make-SeveredTest.bat` does now.

  No Python install is needed: the converter uses only Python's standard
  library (plus our `xasenc.dll` and ffmpeg), so the app is the converter
  packed with its own Python by PyInstaller, with a tkinter window. Build
  it as a folder (`--onedir`) zipped for download rather than a single
  self-unpacking exe, which antivirus tools flag more often. Built on a
  GitHub Actions Windows runner from the repo code alone (no game files).

  Now a classic setup wizard (`tools/app/severed_installer.py`): Welcome
  (install or remove), Locations (one Browse for the add-on: the package
  file, or any file in an unpacked folder; the game folder; ffmpeg only when
  not bundled; free space shown), Ready, Installing (progress, current step
  and the converter's log in a terminal box), Finish (deletes the temporary
  `severed_work` folder next to the program). The game folder is found
  from Steam's library list (app 47780), the EA/Origin registry keys or the
  usual folders (`gamefind.py`). ffmpeg: an LGPL build is downloaded and
  bundled by the GitHub Actions workflow (`.github/workflows/build-app.yml`,
  Windows runner, PyInstaller with its launcher compiled from source, a
  version resource, no UPX, to keep antivirus false alarms down), which
  also runs the app's `--selftest` (data files, native library, ffmpeg's
  xma2 decoder) and uploads the app as the run's artifact. Checked on Linux:
  the build, the self-test, every
  wizard page. A full conversion through the app on Windows completed
  start to end in about 15 minutes (run 10's build, from the add-on file).
  On hold until the DLC plays start to finish: the workflow now runs only
  when started by hand (no build on every push); testing goes through
  `Make-SeveredTest.bat`.

- **The app installs `dinput8.dll` itself (all-in-one, decided by the
  user): done.** The app carries the hook (`_internal/hook/dinput8.dll`),
  copies it next to `deadspace2.exe` after the conversion and deletes it on
  removal. Another mod's `dinput8.dll` is renamed to `dinput8.dll.other`
  and put back on removal. Our hook is recognised by the text
  `severed_probe.log` inside it (`HOOK_TAGS`). The app's `--selftest` checks
  the hook is there. For now it carries the test probe; when the release
  hook replaces it, add a text it carries to `HOOK_TAGS`.
- **App: the Installing/Removing page hid the button bar: fixed.** The log
  box now starts 10 lines high (it still grows with the window), so the
  bar and its Cancel button stay visible. Screenshots retaken.

- **Check the user's add-on before converting.** People's copies can have
  any file name, so the app identifies the add-on by its contents, not its
  name:
  - an MD5 of each file inside the add-on (after unpacking), compared with a
    shipped list of expected hashes. This works for the add-on file and for
    an already-unpacked folder alike;
  - a hash of the whole add-on file is not enough on its own. The package
    header can differ between copies (licence and signature data), so a
    correct copy could fail;
  - the shipped list holds only file names and hashes, no game data;
  - the European and World copies have the same 421 file hashes (FINDINGS
    1), so one list covers both;
  - on a mismatch, the app names the files that differ and stops, rather
    than building a broken archive. Done in the converter (`ds2/addoncheck.py`,
    `ds2/addon_hashes.txt`; `--skip-check` converts anyway); the app reuses it.
- **Severed save pictures and titles (release hook):** the load menu
  (exe 0xBAE170) builds the picture key `chNN` and title `CHNN_TitleString`
  from the save's chapter number alone, so Severed's chapters 1 and 2 share
  the base game's. A small `dinput8.dll` shipped with the mod hooks that
  function in memory (the exe on disk and its DRM are untouched): when the
  save's level is a Severed one, it swaps in Severed's picture key and
  title. Separate from the test probe, without its logging and test keys.
  Must be proofed for performance before shipping:
  - frame time with and without the hook, in a heavy area (the gift shop,
    the drill tunnel) and on the load menu;
  - the hook runs only when the load menu draws a save slot, with no
    per-frame or per-draw work, no heap checks and no file writes;
  - load times unchanged.
- **Bundle ffmpeg with the app**, replacing the third path the `.bat` asks
  for now (`ffmpeg.exe`, used to decode the Xbox XMA audio). Use an LGPL
  build with its licence and source offer included.
