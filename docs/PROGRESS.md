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
| drill_tunnel: drill_tunnel_01, drill_tunnel_02 | works | the thumping in the opening scene was absent in the last two runs (one without F9). Possibly fixed by the video audio conversion (FINDINGS 43); keep listening |
| drill_tunnel: drill_cavern_01 | partial | Flamethrower picked up without a crash once the PC game's own assets were used |
| drill_tunnel: drill_saferoom | works | door, bench, store, save station (second use of the save station locked up in an earlier run: recheck) |
| bomb_run: grinder_hall_z01/z02, grinder_room | works | |
| bomb_run: quarry_entrance, quarry_z01/z02, escape_hall | works | loads and plays (probe 31, and no `D3D GUARD` lines since the LUT fix). Price's scene and attack, the override switch, the door encounter and the cargo lift all work. The black screen when the quarry door opened is fixed (colour-grading LUTs, FINDINGS 45). One door (`door_inner_01_am`) drew as a solid black slab: fix pending (lightmap materials need the PC's 20-byte UV stream, FINDINGS 46) |
| mining_camp: mining_camp_hall, mining_camp01/02, mining_camp_z01 | partial | reached. The upside-down tentacle grab after the lift plays; pressing stomp during it put Gabe inside the ceiling (he got out once the animation ended). The quarantine lockdown with 3 override terminals starts. Died there: Twitchers sometimes repeat the same attack and stunlock Gabe in a damage loop |
| elevator: elevator_hall, elevator_z01-z03, elevator_shaft_04-12 | untested | elevator crash scenes (`ses_player_01_02`, `01_03`) |
| docking_station: docking_airlock_01, docking_station_z01/z02 | untested | scene `igc_01_05`; end of chapter 1 |

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
| Gabe's Pulse Rifle upgrades | fix pending | probe 34 sets the 10 nodes in the PC UpgradeManager (`pulse rifle upgrades:` log lines); RIG upgrades not looked at yet |
| Twitchers | broken | one Twitcher alone keeps Gabe in his flinch: each slash lands before the flinch ends (Normal and Casual; no grab). Their `Zombie` settings differ from the slashers' in an authored way (pain interrupt delays 4/2 s, dodge 0.9, turn speeds doubled, 8 damage per hit), nothing that looks like a conversion error. Next: A/B against the base game's own Twitchers (Government Sector) on the same PC, and a 60 fps cap test |
| Scripted hang after the cargo lift | partial | Gabe hangs upside down from a set piece; stomp is accepted there and moves him into the ceiling |
| Weapons: Flamethrower pickup | works | |
| Weapons, kinesis | works | |
| Necromorph AI | works | navmesh checksums recomputed (the game had rejected every converted navmesh) |
| Crash in the quarry | works | fixed by the LUT conversion; probe 31 stays as a safety net |
| Save stations | partial | saving and loading a save work; the second use of a save station locked up once (recheck); saves are listed as "Chapter 1" and so get chapter 1's picture in the load menu (the PC picks it from a `ch01`-`ch15` table by chapter number). On console the load menu shows "Severed, chapter N" with its own picture (Gabe in a corridor, from footage); Severed's files hold only the two 64x64 Xbox dashboard icons (`weller1_ch1/ch2.png`), so that picture is probably in a front-end file still to find |
| Stores, benches | works | the store lists the base game's suits too (on console Gabe only changes suit in chapter 2); possibly from the PC profile's unlocks, to check |
| Performance near some lights | partial | frame drops in the drill tunnel |
| Overall brightness | works | confirmed by the user after the LUT fix: the darkness was only the quarry's colour grading (FINDINGS 45). Lighting data audit in FINDINGS 44 |
| Gabe's pain sounds | works | Isaac's grunts and damage lines, as on console (the DLC reuses them) |
| First view after the terminal | broken | stretched slabs in front of the camera (screenshot); a mesh still converted wrongly |
| Menu text (localised episode name) | partial | English placeholder via the probe |

## Test tools

- F8 (probe 20+): sends the intro hand-over. F7: sends the messages listed
  in `severed_send.txt`. F9: requests the start sections (and logs the
  episode list). Probe 29+: the F-keys are ignored with Alt, Ctrl or Shift
  held (Alt+F9 records in the Nvidia overlay).
- Crash reports name the meshes near the crash (probe 21+).
- Probe 26+: heap checks every 2 s (`HEAP ... CORRUPT` lines).
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
