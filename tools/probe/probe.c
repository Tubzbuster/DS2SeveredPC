/*
 * Severed hook: a dinput8.dll proxy for Dead Space 2 (PC, 32-bit) that
 * makes the converted Severed DLC playable, then forwards to the real
 * dinput8.dll. Nothing on disk is changed: the game's code is patched in
 * memory only, at places found by byte pattern once the Steam wrapper has
 * decrypted it.
 *
 * What it does:
 *   - adds "Dead Space 2: Severed" to the episode select (the PC has no
 *     DLC loader for the console's weller1.lvl);
 *   - gives Gabe his pre-upgraded Pulse Rifle, as the console DLC does;
 *   - ends Severed the console way: back to the main menu after the
 *     credits, without the base game's New Game+ popup and unlocks;
 *   - F7 sends the level messages listed in severed_send.txt (testing);
 *   - writes a short log, with a crash report, to severed_probe.log next
 *     to deadspace2.exe.
 *
 * The research probe this grew from (file and archive logging, message
 * and sequence traces, Direct3D checks) is in the history up to probe 55
 * (tools/probe/README.md).
 */
#define WIN32_LEAN_AND_MEAN
#include <windows.h>
#include <stdio.h>
#include <stdarg.h>
#include <string.h>

#define HOOK_VERSION "56"

static HANDLE g_log = INVALID_HANDLE_VALUE;
static CRITICAL_SECTION g_cs;
static HMODULE g_real;
static DWORD g_tick0;
static LONG g_lines;
#define MAX_LINES 20000

/* ---- logging ---------------------------------------------------------- */

static void log_line(const char *fmt, ...)
{
    char buf[1024];
    va_list ap;
    int n, m;
    DWORD w;

    if (g_log == INVALID_HANDLE_VALUE || InterlockedIncrement(&g_lines) > MAX_LINES) return;
    n = _snprintf(buf, sizeof buf, "%8lu [%5lu] ", GetTickCount() - g_tick0, GetCurrentThreadId());
    if (n < 0) n = 0;
    va_start(ap, fmt);
    m = _vsnprintf(buf + n, sizeof buf - n - 2, fmt, ap);
    va_end(ap);
    if (m < 0) m = (int)(sizeof buf - n - 3);
    n += m;
    buf[n++] = '\r';
    buf[n++] = '\n';
    EnterCriticalSection(&g_cs);
    WriteFile(g_log, buf, n, &w, NULL);
    LeaveCriticalSection(&g_cs);
}

/* a file next to deadspace2.exe */
static void game_file(char *path, const char *name)
{
    char *slash;
    GetModuleFileNameA(NULL, path, MAX_PATH);
    slash = strrchr(path, '\\');
    if (slash) lstrcpyA(slash + 1, name);
}

/* ---- memory and code patterns ----------------------------------------- */

static int mem_ok(const void *p, SIZE_T n)
{
    MEMORY_BASIC_INFORMATION mi;
    if (!p || !VirtualQuery(p, &mi, sizeof mi) || mi.State != MEM_COMMIT || (mi.Protect & (PAGE_GUARD | PAGE_NOACCESS)))
        return 0;
    return (BYTE *)p + n <= (BYTE *)mi.BaseAddress + mi.RegionSize;
}

static int parse_sig(const char *s, BYTE *b, BYTE *m)
{
    int n = 0;
    while (*s) {
        if (*s == ' ') { s++; continue; }
        if (s[0] == '?') { b[n] = 0; m[n++] = 0; s += 2; continue; }
        {
            int hi = s[0] <= '9' ? s[0] - '0' : s[0] - 'A' + 10, lo = s[1] <= '9' ? s[1] - '0' : s[1] - 'A' + 10;
            b[n] = (BYTE)(hi * 16 + lo); m[n++] = 1; s += 2;
        }
    }
    return n;
}

/* each match of a pattern in the exe's code section: calls `each` (if
   given) and returns the only match, or NULL (none / several) */
static BYTE *scan_sig(const char *sig, int *count, int (*each)(BYTE *))
{
    BYTE b[256], m[256], *base = (BYTE *)GetModuleHandleA(NULL), *t, *e, *p, *hit = NULL;
    IMAGE_NT_HEADERS *nt = (IMAGE_NT_HEADERS *)(base + ((IMAGE_DOS_HEADER *)base)->e_lfanew);
    IMAGE_SECTION_HEADER *sec = IMAGE_FIRST_SECTION(nt);
    int n = parse_sig(sig, b, m), i;
    *count = 0;
    t = base + sec->VirtualAddress;
    e = t + sec->Misc.VirtualSize - n;
    if (!mem_ok(t, sec->Misc.VirtualSize)) return NULL;
    for (p = t; p < e; p++) {
        if (*p != b[0]) continue;
        for (i = 1; i < n && (!m[i] || p[i] == b[i]); i++) ;
        if (i < n) continue;
        (*count)++; hit = p;
        if (each && each(p)) return p;
    }
    return *count == 1 ? hit : NULL;
}

static BYTE *find_sig(const char *sig, int *count)
{
    return scan_sig(sig, count, NULL);
}

static DWORD exe_off(const void *p)
{
    return p ? (DWORD)p - (DWORD)GetModuleHandleA(NULL) : 0;
}

/* code stub: pushad/pushfd, call cb(reg) (reg given by its push opcode:
   0x51 ecx, 0x56 esi), restore, run the original first `len` bytes (no
   relative operands), jump back. The stub stays for the process's life. */
static int hook_call_reg(BYTE *fn, int len, void (__cdecl *cb)(void *), BYTE push_op)
{
    BYTE *t = (BYTE *)VirtualAlloc(NULL, 64, MEM_COMMIT | MEM_RESERVE, PAGE_EXECUTE_READWRITE), *q;
    DWORD old;
    if (!t) return 0;
    q = t;
    *q++ = 0x60; *q++ = 0x9C;                      /* pushad, pushfd */
    *q++ = push_op;                                /* push reg */
    *q++ = 0xE8; *(DWORD *)q = (DWORD)cb - (DWORD)(q + 4); q += 4;
    *q++ = 0x83; *q++ = 0xC4; *q++ = 0x04;         /* add esp, 4 */
    *q++ = 0x9D; *q++ = 0x61;                      /* popfd, popad */
    memcpy(q, fn, len); q += len;
    *q++ = 0xE9; *(DWORD *)q = (DWORD)(fn + len) - (DWORD)(q + 4); q += 4;
    if (!VirtualProtect(fn, len, PAGE_EXECUTE_READWRITE, &old)) { VirtualFree(t, 0, MEM_RELEASE); return 0; }
    fn[0] = 0xE9; *(DWORD *)(fn + 1) = (DWORD)t - (DWORD)(fn + 5);
    if (len > 5) memset(fn + 5, 0x90, len - 5);
    VirtualProtect(fn, len, old, &old);
    FlushInstructionCache(GetCurrentProcess(), fn, len);
    return 1;
}

/* as hook_call_reg, but cb gets the stack word at `off` from the entry
   stack pointer (4 = first argument) */
static int hook_call_arg(BYTE *fn, int len, void (__cdecl *cb)(const void *), int off)
{
    BYTE *t = (BYTE *)VirtualAlloc(NULL, 64, MEM_COMMIT | MEM_RESERVE, PAGE_EXECUTE_READWRITE), *q;
    DWORD old;
    if (!t) return 0;
    q = t;
    *q++ = 0x60; *q++ = 0x9C;                      /* pushad, pushfd */
    *q++ = 0xFF; *q++ = 0x74; *q++ = 0x24; *q++ = (BYTE)(0x24 + off);   /* push [entry esp + off] */
    *q++ = 0xE8; *(DWORD *)q = (DWORD)cb - (DWORD)(q + 4); q += 4;
    *q++ = 0x83; *q++ = 0xC4; *q++ = 0x04;         /* add esp, 4 */
    *q++ = 0x9D; *q++ = 0x61;                      /* popfd, popad */
    memcpy(q, fn, len); q += len;
    *q++ = 0xE9; *(DWORD *)q = (DWORD)(fn + len) - (DWORD)(q + 4); q += 4;
    if (!VirtualProtect(fn, len, PAGE_EXECUTE_READWRITE, &old)) { VirtualFree(t, 0, MEM_RELEASE); return 0; }
    fn[0] = 0xE9; *(DWORD *)(fn + 1) = (DWORD)t - (DWORD)(fn + 5);
    if (len > 5) memset(fn + 5, 0x90, len - 5);
    VirtualProtect(fn, len, old, &old);
    FlushInstructionCache(GetCurrentProcess(), fn, len);
    return 1;
}

/* ---- Windows API hook (PeekMessage) ------------------------------------
 * A hot-patch hook: the 5 padding bytes before the function become a jump
 * to ours and its 2-byte `mov edi,edi` a short jump back to them. */
static int hotpatch(BYTE *fn, void *hook, void **orig)
{
    BYTE *pad = fn - 5;
    DWORD old;
    int i;
    if (fn[0] != 0x8B || fn[1] != 0xFF) return 0;                   /* mov edi,edi */
    for (i = 0; i < 5; i++) if (pad[i] != 0x90 && pad[i] != 0xCC) return 0;
    if (!VirtualProtect(pad, 7, PAGE_EXECUTE_READWRITE, &old)) return 0;
    *orig = fn + 2;
    pad[0] = 0xE9;                                                   /* jmp hook */
    *(DWORD *)(pad + 1) = (DWORD)((BYTE *)hook - (pad + 5));
    *(volatile WORD *)fn = 0xF9EB;                                   /* jmp short -7 */
    VirtualProtect(pad, 7, old, &old);
    FlushInstructionCache(GetCurrentProcess(), pad, 7);
    return 1;
}

/* Length of one instruction from the small set found at the start of
   Windows API functions, or 0 if it cannot be relocated safely. */
static int insn_len(const BYTE *p)
{
    if (p[0] >= 0x50 && p[0] <= 0x57) return 1;                 /* push reg */
    if (p[0] == 0x6A) return 2;                                 /* push imm8 */
    if (p[0] == 0x68) return 5;                                 /* push imm32 */
    if (p[0] == 0x8B && (p[1] == 0xFF || p[1] == 0xEC)) return 2; /* mov edi,edi / mov ebp,esp */
    if (p[0] == 0x83 && p[1] == 0xEC) return 3;                 /* sub esp, imm8 */
    if (p[0] == 0x81 && p[1] == 0xEC) return 6;                 /* sub esp, imm32 */
    if (p[0] == 0x33 && (p[1] & 0xC0) == 0xC0) return 2;        /* xor reg, reg */
    if (p[0] == 0x64 && p[1] == 0xA1) return 6;                 /* mov eax, fs:[imm32] */
    return 0;
}

/* Classic detour: copy the first >=5 bytes of whole instructions to a
   trampoline that jumps back, then put a jmp to the hook at the start. */
static int trampoline(BYTE *fn, void *hook, void **orig)
{
    int len = 0, l;
    BYTE *t;
    DWORD old;
    while (len < 5) {
        if ((l = insn_len(fn + len)) == 0) return 0;
        len += l;
    }
    t = (BYTE *)VirtualAlloc(NULL, 32, MEM_COMMIT | MEM_RESERVE, PAGE_EXECUTE_READWRITE);
    if (!t) return 0;
    memcpy(t, fn, len);
    t[len] = 0xE9;
    *(DWORD *)(t + len + 1) = (DWORD)((fn + len) - (t + len + 5));
    FlushInstructionCache(GetCurrentProcess(), t, 32);
    if (!VirtualProtect(fn, len, PAGE_EXECUTE_READWRITE, &old)) { VirtualFree(t, 0, MEM_RELEASE); return 0; }
    *orig = t;
    fn[0] = 0xE9;
    *(DWORD *)(fn + 1) = (DWORD)((BYTE *)hook - (fn + 5));
    for (l = 5; l < len; l++) fn[l] = 0x90;
    VirtualProtect(fn, len, old, &old);
    FlushInstructionCache(GetCurrentProcess(), fn, len);
    return 1;
}

static void install(const char *name, void *hook, void **orig)
{
    HMODULE m = GetModuleHandleA("user32.dll");
    BYTE *fn;
    if (!m) m = LoadLibraryA("user32.dll");
    fn = m ? (BYTE *)GetProcAddress(m, name) : NULL;
    if (!fn) { log_line("could not find %s", name); return; }
    if (hotpatch(fn, hook, orig)) log_line("hooked %s (hot-patch)", name);
    else if (trampoline(fn, hook, orig)) log_line("hooked %s (trampoline)", name);
    else log_line("could not hook %s (first bytes %02X %02X %02X %02X %02X)", name, fn[0], fn[1], fn[2], fn[3], fn[4]);
}

/* ---- Severed in the episode select ------------------------------------
 * front end constructor: stores `this` in the front end global and builds
 * the episode list at this + 0x980 (0x68-byte entries: +0x20 folder).
 * AddEpisode: thiscall, 8 arguments (ret 0x20): name, description,
 * folder, stream list, checkpoint, flags, unlock key, extra; the console's
 * DLC path (.lvl) calls it with weller1.lvl's fields. The constructor is
 * hooked so Severed is added on the game's own thread right after the
 * built-in episode (calling AddEpisode from another thread hangs the
 * game). It starts with push ebx / push ebp / push esi / mov esi, ecx (5
 * bytes, no relative operands), which the trampoline re-runs. */
static const char SIG_ADD[] =
    "56 81 C1 80 09 00 00 E8 ?? ?? ?? ?? 8B F0 8B 44 24 08 50 8B CE E8 ?? ?? ?? ?? 8B 4C 24 0C 51 8D 4E 10 "
    "E8 ?? ?? ?? ?? 8B 54 24 10 52 8D 4E 20 E8 ?? ?? ?? ?? 8B 44 24 14 50 8D 4E 30 E8 ?? ?? ?? ?? 8B 4C 24 24 "
    "51 8D 4E 40 E8 ?? ?? ?? ?? 8B 54 24 18 52 8D 4E 50 E8 ?? ?? ?? ?? 8B 44 24 1C 8B 4C 24 20 89 46 60 89 4E "
    "64 5E C2 20 00";
static const char SIG_CTOR[] =
    "53 55 56 8B F1 89 35 ?? ?? ?? ?? C7 46 04 ?? ?? ?? ?? 33 DB 89 5E 0C 57 8D 7E 04 BD 01 00 00 00 89 6F 04 "
    "C7 06 ?? ?? ?? ?? C7 07 ?? ?? ?? ?? 89 5E 30 89 5E 38 8D 4E 48 89 5E 3C 89 5E 40 89 5E 44";

typedef void (__attribute__((thiscall)) *add_episode_fn)(void *self, const char *name, const char *desc,
        const char *folder, const char *streams, const char *checkpoint, int flags, int unlock, const char *extra);
typedef void *(__attribute__((thiscall)) *ctor_fn)(void *self);
static ctor_fn g_ctor_tramp;
static add_episode_fn g_add;

static void *__attribute__((thiscall)) hook_frontend_ctor(void *self)
{
    void *r = g_ctor_tramp(self);
    g_add(self, "Dead Space 2: Severed", "Gabe Weller's story",
          "pdlc1_ch01_mng", "pdlc1_ch01_mng.str", "XONTREALPR_CB22182_E50854D_v3", 0, 0, NULL);
    log_line("front end: Severed added to the episode list");
    return r;
}

static int hook_episode_list(BYTE *add, BYTE *ctor)
{
    BYTE *t = (BYTE *)VirtualAlloc(NULL, 16, MEM_COMMIT | MEM_RESERVE, PAGE_EXECUTE_READWRITE);
    DWORD old;
    if (!t) return 0;
    memcpy(t, ctor, 5);
    t[5] = 0xE9; *(DWORD *)(t + 6) = (DWORD)(ctor + 5) - (DWORD)(t + 10);
    g_ctor_tramp = (ctor_fn)t;
    g_add = (add_episode_fn)add;
    if (!VirtualProtect(ctor, 5, PAGE_EXECUTE_READWRITE, &old)) { VirtualFree(t, 0, MEM_RELEASE); return 0; }
    ctor[0] = 0xE9; *(DWORD *)(ctor + 1) = (DWORD)hook_frontend_ctor - (DWORD)(ctor + 5);
    VirtualProtect(ctor, 5, old, &old);
    FlushInstructionCache(GetCurrentProcess(), ctor, 5);
    return 1;
}

/* ---- level start ------------------------------------------------------
 * Level start (retail exe 0x0042C600, this = level start request, +0x28 =
 * folder string): notes the game thread and whether Severed is loaded. */
static const char SIG_LEVELSTART[] =
    "81 EC 40 01 00 00 53 55 8B E9 C7 45 18 07 00 00 00 A1 ?? ?? ?? ?? 8B 40 38 D1 E8 24 01 88 44 24 0A 8A 45 1C "
    "D0 E8 24 01 83 7D 4C 00 56 8D 75 28 88 44 24 0F 8B 06 0F 95 44 24 10 57 85 C0 75 05 B8 ?? ?? ?? ?? 68 ?? ?? ?? ?? "
    "50 E8 ?? ?? ?? ?? 8B 0D ?? ?? ?? ??";
static volatile DWORD g_game_thread;
static volatile int g_severed_level;
static void upgrade_schedule(const char *why);

static void __cdecl on_level_start(void *self)
{
    const char *folder = self && mem_ok((BYTE *)self + 0x28, 4) ? *(const char **)((BYTE *)self + 0x28) : NULL;
    char name[128];
    int n;
    if (!folder || !mem_ok(folder, 1)) return;
    log_line("level start: folder %s", folder);
    g_game_thread = GetCurrentThreadId();
    lstrcpynA(name, folder, sizeof name);
    n = lstrlenA(name);
    while (n && (name[n - 1] == '\\' || name[n - 1] == '/')) name[--n] = 0;
    g_severed_level = !lstrcmpiA(name, "pdlc1_ch01_mng");
    if (g_severed_level) upgrade_schedule("Severed level start");
}

/* ---- Gabe's pre-upgraded Pulse Rifle -----------------------------------
 * On console a Severed-only object (class 2B747EB6, neutralised by the
 * converter) buys 10 Pulse Rifle nodes on `equip_player_upgrade_nodes`.
 * The PC keeps the same state in its UpgradeManager (global read from the
 * Lua getter `GetUpgradeManager`): weapon trees at +0x18 (an inline array
 * of pointers, count at +0x18+0xC8), each tree: name hash +0, node
 * pointers inline from +4, count +0x170; each node: name hash +0, bought
 * flag +0x2C. Hashes are sdbm of the lower-case name. The nodes are set a
 * few seconds after the message, and after each Severed level start. */
static const char SIG_UPGMGR[] =
    "83 EC 0C 56 8B 74 24 14 8D 44 24 04 50 6A 00 68 ?? ?? ?? ?? 6A 01 56 E8 ?? ?? ?? ?? 83 C4 14 85 C0 74 33 "
    "8D 4C 24 04 51 6A 02 56 E8 ?? ?? ?? ?? 83 C4 0C 85 C0 74 1F 8B 15 ?? ?? ?? ?? 68";
static const char SIG_TREEFIND[] =   /* checks the tree array layout */
    "56 57 8B B9 C8 00 00 00 33 C0 33 F6 85 FF 76 18 53 8B 5C 24 10 8B 14 B1 85 D2 74 06 39 1A 75 02 8B C2 46 3B F7 72 EE";
static const char SIG_NODEFILL[] =   /* checks the node layout */
    "8B 81 70 01 00 00 56 33 F6 85 C0 76 2A 57 8B 7C 24 0C 83 C1 04 8B D0 8B 01 85 C0 74 06 39 38 75 02 8B F0 "
    "83 C1 04 83 EA 01 75 EC 5F 85 F6 74 07 C7 46 2C 01 00 00 00";
static BYTE **g_upgmgr;
static volatile DWORD g_upg_due;           /* tick when to set the nodes, 0 = nothing pending */
static DWORD g_upg_deadline;
static const char *const g_rifle_nodes[] = {
    "capacity", "capacity2", "damage", "damage3", "reload2", "altdamage", "altdamage2", "pr12", "pr21", "pr23"
};

static DWORD sdbm_lower(const char *s)
{
    DWORD h = 0;
    for (; *s; s++) h = h * 0x1003F + (BYTE)(*s >= 'A' && *s <= 'Z' ? *s + 32 : *s);
    return h;
}

/* the getter whose type name is "UpgradeManager" (the same code shape
   serves other singletons) */
static int is_upgmgr_getter(BYTE *p)
{
    const char *name = *(const char **)(p + 0x10);
    return mem_ok(name, 15) && !lstrcmpA(name, "UpgradeManager");
}

static BYTE **find_upgmgr(void)
{
    int c = 0;
    BYTE *p;
    if (!find_sig(SIG_TREEFIND, &c) || !find_sig(SIG_NODEFILL, &c)) return NULL;
    p = scan_sig(SIG_UPGMGR, &c, is_upgmgr_getter);
    return p && is_upgmgr_getter(p) ? *(BYTE ***)(p + 0x39) : NULL;
}

static void upgrade_rifle(void)
{
    BYTE *mgr, *tree = NULL, *node;
    DWORD i, k, n, rifle = sdbm_lower("pulserifle");
    int set = 0, had = 0, missing = 0;
    if (!g_upgmgr || !mem_ok(g_upgmgr, 4) || !(mgr = *g_upgmgr) || !mem_ok(mgr + 0x18, 0xCC)) return;
    n = *(DWORD *)(mgr + 0x18 + 0xC8);
    for (i = 0; i < n && i < 50; i++) {
        BYTE *t = ((BYTE **)(mgr + 0x18))[i];
        if (t && mem_ok(t, 0x174) && *(DWORD *)t == rifle) tree = t;
    }
    if (!tree) {
        if (GetTickCount() > g_upg_deadline) {
            log_line("pulse rifle upgrades: no Pulse Rifle tree (%lu trees) - gave up", n);
            g_upg_due = 0;
        }
        return;                            /* the trees may not exist yet: retry */
    }
    g_upg_due = 0;
    n = *(DWORD *)(tree + 0x170);
    for (k = 0; k < sizeof g_rifle_nodes / sizeof *g_rifle_nodes; k++) {
        DWORD h = sdbm_lower(g_rifle_nodes[k]);
        BYTE *found = NULL;
        for (i = 0; i < n && i < 92; i++) {
            node = ((BYTE **)(tree + 4))[i];
            if (node && mem_ok(node, 0x30) && *(DWORD *)node == h) found = node;
        }
        if (!found) { missing++; continue; }
        if (*(DWORD *)(found + 0x2C) == 1) had++;
        else { *(DWORD *)(found + 0x2C) = 1; set++; }
    }
    log_line("pulse rifle upgrades: %d node(s) set, %d already bought, %d missing", set, had, missing);
}

static void upgrade_schedule(const char *why)
{
    if (!g_upgmgr) return;
    g_upg_deadline = GetTickCount() + 63000;
    g_upg_due = GetTickCount() + 3000;
    log_line("pulse rifle upgrades: scheduled (%s)", why);
}

/* ---- level messages ---------------------------------------------------
 * exe 0x756C60 sends a level message (arg 1: message, name hash at +0).
 * The hook watches for `equip_player_upgrade_nodes` and sets the rifle
 * nodes when due, on the game thread. */
static const char SIG_MSGSEND[] =
    "51 8B 54 24 08 8B 0A 56 8B F1 57 8B 3D ?? ?? ?? ?? 81 E6 FF 0F 00 00 8B 34 B7 32 C0 85 F6";
static DWORD g_equip_hash;

static void __cdecl note_msgsend(const void *arg)
{
    const DWORD *msg = (const DWORD *)arg;
    if (!msg || !mem_ok(msg, 4)) return;
    if (msg[0] == g_equip_hash && g_severed_level) upgrade_schedule("equip_player_upgrade_nodes");
    if (g_upg_due && (LONG)(GetTickCount() - g_upg_due) >= 0 && GetCurrentThreadId() == g_game_thread)
        upgrade_rifle();
}

/* ---- F7: send level messages (testing) ---------------------------------
 * The engine's message broadcast (retail exe 0x0084F5A0, behind Lua's
 * SendMessage): cdecl (message name, unused, payload). F7 sends each line
 * of severed_send.txt in the game folder, on the game's thread (from its
 * message loop, PeekMessage hook). */
static const char SIG_SENDMSG[] =
    "83 EC 14 8B 54 24 18 33 C0 66 89 44 24 04 52 8D 44 24 04 33 C9 50 C7 44 24 08 00 00 00 00 66 89 4C 24 0E "
    "E8 ?? ?? ?? ?? 8B 4C 24 08 8B 54 24 28 8D 44 24 10 6A 00 50 89 4C 24 18 C6 44 24 1C 00 89 54 24 20 "
    "E8 ?? ?? ?? ?? 8D 4C 24 10 51 E8 ?? ?? ?? ?? 83 C4 28 C3";
typedef void (__cdecl *send_msg_fn)(const char *name, const char *unused, void *payload);
static send_msg_fn g_sendmsg;
#define MAX_MSGS 32
static char g_msgs[MAX_MSGS][96];
static volatile LONG g_msgs_pending;
static int g_nmsgs;

static void queue_message_file(void)
{
    char path[MAX_PATH], buf[4096], *line;
    HANDLE f;
    DWORD got = 0;
    int n = 0;
    if (g_msgs_pending) { log_line("F7: the last messages are still being sent - try again"); return; }
    if (!g_sendmsg) { log_line("F7: the game's message function was not found - nothing sent"); return; }
    game_file(path, "severed_send.txt");
    f = CreateFileA(path, GENERIC_READ, FILE_SHARE_READ, NULL, OPEN_EXISTING, 0, NULL);
    if (f == INVALID_HANDLE_VALUE) { log_line("F7: no severed_send.txt in the game folder"); return; }
    if (!ReadFile(f, buf, sizeof buf - 1, &got, NULL)) got = 0;
    CloseHandle(f);
    buf[got] = 0;
    for (line = strtok(buf, "\r\n"); line && n < MAX_MSGS; line = strtok(NULL, "\r\n")) {
        while (*line == ' ' || *line == '\t') line++;
        if (*line && *line != '#') lstrcpynA(g_msgs[n++], line, sizeof g_msgs[0]);
    }
    g_nmsgs = n;
    InterlockedExchange(&g_msgs_pending, 1);   /* the list stays untouched until the game thread sets 0 */
    log_line("F7: %d message(s) queued", n);
}

static void run_pending_messages(void)
{
    int i;
    if (!g_msgs_pending || GetCurrentThreadId() != g_game_thread || !g_sendmsg) return;
    if (InterlockedCompareExchange(&g_msgs_pending, 2, 1) != 1) return;
    for (i = 0; i < g_nmsgs; i++) {
        log_line("send message %s", g_msgs[i]);
        g_sendmsg(g_msgs[i], NULL, NULL);
    }
    InterlockedExchange(&g_msgs_pending, 0);
    MessageBeep(MB_ICONASTERISK);
}

typedef BOOL (WINAPI *PeekMessage_t)(LPMSG, HWND, UINT, UINT, UINT);
static PeekMessage_t o_PeekMessageA, o_PeekMessageW;
static BOOL WINAPI h_PeekMessageA(LPMSG m, HWND w, UINT a, UINT b, UINT r) { run_pending_messages(); return o_PeekMessageA(m, w, a, b, r); }
static BOOL WINAPI h_PeekMessageW(LPMSG m, HWND w, UINT a, UINT b, UINT r) { run_pending_messages(); return o_PeekMessageW(m, w, a, b, r); }

static DWORD WINAPI hotkey_thread(LPVOID p)
{
    (void)p;
    for (;;) {
        Sleep(200);
        /* with Alt, Ctrl or Shift held the key belongs to other programs */
        if ((GetAsyncKeyState(VK_MENU) | GetAsyncKeyState(VK_CONTROL) | GetAsyncKeyState(VK_SHIFT)) & 0x8000) {
            while (GetAsyncKeyState(VK_F7) & 0x8000) Sleep(100);
            continue;
        }
        if (GetAsyncKeyState(VK_F7) & 0x8000) {
            if (!g_game_thread) log_line("F7: start a level first");
            else queue_message_file();
            while (GetAsyncKeyState(VK_F7) & 0x8000) Sleep(100);
        }
    }
    return 0;
}

/* ---- Severed's ending: no New Game+ ------------------------------------
 * On the console Severed's ending goes straight back to the main menu.
 * The base game's end-of-game sequence (retail 0xA92A80, state at +0x24)
 * would show the "save for New Game+" popup (state 0xA), record the
 * completion (0xC), award the unlocks (3) and show New Unlocks (4) before
 * its return to the main menu (0xE). Hooked at the state dispatch
 * (mov eax, [esi+0x24]; dec eax; cmp eax, 0xD): in the Severed level,
 * state 0xA becomes 0xE. */
static const char SIG_EOG_STATE[] = "8B 46 24 48 83 F8 0D 0F 87 ?? ?? ?? ?? FF 24 85";

static void __cdecl note_eog_state(void *o)
{
    DWORD *st = (DWORD *)((BYTE *)o + 0x24);
    if (g_severed_level && mem_ok(st, 4) && *st == 0xA) {
        log_line("end of game: Severed - back to the main menu (no New Game+ popup or unlocks)");
        *st = 0xE;
    }
}

/* ---- installing the game hooks -----------------------------------------
 * The Steam wrapper decrypts the code shortly after start, some parts later
 * than others: each pattern is retried for up to a minute. */
static DWORD WINAPI hook_thread(LPVOID p)
{
    BYTE *add = NULL, *ctor = NULL, *ls = NULL, *ms = NULL, *eog = NULL;
    int na = 0, nc = 0, nl = 0, nm = 0, ne = 0, ns = 0, tries, episodes = 0, level = 0, msgs = 0, ending = 0;
    (void)p;
    g_equip_hash = sdbm_lower("equip_player_upgrade_nodes");
    for (tries = 0; tries < 6000 && !(add && ctor); tries++) {
        add = find_sig(SIG_ADD, &na);
        ctor = find_sig(SIG_CTOR, &nc);
        if (!(add && ctor)) Sleep(10);
    }
    episodes = add && ctor && hook_episode_list(add, ctor);
    log_line("episode list: AddEpisode %d match(es) at exe+0x%lx, front end %d match(es) at exe+0x%lx%s",
             na, exe_off(add), nc, exe_off(ctor), episodes ? ", hooked" : " - Severed NOT added");
    for (tries = 0; tries < 300; tries++) {
        if (!ls) ls = find_sig(SIG_LEVELSTART, &nl);
        if (!ms) ms = find_sig(SIG_MSGSEND, &nm);
        if (!eog) eog = find_sig(SIG_EOG_STATE, &ne);
        if (!g_sendmsg) g_sendmsg = (send_msg_fn)find_sig(SIG_SENDMSG, &ns);
        if (!g_upgmgr) g_upgmgr = find_upgmgr();
        if (ls && ms && eog && g_sendmsg && g_upgmgr) break;
        Sleep(200);
    }
    level = ls && hook_call_reg(ls, 6, on_level_start, 0x51);
    msgs = ms && hook_call_arg(ms, 5, note_msgsend, 4);
    ending = eog && hook_call_reg(eog, 7, note_eog_state, 0x56);
    log_line("level start: %d match(es) at exe+0x%lx%s", nl, exe_off(ls), level ? ", hooked" : "");
    log_line("level messages: %d match(es) at exe+0x%lx%s", nm, exe_off(ms), msgs ? ", hooked" : "");
    log_line("end of game: %d match(es) at exe+0x%lx%s", ne, exe_off(eog), ending ? ", hooked" : "");
    log_line("message send (F7): %d match(es) at exe+0x%lx", ns, exe_off(g_sendmsg));
    log_line("upgrade manager: %s", g_upgmgr ? "found" : "not found (no Pulse Rifle upgrades)");
    return 0;
}

/* ---- crash report -------------------------------------------------------
 * A vectored handler logs the first serious exceptions: code, where (module
 * + offset), the faulting data address, registers and the return addresses
 * found on the stack (module + offset only). */
static void addr_name(DWORD a, char *out)
{
    HMODULE m = NULL;
    char path[MAX_PATH], *b;
    if (GetModuleHandleExA(GET_MODULE_HANDLE_EX_FLAG_FROM_ADDRESS | GET_MODULE_HANDLE_EX_FLAG_UNCHANGED_REFCOUNT,
                           (LPCSTR)a, &m) && m && GetModuleFileNameA(m, path, sizeof path)) {
        b = strrchr(path, '\\');
        wsprintfA(out, "%s+0x%lx", b ? b + 1 : path, a - (DWORD)m);
    } else wsprintfA(out, "0x%08lx", a);
}

static LONG WINAPI crash_handler(EXCEPTION_POINTERS *e)
{
    static LONG count;
    static volatile DWORD seen[32];             /* addresses already reported */
    EXCEPTION_RECORD *r = e->ExceptionRecord;
    CONTEXT *c = e->ContextRecord;
    char where[MAX_PATH + 32];
    DWORD *sp, i, found = 0;
    if (r->ExceptionCode < 0xC0000000 || r->ExceptionCode == 0xC0000027 /* unwind */ ||
        r->ExceptionCode == 0xE06D7363 /* C++ throw */ || !g_game_thread /* start-up: the DRM uses exceptions */)
        return EXCEPTION_CONTINUE_SEARCH;
    /* an exception the game handles itself can repeat: report each address once */
    for (i = 0; i < 32; i++)
        if (seen[i] == (DWORD)r->ExceptionAddress) return EXCEPTION_CONTINUE_SEARCH;
    if (InterlockedIncrement(&count) > 10) return EXCEPTION_CONTINUE_SEARCH;
    seen[(count - 1) & 31] = (DWORD)r->ExceptionAddress;
    addr_name((DWORD)r->ExceptionAddress, where);
    log_line("EXCEPTION 0x%08lx at %s thread %lu", r->ExceptionCode, where, GetCurrentThreadId());
    if (r->ExceptionCode == 0xC0000005 && r->NumberParameters >= 2)
        log_line("  %s address 0x%08lx", r->ExceptionInformation[0] == 0 ? "reading" : r->ExceptionInformation[0] == 1 ? "writing" : "executing",
                 (DWORD)r->ExceptionInformation[1]);
    log_line("  eax %08lx ebx %08lx ecx %08lx edx %08lx esi %08lx edi %08lx ebp %08lx esp %08lx",
             c->Eax, c->Ebx, c->Ecx, c->Edx, c->Esi, c->Edi, c->Ebp, c->Esp);
    sp = (DWORD *)c->Esp;
    for (i = 0; i < 2048 && found < 24 && mem_ok(sp + i, 4); i++) {
        MEMORY_BASIC_INFORMATION mi;
        DWORD v = sp[i];
        if (v < 0x10000 || !VirtualQuery((void *)v, &mi, sizeof mi) || mi.State != MEM_COMMIT ||
            !(mi.Protect & (PAGE_EXECUTE | PAGE_EXECUTE_READ | PAGE_EXECUTE_READWRITE | PAGE_EXECUTE_WRITECOPY)))
            continue;
        addr_name(v, where);
        log_line("  stack +0x%03lx %s", i * 4, where);
        found++;
    }
    return EXCEPTION_CONTINUE_SEARCH;
}

/* ---- start ------------------------------------------------------------ */

static void start(void)
{
    char path[MAX_PATH];
    OSVERSIONINFOA vi;

    InitializeCriticalSection(&g_cs);
    g_tick0 = GetTickCount();
    game_file(path, "severed_probe.log");
    g_log = CreateFileA(path, GENERIC_WRITE, FILE_SHARE_READ, NULL, CREATE_ALWAYS, FILE_ATTRIBUTE_NORMAL, NULL);
    log_line("severed hook " HOOK_VERSION);
    vi.dwOSVersionInfoSize = sizeof vi;
#pragma GCC diagnostic ignored "-Wdeprecated-declarations"
    if (GetVersionExA(&vi)) log_line("windows %lu.%lu build %lu", vi.dwMajorVersion, vi.dwMinorVersion, vi.dwBuildNumber);
    install("PeekMessageA", (void *)h_PeekMessageA, (void **)&o_PeekMessageA);
    install("PeekMessageW", (void *)h_PeekMessageW, (void **)&o_PeekMessageW);
    CloseHandle(CreateThread(NULL, 0, hotkey_thread, NULL, 0, NULL));
    CloseHandle(CreateThread(NULL, 0, hook_thread, NULL, 0, NULL));
    AddVectoredExceptionHandler(1, crash_handler);
}

/* ---- dinput8 forwarding ----------------------------------------------- */

static FARPROC real(const char *name)
{
    if (!g_real) {
        char p[MAX_PATH];
        GetSystemDirectoryA(p, MAX_PATH);   /* SysWOW64 for a 32-bit process */
        lstrcatA(p, "\\dinput8.dll");
        g_real = LoadLibraryA(p);
        log_line("real dinput8: %s", g_real ? "loaded" : "FAILED to load");
    }
    return g_real ? GetProcAddress(g_real, name) : NULL;
}

HRESULT WINAPI DirectInput8Create(HINSTANCE h, DWORD v, REFIID r, LPVOID *o, LPVOID u)
{
    typedef HRESULT (WINAPI *fn_t)(HINSTANCE, DWORD, REFIID, LPVOID *, LPVOID);
    fn_t f = (fn_t)real("DirectInput8Create");
    return f ? f(h, v, r, o, u) : E_FAIL;
}

HRESULT WINAPI DllCanUnloadNow(void)
{
    typedef HRESULT (WINAPI *fn_t)(void);
    fn_t f = (fn_t)real("DllCanUnloadNow");
    return f ? f() : S_FALSE;
}

HRESULT WINAPI DllGetClassObject(REFCLSID c, REFIID r, LPVOID *o)
{
    typedef HRESULT (WINAPI *fn_t)(REFCLSID, REFIID, LPVOID *);
    fn_t f = (fn_t)real("DllGetClassObject");
    return f ? f(c, r, o) : E_FAIL;
}

HRESULT WINAPI DllRegisterServer(void)
{
    typedef HRESULT (WINAPI *fn_t)(void);
    fn_t f = (fn_t)real("DllRegisterServer");
    return f ? f() : E_FAIL;
}

HRESULT WINAPI DllUnregisterServer(void)
{
    typedef HRESULT (WINAPI *fn_t)(void);
    fn_t f = (fn_t)real("DllUnregisterServer");
    return f ? f() : E_FAIL;
}

BOOL WINAPI DllMain(HINSTANCE inst, DWORD reason, LPVOID reserved)
{
    (void)reserved;
    if (reason == DLL_PROCESS_ATTACH) {
        DisableThreadLibraryCalls(inst);
        start();
    }
    return TRUE;
}
