# Optional Contact Beam standing-charge fix

In Severed, Gabe can fold forward while charging the Contact Beam's primary fire from a stationary aim. With classic laser aiming, a distant shot can also miss the point indicated by the laser. This was reproduced on Steam with the Hacker Contact Beam bought from the Severed store, using DS2SeveredPC v1.3.0 and MarkerPatch 3.3.1. Other Contact Beam variants share the affected character state and are expected to be affected when made available in Severed. They have yet to be tested individually.

## How it works

The DLC suit banks supply a duplicate `pc_2h_aim_cbeam_firehold` state with a different animation clip. Renaming the duplicate in each of the eleven banks lets the game use the base rifle bank's same-named state. A prior Steam gameplay test changed just those eleven bytes in a test copy of the archive and restored the aiming posture and distant hits.

This standalone ASI checks the SHA-256 of all eleven expected banks in the local `DS2DAT2.DAT`. It changes the final character of that state name in completed `ReadFile` buffers only when the original field is fully present at a verified offset in the same archive. Partial reads and pending asynchronous reads pass through, and a matching pending read produces a diagnostic. The plugin opens the archive read-only and writes its own diagnostic log.

## Build and test

From a Visual Studio 2022 **x86 Native Tools Command Prompt** with the Windows SDK, run `build_msvc.cmd` in this directory. It builds the ASI and a native test harness. To run the harness against your original v1.3.0 conversion, use:

```bat
build\hook_test.exe "X:\path\to\Dead Space 2\DS2DAT2.DAT"
```

The harness checks live Win32 reads at all eleven offsets and verifies that partial reads preserve the original bytes. To try the plugin in-game, put `build/SeveredContactBeamFix.asi` in the `plugins` directory alongside the upstream `SeveredPC.asi`. Enable ASI loading in MarkerPatch and restart the game. To disable it, remove the optional ASI while the game is closed and restart. The plugin logs archive verification and each newly encountered replacement to `plugins/SeveredContactBeamFix.log`.

The native harness passed on the official v1.3.0 conversion. The archive's SHA-256 stayed identical before and after testing. A separate Steam launch with that archive logged verification of all eleven banks and a replacement in a suit-stream read. An in-game shot comparison with the ASI and coverage across weapon variants are still pending.

The issue was found and tested by the Chinese Dead Space community. AI participated in analysis and implementation.
