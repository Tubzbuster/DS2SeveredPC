# Optional Severed Power Node shop fix (draft)

This node-specific derivative builds on MarkerPatch's existing chapter/round bypass mechanism. Thank you to Tubzbuster and Wemino for the port, hook implementations and public sources. AI participated in the investigation, candidate implementation and documentation.

The default `../build.sh` stays unchanged and does not enable this module. For this optional Windows x86 MSVC build, run `build_msvc.cmd` in an x86 VS 2022 Build Tools environment (or the script's standard Build Tools path). Output is `build/SeveredPC.asi`. Keep the usual MarkerPatch DLL and Severed data installation. To opt in, copy `SeveredNodeFix.ini.example` as `SeveredNodeFix.ini` next to the ASI and set `EnablePowerNodeShopFix=1`. With no setting or a value other than 1, the node module does not install store hooks.

It handles only Power Node GUID 37C7B444-8607BF9D-4E59414D-36445241, during store-list construction in the already-identified Severed episode. The temporary chapter/round field is restored after the call. Price and node entitlement checks are retained. The implementation needs known MarkerPatch shop hooks (`EnableHackerDLC=1`); that setting also unlocks Hacker equipment in the base campaign. Ignition rooms are a separate switch. Independent integration advice is requested from MarkerPatch maintainers.

The primary route chains the existing game-entry hooks. After a failed attempt is rolled back, it may hook the validated MarkerPatch callbacks instead. Unknown image layouts or chains fail closed. Detailed hook errors are written to SeveredPowerNodeFix.log next to the ASI when enabled. These callbacks are not claimed as a stable upstream API.

The test suite covers only node scope, other-item rejection, temporary state restoration, price/entitlement preservation, existing-hook chaining and fallback. Constructor/AddEpisode ABI is checked with the module both compiled out and enabled. Gameplay with this node-specific draft remains unverified; do not treat it as ready to merge.

Sources: https://github.com/Tubzbuster/DS2SeveredPC (base 051fad379a7fdd9598a3e7fb96279f393ba91730), https://github.com/Wemino/MarkerPatch (reference d40f9ce31175c8fa5d59cca9dc3b417a396076f8). Modified integration is GPL-2.0; upstream notices and complete unmodified SafetyHook/Zydis dependency sources and license headers are retained. The vendor directory is marked vendored for review.

Validation performed for this draft: 33 isolated x86 node/hook checks passed, and constructor/AddEpisode ABI passed with the optional module compiled out and enabled. The original Zig build was not re-run. Game validation remains pending.
