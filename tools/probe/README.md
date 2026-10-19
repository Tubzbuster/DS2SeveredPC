# Severed probe (dinput8.dll)

A diagnostic DLL. It does **not** add Severed. It writes a log of every file
Dead Space 2 tries to open, look up or list, and (version 2) which archive
each file inside `DS2DAT*.DAT` is actually read from (`READ DS2DAT6.DAT
#C2B10B96 ...`). That tells us:

- whether the game looks for `DS2DAT2.DAT` … `DS2DAT5.DAT` (free archive
  slots for Severed)
- whether it looks for DLC folders or DLC files (`*.pid`, `*.lvl`, …)
  anywhere
- the order in which it loads the archives and level files
- whether an added archive (`tools/archive/New-TestArchive.ps1`) overrides
  the game's own copies of a file

It works as a `dinput8.dll` proxy: the game loads it from its own folder,
it installs the logger, then passes every DirectInput call on to the real
Windows `dinput8.dll`. It never modifies `deadspace2.exe` or any game file.


## The release hook (56)

Since v0.8.5 `probe.c` is the slimmed-down hook that ships with the
converter. It keeps only what the game needs:
- Severed in the episode select (front end constructor + AddEpisode);
- Gabe's Pulse Rifle upgrades (UpgradeManager, on the level message
  `equip_player_upgrade_nodes` and at each Severed level start);
- the ending: in the Severed level the end-of-game sequence goes from the
  New Game+ popup state straight to its return to the main menu;
- F7: sends the lines of `severed_send.txt` as level messages (testing);
- `severed_probe.log`: hook status, level starts and crash reports.

Everything else below (file and archive logging, message, sequence and
SimGroup traces, the Direct3D guard, position watches, heap checks,
reflection scans) was research and is gone from the source; it is in the
git history up to probe 55 (commit a118774) for later research.

## How to use

1. If the Dead Space 2 folder already has a `dinput8.dll` (from another mod),
   move it somewhere safe first.
2. Copy `bin\dinput8.dll` into the Dead Space 2 folder, next to
   `deadspace2.exe`.
3. Start the game as normal (Steam).
4. At the main menu, wait about 30 seconds. Then open the chapter select /
   load a save so a level loads, play for a few seconds, and quit to
   desktop.
5. Send `severed_probe.log` from the Dead Space 2 folder. It contains your
   Windows user name in some paths; edit those out if you like.
6. Delete `dinput8.dll` from the game folder.

If the game refuses to start or crashes with the DLL in place, delete it and
say so. The copy protection might object to it, and that is useful to know
too.

Antivirus software may flag it, because it is unsigned and intercepts file
functions. The full source is `probe.c`.

## Reflection scan (version 4)

Severed's level objects (SimGroups) are stored in a newer, packed format
that the base game never uses, so their conversion needs each class's field
layout, which the game only builds in memory. With the probe installed:

1. Start the game and wait at the main menu.
2. Press **F10** once. After a few seconds Windows plays its "asterisk"
   sound: the scan is done.
3. Quit the game.
4. Zip and send `severed_reflect.log` and `severed_data.bin` from the game
   folder (and `severed_probe.log`).

The scan only reads memory. It writes the places that point at the class
names in `reflect_names.h` with the bytes around them, how often two
SimGroup format markers occur in the loaded exe, and a copy of the exe's
`.data` section as it is in memory (its static data, not code).

## Descriptor dump (version 5, fixed in 6)

Same as the scan, but press **F11** at the main menu instead of F10, wait for
the sound, quit, and send `severed_desc.bin` (about 10-50 MB; zip it). It
holds the exe's `.data` section and the heap blocks of the engine's class
descriptors (field lists: offsets and types of every field). Version 6
fixes memory lost at region edges and long field lists cut short.

## Building

`build.sh` cross-compiles it with Zig (`pip install ziglang==0.13.0`).

## Severed in the episode list (probe 9)

With the Severed test archive installed (`tools/test`, without
`--hijack-ch01`), probe 9 adds "Dead Space 2: Severed" to the episode list
by itself: it waits for the Steam wrapper to decrypt the game's code, finds
the front end constructor and the game's add-episode function by byte
pattern, and hooks the constructor in memory (nothing on disk). Right
after the game adds its own episode, on the game's thread, the probe adds
Severed with the values from Severed's `weller1.lvl`, the same call the
console's DLC `.lvl` handler makes. **F9** only writes the episode list to
the log.

(Probes 7 and 8 called the function from the probe's own thread on F9:
that hangs the game, its memory allocator is not for foreign threads.)

Probe 10 also logs every read inside `DS2DAT2.DAT` (entry hash and
offset, so a crash can be tied to one asset of a stream) and, once Severed
has been added, the first serious exceptions: code, module + offset, the
faulting address, registers and the return addresses on the stack.

Probe 11 also logs every stream the game requests ("STREAM request
<path>", from a hook on the loader's stream request function, found by
byte pattern), and the Severed entry's description is just "Gabe Weller's
story".

Probe 12 (experiment): at the start of a level whose folder contains
"pdlc", also requests `<folder>\<folder>_streamsets.str` in stream-sets
mode, as the game does for the base chapters (the test archive holds
Severed's level SimGroup under that name).

Probe 13 logs every SimGroup data block the game loads ("SIMGROUP block
<magic> size records -> ok/FAILED") from a wrapper around the block
dispatcher (packed 0x011795D9 / property tree 0x91C8773C).

Probe 14 writes the field list of the `Uniform` class (player suits) to
the log when the front end starts ("CLASS Uniform ..." and "FIELD" lines,
read-only from the class descriptor at 0x02098B78): the earlier
descriptor dump missed it, so Severed's 11 Uniform records were converted
without a layout.

Probe 15: the Uniform field list is filled in lazily (probe 14 found 0
fields at the main menu), so it is logged once it exists - after a
SimGroup block load, or on F9.

Probe 16 logs every path-like name the game hashes ("NAME #hash path",
once each) from a hook on its name hash function: all the files a run
looks for, found or not.

Probe 17 (experiment): when Severed starts, also requests the five
sections of its start checkpoint's stream set (drill tunnel 01/02, drill
cavern, drill saferoom, doors) directly as level streams. The name hash
log of probe 16 is off again (that function only sees UI names).

Probe 18: the start sections are no longer requested at level start
(probe 17 did that before the main level stream was set up and ZoneRender
crashed on its missing zone). Instead press **F9** in the black Severed
level: the request is queued and the game's main thread runs it from its
message loop (PeekMessage hook).

## Level messages: F8 / F7 (probe 19)

Severed's level objects talk to each other by named messages (a
MultiManager sends `push_cam_pole_initial`, a scripted sequence sends
`ses_player_01_01_end` when it finishes, ...). Probe 19 finds the engine's
own message broadcast (the function behind Lua's `SendMessage`, retail exe
0x0084F5A0) by byte pattern and can send messages on the game's thread:

- **F8** (in the Severed level) sends Severed's intro hand-over, as if the
  RIG call scene had finished:
  - `pop_cam_pole_initial`
  - `ses_player_01_01_end`, which pops the scene camera, adds the first
    objective and sets the post-intro checkpoint
  - `equip_command_player_initial`, Gabe's starting equipment

  Use it if the scene doesn't end by itself. The Windows "asterisk" sound
  confirms the messages were sent.
- **F7** sends every line of `severed_send.txt` from the Dead Space 2 folder
  (one message name per line; `#` starts a comment), for trying other
  triggers without a new build.

## Gabe's position through the hanging-fight drop (probe 47)

When `ses_player_01_03` starts, the probe takes the hanging-fight teleport
point as a reference and looks for positions within 20 m of it in the
sequence's player-side object ([+88]) and two pointer levels below. It
logs where it found them (`POS [n] address (level, under base +offset)`)
and then their values in millimetres every 200 ms for 14 seconds
(`POS +ms: [n] x y z ...`, Y is up). Nothing to press.

## Lighter for play-throughs (probe 48)

The chapter 2 slabs are fixed (FINDINGS 59), so probe 48 turns off what ran
all the time for those hunts:
- the D3D guard: its hooks on about 15 Direct3D methods, every draw call
  among them, and with it the F3-F6 shader and piece hiding;
- the per-frame position watch of the hanging-fight drop (probe 47);
- the texture list check (an old crash hunt).

Still there: Severed in the episode list, the Pulse Rifle upgrades, F7/F8
level messages, F9 (episode list), F10/F11 (scans on request), the file
and message log, and the crash report. The code of the removed parts stays
in `probe.c` for later probes.

## Only F7 left (probe 49)

F8 (the RIG scene hand-over), F9 (start sections, episode list) and F10/F11
(the reflection scan and descriptor dump) are off the keys: everything
they covered is confirmed working. F7 stays: it sends the messages listed
in `severed_send.txt`. For wrong surfaces, compare the area with the base
game's own files (`tools/research/extract_base_sections.py`) rather than
bring back the draw hooks.


## The final fight's tally (probe 50)

The landing bay's Twitcher fight ends on `twitcher_combat_over`, sent by a
variable watcher once `oracle_dead` has been counted past 3 (threshold 3,
condition 4). The Infector and the Oracle Twitcher template send
`oracle_dead` both when they die and when they go to sleep. Probe 50 logs
every `oracle_dead` and `twitcher_combat_over` (other messages: the first
3 sends as before), to see the count when the fight does not end.

## The end-of-game save (probe 51)

After the credits the end-of-game sequence shows "save for New Game+" (OK
only), then opens the save screen only if a save target is set (exe
0xA92D90 checks `[[esi+0x28]+0x5C]`), else moves on. Probe 51 logs
`END OF GAME:` lines: the check with that pointer, and whether the save
screen opened (state 0xD) or was skipped (state 3).

## Test shortcut: invincibility and the boss door

`tools/probe/severed_send.txt` is a ready-made F7 file. Copy it next to
`deadspace2.exe` and press F7 in the landing bay:
- `invincible_weller_on` makes Gabe unkillable (Severed's own switch for
  its scenes); press F7 again after loading a checkpoint;
- `hotshot_pdlc_boss_door_unlock` unlocks the door to the final fight, as
  the power cell in the receptacle does, so the stalker room can be skipped.

## No Hardcore for Severed (probe 53)

The console DLC's `weller1.lvl` says "Difficulty setting not available for
this episode." (`$weller1_no_difficulty`): Severed was not offered on
Hardcore. The PC exe ignores that field, so the probe hooks the difficulty
screen: with Severed chosen, Hardcore is greyed out the way the game greys
it out for New Game+, with that line as its description. The base game's
list is unchanged. The log shows `difficulty screen: episode N (Severed),
enabled ...` each time the screen opens.

## Hardcore available again (probe 54)

A Hardcore run of Severed applies Hardcore's rules, so Hardcore is left
available as a choice for Severed. The probe no longer greys it out; it
only logs the difficulty screen (`difficulty screen: episode N ...`).

## No New Game+ for Severed (probe 55)

Severed has no New Game+: on the console its ending returns straight to the
main menu. Probe 55 skips the base game's end-of-game popup ("save for New
Game+"), its completion record and the unlocks (New Unlocks screen) in the
Severed level. The log shows `END OF GAME: Severed - no New Game+ popup or
unlocks, back to the main menu`.

## Marker Patch: the plugin build (SeveredPC.asi)

`build.sh` also builds `bin/SeveredPC.asi`: the same hook as an ASI plugin,
without the dinput8 pass-through. For players who use Marker Patch (its own
`dinput8.dll`, with `LoadASIPlugins = 1` in `MarkerPatch.ini`), or Ultimate
ASI Loader:
1. keep Marker Patch's `dinput8.dll` in the game folder (do not install
   ours; if the converter app installed it, Marker Patch's was moved to
   `dinput8.dll.other`: rename it back);
2. put `SeveredPC.asi` in the `plugins` folder next to `deadspace2.exe`.

The log is still `severed_probe.log` next to the game. Untested so far:
check that it shows `episode list: ... hooked`, `level messages: ...
hooked` and `end of game: ... hooked`. If Marker Patch has already patched
one of those places, that line says 0 matches and that feature is missing.
