/*
 * Severed probe: a dinput8.dll proxy for Dead Space 2 (PC, 32-bit) that
 * logs every file the game tries to open or look up, then forwards to the
 * real dinput8.dll. It changes nothing about how the game behaves.
 *
 * Output: severed_probe.log next to deadspace2.exe.
 *
 * Version 2 also tracks reads from the game's archives (DS2DAT*.DAT,
 * *.viv): when one is opened, the probe reads its directory itself and logs
 * the first read of each entry ("READ DS2DAT6.DAT #C2B10B96 ..."), so we
 * can see which archive each file is actually loaded from.
 *
 * Hooks are "hot-patch" hooks on Windows' own file functions in
 * kernelbase.dll (or kernel32.dll): the 5 padding bytes before the
 * function become a jump to our logger and the 2-byte `mov edi,edi` at the
 * start becomes a short jump back to it. The game's own code is never
 * touched. A function without that standard prologue is left alone and
 * reported in the log.
 */
#define WIN32_LEAN_AND_MEAN
#include <windows.h>
#include <stdio.h>
#include <stdarg.h>

static HANDLE g_log = INVALID_HANDLE_VALUE;
static CRITICAL_SECTION g_cs;
static HMODULE g_real;
static DWORD g_tick0;
static DWORD g_tls = TLS_OUT_OF_INDEXES;
static LONG g_lines;
#define MAX_LINES 300000

/* ---- logging ---------------------------------------------------------- */

static void log_line(const char *fmt, ...)
{
    char buf[4096];
    va_list ap;
    int n, m;
    DWORD w;

    if (g_log == INVALID_HANDLE_VALUE) return;
    if (InterlockedIncrement(&g_lines) > MAX_LINES) return;
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

static void caller_name(void *addr, char *out, int len)
{
    HMODULE mod = NULL;
    char path[MAX_PATH];
    const char *base;

    if (!GetModuleHandleExA(GET_MODULE_HANDLE_EX_FLAG_FROM_ADDRESS | GET_MODULE_HANDLE_EX_FLAG_UNCHANGED_REFCOUNT,
                            (LPCSTR)addr, &mod) || !GetModuleFileNameA(mod, path, sizeof path)) {
        _snprintf(out, len, "%p", addr);
        return;
    }
    base = strrchr(path, '\\');
    base = base ? base + 1 : path;
    _snprintf(out, len, "%s+0x%lx", base, (unsigned long)((char *)addr - (char *)mod));
}

static void wide_to_utf8(LPCWSTR w, char *out, int len)
{
    if (!w) { lstrcpynA(out, "(null)", len); return; }
    if (!WideCharToMultiByte(CP_UTF8, 0, w, -1, out, len, NULL, NULL)) lstrcpynA(out, "(unconvertible)", len);
}

/* Re-entrancy guard: CreateFileA calls CreateFileW internally, and only the
   outermost call should be logged. */
static int enter(void)
{
    LONG_PTR d;
    if (g_tls == TLS_OUT_OF_INDEXES) return 0;
    d = (LONG_PTR)TlsGetValue(g_tls);
    TlsSetValue(g_tls, (LPVOID)(d + 1));
    return d == 0;
}

static void leave(void)
{
    if (g_tls == TLS_OUT_OF_INDEXES) return;
    TlsSetValue(g_tls, (LPVOID)((LONG_PTR)TlsGetValue(g_tls) - 1));
}

static const char *access_str(DWORD a)
{
    if ((a & GENERIC_WRITE) && (a & GENERIC_READ)) return "rw";
    if (a & GENERIC_WRITE) return "w";
    if (a & GENERIC_READ) return "r";
    return "-";
}

/* ---- hooks ------------------------------------------------------------ */

typedef HANDLE (WINAPI *CreateFileA_t)(LPCSTR, DWORD, DWORD, LPSECURITY_ATTRIBUTES, DWORD, DWORD, HANDLE);
typedef HANDLE (WINAPI *CreateFileW_t)(LPCWSTR, DWORD, DWORD, LPSECURITY_ATTRIBUTES, DWORD, DWORD, HANDLE);
typedef HANDLE (WINAPI *FindFirstFileA_t)(LPCSTR, LPWIN32_FIND_DATAA);
typedef HANDLE (WINAPI *FindFirstFileW_t)(LPCWSTR, LPWIN32_FIND_DATAW);
typedef HANDLE (WINAPI *FindFirstFileExA_t)(LPCSTR, FINDEX_INFO_LEVELS, LPVOID, FINDEX_SEARCH_OPS, LPVOID, DWORD);
typedef HANDLE (WINAPI *FindFirstFileExW_t)(LPCWSTR, FINDEX_INFO_LEVELS, LPVOID, FINDEX_SEARCH_OPS, LPVOID, DWORD);
typedef DWORD (WINAPI *GetFileAttributesA_t)(LPCSTR);
typedef DWORD (WINAPI *GetFileAttributesW_t)(LPCWSTR);
typedef BOOL (WINAPI *GetFileAttributesExA_t)(LPCSTR, GET_FILEEX_INFO_LEVELS, LPVOID);
typedef BOOL (WINAPI *GetFileAttributesExW_t)(LPCWSTR, GET_FILEEX_INFO_LEVELS, LPVOID);

static CreateFileA_t o_CreateFileA;
static CreateFileW_t o_CreateFileW;
static FindFirstFileA_t o_FindFirstFileA;
static FindFirstFileW_t o_FindFirstFileW;
static FindFirstFileExA_t o_FindFirstFileExA;
static FindFirstFileExW_t o_FindFirstFileExW;
static GetFileAttributesA_t o_GetFileAttributesA;
static GetFileAttributesW_t o_GetFileAttributesW;
static GetFileAttributesExA_t o_GetFileAttributesExA;
static GetFileAttributesExW_t o_GetFileAttributesExW;

static void track_open_w(LPCWSTR wpath, const char *u8path, HANDLE h);
static void track_open_a(LPCSTR path, HANDLE h);

#define CALLER(v) char v[96]; caller_name(__builtin_return_address(0), v, sizeof v)

static HANDLE WINAPI h_CreateFileA(LPCSTR n, DWORD a, DWORD s, LPSECURITY_ATTRIBUTES sa, DWORD c, DWORD f, HANDLE t)
{
    int top = enter();
    HANDLE r = o_CreateFileA(n, a, s, sa, c, f, t);
    DWORD e = GetLastError();
    if (top) { CALLER(cl); log_line("CreateFileA  %-2s %s -> %s (err %lu) from %s", access_str(a), n ? n : "(null)", r == INVALID_HANDLE_VALUE ? "FAIL" : "ok", r == INVALID_HANDLE_VALUE ? e : 0, cl); track_open_a(n, r); }
    leave();
    SetLastError(e);
    return r;
}

static HANDLE WINAPI h_CreateFileW(LPCWSTR n, DWORD a, DWORD s, LPSECURITY_ATTRIBUTES sa, DWORD c, DWORD f, HANDLE t)
{
    int top = enter();
    HANDLE r = o_CreateFileW(n, a, s, sa, c, f, t);
    DWORD e = GetLastError();
    if (top) { char p[1024]; CALLER(cl); wide_to_utf8(n, p, sizeof p); log_line("CreateFileW  %-2s %s -> %s (err %lu) from %s", access_str(a), p, r == INVALID_HANDLE_VALUE ? "FAIL" : "ok", r == INVALID_HANDLE_VALUE ? e : 0, cl); track_open_w(n, p, r); }
    leave();
    SetLastError(e);
    return r;
}

static HANDLE WINAPI h_FindFirstFileA(LPCSTR n, LPWIN32_FIND_DATAA d)
{
    int top = enter();
    HANDLE r = o_FindFirstFileA(n, d);
    DWORD e = GetLastError();
    if (top) { CALLER(cl); log_line("FindFirstA      %s -> %s from %s", n ? n : "(null)", r == INVALID_HANDLE_VALUE ? "none" : d->cFileName, cl); }
    leave();
    SetLastError(e);
    return r;
}

static HANDLE WINAPI h_FindFirstFileW(LPCWSTR n, LPWIN32_FIND_DATAW d)
{
    int top = enter();
    HANDLE r = o_FindFirstFileW(n, d);
    DWORD e = GetLastError();
    if (top) { char p[1024], q[MAX_PATH * 3]; CALLER(cl); wide_to_utf8(n, p, sizeof p); if (r != INVALID_HANDLE_VALUE) wide_to_utf8(d->cFileName, q, sizeof q); else lstrcpyA(q, "none"); log_line("FindFirstW      %s -> %s from %s", p, q, cl); }
    leave();
    SetLastError(e);
    return r;
}

static HANDLE WINAPI h_FindFirstFileExA(LPCSTR n, FINDEX_INFO_LEVELS l, LPVOID d, FINDEX_SEARCH_OPS o, LPVOID sf, DWORD fl)
{
    int top = enter();
    HANDLE r = o_FindFirstFileExA(n, l, d, o, sf, fl);
    DWORD e = GetLastError();
    if (top) { CALLER(cl); log_line("FindFirstExA    %s -> %s from %s", n ? n : "(null)", r == INVALID_HANDLE_VALUE ? "none" : ((LPWIN32_FIND_DATAA)d)->cFileName, cl); }
    leave();
    SetLastError(e);
    return r;
}

static HANDLE WINAPI h_FindFirstFileExW(LPCWSTR n, FINDEX_INFO_LEVELS l, LPVOID d, FINDEX_SEARCH_OPS o, LPVOID sf, DWORD fl)
{
    int top = enter();
    HANDLE r = o_FindFirstFileExW(n, l, d, o, sf, fl);
    DWORD e = GetLastError();
    if (top) { char p[1024], q[MAX_PATH * 3]; CALLER(cl); wide_to_utf8(n, p, sizeof p); if (r != INVALID_HANDLE_VALUE) wide_to_utf8(((LPWIN32_FIND_DATAW)d)->cFileName, q, sizeof q); else lstrcpyA(q, "none"); log_line("FindFirstExW    %s -> %s from %s", p, q, cl); }
    leave();
    SetLastError(e);
    return r;
}

static DWORD WINAPI h_GetFileAttributesA(LPCSTR n)
{
    int top = enter();
    DWORD r = o_GetFileAttributesA(n);
    DWORD e = GetLastError();
    if (top) { CALLER(cl); log_line("GetAttrA        %s -> %s from %s", n ? n : "(null)", r == INVALID_FILE_ATTRIBUTES ? "missing" : (r & FILE_ATTRIBUTE_DIRECTORY ? "dir" : "file"), cl); }
    leave();
    SetLastError(e);
    return r;
}

static DWORD WINAPI h_GetFileAttributesW(LPCWSTR n)
{
    int top = enter();
    DWORD r = o_GetFileAttributesW(n);
    DWORD e = GetLastError();
    if (top) { char p[1024]; CALLER(cl); wide_to_utf8(n, p, sizeof p); log_line("GetAttrW        %s -> %s from %s", p, r == INVALID_FILE_ATTRIBUTES ? "missing" : (r & FILE_ATTRIBUTE_DIRECTORY ? "dir" : "file"), cl); }
    leave();
    SetLastError(e);
    return r;
}

static BOOL WINAPI h_GetFileAttributesExA(LPCSTR n, GET_FILEEX_INFO_LEVELS l, LPVOID d)
{
    int top = enter();
    BOOL r = o_GetFileAttributesExA(n, l, d);
    DWORD e = GetLastError();
    if (top) { CALLER(cl); log_line("GetAttrExA      %s -> %s from %s", n ? n : "(null)", r ? "found" : "missing", cl); }
    leave();
    SetLastError(e);
    return r;
}

static BOOL WINAPI h_GetFileAttributesExW(LPCWSTR n, GET_FILEEX_INFO_LEVELS l, LPVOID d)
{
    int top = enter();
    BOOL r = o_GetFileAttributesExW(n, l, d);
    DWORD e = GetLastError();
    if (top) { char p[1024]; CALLER(cl); wide_to_utf8(n, p, sizeof p); log_line("GetAttrExW      %s -> %s from %s", p, r ? "found" : "missing", cl); }
    leave();
    SetLastError(e);
    return r;
}


/* ---- archive read tracking -------------------------------------------- */

typedef BOOL (WINAPI *ReadFile_t)(HANDLE, LPVOID, DWORD, LPDWORD, LPOVERLAPPED);
typedef BOOL (WINAPI *CloseHandle_t)(HANDLE);
static ReadFile_t o_ReadFile;
static CloseHandle_t o_CloseHandle;

typedef struct { DWORD off, size, hash; } Entry;
typedef struct {
    char name[64];
    Entry *ent;
    DWORD n, dir_end;
    BYTE *seen;
    int dir_logged, stray_logged;
} Archive;

#define MAX_ARCH 32
#define MAX_HANDLES 256
static Archive g_arch[MAX_ARCH];
static volatile LONG g_narch;
static struct { HANDLE h; int a; } g_hmap[MAX_HANDLES];
static volatile LONG g_nh;
static CRITICAL_SECTION g_acs;

static DWORD be32(const BYTE *p) { return (DWORD)p[0] << 24 | (DWORD)p[1] << 16 | (DWORD)p[2] << 8 | p[3]; }

static int cmp_ent(const void *a, const void *b)
{
    DWORD x = ((const Entry *)a)->off, y = ((const Entry *)b)->off;
    return x < y ? -1 : x > y;
}

static const char *base_name(const char *path)
{
    const char *a = strrchr(path, '\\'), *b = strrchr(path, '/');
    if (b > a) a = b;
    return a ? a + 1 : path;
}

static int is_archive(const char *path)
{
    const char *b = base_name(path);
    size_t n = strlen(b);
    if (n < 5) return 0;
    if (_stricmp(b + n - 4, ".viv") == 0) return 1;
    return _stricmp(b + n - 4, ".DAT") == 0 && _strnicmp(b, "DS2DAT", 6) == 0;
}

static BOOL raw_read(HANDLE h, void *buf, DWORD n)
{
    DWORD got = 0;
    ReadFile_t rf = o_ReadFile ? o_ReadFile : ReadFile;
    return rf(h, buf, n, &got, NULL) && got == n;
}

/* Find or load the directory of an archive; returns its index or -1. */
static int load_archive(const char *u8path, HANDLE own)
{
    const char *b = base_name(u8path);
    BYTE hdr[16], *dir = NULL;
    DWORD count, i;
    Archive *ar;
    int idx;

    for (idx = 0; idx < g_narch; idx++)
        if (_stricmp(g_arch[idx].name, b) == 0) return idx;
    if (g_narch >= MAX_ARCH || own == INVALID_HANDLE_VALUE) return -1;
    if (!raw_read(own, hdr, 16) || memcmp(hdr, "BIGH", 4) != 0) { log_line("archive %s: not a BIGH archive", b); return -1; }
    count = be32(hdr + 8);
    if (count == 0 || count > 200000) { log_line("archive %s: bad entry count %lu", b, count); return -1; }
    dir = (BYTE *)HeapAlloc(GetProcessHeap(), 0, count * 12);
    ar = &g_arch[g_narch];
    ar->ent = (Entry *)HeapAlloc(GetProcessHeap(), 0, count * sizeof(Entry));
    ar->seen = (BYTE *)HeapAlloc(GetProcessHeap(), HEAP_ZERO_MEMORY, count);
    if (!dir || !ar->ent || !ar->seen || !raw_read(own, dir, count * 12)) { log_line("archive %s: could not read directory", b); return -1; }
    for (i = 0; i < count; i++) {
        ar->ent[i].off = be32(dir + i * 12);
        ar->ent[i].size = be32(dir + i * 12 + 4);
        ar->ent[i].hash = be32(dir + i * 12 + 8);
    }
    HeapFree(GetProcessHeap(), 0, dir);
    qsort(ar->ent, count, sizeof(Entry), cmp_ent);
    lstrcpynA(ar->name, b, sizeof ar->name);
    ar->n = count;
    ar->dir_end = be32(hdr + 12);
    ar->dir_logged = ar->stray_logged = 0;
    log_line("archive %s: %lu entries, directory read", ar->name, count);
    return (int)InterlockedIncrement(&g_narch) - 1;
}

static void track_open(const char *u8path, HANDLE h, HANDLE own)
{
    int a, i, slot = -1;
    if (h == INVALID_HANDLE_VALUE || !is_archive(u8path)) return;
    EnterCriticalSection(&g_acs);
    a = load_archive(u8path, own);
    if (a >= 0) {
        for (i = 0; i < g_nh; i++) if (g_hmap[i].h == NULL || g_hmap[i].h == h) { slot = i; break; }
        if (slot < 0 && g_nh < MAX_HANDLES) slot = (int)g_nh++;
        if (slot >= 0) { g_hmap[slot].h = h; g_hmap[slot].a = a; }
    }
    LeaveCriticalSection(&g_acs);
}

static int archive_of(HANDLE h)
{
    int i, a = -1;
    if (g_nh == 0 || h == NULL || h == INVALID_HANDLE_VALUE) return -1;
    EnterCriticalSection(&g_acs);
    for (i = 0; i < g_nh; i++) if (g_hmap[i].h == h) { a = g_hmap[i].a; break; }
    LeaveCriticalSection(&g_acs);
    return a;
}

static void note_read(int a, ULONGLONG pos, DWORD n, void *ret)
{
    Archive *ar = &g_arch[a];
    long lo = 0, hi = (long)ar->n - 1, best = -1;
    char cl[96];

    EnterCriticalSection(&g_acs);
    if (pos < ar->dir_end) {
        if (!ar->dir_logged) { ar->dir_logged = 1; caller_name(ret, cl, sizeof cl); log_line("READ %s directory (%lu bytes at 0x%llx) from %s", ar->name, n, pos, cl); }
        LeaveCriticalSection(&g_acs);
        return;
    }
    while (lo <= hi) {
        long mid = (lo + hi) / 2;
        if (ar->ent[mid].off <= pos) { best = mid; lo = mid + 1; } else hi = mid - 1;
    }
    if (best >= 0 && pos < (ULONGLONG)ar->ent[best].off + ar->ent[best].size) {
        if (!ar->seen[best]) {
            ar->seen[best] = 1;
            caller_name(ret, cl, sizeof cl);
            log_line("READ %s #%08lX +0x%llx len %lu (entry %lu bytes) from %s", ar->name, ar->ent[best].hash,
                     pos - ar->ent[best].off, n, ar->ent[best].size, cl);
        }
    } else if (ar->stray_logged < 20) {
        ar->stray_logged++;
        log_line("READ %s at 0x%llx len %lu: not inside any entry", ar->name, pos, n);
    }
    LeaveCriticalSection(&g_acs);
}

static BOOL WINAPI h_ReadFile(HANDLE h, LPVOID buf, DWORD n, LPDWORD rd, LPOVERLAPPED ov)
{
    int a = archive_of(h);
    LARGE_INTEGER pos;
    BOOL r;
    DWORD e;

    pos.QuadPart = -1;
    if (a >= 0) {
        if (ov) pos.QuadPart = (LONGLONG)(((ULONGLONG)ov->OffsetHigh << 32) | ov->Offset);
        else {
            LARGE_INTEGER z;
            z.QuadPart = 0;
            if (!SetFilePointerEx(h, z, &pos, FILE_CURRENT)) pos.QuadPart = -1;
        }
    }
    r = o_ReadFile(h, buf, n, rd, ov);
    e = GetLastError();
    if (a >= 0 && pos.QuadPart >= 0) note_read(a, (ULONGLONG)pos.QuadPart, n, __builtin_return_address(0));
    SetLastError(e);
    return r;
}

static BOOL WINAPI h_CloseHandle(HANDLE h)
{
    if (g_nh) {
        int i;
        EnterCriticalSection(&g_acs);
        for (i = 0; i < g_nh; i++) if (g_hmap[i].h == h) g_hmap[i].h = NULL;
        LeaveCriticalSection(&g_acs);
    }
    return o_CloseHandle(h);
}

/* Open a second handle of our own to read an archive's directory. */
static void track_open_w(LPCWSTR wpath, const char *u8path, HANDLE h)
{
    HANDLE own;
    if (h == INVALID_HANDLE_VALUE || !is_archive(u8path)) return;
    own = o_CreateFileW(wpath, GENERIC_READ, FILE_SHARE_READ | FILE_SHARE_WRITE, NULL, OPEN_EXISTING, 0, NULL);
    track_open(u8path, h, own);
    if (own != INVALID_HANDLE_VALUE) o_CloseHandle ? o_CloseHandle(own) : CloseHandle(own);
}

static void track_open_a(LPCSTR path, HANDLE h)
{
    HANDLE own;
    if (!path || h == INVALID_HANDLE_VALUE || !is_archive(path)) return;
    own = o_CreateFileA(path, GENERIC_READ, FILE_SHARE_READ | FILE_SHARE_WRITE, NULL, OPEN_EXISTING, 0, NULL);
    track_open(path, h, own);
    if (own != INVALID_HANDLE_VALUE) o_CloseHandle ? o_CloseHandle(own) : CloseHandle(own);
}

/* ---- hot-patch installer ---------------------------------------------- */

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
   Windows API functions, or 0 if it is not one we can relocate safely
   (anything IP-relative such as call/jmp rel32 is refused). */
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
    if (!VirtualProtect(fn, len, PAGE_EXECUTE_READWRITE, &old)) return 0;
    *orig = t;
    fn[0] = 0xE9;
    *(DWORD *)(fn + 1) = (DWORD)((BYTE *)hook - (fn + 5));
    for (l = 5; l < len; l++) fn[l] = 0x90;
    VirtualProtect(fn, len, old, &old);
    FlushInstructionCache(GetCurrentProcess(), fn, len);
    return 1;
}

/* kernel32 export that is only "jmp dword ptr [slot]": point the slot at us. */
static int stub_pointer(BYTE *fn, void *hook, void **orig)
{
    void **slot;
    DWORD old;
    if (fn[0] != 0xFF || fn[1] != 0x25) return 0;
    slot = *(void ***)(fn + 2);
    if (!VirtualProtect(slot, sizeof *slot, PAGE_READWRITE, &old)) return 0;
    *orig = *slot;
    *slot = hook;
    VirtualProtect(slot, sizeof *slot, old, &old);
    return 1;
}

static void install(const char *name, void *hook, void **orig)
{
    static const char *mods[] = { "kernelbase.dll", "kernel32.dll" };
    int i;
    for (i = 0; i < 2; i++) {
        HMODULE m = GetModuleHandleA(mods[i]);
        BYTE *fn = m ? (BYTE *)GetProcAddress(m, name) : NULL;
        if (!fn) continue;
        if (hotpatch(fn, hook, orig)) { log_line("hooked %s in %s (hot-patch)", name, mods[i]); return; }
        if (trampoline(fn, hook, orig)) { log_line("hooked %s in %s (trampoline)", name, mods[i]); return; }
        if (stub_pointer(fn, hook, orig)) { log_line("hooked %s in %s (stub pointer)", name, mods[i]); return; }
        log_line("could not hook %s in %s (first bytes %02X %02X %02X %02X %02X %02X %02X)", name, mods[i], fn[0], fn[1], fn[2], fn[3], fn[4], fn[5], fn[6]);
    }
}

static void start(HMODULE self)
{
    char path[MAX_PATH], *slash;
    OSVERSIONINFOA vi;

    InitializeCriticalSection(&g_cs);
    InitializeCriticalSection(&g_acs);
    g_tls = TlsAlloc();
    g_tick0 = GetTickCount();
    GetModuleFileNameA(NULL, path, sizeof path);
    slash = strrchr(path, '\\');
    if (slash) lstrcpyA(slash + 1, "severed_probe.log");
    g_log = CreateFileA(path, GENERIC_WRITE, FILE_SHARE_READ, NULL, CREATE_ALWAYS, FILE_ATTRIBUTE_NORMAL, NULL);

    GetModuleFileNameA(NULL, path, sizeof path);
    log_line("severed probe 3 - process %s", path);
    vi.dwOSVersionInfoSize = sizeof vi;
#pragma GCC diagnostic ignored "-Wdeprecated-declarations"
    if (GetVersionExA(&vi)) log_line("windows %lu.%lu build %lu", vi.dwMajorVersion, vi.dwMinorVersion, vi.dwBuildNumber);
    GetModuleFileNameA(self, path, sizeof path);
    log_line("probe dll %s", path);

    install("CreateFileA", (void *)h_CreateFileA, (void **)&o_CreateFileA);
    install("CreateFileW", (void *)h_CreateFileW, (void **)&o_CreateFileW);
    install("FindFirstFileA", (void *)h_FindFirstFileA, (void **)&o_FindFirstFileA);
    install("FindFirstFileW", (void *)h_FindFirstFileW, (void **)&o_FindFirstFileW);
    install("FindFirstFileExA", (void *)h_FindFirstFileExA, (void **)&o_FindFirstFileExA);
    install("FindFirstFileExW", (void *)h_FindFirstFileExW, (void **)&o_FindFirstFileExW);
    install("GetFileAttributesA", (void *)h_GetFileAttributesA, (void **)&o_GetFileAttributesA);
    install("GetFileAttributesW", (void *)h_GetFileAttributesW, (void **)&o_GetFileAttributesW);
    install("GetFileAttributesExA", (void *)h_GetFileAttributesExA, (void **)&o_GetFileAttributesExA);
    install("GetFileAttributesExW", (void *)h_GetFileAttributesExW, (void **)&o_GetFileAttributesExW);
    install("CloseHandle", (void *)h_CloseHandle, (void **)&o_CloseHandle);
    install("ReadFile", (void *)h_ReadFile, (void **)&o_ReadFile);
    log_line("--- hooks installed ---");
}

/* ---- dinput8 forwarding ----------------------------------------------- */

static FARPROC real(const char *name)
{
    if (!g_real) {
        char p[MAX_PATH];
        GetSystemDirectoryA(p, MAX_PATH);   /* SysWOW64 for a 32-bit process */
        lstrcatA(p, "\\dinput8.dll");
        g_real = LoadLibraryA(p);
        log_line("loaded real dinput8 from %s -> %s", p, g_real ? "ok" : "FAILED");
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
        start(inst);
    }
    return TRUE;
}
