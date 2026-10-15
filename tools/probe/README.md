# Severed probe (dinput8.dll)

A diagnostic DLL. It does **not** add Severed. It writes a log of every file
Dead Space 2 tries to open, look up or list. That tells us:

- whether the game looks for `DS2DAT2.DAT` … `DS2DAT5.DAT` (free archive
  slots for Severed)
- whether it looks for DLC folders or DLC files (`*.pid`, `*.lvl`, …)
  anywhere
- the order in which it loads the archives and level files

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
5. Send `severed_probe.log` from the Dead Space 2 folder.
6. Delete `dinput8.dll` from the game folder.

If the game refuses to start or crashes with the DLL in place, delete it and
say so. The copy protection might object to it, and that is useful to know
too.

Antivirus software may flag it, because it is unsigned and intercepts file
functions. The full source is `probe.c`.

## Building

`build.sh` cross-compiles it with Zig (`pip install ziglang==0.13.0`).
