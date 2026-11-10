# Optional standalone Severed Power Node fix

When the first Severed store omits Power Nodes, this candidate tries the existing chapter/round bypass byte for the Power Node GUID only, inside a store-list call and only in the Severed campaign. The original value is restored after the call, including on Windows exceptions. Prices, entitlements, other merchandise and base-game store policy are unchanged.

## Build and enable

Use an x86 Visual Studio 2022 Native Tools shell with a Windows SDK:

    build_msvc.cmd <compatible-original-game.exe>

The result is `build/SeveredPowerNodeFix.asi`. The optional argument runs the observer fixture checks; policy checks run without it. No game data is needed to build the ASI.

1. Use the original MarkerPatch loader (`LoadASIPlugins=1`) and put this ASI in the game's `plugins` folder. The normal DLC data/core are still required to play the DLC; this plugin does not import or modify `SeveredPC.asi`.
2. Rename the example to `SeveredNodeFix.ini` beside the ASI and set `[Shop] EnablePowerNodeShopFix=1`. Missing INI or value 0 leaves it disabled. Restart after changing settings.
3. This candidate still requires MarkerPatch's `EnableHackerDLC=1` shop hooks. That upstream switch also exposes base-game Hacker equipment. It does not enable Ignition rooms.

The independent level observer attaches after the original 86-byte entry signature, leaving the port's entry hook intact. Known older combined local fixes cause this candidate to remain inactive, avoiding duplicate implementations. Do not combine it with `SeveredExtras.asi`.

## Validation and limits

33 node-only policy checks and 33 independent observer/hook-order checks pass with x86 MSVC. The shared support tests check coordination between separate DLL copies; both standalone candidates can load together without the DLC core in a non-game host. Supported retail/current address layouts and known MarkerPatch shop callbacks are required; unsupported layouts stay inactive. Standalone gameplay still needs broader validation, so the PR remains Draft. Zig builds have not been validated.

This does not address mine/checkpoint interaction problems. The original probe/core, converter and its build scripts remain unchanged.

Thank you to Tubzbuster/DS2SeveredPC and Wemino/MarkerPatch for the port, fixes and guidance. AI participated in analysis and implementation.

---

独立可选 ASI；默认关闭，只尝试恢复 DLC 商店中的能量节点，价格与其他商品不变。加载器使用原版 MarkerPatch，不修改或导入原移植核心。仍需 DLC 数据／运行核心才能游玩；EnableHackerDLC 的本体黑客装备影响保留，不开放 Ignition 房间。没有矿区互动修复，独立版本实机仍待扩展验证。感谢作者；AI 参与分析和实现。
