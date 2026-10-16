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
