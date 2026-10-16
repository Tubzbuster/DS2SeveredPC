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
#include <stdlib.h>
#include <string.h>

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
        static LONG ours;
        if (!lstrcmpiA(ar->name, "DS2DAT2.DAT") && ar->seen[best] && ours < 50000) {
            ours++;     /* every read of the Severed test archive: shows which asset is being loaded */
            log_line("READ %s #%08lX +0x%llx len %lu", ar->name, ar->ent[best].hash, pos - ar->ent[best].off, n);
        }
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

/* ---- reflection scan (version 4) --------------------------------------
 *
 * Severed's level objects are stored as packed per-class records, so
 * converting them needs the field layout of each class (which fields are
 * 32-bit values, which are bytes or strings). The game builds that
 * information in memory at startup. Pressing F10 makes the probe look,
 * read-only, for it:
 *
 *   - places in memory that point at one of the class names in
 *     reflect_names.h (plain strings in the exe), up to 8 per name, with
 *     the 128 bytes around each and 32 bytes from each nearby pointer;
 *   - a copy of the exe's .data section as it is in memory
 *     (severed_data.bin);
 *   - how often two SimGroup format markers occur in the loaded exe.
 *
 * Memory is read with ReadProcessMemory on the game's own process, so
 * memory that goes away during the scan is skipped instead of crashing.
 */
#include "reflect_names.h"
#define NNAMES ((int)(sizeof g_reflect_names / sizeof g_reflect_names[0]))

typedef struct { DWORD addr; int name; } target_t;
static target_t g_targets[4096];
static int g_ntargets;
static int g_hits_per_name[NNAMES];
static HANDLE g_out = INVALID_HANDLE_VALUE;

static void out_text(const char *fmt, ...)
{
    char buf[2048];
    va_list ap;
    int n;
    DWORD w;
    va_start(ap, fmt);
    n = _vsnprintf(buf, sizeof buf - 2, fmt, ap);
    va_end(ap);
    if (n < 0) n = (int)sizeof buf - 3;
    buf[n++] = '\r';
    buf[n++] = '\n';
    WriteFile(g_out, buf, n, &w, NULL);
}

static int readable(DWORD addr, DWORD *region_end, DWORD *type)
{
    MEMORY_BASIC_INFORMATION mi;
    DWORD p;
    if (region_end) *region_end = 0;
    if (!VirtualQuery((void *)addr, &mi, sizeof mi)) return 0;
    if (region_end) *region_end = (DWORD)mi.BaseAddress + mi.RegionSize;
    if (type) *type = mi.Type;
    if (mi.State != MEM_COMMIT) return 0;
    p = mi.Protect;
    if (p & (PAGE_GUARD | PAGE_NOACCESS)) return 0;
    return (p & (PAGE_READONLY | PAGE_READWRITE | PAGE_WRITECOPY | PAGE_EXECUTE_READ |
                 PAGE_EXECUTE_READWRITE | PAGE_EXECUTE_WRITECOPY)) != 0;
}

static int copy_mem(DWORD addr, void *buf, DWORD len)
{
    SIZE_T got = 0;
    return ReadProcessMemory(GetCurrentProcess(), (void *)addr, buf, len, &got) && got == len;
}

static int cmp_target(const void *a, const void *b)
{
    DWORD x = ((const target_t *)a)->addr, y = ((const target_t *)b)->addr;
    return x < y ? -1 : x > y;
}

static int find_target(DWORD v)
{
    int lo = 0, hi = g_ntargets - 1;
    if (g_ntargets == 0 || v < g_targets[0].addr || v > g_targets[g_ntargets - 1].addr) return -1;
    while (lo <= hi) {
        int mid = (lo + hi) / 2;
        if (g_targets[mid].addr == v) return mid;
        if (g_targets[mid].addr < v) lo = mid + 1; else hi = mid - 1;
    }
    return -1;
}

static void hexline(const char *tag, DWORD addr, const BYTE *b, int n)
{
    char s[3 * 64 + 1];
    int i;
    for (i = 0; i < n && i < 64; i++) wsprintfA(s + 3 * i, "%02X ", b[i]);
    s[3 * i] = 0;
    out_text("%s %08lX %s", tag, addr, s);
}

/* a short printable NUL-terminated string at addr, or 0 */
static int string_at(DWORD addr, char *out, int len)
{
    BYTE b[64];
    int i;
    if (!readable(addr, NULL, NULL) || !copy_mem(addr, b, sizeof b)) return 0;
    for (i = 0; i < len - 1 && i < (int)sizeof b; i++) {
        if (b[i] == 0) break;
        if (b[i] < 32 || b[i] > 126) return 0;
        out[i] = (char)b[i];
    }
    out[i] = 0;
    return i >= 3 && i < (int)sizeof b && b[i] == 0;
}

static void dump_hit(DWORD at, int name)
{
    BYTE win[128];
    DWORD start = at - 32, i;
    char s[64];
    if (!copy_mem(start, win, sizeof win)) {
        start = at;
        if (!copy_mem(start, win, 96)) return;
        memset(win + 96, 0, 32);
    }
    out_text("HIT %s at %08lX", g_reflect_names[name], at);
    for (i = 0; i < sizeof win; i += 32) hexline("  W", start + i, win + i, 32);
    for (i = 0; i + 4 <= sizeof win; i += 4) {
        DWORD v = *(DWORD *)(win + i), t;
        BYTE pb[128];
        int n, j;
        if (v < 0x10000 || v == at) continue;
        if (string_at(v, s, sizeof s)) { out_text("  S %08lX -> %08lX \"%s\"", start + i, v, s); continue; }
        if (!readable(v, NULL, &t)) continue;
        n = t == MEM_PRIVATE ? 128 : 32;   /* heap blocks may hold field lists */
        if (!copy_mem(v, pb, n)) continue;
        out_text("  P %08lX -> %08lX (%s)", start + i, v, t == MEM_IMAGE ? "image" : t == MEM_PRIVATE ? "private" : "mapped");
        for (j = 0; j < n; j += 32) hexline("   ", v + j, pb + j, 32);
    }
}

static void find_names(BYTE *img, DWORD size)
{
    BYTE *buf = (BYTE *)VirtualAlloc(NULL, 1 << 20, MEM_COMMIT | MEM_RESERVE, PAGE_READWRITE);
    DWORD off;
    int k;
    if (!buf) return;
    for (off = 0; off < size; off += (1 << 20) - 128) {
        DWORD n = size - off < (1 << 20) ? size - off : (1 << 20);
        DWORD i;
        if (!readable((DWORD)img + off, NULL, NULL) || !copy_mem((DWORD)img + off, buf, n)) continue;
        for (i = 1; i + 2 < n; i++) {
            if (buf[i - 1] != 0) continue;   /* names start after a NUL */
            for (k = 0; k < NNAMES; k++) {
                const char *nm = g_reflect_names[k];
                int L = lstrlenA(nm);
                if (buf[i] != (BYTE)nm[0] || i + L >= n) continue;
                if (memcmp(buf + i, nm, L) == 0 && buf[i + L] == 0 && g_ntargets < (int)(sizeof g_targets / sizeof g_targets[0])) {
                    DWORD a = (DWORD)img + off + i;
                    int j, dup = 0;
                    for (j = 0; j < g_ntargets; j++) if (g_targets[j].addr == a) dup = 1;
                    if (!dup) { g_targets[g_ntargets].addr = a; g_targets[g_ntargets].name = k; g_ntargets++; }
                }
            }
        }
    }
    VirtualFree(buf, 0, MEM_RELEASE);
    qsort(g_targets, g_ntargets, sizeof g_targets[0], cmp_target);
}

static void count_constants(BYTE *img, DWORD size)
{
    static const DWORD consts[] = { 0x011795D9, 0x91C8773C, 0xCCB51828, 0x07B6C269, 0xACBDFE47 };
    BYTE *buf = (BYTE *)VirtualAlloc(NULL, 1 << 20, MEM_COMMIT | MEM_RESERVE, PAGE_READWRITE);
    int c, counts[5] = { 0 };
    DWORD off;
    if (!buf) return;
    for (off = 0; off < size; off += (1 << 20) - 4) {
        DWORD n = size - off < (1 << 20) ? size - off : (1 << 20), i;
        if (!readable((DWORD)img + off, NULL, NULL) || !copy_mem((DWORD)img + off, buf, n)) continue;
        for (i = 0; i + 4 <= n; i++)
            for (c = 0; c < 5; c++)
                if (*(DWORD *)(buf + i) == consts[c]) {
                    if (counts[c] < 40) out_text("CONST %08lX at %08lX", consts[c], (DWORD)img + off + i);
                    counts[c]++;
                }
    }
    for (c = 0; c < 5; c++) out_text("CONST %08lX total %d", consts[c], counts[c]);
    VirtualFree(buf, 0, MEM_RELEASE);
}

static void dump_data_section(BYTE *img, const char *dir)
{
    IMAGE_DOS_HEADER dos;
    IMAGE_NT_HEADERS32 nt;
    IMAGE_SECTION_HEADER sh;
    char path[MAX_PATH];
    int i;
    if (!copy_mem((DWORD)img, &dos, sizeof dos) || !copy_mem((DWORD)img + dos.e_lfanew, &nt, sizeof nt)) return;
    for (i = 0; i < nt.FileHeader.NumberOfSections; i++) {
        DWORD shoff = (DWORD)img + dos.e_lfanew + sizeof(DWORD) + sizeof(IMAGE_FILE_HEADER) + nt.FileHeader.SizeOfOptionalHeader + i * sizeof sh;
        if (!copy_mem(shoff, &sh, sizeof sh)) return;
        out_text("SECTION %.8s va %08lX size %08lX", sh.Name, (DWORD)img + sh.VirtualAddress, sh.Misc.VirtualSize);
        if (memcmp(sh.Name, ".data\0", 6) == 0) {
            HANDLE f;
            DWORD a = (DWORD)img + sh.VirtualAddress, end = a + sh.Misc.VirtualSize, w;
            BYTE page[4096];
            lstrcpyA(path, dir);
            lstrcatA(path, "severed_data.bin");
            f = CreateFileA(path, GENERIC_WRITE, 0, NULL, CREATE_ALWAYS, FILE_ATTRIBUTE_NORMAL, NULL);
            if (f == INVALID_HANDLE_VALUE) continue;
            for (; a < end; a += sizeof page) {
                if (!copy_mem(a, page, sizeof page)) memset(page, 0xCC, sizeof page);
                WriteFile(f, page, sizeof page, &w, NULL);
            }
            CloseHandle(f);
        }
    }
}

static void reflect_scan(void)
{
    char dir[MAX_PATH], path[MAX_PATH], *slash;
    BYTE *img = (BYTE *)GetModuleHandleA(NULL);
    IMAGE_DOS_HEADER dos;
    IMAGE_NT_HEADERS32 nt;
    DWORD addr, end, type, size, hits = 0;
    BYTE *buf;

    GetModuleFileNameA(NULL, dir, sizeof dir);
    slash = strrchr(dir, '\\');
    if (slash) slash[1] = 0;
    lstrcpyA(path, dir);
    lstrcatA(path, "severed_reflect.log");
    g_out = CreateFileA(path, GENERIC_WRITE, FILE_SHARE_READ, NULL, CREATE_ALWAYS, FILE_ATTRIBUTE_NORMAL, NULL);
    if (g_out == INVALID_HANDLE_VALUE) return;
    log_line("reflection scan started");
    out_text("severed reflect scan 4, module %08lX", (DWORD)img);
    if (!copy_mem((DWORD)img, &dos, sizeof dos) || !copy_mem((DWORD)img + dos.e_lfanew, &nt, sizeof nt)) {
        out_text("cannot read module header");
        CloseHandle(g_out);
        return;
    }
    size = nt.OptionalHeader.SizeOfImage;
    dump_data_section(img, dir);
    count_constants(img, size);
    g_ntargets = 0;
    memset(g_hits_per_name, 0, sizeof g_hits_per_name);
    {
        /* the names are plain strings in .rdata */
        IMAGE_SECTION_HEADER sh;
        int i;
        for (i = 0; i < nt.FileHeader.NumberOfSections; i++) {
            DWORD shoff = (DWORD)img + dos.e_lfanew + sizeof(DWORD) + sizeof(IMAGE_FILE_HEADER) + nt.FileHeader.SizeOfOptionalHeader + i * sizeof sh;
            if (copy_mem(shoff, &sh, sizeof sh) && memcmp(sh.Name, ".rdata\0", 7) == 0)
                find_names(img + sh.VirtualAddress, sh.Misc.VirtualSize);
        }
    }
    out_text("TARGETS %d strings for %d names", g_ntargets, NNAMES);
    for (addr = 0; addr < (DWORD)g_ntargets; addr++)
        out_text("NAME %s at %08lX", g_reflect_names[g_targets[addr].name], g_targets[addr].addr);

    buf = (BYTE *)VirtualAlloc(NULL, 1 << 20, MEM_COMMIT | MEM_RESERVE, PAGE_READWRITE);
    for (addr = 0x10000; buf && addr < 0x7FFF0000; addr = end) {
        int ok = readable(addr, &end, &type);
        DWORD a;
        if (end <= addr) break;
        if (!ok || (DWORD)buf == addr) continue;
        for (a = addr; a < end; a += 1 << 20) {
            DWORD n = end - a < (1 << 20) ? end - a : (1 << 20), i;
            if (!copy_mem(a, buf, n)) continue;
            for (i = 0; i + 4 <= n; i += 4) {
                int t = find_target(*(DWORD *)(buf + i));
                if (t < 0) continue;
                if (g_hits_per_name[g_targets[t].name]++ >= 8) continue;
                if (hits++ > 30000) break;
                dump_hit(a + i, g_targets[t].name);
            }
        }
    }
    if (buf) VirtualFree(buf, 0, MEM_RELEASE);
    out_text("DONE %lu hits", hits);
    CloseHandle(g_out);
    g_out = INVALID_HANDLE_VALUE;
    log_line("reflection scan finished: %lu hits", hits);
    MessageBeep(MB_ICONASTERISK);
}

/* ---- descriptor dump (version 5) --------------------------------------
 *
 * The scan above showed that the engine describes each class with a
 * static descriptor in .data (vtable 01B1E648; flag sets 01AA6C80, enums
 * 01AA6C68), whose field list lives on the heap. Pressing F11 writes
 * severed_desc.bin: the .data section, every descriptor's heap blocks,
 * and one more level of heap blocks they point to, as chunks of
 * (u32 address, u32 length, bytes). Read-only, like the scan.
 */
static const DWORD g_desc_vt[] = { 0x01B1E648, 0x01AA6C80, 0x01AA6C68 };
static HANDLE g_dout = INVALID_HANDLE_VALUE;
static DWORD g_seen[1 << 16];
static DWORD g_dumped_bytes;
#define DUMP_LIMIT (48u << 20)

static int seen_add(DWORD va)
{
    DWORD h = (va * 2654435761u) >> 16, i;
    for (i = 0; i < (1 << 16); i++) {
        DWORD *s = &g_seen[(h + i) & 0xFFFF];
        if (*s == va) return 0;
        if (*s == 0) { *s = va; return 1; }
    }
    return 0;
}

static void chunk(DWORD va, DWORD len)
{
    static BYTE buf[65536];
    DWORD w, hdr[2], end, t, n;
    if (len > sizeof buf) len = sizeof buf;
    while (len > 0 && g_dumped_bytes <= DUMP_LIMIT) {
        /* a range can span memory regions: copy each readable part */
        if (!readable(va, &end, &t)) {
            if (end <= va) return;
            n = end - va;
        } else {
            n = end - va < len ? end - va : len;
            if (copy_mem(va, buf, n)) {
                hdr[0] = va;
                hdr[1] = n;
                WriteFile(g_dout, hdr, 8, &w, NULL);
                WriteFile(g_dout, buf, n, &w, NULL);
                g_dumped_bytes += n + 8;
            }
        }
        if (n >= len) return;
        va += n;
        len -= n;
    }
}

/* dumps a heap block and, one level down, the heap blocks it points to */
static void heap_block(DWORD va, DWORD len, int depth)
{
    BYTE b[4096];
    DWORD t, i, n;
    if (va < 0x10000 || !readable(va, NULL, &t) || t != MEM_PRIVATE || !seen_add(va)) return;
    chunk(va, len);
    if (depth == 0) return;
    n = len < sizeof b ? len : sizeof b;
    if (!copy_mem(va, b, n)) return;
    for (i = 0; i + 4 <= n; i += 4) heap_block(*(DWORD *)(b + i), 256, depth - 1);
}

static void desc_dump(void)
{
    char path[MAX_PATH], *slash;
    BYTE *img = (BYTE *)GetModuleHandleA(NULL);
    IMAGE_DOS_HEADER dos;
    IMAGE_NT_HEADERS32 nt;
    IMAGE_SECTION_HEADER sh;
    DWORD data = 0, data_size = 0, rdata = 0, rdata_size = 0, a, w, count = 0;
    int i;

    GetModuleFileNameA(NULL, path, sizeof path);
    slash = strrchr(path, '\\');
    if (slash) lstrcpyA(slash + 1, "severed_desc.bin");
    if (!copy_mem((DWORD)img, &dos, sizeof dos) || !copy_mem((DWORD)img + dos.e_lfanew, &nt, sizeof nt)) return;
    for (i = 0; i < nt.FileHeader.NumberOfSections; i++) {
        DWORD shoff = (DWORD)img + dos.e_lfanew + sizeof(DWORD) + sizeof(IMAGE_FILE_HEADER) + nt.FileHeader.SizeOfOptionalHeader + i * sizeof sh;
        if (!copy_mem(shoff, &sh, sizeof sh)) return;
        if (memcmp(sh.Name, ".data\0", 6) == 0) { data = (DWORD)img + sh.VirtualAddress; data_size = sh.Misc.VirtualSize; }
        if (memcmp(sh.Name, ".rdata\0", 7) == 0) { rdata = (DWORD)img + sh.VirtualAddress; rdata_size = sh.Misc.VirtualSize; }
    }
    if (!data || !rdata) return;
    g_dout = CreateFileA(path, GENERIC_WRITE, FILE_SHARE_READ, NULL, CREATE_ALWAYS, FILE_ATTRIBUTE_NORMAL, NULL);
    if (g_dout == INVALID_HANDLE_VALUE) return;
    log_line("descriptor dump started");
    WriteFile(g_dout, "SVDESC6\0", 8, &w, NULL);
    memset(g_seen, 0, sizeof g_seen);
    g_dumped_bytes = 0;
    for (a = data; a < data + data_size; a += 65536) chunk(a, data + data_size - a < 65536 ? data + data_size - a : 65536);
    for (a = data; a < data + data_size; a += 65536) {
        static DWORD blk[16384];
        DWORD n = data + data_size - a < 65536 ? data + data_size - a : 65536, j;
        if (!copy_mem(a, blk, n)) continue;
        for (j = 0; j + 2 <= n / 4; j++) {
            DWORD d[24];
            int k, kind = -1;
            for (k = 0; k < 3; k++) if (blk[j] == g_desc_vt[k]) kind = k;
            if (kind < 0 || blk[j + 1] < rdata || blk[j + 1] >= rdata + rdata_size) continue;
            if (!copy_mem(a + 4 * j, d, sizeof d)) continue;
            count++;
            if (kind == 0 && d[8] > d[7] && d[8] - d[7] <= 65536) heap_block(d[7], d[8] - d[7] + 64, 1);
            /* field list: (d[17] & 0xFFFF) entries of 16 bytes at d[10] */
            if (kind == 0) heap_block(d[10], 16 * (d[17] & 0xFFFF) + 16, 1);
            for (k = 2; k < 24; k++) heap_block(d[k], kind == 0 ? 1024 : 2048, 1);
        }
    }
    CloseHandle(g_dout);
    g_dout = INVALID_HANDLE_VALUE;
    log_line("descriptor dump finished: %lu descriptors, %lu bytes", count, g_dumped_bytes);
    MessageBeep(MB_ICONASTERISK);
}


/* ---- F9: add Severed to the episode list --------------------------------
 * Found in a retail build of the exe without the Steam wrapper (same data
 * layout; the Steam build's code may sit at other addresses, so the two
 * functions are located by byte pattern in the running game's code, ??
 * = relative call targets / absolute addresses):
 *   front end constructor: stores `this` in the front end global
 *     (`mov [imm32], esi` at +5, address at +7) and builds the episode
 *     list at this + 0x980: vector {begin, end, cap} of 0x68-byte entries
 *     (16-byte strings, text pointer first): +0x00 name, +0x10
 *     description, +0x20 folder, +0x30 stream list, +0x40 extra, +0x50 start
 *     checkpoint GUID, +0x60 flags, +0x64 unlock key
 *   AddEpisode: thiscall, 8 arguments (ret 0x20); the console DLC path
 *     (.lvl) calls it with weller1.lvl's fields.
 * Only addresses are logged; no code is copied out.
 */
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

/* the one match of a pattern in the exe's .text, or NULL (none / several) */
static BYTE *find_sig(const char *sig, int *count)
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
        if (i == n) { (*count)++; hit = p; }
    }
    return *count == 1 ? hit : NULL;
}

static void log_episodes(void *fe)
{
    BYTE *v = (BYTE *)fe + 0x980, *b, *e, *x;
    if (!mem_ok(v, 12)) return;
    b = *(BYTE **)v; e = *(BYTE **)(v + 4);
    log_line("episode list: %d entries", b && e > b ? (int)((e - b) / 0x68) : 0);
    for (x = b; x && x < e && mem_ok(x, 0x68); x += 0x68) {
        const char *n = *(const char **)x, *f = *(const char **)(x + 0x20), *c = *(const char **)(x + 0x50);
        log_line("  %s | %s | %s", n && mem_ok(n, 1) ? n : "-", f && mem_ok(f, 1) ? f : "-", c && mem_ok(c, 1) ? c : "-");
    }
}

/* Calling AddEpisode from the probe's own thread hangs the game (its
 * allocator is not for foreign threads), and by the title screen the list
 * has already been consumed. So the front end constructor is hooked in
 * memory (nothing on disk): right after it adds the built-in episode, on
 * the game's own thread, Severed is added the same way. The constructor
 * starts with push ebx / push ebp / push esi / mov esi, ecx (5 bytes, no
 * relative operands), which the trampoline re-runs before jumping back. */
typedef void *(__attribute__((thiscall)) *ctor_fn)(void *self);
static ctor_fn g_ctor_tramp;
static add_episode_fn g_add;
static volatile LONG g_added;

static void *__attribute__((thiscall)) hook_frontend_ctor(void *self)
{
    void *r = g_ctor_tramp(self);
    log_line("front end constructed (thread %lu)", GetCurrentThreadId());
    log_episodes(self);
    g_add(self, "Dead Space 2: Severed", "Gabe Weller's story (converted from the Xbox 360 DLC)",
          "pdlc1_ch01_mng", "pdlc1_ch01_mng.str", "XONTREALPR_CB22182_E50854D_v3", 0, 0, NULL);
    InterlockedIncrement(&g_added);
    log_line("added Severed to the episode list");
    log_episodes(self);
    return r;
}

static DWORD WINAPI menu_hook_thread(LPVOID p)
{
    int na = 0, nc = 0, tries;
    BYTE *add = NULL, *ctor = NULL, *t;
    DWORD old, base = (DWORD)GetModuleHandleA(NULL);
    (void)p;
    /* the Steam wrapper decrypts the code shortly after start: wait for it */
    for (tries = 0; tries < 6000; tries++) {
        add = find_sig(SIG_ADD, &na);
        ctor = find_sig(SIG_CTOR, &nc);
        if (add && ctor) break;
        Sleep(10);
    }
    log_line("menu hook: AddEpisode %d match(es) at exe+0x%lx, front end constructor %d match(es) at exe+0x%lx",
             na, add ? (DWORD)add - base : 0, nc, ctor ? (DWORD)ctor - base : 0);
    if (!add || !ctor) { log_line("menu hook: functions not found - Severed not added"); return 0; }
    t = (BYTE *)VirtualAlloc(NULL, 16, MEM_COMMIT | MEM_RESERVE, PAGE_EXECUTE_READWRITE);
    if (!t) return 0;
    memcpy(t, ctor, 5);
    t[5] = 0xE9; *(DWORD *)(t + 6) = (DWORD)(ctor + 5) - (DWORD)(t + 10);
    g_ctor_tramp = (ctor_fn)t;
    g_add = (add_episode_fn)add;
    if (!VirtualProtect(ctor, 5, PAGE_EXECUTE_READWRITE, &old)) { log_line("menu hook: cannot patch"); return 0; }
    ctor[0] = 0xE9; *(DWORD *)(ctor + 1) = (DWORD)hook_frontend_ctor - (DWORD)(ctor + 5);
    VirtualProtect(ctor, 5, old, &old);
    FlushInstructionCache(GetCurrentProcess(), ctor, 5);
    log_line("menu hook: installed after %d ms", tries * 10);
    return 0;
}

static void add_severed(void)
{
    int nc;
    BYTE *ctor = find_sig(SIG_CTOR, &nc);   /* hooked now: pattern gone */
    void **global = (void **)0x0201C0E4, *fe;
    (void)ctor; (void)nc;
    log_line("F9: Severed added %ld time(s) by the menu hook", g_added);
    if (mem_ok(global, 4) && (fe = *global)) log_episodes(fe);
}


/* ---- crash report -------------------------------------------------------
 * A vectored handler logs the first serious exceptions: code, where (module
 * + offset), the faulting data address, registers and the return addresses
 * found on the stack (module + offset only, no code is read). */
static void addr_name(DWORD a, char *out, int n)
{
    HMODULE m = NULL;
    char path[MAX_PATH], *b;
    if (GetModuleHandleExA(GET_MODULE_HANDLE_EX_FLAG_FROM_ADDRESS | GET_MODULE_HANDLE_EX_FLAG_UNCHANGED_REFCOUNT,
                           (LPCSTR)a, &m) && m && GetModuleFileNameA(m, path, sizeof path)) {
        b = strrchr(path, '\\');
        wsprintfA(out, "%s+0x%lx", b ? b + 1 : path, a - (DWORD)m);
    } else wsprintfA(out, "0x%08lx", a);
    (void)n;
}

static LONG WINAPI crash_handler(EXCEPTION_POINTERS *e)
{
    static LONG count;
    EXCEPTION_RECORD *r = e->ExceptionRecord;
    CONTEXT *c = e->ContextRecord;
    char where[MAX_PATH + 32], ra[MAX_PATH + 32];
    DWORD *sp, i, found = 0;
    if (r->ExceptionCode < 0xC0000000 || r->ExceptionCode == 0xC0000027 /* unwind */ ||
        r->ExceptionCode == 0xE06D7363 /* C++ throw */ || !g_added /* start-up: the DRM uses exceptions */ ||
        InterlockedIncrement(&count) > 20)
        return EXCEPTION_CONTINUE_SEARCH;
    addr_name((DWORD)r->ExceptionAddress, where, sizeof where);
    log_line("EXCEPTION 0x%08lx at %s thread %lu%s", r->ExceptionCode, where, GetCurrentThreadId(),
             r->ExceptionCode == 0xC0000005 ? "" : "");
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
        addr_name(v, ra, sizeof ra);
        log_line("  stack +0x%03lx %s", i * 4, ra);
        found++;
    }
    return EXCEPTION_CONTINUE_SEARCH;
}

static DWORD WINAPI hotkey_thread(LPVOID p)
{
    (void)p;
    for (;;) {
        Sleep(200);
        if (GetAsyncKeyState(VK_F9) & 0x8000) {
            add_severed();
            while (GetAsyncKeyState(VK_F9) & 0x8000) Sleep(100);
        }
        if (GetAsyncKeyState(VK_F10) & 0x8000) {
            reflect_scan();
            while (GetAsyncKeyState(VK_F10) & 0x8000) Sleep(100);
        }
        if (GetAsyncKeyState(VK_F11) & 0x8000) {
            desc_dump();
            while (GetAsyncKeyState(VK_F11) & 0x8000) Sleep(100);
        }
    }
    return 0;
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
    log_line("severed probe 10 - process %s", path);
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
    CreateThread(NULL, 0, hotkey_thread, NULL, 0, NULL);
    CreateThread(NULL, 0, menu_hook_thread, NULL, 0, NULL);
    AddVectoredExceptionHandler(1, crash_handler);
    log_line("Severed is added to the episode list when the front end starts; F9 logs the list, F10 for the reflection scan, F11 for the descriptor dump");
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
