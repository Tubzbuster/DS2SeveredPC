# Standalone plugin support

Shared x86 scanning, module-relative paths, optional diagnostic logging and collision checks for independent ASI candidates. No imports from SeveredPC and no game data. Known older combined local modules, or SeveredExtras.asi, cause a candidate to remain inactive to avoid duplicate hooks. Unknown executable layouts are left unchanged.

SafetyHook and Zydis sources retain upstream notices; license copies are in licenses. This support code does not modify MarkerPatch or the original DLC core.

`build_checks_msvc.cmd` builds two independent DLL copies and verifies their shared process-local attachment guard (8 checks). It also builds an inactive-host loader for testing standalone ASI imports. Hook attachment is coordinated because each ASI statically links its own copy of the hook library.
