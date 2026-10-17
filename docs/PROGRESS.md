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

## Summary (2026-10-17)

**Where we are:** all of chapter 1 plays, and chapter 2 has started. Last
reached: the zero-oxygen hallway after the Tormentor fight, then a crash on
entering the decompression room.

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

**Tests waiting on you:**
1. Hanging fight drop with probe 40: the release still had a listener at
   the drop's end; the probe now names it.
2. Save pictures: start Severed fresh from Episode Select and save: the
   picture should now be Severed's (the title stays "Chapter 16": the
   string tables can't be replaced from the test archive yet).
3. Decompression room: fixed (`loop_split.ok`).
4. Zero-oxygen hallway with probe 46: as before (F6 until the level
   vanishes, F3 through the pieces, F5 when the box goes), then wait 5
   seconds before F4: F5 now also logs every draw of that piece.
5. Gift shop: lights back to the second version (0.85-1.15x every 0.5 s,
   `calm_lights5.ok`); the livelier third version flashed too much.
6. Bed room after the elevator: check again with F4 pressed (the black
   bar may have been probe 43's hidden shader).

**Reported in the replay (new game):**
- Gabe floats above the gunship after the docking transition, unable to
  move (worked before). Test build reverts the two script changes made
  since: chapter numbers back to 1/2 and the hanging release as on the
  console (`chapters_restored.ok`); the save picture goes back to the base
  chapter pictures meanwhile.
- hanging fight drop: the hanging state now ends 1 s before the drop
  sequence starts (`hang_drop2.ok`): Gabe should fall to the grate as the
  fight ends, then get up.
- black stretched shapes in several hospital rooms: the hallway's box is
  the scratched-metal wall panels shaded black (lightmap-shader material);
  probe 46 trace pending.
- bodies in the drill tunnel lie in different places on each new game
  (likely settling during the intro).
- the clinic overlook room's reflections are sideways.

**Open bugs** (strike out any that are no longer bugs):
- ~~crash entering the decompression room~~ fixed (looping sound split)
- black shape in the zero-oxygen hallway (ruled out: the depth-of-field
  effect's file, which is the PC game's own; the floating debris meshes,
  the PC game's own; the hallway's glass, which converts exactly like the
  base game's). `msg_vfx_airless_dof_stop` changed nothing; the broken
  windows there also show flat beige. Next F7 tests:
  `lt_airless_hall_post_fx_off`, `msg_vfx_airless_stop`
- Gabe does not drop to the floor after the hanging fight (plays the
  get-up inside the rock overhang). The F7 test showed the hanging state
  holds him up until the drop animation ends; releasing it at the drop's
  start did not help, and the release message still had a listener at the
  end (probe 40 names it)
- thump in the opening scene (not the two corpses, Gabe's gun or the
  tunnel's 4 physics props, tests 1-4)
- the Pulse Rifle sits oddly in Gabe's hands (other weapons are fine): deferred to a future release
- saves show as "Chapter 1" with chapter 1's picture: fix pushed, to test
  (both chapters numbered 16, with Severed's own picture and title)
- save station lock-up: happens when the terminal is used again during
  its closing animation
- Twitchers stunlocking Gabe (not reproduced since)
- frame drops near some lights in the drill tunnel

**No longer bugs** (confirmed by the user): the stretched slabs after the
intro terminal, the alt-tab hang, the gunship hull textures.

## Start-up

| Step | Status | Notes |
|---|---|---|
| Building the test archive (`Make-SeveredTest.bat`) | works | |
| Severed in Single Player > Episode Select | works | via the probe DLL |
| Level loads (no black void, no crash) | works | |
| Intro terminal ("Primary mission assets", RIG call video, dialogue) | works | |
| Gabe on the ground, RIG call scene, getting up | works | since probe 23 stopped loading a second copy of the level data |
| Control handed back after the scene | works | no F8 needed |

## Chapter 1: the mines

| Area / sections | Status | Notes |
|---|---|---|
| drill_tunnel: drill_tunnel_01, drill_tunnel_02 | works, fix pending | thumping in the opening scene (fine once it ends). Ruled out: raising both corpses 12 cm; removing either corpse; removing Gabe's dropped Flamethrower (tests 1-3). Test 4 (step `prop_test.ok`, `simgroup.NUDGE`): the tunnel's 4 ScriptableProps 200 m below the level, everything else in place |
| drill_tunnel: drill_cavern_01 | partial | Flamethrower picked up without a crash once the PC game's own assets were used |
| drill_tunnel: drill_saferoom | works | door, bench, store, save station (second use of the save station locked up in an earlier run: recheck) |
| bomb_run: grinder_hall_z01/z02, grinder_room | works | |
| bomb_run: quarry_entrance, quarry_z01/z02, escape_hall | works | loads and plays (probe 31, and no `D3D GUARD` lines since the LUT fix). Price's scene and attack, the override switch, the door encounter and the cargo lift all work. The black screen when the quarry door opened is fixed (colour-grading LUTs, FINDINGS 45). The door that drew as a solid black slab (`door_inner_01_am`) is fixed and confirmed (20-byte UV streams, FINDINGS 46) |
| mining_camp: mining_camp_hall, mining_camp01/02, mining_camp_z01 | partial | played through to the docking station. The upside-down tentacle grab after the lift plays; pressing stomp during it put Gabe inside the ceiling (he got out once the animation ended). The quarantine lockdown with 3 override terminals starts. Died there: Twitchers sometimes repeat the same attack and stunlock Gabe in a damage loop |
| elevator: elevator_hall, elevator_z01-z03, elevator_shaft_04-12 | untested | elevator crash scenes (`ses_player_01_02`, `01_03`) |
| docking_station: docking_airlock_01, docking_station_z01/z02 | works, fix pending | the gunship fight, destroying it and boarding work (FINDINGS 47). The smeared hull textures: Severed's `exterior_black_win` is the base game's gunship hull with another window material; it is now built from the PC game's own `exterior.dae` with that material (`pcassets.DERIVED`, step `gunship_hull.ok`, FINDINGS 51) |
| chapter 1 -> 2 transition (emergency_arrival) | works | confirmed: the crash-landing scene, its dialogue and the Chapter 2 title play (FINDINGS 49). A side-by-side screenshot with console footage at the psych ward line matches |
| emergency / psych ward: Tormentor fight, airless hallway | works, issues | the Tormentor boss fight works; a flat black shape floats in the zero-oxygen hallway (Gabe walks through it). The hallway turns on a depth-of-field effect (`msg_vfx_airless_dof_start`), but that effect, the floating debris meshes and all the hallway's materials are the PC game's own, and its glass converts exactly like the base game's: cause still open |
| decompression room | crash | crashed on entering (doors open, light supports destroyed): audio thread, exe 0x515F0F, the sample decoder (0x515EE0) read a block through a null pointer (voice +0x34). Severed's sound banks are the only XAS bank samples the PC plays (its own banks are all EALayer3). Probe 39 dumps the voice and the sample header at this crash |

## Chapter 2: the hospital

| Area / sections | Status | Notes |
|---|---|---|
| emergency: emergency_arrival_z01, emergency_arrival_hall_z01, storage_z01, hacking_room_z01 | untested | scene `ses_player_02_01` |
| emergency: decompression_z01, decom_hall_z01, airless_hall_z01, vista_sprawl_z01/z03 | untested | |
| trauma: triage_z01, triage_hall_z01, morgue_z01, morgue_hall_z01-z03, elevator_morgue_z01 | untested | |
| recreation: recreation_z01/z02, recreation_hall_z01-z03, bathroom_z01/z02, elevator_rec_z01/z02, elevator_recreation_hall_z01 | untested | |
| upper_corridors: patient_z01/z02, patient_hall_z02-z05, store_room_z01, surgery_lobby_z01 | untested | |
| surgery_ward: surgery_z01, surgery_hall_z01, surgery_observation_z01, surgery_pit_z01, elev_surg_pit_z01, decontamination_z01 | untested | |
| observation: observation_z01, observation_hall_z01, psycho_development_z01, psycho_dev_hall_z01 | untested | scene `igc_02_01` |
| chase_hall: chase_hall_z01/z02, chase_hall_saferoom_z01 | untested | |
| psych_ward: psych_arrival_hall_z01, psych_hall_z01/z03-z05, isaacs_cell_z01, vista_sprawl_psych_z01/z02, landing_bay_psycho_z01 | untested | finale (`igc_02_03` onwards) |
| Also in the DLC: entry_hall, hospital_entrance, security, pre_moonquake | untested | where these fit is not known yet |
| End of the DLC (credits) | untested | |

## Systems

| System | Status | Notes |
|---|---|---|
| Level geometry, lighting, collision | works | in the areas seen so far |
| Gabe (security suit) | works | |
| HUD, menus, inventory screen | works | |
| Subtitles | works | |
| Dialogue and audio logs (stereo streams) | works | |
| Cutscene audio (5.1 streams) | fix pending | stereo downmix |
| RIG health spine | works | since the PC game's own RIG bar meshes are used |
| Starting equipment (`equip_command_player_initial`) | works | Pulse Rifle, Seeker Rifle, ammo; 50,000 credits (to compare with the console) |
| Gabe's Pulse Rifle upgrades | works | probe 34: `10 node(s) set, 0 missing`; the user confirmed the upgraded rifle in game. RIG upgrades not looked at yet |
| Twitchers | not reproduced since | parked by the user; previously: one Twitcher alone keeps Gabe in his flinch: each slash lands before the flinch ends (Normal and Casual; no grab). Their `Zombie` settings differ from the slashers' in an authored way (pain interrupt delays 4/2 s, dodge 0.9, turn speeds doubled, 8 damage per hit), nothing that looks like a conversion error. Next: A/B against the base game's own Twitchers (Government Sector) on the same PC, and a 60 fps cap test (the user plays at 75 fps with external V-Sync) |
| Scripted hang after the cargo lift | partial | the entry into the hang looks like the console. Gabe still does not drop to the floor at the end. Probe 37: `ses_player_01_03` runs and finishes; its anchor is the origin (no transform, as on the 360) and the hanging proxy offset is tiny, so neither explains it (FINDINGS 48). Next: F7 test sending `PlayerChangeState_hanging_combat_deactivate` as the fight ends |
| Weapons: Flamethrower pickup | works | |
| Weapons, kinesis | works | |
| Weapon in Gabe's hands | partial | only the Pulse Rifle sits oddly (other weapons are held properly); not caused by its upgrades (tested without them). Deferred to a future release: the rifle's files are the PC's own, the likeliest cause is Gabe's converted animation bank `pc_nolegs_patrol.bnk` (Severed-only, nothing to check it against) |
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

- F8 (probe 20+): sends the intro hand-over. F7: sends the messages listed
  in `severed_send.txt`. F9: requests the start sections (and logs the
  episode list). Probe 29+: the F-keys are ignored with Alt, Ctrl or Shift
  held (Alt+F9 records in the Nvidia overlay).
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
  - on a mismatch, the app names the files that differ and stops, rather
    than building a broken archive.
- **Bundle ffmpeg with the app**, replacing the third path the `.bat` asks
  for now (`ffmpeg.exe`, used to decode the Xbox XMA audio). Use an LGPL
  build with its licence and source offer included.
