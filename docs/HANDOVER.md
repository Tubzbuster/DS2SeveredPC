# Handover

For a Claude session picking up this project, after a context reset or in a
new conversation. Read this first, then `docs/PROGRESS.md` (what plays) and
the latest sections of `docs/FINDINGS.md` (how things were worked out).
Update this file whenever the state or the next steps change.

## The project

Make the Xbox 360 DLC **Dead Space 2: Severed** playable on the PC Dead Space
2, started from Single Player > Episode Select, as on the console. It has two
parts:
- **Converter:** turns the user's own Severed add-on file
  (`29E2FCC04BEF1D2532C48269EC42EF2E3DBFC45845`) into `DS2DAT2.DAT` for the
  PC game. For now this is the test build, `tools/test/Make-SeveredTest.bat`
  → `make_severed_test.py`.
- **Hook DLL:** the "probe", `tools/probe/probe.c` → `tools/probe/bin/dinput8.dll`,
  placed in the game folder. It adds the menu entry and, for now, logs
  diagnostics to `severed_probe.log`.

The user tests on their own PC (Steam version, Windows). Claude cannot run
the game: every in-game result comes from the user's tests, logs, screenshots
and videos.

## Rules (keep)

- **Repo and branch:** `Tubzbuster/DS2SeveredPC`, branch
  `claude/fervent-lovelace-80fw4s`. Commit and push there. No pull requests
  unless asked. The repo is public.
- **Commit messages** end with:
  `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>` and
  (no conversation link).
  No model names in code or commits.
- **Never commit EA game files** (archives, streams, audio, video, textures,
  exe). Learned models and tables hold byte-order rules, names and hashes
  only.
- **Never commit probe logs:** they contain the user's Windows username.
- **Never modify `deadspace2.exe` on disk**, and never bypass the DRM (Steam +
  Solidshield). The probe patches code in memory only.
- **Probe memory reads are read-only diagnostics:** addresses and values are
  logged, no code bytes are dumped.
- **The user's unwrapped retail exe** is for read-only static analysis only:
  never run, distribute or commit it.
- **References:** the DS1-3 Modding Toolkit (4Kodda) is a format reference
  only; copy no code from it. Gibbed.Visceral (zlib) and vgmstream (ISC) may
  be used with attribution.
- **The README** is GameFAQs-style. Its header image is EA key art, used with
  permission on a non-commercial basis. The user also edits the README on
  GitHub, so always `git pull` before committing.
- **Working rhythm:** pause and commit after each step, and tell the user
  clearly what to test and what to send back. The user follows along in the
  Claude app; be concise and honest about what is verified and what is
  guessed.

## Layout

| Path | What |
|---|---|
| `docs/PROGRESS.md` | in-game status per area and system, and the to-do list for a release |
| `docs/FINDINGS.md` | numbered research notes (1-43 so far); add a section per finding |
| `docs/DESIGN.md` | overall design |
| `tools/research/ds2/` | the converters, one module per asset type, plus `build.py` (converts a 360 tree) and `convert.py` (`CONVERTERS` table) |
| `tools/research/*.py` | `score.py <Type>` scores a converter against the paired samples; `learn_*.py` rebuild the learned models |
| `tools/research/re/`, `simgroup_tools/`, `checks/`, `rpenc.py` | analysis helpers: exe disassembly (`DS2_EXE`), SimGroup inspection, consistency checks (see `tools/research/README.md`) |
| `tools/research/native/` | `refpack.c` and `xas_enc.c`, built by `build.sh` into `libxasenc.so` (Linux) and `xasenc.dll` (64-bit Windows) |
| `tools/test/` | `Make-SeveredTest.bat` / `make_severed_test.py`: the user's test build; work folder with `*.ok` step markers |
| `tools/probe/` | `probe.c`, `build.sh` (Zig: `pip install ziglang==0.13.0`), `bin/dinput8.dll` (committed; force-add, the folder is in .gitignore) |
| `src/` | an early C# tool (`Severed.Cli`); the Python tools are what is used now |

## How things are done

- **Pairs:** `pairs.py` loads PC/360 asset pairs from the export
  (`DS2_PAIRS`, default the session scratchpad `exp/`, holding `pc/<Type>.str`
  and `x360/<Type>.str`). Measure every converter change with `score.py`,
  held-out where a model is learned.
- **Test build steps:** steps added after the user's first build run once
  each, guarded by a marker file in the work folder, so the user only
  re-runs the `.bat`:
  `hkx_fix`, `strip_fix2`, `snu_channels2`, `nav_sums`, `reloc_fix`, then
  `pc_assets` (last: takes the PC game's own copies of reused assets), then
  the video audio check (runs every time).
- **Probe versions:** bump the number in `start()`'s first `log_line` with
  each build ("severed probe N"), so the log shows which build ran. Hooks
  are found by byte signatures (`find_sig`), because the exe is
  DRM-wrapped. Parts of the code are decrypted late, so retry signatures.
- **Static analysis:** of the user's unwrapped exe, with capstone through
  `tools/research/re/dsx.py` (`dis(addr, n)`, `func_start`, `cstr`; set
  `DS2_EXE`).
- **What is not in the repo** (game data, about 9 GB; it lived in the
  session scratchpad):
  - the user's unwrapped exe: re-uploaded by the user;
  - the unpacked add-on and the converted output: rebuilt from the user's
    add-on with the repo's tools;
  - the PC/360 sample export (4.3 GB): needed only to re-score or retrain
    converters; rebuilt with `tools/export`.

## State (end of this session)

Plays from the start through the drill tunnel, saferoom (bench, store, save)
and grinder area. Works:
- the opening scene and the hand-over to the player;
- starting gear, the Flamethrower and kinesis;
- RIG health;
- the Necromorph AI, with the navmesh fixed (FINDINGS 41);
- saving and loading.

Open, most important first:

1. **Quarry crash: worked around by probe 31**, which refuses
   SetTexture/SetSamplerState on invalid stages. The quarry now loads and
   plays.
   - The bad call came from exe `0x6DAF10` (per-frame pass; chain
     `0x6DF625` → `0x6DB018` → `0x13D2710` → `0x13C8070` →
     `0x13D8540`). It binds a list of textures `[ebp+8]` (count
     `[ebp+0xC]`) using the slot table `0x2033E90` (6 dwords per shader:
     index `(obj+0xB0)*6 + i`); `0x13D2710` takes the slot from the low
     byte, +16 for vertex shaders.
   - An object handed more textures than its shader has slots reads past
     the table: slot 176 → stage 417 → Direct3D writes past its tables.
   - **Next (probe 32 logs this as `TEXTURE LIST:` lines):** log the object (shader index `[esi+0xB0]`, texture count,
     texture handles; the texture table is `0x20E04D8`, 0x3C bytes per
     entry) to find the asset. Suspects: quarry_z01's converted VFX,
     especially `pdlc_quarry_atmo_01-07`. Then fix the conversion.
   - Probably related: the quarry is very dark, with "black smog" (the
     object draws with a leftover texture on that slot).
2. **Quarry progression blocked:** the door switch shows LOCKED (its
   disabled panel; on console a blue press-and-hold "OVERRIDE?" starting a
   60 s security override), and Price is never attacked.
   - The switch (`AA6A826D` → `SimplePressAndHoldSwitch`) is enabled only
     by `enable_quarry_switch`, sent by a TriggerAuto in quarry_z01.
   - The attack chain in quarry_z02: TriggerPhysical `805B0158` arms
     TriggerLOS `73ECC542`/`338BC582` → `mm_spawn_infection_npcs` → FuncSpawn
     infector/slasher → AndEventGate → `mm_trigger_price_infection`.
   - Message send: exe `0x756C60` (hash at msg+0; listener table global;
     drops when no listener). Hashes are sdbm of the name.
   - Probe 33 logs `MSG <hash>` lines with their listener state. Match
     them to names from the SimGroup strings to find the broken link.
   - The user is also testing F7 with `enable_quarry_switch` in
     `severed_send.txt`.
3. **Thumping in the opening scene:** absent in the user's last two runs
   (one without F9). Possibly fixed by the video audio conversion
   (FINDINGS 43); not confirmed. Ruled out: the cutscene audio, corpse
   physics, the video screen, Gabe's animation, the floor collision.
4. Smaller items in `docs/PROGRESS.md`:
   - stretched slabs in the first view after the terminal;
   - the save station's second use locked up once;
   - saves listed as "Chapter 1";
   - the store lists the base game's suits;
   - 50,000 starting credits (to compare with the console);
   - Gabe's Pulse Rifle and RIG upgrades: a Severed-only class, neutralised
     for now;
   - frame drops near some lights;
   - the localised episode name.

Not yet played: the mining camp onwards, and all of chapter 2.

## Next steps

0. **State at the last update:** the quarry plays through Price's scene,
   the override switch and the door encounter (probe 33's message trace:
   the whole chain fired). The black screen is fixed in the converter
   (colour-grading LUTs, FINDINGS 45); waiting for a rebuild and test.
   Next feature: **Gabe's upgraded Pulse Rifle**.
   - Severed-only class `2B747EB6`, neutralised, on message
     `equip_player_upgrade_nodes`; 10 nodes, listed in FINDINGS "Severed-only
     classes".
   - The exe's Lua bindings: name strings `GetUpgradeManager` 0x1B90FD8,
     `Upgrade` 0x1B90FD0, `Connect` 0x1B90FC8, `UpgradeValue` 0x1B90FAC,
     `DebugFillUpgradeNode` 0x1B90F94, registered around exe `0x1355E89`.
   - Plan: find the native functions behind them, then have the probe
     apply the 10 nodes when the message fires.

1. **Read the user's probe 28 log.** Check for:
   - `game thread:`, `D3D guard: device`, `geometry batch tracker: 1
     match(es)`;
   - any `D3D GUARD` lines: they name the game code that bound the bad
     object;
   - `texture stage` lines in the crash report.

   Trace the named code to the asset it belongs to (likely something
   streamed in with `quarry_z01`).
2. **Compare the user's thump recording** with the clip (47.2-51.5 s of
   `igc_01_01`) and the console video. If it is the authored sound, it is
   expected behaviour. If not, find the impact-sound path in the exe and log
   its source object.
3. **Then play on through the quarry and the mining camp**, updating
   `PROGRESS.md` each run.
4. **Later, the release app** (to-do list in `PROGRESS.md`):
   - a window asking for the add-on (file or unpacked folder) and the
     Dead Space 2 folder;
   - identifying the add-on by MD5s of its contents;
   - bundling ffmpeg (an LGPL build);
   - turning the probe into a proper hook DLL without the diagnostics.
