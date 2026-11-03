# Optional standalone Severed save-display fix

The PC load list can show base-game chapter labels/pictures for Severed saves. This opt-in ASI changes only the temporary APX/SP11SaveSlot display output for an identified DLC slot. It does not rewrite saves, alter progress, replace the game's loader, or make DLC saves loadable without the DLC/runtime.

## Build and enable

Use an x86 Visual Studio 2022 Native Tools shell with a Windows SDK:

    build_msvc.cmd

Result: `build/SeveredSaveDisplay.asi`. To run all 109 fixture checks, pass a fresh output directory and a matching preview archive as the first and second arguments. No game data or pictures are needed to build the ASI itself.

Load the ASI from `plugins` with the original MarkerPatch loader. Rename the example to `SeveredSaveDisplay.ini`; set `[SaveDisplay] TitleFix=1` to opt in. `IconFix=1` additionally enables matching preview resources. Missing INI/default 0 installs no display hooks. Restart after changing settings.

English labels are `Severed, chapter 1` and `Severed, chapter 2`. `[Localization] SimplifiedChinese=1` is an optional label choice for an already localized game; this plugin does not install Chinese data/fonts or localize DLC menus. It defaults to English.

## Read-only identification and pictures

- Read at most the first 64 KiB of the 20 expected save files under the Windows Documents game folder. Validate supported RGMH/NMSD/MC02 metadata and bind the exact native slot/controller; do not infer DLC from the chapter number alone.
- Refresh on list population; verify file identity/size/time around the read. Base-game, missing, unknown, corrupt or ambiguous rows retain original display. Save-body checksums and custom save directories are not validated.
- Write only the output title and preview index, preserving chapter, timestamps, difficulty, elapsed time, round, native rows and return flow.
- Pictures use a matching `DS2DAT3.DAT` preview overlay, checked by size and SHA-256. An absent/unknown overlay retains original pictures; titles can work independently. No game archives, saves or artwork are included in the PR.

`tools/build_save_preview_assets.py` reproduces the overlay/delta from a legitimate original `DS2DAT6.DAT`, two supplied chapter pictures and the upstream research Python modules. Run `--help` for paths. The known output contract is in `save_icon_contract.hpp`; other inputs require a reviewed contract update. Original preview frames and compressed image blocks are retained.

## Validation and limits

109 x86 checks cover title languages, both chapter indices, actual MidHook stack/return preservation, unchanged native metadata, missing/replaced/deleted slots, base/unknown rows and archive verification. Both standalone ASIs load together without the port core in a non-game host; shared tests exercise hook-install coordination across DLL copies. Final standalone gameplay across both chapters and platform variants is still pending; this PR remains Draft. Zig builds have not been validated.

Known older combined local fixes cause this candidate to remain inactive; do not also load `SeveredExtras.asi`. The original DLC core, converter and MarkerPatch are unchanged. This does not address the mine interaction issue.

Thank you to Tubzbuster/DS2SeveredPC and Wemino/MarkerPatch. AI participated in analysis and implementation.

---

独立可选 ASI，默认关闭。只修临时存档列表的 DLC 章节名称／预览，不写存档或转换进度；仅 MarkerPatch 负责加载，没有对移植核心的导入依赖。图片需要已验证的配套资源，缺少时保留原图片，原游戏／未知条目保持不变。汉化仍由已有数据补丁提供；本插件只提供已汉化游戏的可选存档文字，不安装汉化数据。DLC 存档仍需 DLC 与运行组件。没有矿区互动修复，独立版本实机仍待验证。感谢作者；AI 参与分析和实现。
