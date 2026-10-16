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
| drill_tunnel: drill_tunnel_01, drill_tunnel_02 | works | something collides constantly off camera during the opening scene (sound) |
| drill_tunnel: drill_cavern_01 | partial | Flamethrower picked up without a crash once the PC game's own assets were used |
| drill_tunnel: drill_saferoom | works | door, bench, store, save station (second use of the save station locked up in an earlier run: recheck) |
| bomb_run: grinder_hall_z01/z02, grinder_room | works | |
| bomb_run: quarry_entrance, quarry_z01/z02, escape_hall | broken | crash in Direct3D a few seconds after quarry_z01 loaded, while drawing the frame's dynamic geometry (particles / decals); probe 24 names the code that queued it |
| mining_camp: mining_camp_hall, mining_camp01/02, mining_camp_z01 | untested | |
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
| Gabe's Pulse Rifle and RIG upgrades | missing | Severed-only object type, to be redone |
| Weapons: Flamethrower pickup | works | |
| Weapons, kinesis | works | |
| Necromorph AI | broken | enemies attack but run in place (navigation data, likely the converted NAV meshes) |
| Crash in the quarry | broken | see bomb_run |
| Save stations | partial | first save works; second use locks up; saves are listed as "Chapter 1" (loading one probably starts the base game: do not rely on them) |
| Stores, benches | works | the store lists the base game's suits too (on console Gabe only changes suit in chapter 2); possibly from the PC profile's unlocks, to check |
| Performance near some lights | partial | frame drops in the drill tunnel |
| Gabe's pain sounds | untested | possibly Isaac's; whether Severed has its own is not known yet |
| First view after the terminal | broken | stretched slabs in front of the camera (screenshot); a mesh still converted wrongly |
| Menu text (localised episode name) | partial | English placeholder via the probe |

## Test tools

- F8 (probe 20+): sends the intro hand-over. F7: sends the messages listed
  in `severed_send.txt`.
- Crash reports name the meshes near the crash (probe 21+).
