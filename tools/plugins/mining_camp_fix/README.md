# Optional mining-camp initialization fix

After activating a mining-camp terminal and dying after the elevator sequence, all three terminals can remain unavailable on reload (issue #7). The shared TriggerAuto initializer was configured as one-shot. A controlled data-only A/B test changed its Options from 1 to 0: the reload enable event returned, all three distinct progress events were still required, and the next checkpoint was reached. Repeated use of one terminal did not bypass the puzzle.

This opt-in standalone ASI applies that same setting to the exact initializer's loaded parameters after base construction and before its derived event subscription. Identity checks require all four GUID words, the matching object hash, the enable message, zero delay, and exactly Options=1. Other objects and flag combinations remain unchanged. The plugin does not broadcast enable messages, edit progress/enemy counts, or change DAT/save files.

Build from an x86 Visual Studio 2022 Native Tools shell with a Windows SDK:

    build_msvc.cmd

Place `build/SeveredMiningCampFix.asi` and `SeveredMiningCampFix.ini` in `plugins`. Set `[MiningCamp] InitializationFix=1` to opt in; it defaults to 0 and requires a restart. Load with the original MarkerPatch ASI loader. No import or patched version of the DLC core is required. The existing core and other independent fixes can remain installed.

The unique constructor signature and the base constructor's GUID/configuration layout must match. Unknown layouts or non-writable parameters are left unchanged; no page protection is relaxed for the data correction. Hook attachment is serialized with the other independent plugins. The bounded log records attachment and at most eight matching corrections.

Validation: 20 x86 checks cover exact identity/parameter rejection, read-only memory, the one changed option, and a real MidHook preserving stack/register/return behavior. Separate checks against a read-only runtime code capture confirm the actual constructor ABI and reject altered layouts. These checks do not replace gameplay testing. The earlier DAT-only reproduction is validated; this independent ASI still requires live acceptance on an unmodified DAT2. Continuous deaths, revisits after completion, other checkpoints, other executable variants, and Zig builds are not claimed as validated. Keep this PR Draft until that coverage is reviewed.

No game archives, artwork, saves, binary plugins, or runtime captures are included. Thank you to Tubzbuster/DS2SeveredPC and Wemino/MarkerPatch. AI participated in analysis and implementation.

---

独立可选矿区初始化 ASI，默认关闭，对应 Issue #7。此前仅将指定初始化对象 Options 从 1 改为 0 的数据对照已由玩家实测：死亡读档后重新启用，三个面板仍须分别完成，不能重复刷一个面板跳过谜题，之后可进入下一检查点。

本插件只在指定对象构造后修正内存参数，并核对完整 GUID、对象哈希、启用消息、零延时及原始 Options=1；不写 DAT／存档，不广播解锁，不改战斗或进度。20 项原生隔离检查及真实代码布局检查通过。独立 ASI 在未改 DAT2 上的实机验收仍待完成，保留 Draft，不将既有数据对照等同于独立 ASI 已验收。感谢原作者；AI 参与分析与实现。
