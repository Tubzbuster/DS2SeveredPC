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
#define CRASH_RESERVE 20000
static volatile DWORD g_crash_thread;  /* thread inside crash_handler */

/* ---- logging ---------------------------------------------------------- */

static void log_line(const char *fmt, ...)
{
    char buf[4096];
    va_list ap;
    int n, m;
    DWORD w;

    if (g_log == INVALID_HANDLE_VALUE) return;
    n = InterlockedIncrement(&g_lines);
    /* past the cap only the crash handler still writes (up to a reserve) */
    if (n > MAX_LINES && (GetCurrentThreadId() != g_crash_thread || n > MAX_LINES + CRASH_RESERVE)) {
        if (n == MAX_LINES + 1) {
            static const char cap[] = "log limit reached: only crash reports are logged from here\r\n";
            EnterCriticalSection(&g_cs);
            WriteFile(g_log, cap, sizeof cap - 1, &w, NULL);
            LeaveCriticalSection(&g_cs);
        }
        return;
    }
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
    if (!dir || !ar->ent || !ar->seen || !raw_read(own, dir, count * 12)) {
        log_line("archive %s: could not read directory", b);
        if (dir) HeapFree(GetProcessHeap(), 0, dir);
        if (ar->ent) HeapFree(GetProcessHeap(), 0, ar->ent);
        if (ar->seen) HeapFree(GetProcessHeap(), 0, ar->seen);
        ar->ent = NULL; ar->seen = NULL;
        return -1;
    }
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
    {
        /* which name form Severed's first dialogue streams are stored under */
        static const DWORD probe_h[4] = { 0xC35FDD3DUL, 0x4E3C38B9UL, 0xB3303B75UL, 0x6BF04984UL };
        static const char *probe_n[4] = { "360 path vo_01_01", "360 path igc_01_01", "PC path vo_01_01", "PC path igc_01_01" };
        int k;
        for (k = 0; k < 4; k++)
            for (i = 0; i < count; i++)
                if (ar->ent[i].hash == probe_h[k]) { log_line("archive %s: has %s (#%08lX)", ar->name, probe_n[k], probe_h[k]); break; }
    }
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
    static const char *mods[] = { "kernelbase.dll", "kernel32.dll", "user32.dll" };
    int i;
    for (i = 0; i < 3; i++) {
        HMODULE m = GetModuleHandleA(mods[i]);
        if (!m && i == 2) m = LoadLibraryA("user32.dll");
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


/* ---- class layout log ---------------------------------------------------
 * Logs one class's field list from its descriptor in .data (read-only):
 * descriptor words w[2] = name hash, w[3] = version, w[10] = field array,
 * w[16] >> 16 = size, w[17] & 0xFFFF = field count; field entries are 16
 * bytes {typeinfo*, fielddesc*, u16 offset, ...}; fielddesc {name*, hash,
 * type, ...}; typeinfo for arrays (0x13) {count, element type, class*}, for
 * structs (0x16) {.., .., class*}. Used for classes whose field list the
 * earlier descriptor dump missed (Uniform). */
static int g_uniform_logged;

static void log_class_fields(DWORD va, DWORD hash)
{
    DWORD *w = (DWORD *)va, i, n;
    BYTE *fa;
    if (!mem_ok(w, 18 * 4) || w[2] != hash) { log_line("CLASS 0x%08lx: no descriptor at 0x%08lx", hash, va); return; }
    n = w[17] & 0xFFFF;
    fa = (BYTE *)w[10];
    log_line("CLASS %s hash 0x%08lx version %lu size %lu fields %lu",
             mem_ok((void *)w[1], 1) ? (const char *)w[1] : "?", w[2], w[3], w[16] >> 16, n);
    if (n && fa) g_uniform_logged = 1;
    for (i = 0; i < n && mem_ok(fa + 16 * i, 16); i++) {
        DWORD *e = (DWORD *)(fa + 16 * i), *fd = (DWORD *)e[1], *ti = (DWORD *)e[0];
        WORD off = *(WORD *)(fa + 16 * i + 8);
        const char *name = fd && mem_ok(fd, 20) && mem_ok((void *)fd[0], 1) ? (const char *)fd[0] : "?";
        DWORD type = fd && mem_ok(fd, 20) ? fd[2] : 0xFFFFFFFF;
        DWORD a = 0, b = 0, c = 0, x = fd && mem_ok(fd, 20) ? fd[3] : 0;
        if (x && mem_ok((void *)x, 12)) x = ((DWORD *)x)[2];        /* struct class hash */
        if (ti && mem_ok(ti, 12)) {
            a = ti[0]; b = ti[1]; c = ti[2];
            if (c && mem_ok((void *)c, 12)) c = ((DWORD *)c)[2];   /* element / struct class hash */
        }
        log_line("  FIELD %u 0x%lx %s ti %lx %lx %lx x %lx", off, type, name, a, b, c, x);
    }
}

static void *__attribute__((thiscall)) hook_frontend_ctor(void *self)
{
    void *r = g_ctor_tramp(self);
    static int classes_logged;
    log_line("front end constructed (thread %lu)", GetCurrentThreadId());
    if (!classes_logged) { classes_logged = 1; log_class_fields(0x02098B78, 0x0575C2F4); }
    log_episodes(self);
    g_add(self, "Dead Space 2: Severed", "Gabe Weller's story",
          "pdlc1_ch01_mng", "pdlc1_ch01_mng.str", "XONTREALPR_CB22182_E50854D_v3", 0, 0, NULL);
    InterlockedIncrement(&g_added);
    log_line("added Severed to the episode list");
    log_episodes(self);
    return r;
}


/* ---- stream request log -------------------------------------------------
 * The level loader asks for each stream through one function (retail exe
 * 0x0074BDD0: sub esp, 0x124 ...; first stack argument = stream path).
 * A small stub logs that argument and continues in the original code. */
static const char SIG_STREAMREQ[] =
    "81 EC 24 01 00 00 53 55 8B E9 8B ?? ?? ?? ?? 00 00 56 33 C0 57 85 C9 0F 84 ?? ?? ?? ?? 38 01 0F 84 ?? ?? ?? ?? "
    "51 8D 4C 24 14 E8 ?? ?? ?? ?? 8B ?? ?? ?? ?? 00 00 8B C7 8D 74 24 10 E8 ?? ?? ?? ?? 6A 01 8B CE E8";

static void __cdecl log_stream_request(const char *path)
{
    static LONG n;
    if (InterlockedIncrement(&n) > 5000) return;
    log_line("STREAM request %s", path && mem_ok(path, 1) ? path : "(null)");
}

/* fn starts with `len` bytes of position-independent code; cb gets the
   stack word at `off` from the entry stack pointer (0 = return address,
   4 = first argument) */
static int hook_log_word(BYTE *fn, int len, void (__cdecl *cb)(const char *), int off);
static int hook_log_arg1(BYTE *fn, int len, void (__cdecl *cb)(const char *))
{
    return hook_log_word(fn, len, cb, 4);
}

/* like hook_log_word, but cb gets the entry stack pointer (sp[0] = return
   address, sp[1..] = arguments) */
static int hook_log_sp(BYTE *fn, int len, void (__cdecl *cb)(const DWORD *))
{
    BYTE *t = (BYTE *)VirtualAlloc(NULL, 64, MEM_COMMIT | MEM_RESERVE, PAGE_EXECUTE_READWRITE), *q;
    DWORD old;
    if (!t) return 0;
    q = t;
    *q++ = 0x60;                                   /* pushad */
    *q++ = 0x9C;                                   /* pushfd */
    *q++ = 0x8D; *q++ = 0x44; *q++ = 0x24; *q++ = 0x24;   /* lea eax, [entry esp] */
    *q++ = 0x50;                                   /* push eax */
    *q++ = 0xE8; *(DWORD *)q = (DWORD)cb - (DWORD)(q + 4); q += 4;
    *q++ = 0x83; *q++ = 0xC4; *q++ = 0x04;         /* add esp, 4 */
    *q++ = 0x9D;                                   /* popfd */
    *q++ = 0x61;                                   /* popad */
    memcpy(q, fn, len); q += len;
    *q++ = 0xE9; *(DWORD *)q = (DWORD)(fn + len) - (DWORD)(q + 4); q += 4;
    if (!VirtualProtect(fn, len, PAGE_EXECUTE_READWRITE, &old)) { VirtualFree(t, 0, MEM_RELEASE); return 0; }
    fn[0] = 0xE9; *(DWORD *)(fn + 1) = (DWORD)t - (DWORD)(fn + 5);
    if (len > 5) memset(fn + 5, 0x90, len - 5);
    VirtualProtect(fn, len, old, &old);
    FlushInstructionCache(GetCurrentProcess(), fn, len);
    return 1;
}

static int hook_log_word(BYTE *fn, int len, void (__cdecl *cb)(const char *), int off)
{
    BYTE *t = (BYTE *)VirtualAlloc(NULL, 64, MEM_COMMIT | MEM_RESERVE, PAGE_EXECUTE_READWRITE), *q;
    DWORD old;
    if (!t) return 0;
    q = t;
    *q++ = 0x60;                                   /* pushad */
    *q++ = 0x9C;                                   /* pushfd */
    *q++ = 0xFF; *q++ = 0x74; *q++ = 0x24; *q++ = (BYTE)(0x24 + off);   /* push [entry esp + off] */
    *q++ = 0xE8; *(DWORD *)q = (DWORD)cb - (DWORD)(q + 4); q += 4;
    *q++ = 0x83; *q++ = 0xC4; *q++ = 0x04;         /* add esp, 4 */
    *q++ = 0x9D;                                   /* popfd */
    *q++ = 0x61;                                   /* popad */
    memcpy(q, fn, len); q += len;                  /* the original first instructions */
    *q++ = 0xE9; *(DWORD *)q = (DWORD)(fn + len) - (DWORD)(q + 4); q += 4;
    if (!VirtualProtect(fn, len, PAGE_EXECUTE_READWRITE, &old)) return 0;
    fn[0] = 0xE9; *(DWORD *)(fn + 1) = (DWORD)t - (DWORD)(fn + 5);
    if (len > 5) memset(fn + 5, 0x90, len - 5);
    VirtualProtect(fn, len, old, &old);
    FlushInstructionCache(GetCurrentProcess(), fn, len);
    return 1;
}


/* ---- Severed's stream sets ---------------------------------------------
 * Level start (retail exe 0x0042C600, this = level start request, +0x28 =
 * folder string) requests the base chapters' "%s\%s_streamsets.str" in
 * stream-sets mode (request(path, 0.0f, 0, 0, 0)) - but skips that for
 * folders containing "pdlc". Severed's StreamSet and checkpoint objects only
 * come inside its level SimGroup; as an experiment the probe also requests
 * <folder>\<folder>_streamsets.str (the test archive holds that SimGroup
 * under this name) in stream-sets mode for "pdlc" levels. */
static const char SIG_LEVELSTART[] =
    "81 EC 40 01 00 00 53 55 8B E9 C7 45 18 07 00 00 00 A1 ?? ?? ?? ?? 8B 40 38 D1 E8 24 01 88 44 24 0A 8A 45 1C "
    "D0 E8 24 01 83 7D 4C 00 56 8D 75 28 88 44 24 0F 8B 06 0F 95 44 24 10 57 85 C0 75 05 B8 ?? ?? ?? ?? 68 ?? ?? ?? ?? "
    "50 E8 ?? ?? ?? ?? 8B 0D ?? ?? ?? ??";
typedef void *(__attribute__((thiscall)) *stream_req_fn)(void *mgr, const char *path, float f, int a, int b, int c);
static stream_req_fn g_streamreq;
static void **g_streammgr;


/* ---- F9: request the start sections on the game's thread ---------------
 * Probe 17 requested them at level start, before the main level stream was
 * set up, and ZoneRender crashed on its missing zone. Now F9 (in the black
 * level) queues the request and the game's own thread runs it from its
 * message loop (PeekMessage hook). */
static volatile LONG g_sections_pending;
static int g_severed_level;
static DWORD g_game_thread;
static DWORD g_main_thread;            /* the thread that loaded the probe: the game's main thread */
static const char *g_sections[] = {
    "pdlc1_ch01_mng\\pdlc1_ch01_mng\\drill_tunnel\\drill_tunnel_01\\drill_tunnel_01.str",
    "pdlc1_ch01_mng\\pdlc1_ch01_mng\\drill_tunnel\\drill_tunnel_02\\drill_tunnel_02.str",
    "pdlc1_ch01_mng\\pdlc1_ch01_mng\\drill_tunnel\\drill_cavern_01\\drill_cavern_01.str",
    "pdlc1_ch01_mng\\pdlc1_ch01_mng\\drill_tunnel\\drill_saferoom\\drill_saferoom.str",
    "pdlc1_ch01_mng\\pdlc1_ch01_mng\\shared\\design\\mini-global\\doors_mng\\doors_mng_folderstream.str",
};

/* ---- F8 / F7: send level messages on the game's thread -----------------
 * The engine's message broadcast (retail exe 0x0084F5A0, behind Lua's
 * SendMessage): cdecl (message name, unused, payload); it hashes the name
 * and hands the message to every object listening for it - the same way
 * Severed's own level objects (MultiManagers, scripted sequences) talk.
 * F8 sends Severed's intro hand-over: the end of the RIG call scene
 * (ses_player_01_01_end: pops the scene camera, adds the objective, sets
 * the post-intro checkpoint) and Gabe's starting equipment. F7 sends each
 * line of severed_send.txt in the game folder. */
static const char SIG_SENDMSG[] =
    "83 EC 14 8B 54 24 18 33 C0 66 89 44 24 04 52 8D 44 24 04 33 C9 50 C7 44 24 08 00 00 00 00 66 89 4C 24 0E "
    "E8 ?? ?? ?? ?? 8B 4C 24 08 8B 54 24 28 8D 44 24 10 6A 00 50 89 4C 24 18 C6 44 24 1C 00 89 54 24 20 "
    "E8 ?? ?? ?? ?? 8D 4C 24 10 51 E8 ?? ?? ?? ?? 83 C4 28 C3";
typedef void (__cdecl *send_msg_fn)(const char *name, const char *unused, void *payload);
static send_msg_fn g_sendmsg;
static const char *g_handover[] = {
    "pop_cam_pole_initial",
    "ses_player_01_01_end",
    "equip_command_player_initial",
};
#define MAX_MSGS 32
static char g_msgs[MAX_MSGS][96];
static volatile LONG g_msgs_pending;
static int g_nmsgs;

/* the message function, looked up again on first use (the code may not be
   ready when the hooks are installed); on failure, where the pattern stops
   matching at the retail address (a position only, no code bytes) */
static int find_sendmsg(void)
{
    BYTE b[256], m[256], *p;
    int n, i, nm;
    if (g_sendmsg) return 1;
    g_sendmsg = (send_msg_fn)find_sig(SIG_SENDMSG, &nm);
    if (g_sendmsg) {
        log_line("message send: found at exe+0x%lx", (DWORD)g_sendmsg - (DWORD)GetModuleHandleA(NULL));
        return 1;
    }
    n = parse_sig(SIG_SENDMSG, b, m);
    p = (BYTE *)GetModuleHandleA(NULL) + 0x44F5A0;
    if (!mem_ok(p, n)) { log_line("message send: %d match(es); retail address not readable", nm); return 0; }
    for (i = 0; i < n && (!m[i] || p[i] == b[i]); i++) ;
    log_line("message send: %d match(es); at the retail address the pattern %s at byte %d of %d",
             nm, i == n ? "matches" : "differs", i, n);
    return 0;
}

static void queue_messages(const char **names, int n)
{
    int i;
    if (g_msgs_pending) { log_line("messages: the last ones are still being sent - try again"); return; }
    if (!find_sendmsg()) { log_line("messages: the game's message function was not found - nothing sent"); return; }
    for (i = 0; i < n && i < MAX_MSGS; i++) lstrcpynA(g_msgs[i], names[i], sizeof g_msgs[i]);
    g_nmsgs = i;
    InterlockedExchange(&g_msgs_pending, 1);   /* the list stays untouched until the game thread sets 0 */
    log_line("messages: %d queued for the game thread", g_nmsgs);
}

static void queue_message_file(void)
{
    char path[MAX_PATH], *slash, buf[4096], *line, *names[MAX_MSGS];
    HANDLE f;
    DWORD got = 0;
    int n = 0;
    GetModuleFileNameA(NULL, path, sizeof path);
    slash = strrchr(path, '\\');
    if (slash) lstrcpyA(slash + 1, "severed_send.txt");
    f = CreateFileA(path, GENERIC_READ, FILE_SHARE_READ, NULL, OPEN_EXISTING, 0, NULL);
    if (f == INVALID_HANDLE_VALUE) { log_line("F7: no severed_send.txt in the game folder"); return; }
    ReadFile(f, buf, sizeof buf - 1, &got, NULL);
    CloseHandle(f);
    buf[got] = 0;
    for (line = strtok(buf, "\r\n"); line && n < MAX_MSGS; line = strtok(NULL, "\r\n")) {
        while (*line == ' ' || *line == '\t') line++;
        if (*line && *line != '#') names[n++] = line;
    }
    queue_messages((const char **)names, n);
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

static void heap_watch(void);
static void d3d_guard(void);

static void run_pending_sections(void)
{
    int i;
    if (!g_game_thread && g_main_thread && GetCurrentThreadId() == g_main_thread) {
        g_game_thread = g_main_thread;            /* without the level start hook */
        log_line("game thread: %lu (the main thread)", g_game_thread);
    }
    run_pending_messages();
    heap_watch();
    d3d_guard();
    if (!g_sections_pending || GetCurrentThreadId() != g_game_thread || !g_streamreq || !g_streammgr || !*g_streammgr)
        return;
    if (InterlockedExchange(&g_sections_pending, 0) == 0) return;
    for (i = 0; i < (int)(sizeof g_sections / sizeof g_sections[0]); i++) {
        log_line("F9: requesting section %s", g_sections[i]);
        g_streamreq(*g_streammgr, g_sections[i], 0.0f, 2, 0, 0);
    }
    MessageBeep(MB_ICONASTERISK);
}

typedef BOOL (WINAPI *PeekMessageA_t)(LPMSG, HWND, UINT, UINT, UINT);
typedef BOOL (WINAPI *PeekMessageW_t)(LPMSG, HWND, UINT, UINT, UINT);
static PeekMessageA_t o_PeekMessageA;
static PeekMessageW_t o_PeekMessageW;
static BOOL WINAPI h_PeekMessageA(LPMSG m, HWND w, UINT a, UINT b, UINT r) { run_pending_sections(); return o_PeekMessageA(m, w, a, b, r); }
static BOOL WINAPI h_PeekMessageW(LPMSG m, HWND w, UINT a, UINT b, UINT r) { run_pending_sections(); return o_PeekMessageW(m, w, a, b, r); }

static void __cdecl on_level_start(void *self)
{
    const char *folder = self && mem_ok((BYTE *)self + 0x28, 4) ? *(const char **)((BYTE *)self + 0x28) : NULL;
    char name[128], path[300];
    int n;
    if (!folder || !mem_ok(folder, 1)) return;
    log_line("level start: folder %s", folder);
    g_game_thread = GetCurrentThreadId();
    g_severed_level = 0;
    if (!strstr(folder, "pdlc") || !g_streamreq || !g_streammgr || !*g_streammgr) return;
    lstrcpynA(name, folder, sizeof name);
    n = lstrlenA(name);
    while (n && (name[n - 1] == '\\' || name[n - 1] == '/')) name[--n] = 0;
    if (!lstrcmpiA(name, "pdlc1_ch01_mng")) g_severed_level = 1;
    /* Probe 12's experiment loaded a copy of the level's SimGroup as a stream
       sets file. Since probe 23 it is off: every level object then existed
       twice under the same GUID, and messages aimed at the Player (starting
       equipment, health, Gabe's opening scene) reached the copy instead of
       the player. A file named severed_streamsets.on in the game folder
       turns it back on. */
    {
        char flag[MAX_PATH], *slash;
        GetModuleFileNameA(NULL, flag, sizeof flag);
        slash = strrchr(flag, '\\');
        if (slash) lstrcpyA(slash + 1, "severed_streamsets.on");
        if (GetFileAttributesA(flag) == INVALID_FILE_ATTRIBUTES) {
            log_line("level start: level SimGroup copy not requested (severed_streamsets.on absent)");
            return;
        }
    }
    wsprintfA(path, "%s\\%s_streamsets.str", name, name);
    log_line("level start: requesting %s in stream-sets mode", path);
    g_streamreq(*g_streammgr, path, 0.0f, 0, 0, 0);
}

/* stub: pushad/pushfd, call cb(ecx), restore, run the original first
 * `len` bytes, jump back */
static int hook_call_ecx(BYTE *fn, int len, void (__cdecl *cb)(void *))
{
    BYTE *t = (BYTE *)VirtualAlloc(NULL, 64, MEM_COMMIT | MEM_RESERVE, PAGE_EXECUTE_READWRITE), *q;
    DWORD old;
    if (!t) return 0;
    q = t;
    *q++ = 0x60; *q++ = 0x9C;                      /* pushad, pushfd */
    *q++ = 0x51;                                   /* push ecx */
    *q++ = 0xE8; *(DWORD *)q = (DWORD)cb - (DWORD)(q + 4); q += 4;
    *q++ = 0x83; *q++ = 0xC4; *q++ = 0x04;         /* add esp, 4 */
    *q++ = 0x9D; *q++ = 0x61;                      /* popfd, popad */
    memcpy(q, fn, len); q += len;
    *q++ = 0xE9; *(DWORD *)q = (DWORD)(fn + len) - (DWORD)(q + 4); q += 4;
    if (!VirtualProtect(fn, len, PAGE_EXECUTE_READWRITE, &old)) return 0;
    fn[0] = 0xE9; *(DWORD *)(fn + 1) = (DWORD)t - (DWORD)(fn + 5);
    if (len > 5) memset(fn + 5, 0x90, len - 5);
    VirtualProtect(fn, len, old, &old);
    FlushInstructionCache(GetCurrentProcess(), fn, len);
    return 1;
}


/* ---- SimGroup block loads -----------------------------------------------
 * The SimGroup data block dispatcher (retail exe 0x0085D090, cdecl,
 * argument = block, returns al) sends block 0x011795D9 (packed records,
 * Severed's format) and 0x91C8773C (property tree, base game) to their
 * loaders. Wrapped to log every block and the result. */
static const char SIG_SGBLOCK[] =
    "8B 54 24 04 8B 0A 32 C0 81 F9 D9 95 17 01 75 09 89 54 24 04 E9 ?? ?? ?? ?? 81 F9 3C 77 C8 91 75 09 89 54 24 04 E9";
typedef unsigned char (__cdecl *sgblock_fn)(DWORD *blk);
static sgblock_fn g_sgblock_tramp;

static unsigned char __cdecl hook_sgblock(DWORD *blk)
{
    static LONG n;
    unsigned char r = g_sgblock_tramp(blk);
    if (!g_uniform_logged && mem_ok((void *)0x02098B78, 18 * 4) && (((DWORD *)0x02098B78)[17] & 0xFFFF))
        log_class_fields(0x02098B78, 0x0575C2F4);    /* field list is filled in lazily */
    if (InterlockedIncrement(&n) <= 3000 && mem_ok(blk, 0x18))
        log_line("SIMGROUP block %08lx size 0x%lx records %lu -> %s", blk[0], blk[1], blk[4], r ? "ok" : "FAILED");
    return r;
}

static int hook_wrap(BYTE *fn, int len, void *hook, void **tramp)
{
    BYTE *t = (BYTE *)VirtualAlloc(NULL, 32, MEM_COMMIT | MEM_RESERVE, PAGE_EXECUTE_READWRITE);
    DWORD old;
    if (!t) return 0;
    memcpy(t, fn, len);
    t[len] = 0xE9; *(DWORD *)(t + len + 1) = (DWORD)(fn + len) - (DWORD)(t + len + 5);
    *tramp = t;
    if (!VirtualProtect(fn, len, PAGE_EXECUTE_READWRITE, &old)) return 0;
    fn[0] = 0xE9; *(DWORD *)(fn + 1) = (DWORD)hook - (DWORD)(fn + 5);
    if (len > 5) memset(fn + 5, 0x90, len - 5);
    VirtualProtect(fn, len, old, &old);
    FlushInstructionCache(GetCurrentProcess(), fn, len);
    return 1;
}


/* ---- dynamic geometry batches (probe 24) ---------------------------------
 * Particles, decals and other geometry built each frame go through one batch
 * (retail exe 0x013D2CE0 starts a batch; the batch is drawn at the end of
 * the frame, so a crash there has no useful stack). The return addresses
 * of the latest batch starts are kept and printed with a crash. */
static const char SIG_BATCHBEGIN[] =
    "8B 44 24 14 53 8B 5C 24 14 56 57 81 FB 00 00 00 80 74 04 8B 44 24 14 8B 7C 24 18 8B 15 ?? ?? ?? ?? "
    "0F AF C7 83 C0 0F C1 E8 04 40 C1 E0 04 8B F0";
/* per batch: caller, then begin's arguments (primitive, vertex count,
   stride, count override (0x80000000 = use the next one), count, flag) */
static volatile DWORD g_batch_ring[16][7];
static volatile LONG g_batch_pos;

static void __cdecl note_batch(const DWORD *sp)
{
    LONG i = InterlockedIncrement(&g_batch_pos);
    int k;
    for (k = 0; k < 7; k++) g_batch_ring[i & 15][k] = sp[k];
}

/* ---- heap watch (probe 26) ------------------------------------------------
 * The quarry crash is inside a heap function called by Direct3D, with
 * garbage in the registers: heap corruption. Every 2 s (on the game
 * thread, from the PeekMessage hook) and at a crash, every process heap is
 * validated; the first failure of each heap is logged, which dates the
 * corruption (loading a section vs rendering). */
static DWORD g_heap_tick;
static HANDLE g_heap_bad[64];
static int g_nheap_bad;

static int heap_known_bad(HANDLE h)
{
    int i;
    for (i = 0; i < g_nheap_bad; i++) if (g_heap_bad[i] == h) return 1;
    return 0;
}

static void check_heaps(const char *when)
{
    HANDLE heaps[64];
    DWORD n, i;
    n = GetProcessHeaps(64, heaps);
    if (n > 64) n = 64;
    for (i = 0; i < n; i++) {
        if (heap_known_bad(heaps[i])) continue;
        if (!HeapValidate(heaps[i], 0, NULL)) {
            log_line("HEAP %lu of %lu (%p%s) is CORRUPT - found %s", i, n, heaps[i],
                     heaps[i] == GetProcessHeap() ? ", process heap" : "", when);
            if (g_nheap_bad < 64) g_heap_bad[g_nheap_bad++] = heaps[i];
        }
    }
}

static void heap_watch(void)
{
    DWORD now = GetTickCount();
    if (!g_added || GetCurrentThreadId() != g_game_thread || now - g_heap_tick < 2000) return;
    if (!g_heap_tick) log_line("heap watch: validating all heaps every 2 s");
    g_heap_tick = now;
    check_heaps("by the 2 s check");
}


/* ---- scripted sequence trace (probe 22) ---------------------------------
 * A ScriptedEventSequence runs a table-driven state machine
 * (ScriptedSequenceSM: idle, gotoSS, gotoPos, trackToPos, waitAtSS, faceOrient,
 * action, done, exit). Its states' checks and actions are numbered handlers
 * dispatched by one function (retail exe 0x00ECA440, thiscall, handler number
 * = third argument, 0x0A-0x16). Each handler's result is logged when first
 * seen and whenever it changes, per state machine, so the log shows which
 * state a stuck sequence is in and what it waits for. Values only. */
static const char SIG_SSMHANDLER[] =
    "55 8B EC 83 E4 F0 83 EC 2C 56 8B F1 8B 4D 10 8D 41 F6 83 F8 0C 0F 87 ?? ?? ?? ?? FF 24 85 ?? ?? ?? ?? "
    "8A 46 5C 24 01 5E 8B E5 5D C2 10 00";
typedef DWORD (__attribute__((thiscall)) *ssm_fn)(void *self, DWORD a, DWORD b, DWORD idx, DWORD c);
static ssm_fn g_ssm_tramp;
#define SSM_SLOTS 256
static struct { void *self; DWORD idx, result; } g_ssm[SSM_SLOTS];
static int g_nssm;

static DWORD __attribute__((thiscall)) hook_ssm(void *self, DWORD a, DWORD b, DWORD idx, DWORD c)
{
    static LONG lines;
    DWORD r = g_ssm_tramp(self, a, b, idx, c);
    int i;
    for (i = 0; i < g_nssm; i++)
        if (g_ssm[i].self == self && g_ssm[i].idx == idx) break;
    if (i < g_nssm && g_ssm[i].result == r) return r;
    if (i == g_nssm) {
        if (g_nssm >= SSM_SLOTS) return r;
        g_ssm[i].self = self; g_ssm[i].idx = idx; g_nssm++;
    }
    g_ssm[i].result = r;
    if (InterlockedIncrement(&lines) <= 3000) {
        BYTE *o = (BYTE *)self;
        log_line("SSM %08lx handler 0x%02lx -> %08lx  [+20]=%08lx [+5c]=%08lx [+88]=%08lx", (DWORD)self, idx, r,
                 mem_ok(o + 0x20, 4) ? *(DWORD *)(o + 0x20) : 0, mem_ok(o + 0x5c, 4) ? *(DWORD *)(o + 0x5c) : 0,
                 mem_ok(o + 0x88, 4) ? *(DWORD *)(o + 0x88) : 0);
    }
    return r;
}


/* ---- name hash log ------------------------------------------------------
 * The game's name hash (retail exe 0x007423C0: lower-case sdbm of a C
 * string, cdecl) is used for archive lookups among many other things.
 * Path-like names (containing '\' or '/', or a file extension) are logged
 * once each, so a run shows every file name the game looks for. */
static const char SIG_NAMEHASH[] =
    "8B 54 24 04 33 C0 85 D2 74 25 8A 0A 84 C9 74 1F 56 0F B6 C9 8D 71 BF 42 83 FE 19 77 03 83 C1 20 69 C0 3F 00 01 00";

#define SEEN_BITS (1 << 20)
static BYTE g_nameseen[SEEN_BITS / 8];

static void __cdecl log_name_hash(const char *n)
{
    static LONG count;
    DWORD h = 0, i;
    int pathy = 0;
    if (!n || !mem_ok(n, 1)) return;
    for (i = 0; n[i] && i < 260; i++) {
        BYTE c = (BYTE)n[i];
        if (c == '\\' || c == '/') pathy = 1;
        if (c >= 'A' && c <= 'Z') c += 32;
        h = h * 65599 + c;
    }
    if (!pathy && !(i > 4 && (n[i - 4] == '.' || n[i - 3] == '.'))) return;
    if (g_nameseen[(h >> 3) & (SEEN_BITS / 8 - 1)] & (1 << (h & 7))) return;
    g_nameseen[(h >> 3) & (SEEN_BITS / 8 - 1)] |= (BYTE)(1 << (h & 7));
    if (InterlockedIncrement(&count) > 20000) return;
    log_line("NAME #%08lX %s", h, n);
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
    {
        int ns;
        BYTE *sr = find_sig(SIG_STREAMREQ, &ns);
        log_line("stream request log: %d match(es) at exe+0x%lx%s", ns, sr ? (DWORD)sr - base : 0,
                 sr && hook_log_arg1(sr, 6, log_stream_request) ? ", hooked" : "");
        if (sr) {
            int nl;
            BYTE *ls = find_sig(SIG_LEVELSTART, &nl);
            /* the stub runs the original first bytes, so the request
               function is called through its trampoline-free entry: the
               hooked entry still works (it just logs) */
            g_streamreq = (stream_req_fn)sr;
            if (ls) g_streammgr = *(void ***)(ls + 0x52);
            {
                int nh;
                BYTE *nhf = find_sig(SIG_NAMEHASH, &nh);
                /* probe 16's name hash log: only UI names go through this
                   function, not file paths - left off (it slows the game) */
                (void)nhf; (void)nh; (void)log_name_hash;
            }
            {
                int ng;
                BYTE *sg = find_sig(SIG_SGBLOCK, &ng);
                log_line("simgroup block log: %d match(es) at exe+0x%lx%s", ng, sg ? (DWORD)sg - base : 0,
                         sg && hook_wrap(sg, 6, (void *)hook_sgblock, (void **)&g_sgblock_tramp) ? ", hooked" : "");
            }
            {
                int nq;
                BYTE *q = find_sig(SIG_SSMHANDLER, &nq);
                log_line("scripted sequence trace: %d match(es) at exe+0x%lx%s", nq, q ? (DWORD)q - base : 0,
                         q && hook_wrap(q, 9, (void *)hook_ssm, (void **)&g_ssm_tramp) ? ", hooked" : "");
            }
            {
                int nm;
                g_sendmsg = (send_msg_fn)find_sig(SIG_SENDMSG, &nm);
                log_line("message send: %d match(es) at exe+0x%lx", nm, g_sendmsg ? (DWORD)g_sendmsg - base : 0);
            }
            {
                /* parts of the code are decrypted later than others (probe
                   27's run found neither of these at 0.6 s): retry them
                   every 200 ms for a minute */
                int nb = 0, nm2 = 0, k;
                BYTE *bb = find_sig(SIG_BATCHBEGIN, &nb);
                for (k = 0; k < 300 && (!bb || !ls); k++) {
                    Sleep(200);
                    if (!bb) bb = find_sig(SIG_BATCHBEGIN, &nb);
                    if (!ls) {
                        ls = find_sig(SIG_LEVELSTART, &nl);
                        if (ls) g_streammgr = *(void ***)(ls + 0x52);
                    }
                    if (!g_sendmsg) g_sendmsg = (send_msg_fn)find_sig(SIG_SENDMSG, &nm2);
                }
                log_line("geometry batch tracker: %d match(es) at exe+0x%lx%s (after %d retries)", nb,
                         bb ? (DWORD)bb - base : 0, bb && hook_log_sp(bb, 9, note_batch) ? ", hooked" : "", k);
            }
            log_line("level start: %d match(es) at exe+0x%lx, stream manager global 0x%08lx%s", nl,
                     ls ? (DWORD)ls - base : 0, (DWORD)g_streammgr,
                     ls && hook_call_ecx(ls, 6, on_level_start) ? ", hooked" : "");
        }
    }
    return 0;
}

static void add_severed(void)
{
    int nc;
    BYTE *ctor = find_sig(SIG_CTOR, &nc);   /* hooked now: pattern gone */
    void **global = (void **)0x0201C0E4, *fe;
    (void)ctor; (void)nc;
    log_line("F9: Severed added %ld time(s) by the menu hook", g_added);
    if (g_severed_level) {
        log_line("F9: start sections queued for the game thread (%lu)", g_game_thread);
        InterlockedExchange(&g_sections_pending, 1);
    }
    log_class_fields(0x02098B78, 0x0575C2F4);
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

/* ---- Direct3D object guard (probe 27) -------------------------------------
 * Both quarry crashes read through the same bogus pointer (0x15FFCF8F)
 * inside Direct3D while drawing a full-screen pass, with the heaps intact:
 * likely a released resource still bound. The device's Set* methods are
 * wrapped: an object whose vtable is not in a loaded module is logged with
 * the game code that passed it (once per method and caller), and for
 * textures, buffers, shaders and declarations NULL is passed instead.
 * Textures bound earlier are rechecked before every draw. The
 * device comes from the game's own global, read from the batch flush
 * (exe 0x13D2DC0: `mov eax, [device]` at +0x78). */
static const char SIG_FLUSH[] =
    "51 A1 ?? ?? ?? ?? 8B 0D ?? ?? ?? ?? C6 00 00 8B 01 8B 10 56 50 8B 42 30 FF D0";
static void ***g_devglobal;
static int g_guard_state;              /* 0 not tried, 1 waiting for the device, 2 done */
static volatile LONG g_guard_logs;
static DWORD g_guard_seen[64][2];
static volatile LONG g_guard_nseen;

static int d3d_obj_ok_slow(const void *p)
{
    MEMORY_BASIC_INFORMATION mi;
    const void *vt = *(const void * const *)p;
    return vt && mem_ok(vt, 4) && VirtualQuery(vt, &mi, sizeof mi) && mi.Type == MEM_IMAGE;
}

/* the Set* methods run thousands of times a frame: pages found readable
   this frame and vtables found inside a loaded module are remembered, so
   VirtualQuery runs only for a new page or a new object type (the page
   cache is cleared every frame, so a page freed since is checked again) */
static DWORD g_okpage[256];
static const void *g_okvt[32];
static int g_nokvt;

static int d3d_obj_ok(const void *p)
{
    MEMORY_BASIC_INFORMATION mi;
    const void *vt;
    DWORD pg = (DWORD)p >> 12;
    int i;
    if (!p) return 1;
    if (((DWORD)p & 0xFFF) > 0xFFC) return mem_ok(p, 4) && d3d_obj_ok_slow(p);
    if (g_okpage[pg & 255] != pg) {
        if (!mem_ok(p, 4)) return 0;
        g_okpage[pg & 255] = pg;
    }
    vt = *(const void * const *)p;
    for (i = 0; i < g_nokvt; i++) if (g_okvt[i] == vt) return 1;
    if (!vt || !mem_ok(vt, 4) || !VirtualQuery(vt, &mi, sizeof mi) || mi.Type != MEM_IMAGE) return 0;
    if (g_nokvt < 32) g_okvt[g_nokvt++] = vt;
    return 1;
}

/* returns 1 if p may be passed on */
static int d3d_check(const char *method, DWORD slot, const void *p, void *ret, int replace)
{
    char who[MAX_PATH + 32];
    LONG i, n;
    if (d3d_obj_ok(p)) return 1;
    n = g_guard_nseen < 64 ? g_guard_nseen : 64;
    for (i = 0; i < n; i++)
        if (g_guard_seen[i][0] == (DWORD)method && g_guard_seen[i][1] == (DWORD)ret) return !replace;
    i = InterlockedIncrement(&g_guard_nseen) - 1;
    if (i < 64) { g_guard_seen[i][0] = (DWORD)method; g_guard_seen[i][1] = (DWORD)ret; }
    if (InterlockedIncrement(&g_guard_logs) <= 64) {
        addr_name((DWORD)ret, who, sizeof who);
        log_line("D3D GUARD: %s slot %lu given invalid object %p from %s%s", method, slot, p, who,
                 replace ? " - NULL passed instead" : "");
    }
    return !replace;
}

typedef HRESULT (WINAPI *SetTexture_t)(void *, DWORD, void *);
typedef HRESULT (WINAPI *SetStreamSource_t)(void *, UINT, void *, UINT, UINT);
typedef HRESULT (WINAPI *SetOne_t)(void *, void *);
typedef HRESULT (WINAPI *SetRT_t)(void *, DWORD, void *);
static SetTexture_t o_SetTexture;
static SetStreamSource_t o_SetStreamSource;
static SetOne_t o_SetIndices, o_SetVertexDeclaration, o_SetVertexShader, o_SetPixelShader, o_SetDepthStencil;
static SetRT_t o_SetRenderTarget;

/* what is bound per texture stage (0-15, vertex samplers 257-260 as
   16-19) and by whom, rechecked before each draw: a texture freed while
   still bound is unbound there */
static void *g_bound[20], *g_boundby[20];

static int stage_slot(DWORD st)
{
    return st < 16 ? (int)st : st >= 257 && st <= 260 ? (int)(st - 257 + 16) : -1;
}

/* vertex textures (stages 257-260): the 360 reads any format in a vertex
   shader, PC cards only a few (mostly floating point). Each distinct one is
   logged with its format; with severed_novtf.on in the game folder they are
   unbound before every dynamic-geometry draw (from the batch flush). */
static void *g_vtf_seen[64];
static int g_nvtf_seen, g_novtf;
static BYTE *g_flush_draw_ret;         /* return address of the flush's DrawIndexedPrimitive */

static void log_vertex_texture(DWORD st, void *t, void *ret)
{
    typedef DWORD (WINAPI *GetType_t)(void *);
    typedef HRESULT (WINAPI *GetLevelDesc_t)(void *, UINT, DWORD *);
    DWORD desc[8] = {0}, type;
    char who[MAX_PATH + 32];
    int i;
    for (i = 0; i < g_nvtf_seen; i++) if (g_vtf_seen[i] == t) return;
    if (g_nvtf_seen < 64) g_vtf_seen[g_nvtf_seen++] = t;
    type = ((GetType_t)(*(void ***)t)[10])(t);                 /* IDirect3DResource9::GetType */
    if (type == 3)                                             /* D3DRTYPE_TEXTURE */
        ((GetLevelDesc_t)(*(void ***)t)[17])(t, 0, desc);      /* IDirect3DTexture9::GetLevelDesc */
    addr_name((DWORD)ret, who, sizeof who);
    if (InterlockedIncrement(&g_guard_logs) <= 64)
        log_line("vertex texture: stage %lu texture %p type %lu format 0x%08lx (%c%c%c%c) %lux%lu, from %s", st, t, type,
                 desc[0], (char)(desc[0] & 0xFF) >= 32 ? (char)(desc[0] & 0xFF) : '.',
                 (char)(desc[0] >> 8 & 0xFF) >= 32 ? (char)(desc[0] >> 8 & 0xFF) : '.',
                 (char)(desc[0] >> 16 & 0xFF) >= 32 ? (char)(desc[0] >> 16 & 0xFF) : '.',
                 (char)(desc[0] >> 24 & 0xFF) >= 32 ? (char)(desc[0] >> 24 & 0xFF) : '.', desc[6], desc[7], who);
}

static HRESULT WINAPI g_SetTexture(void *d, DWORD st, void *t)
{
    void *ret = __builtin_return_address(0);
    int k = stage_slot(st);
    if (!d3d_check("SetTexture", st, t, ret, 1)) t = NULL;
    if (t && st >= 257 && st <= 260) log_vertex_texture(st, t, ret);
    if (k >= 0) { g_bound[k] = t; g_boundby[k] = ret; }
    return o_SetTexture(d, st, t);
}

static void check_bound(void *d, void *drawret)
{
    char who[MAX_PATH + 32], draw[MAX_PATH + 32];
    int k;
    if (g_novtf && drawret == g_flush_draw_ret)
        for (k = 16; k < 20; k++)
            if (g_bound[k]) { o_SetTexture(d, (DWORD)(257 + k - 16), NULL); g_bound[k] = NULL; }
    for (k = 0; k < 20; k++) {
        if (!g_bound[k] || d3d_obj_ok(g_bound[k])) continue;
        if (InterlockedIncrement(&g_guard_logs) <= 64) {
            addr_name((DWORD)g_boundby[k], who, sizeof who);
            addr_name((DWORD)drawret, draw, sizeof draw);
            log_line("D3D GUARD: texture %p on stage %d (set from %s) is no longer valid at a draw from %s - unbound",
                     g_bound[k], k < 16 ? k : 257 + k - 16, who, draw);
        }
        o_SetTexture(d, k < 16 ? (DWORD)k : (DWORD)(257 + k - 16), NULL);
        g_bound[k] = NULL;
    }
}

/* ---- state calls (probe 30) ---------------------------------------------
 * Probe 29 found every bound object valid at the crash, with 0x15FFCF8F
 * still in a register: possibly a state value used by Direct3D as an
 * index. Render, texture stage and sampler state calls go into a ring
 * (shown at a crash, with any call whose value matches a register), and
 * sampler states outside their valid ranges are logged when set. */
typedef HRESULT (WINAPI *SetState_t)(void *, DWORD, DWORD);
typedef HRESULT (WINAPI *SetStage_t)(void *, DWORD, DWORD, DWORD);
static SetState_t o_SetRenderState;
static SetStage_t o_SetTextureStageState, o_SetSamplerState;
static volatile DWORD g_st_ring[256][5];   /* kind, stage, state, value, caller */
static volatile LONG g_st_pos;

static void note_state(DWORD kind, DWORD stage, DWORD state, DWORD value, void *ret)
{
    LONG i = InterlockedIncrement(&g_st_pos) & 255;
    g_st_ring[i][0] = kind; g_st_ring[i][1] = stage; g_st_ring[i][2] = state;
    g_st_ring[i][3] = value; g_st_ring[i][4] = (DWORD)ret;
}

static int sampler_value_ok(DWORD state, DWORD v)
{
    switch (state) {
    case 1: case 2: case 3: return v >= 1 && v <= 5;          /* ADDRESSU/V/W */
    case 5: case 6: case 7: return v <= 8;                    /* MAG/MIN/MIPFILTER */
    case 9: return v < 16;                                    /* MAXMIPLEVEL */
    case 10: return v <= 16;                                  /* MAXANISOTROPY */
    case 11: return v <= 1;                                   /* SRGBTEXTURE */
    case 12: return v < 256;                                  /* ELEMENTINDEX */
    case 4: case 8: case 13: return 1;                        /* border colour, LOD bias, DMAP offset */
    default: return 0;                                        /* no such state */
    }
}

static HRESULT WINAPI g_SetRenderState(void *d, DWORD st, DWORD v)
{ note_state(1, 0, st, v, __builtin_return_address(0)); return o_SetRenderState(d, st, v); }
static HRESULT WINAPI g_SetTextureStageState(void *d, DWORD stage, DWORD st, DWORD v)
{ note_state(2, stage, st, v, __builtin_return_address(0)); return o_SetTextureStageState(d, stage, st, v); }
static HRESULT WINAPI g_SetSamplerState(void *d, DWORD stage, DWORD st, DWORD v)
{
    void *ret = __builtin_return_address(0);
    note_state(3, stage, st, v, ret);
    if (!sampler_value_ok(st, v)) {
        char who[MAX_PATH + 32];
        LONG i, n = g_guard_nseen < 64 ? g_guard_nseen : 64;
        for (i = 0; i < n; i++)
            if (g_guard_seen[i][0] == 3 && g_guard_seen[i][1] == (DWORD)ret) goto pass;
        i = InterlockedIncrement(&g_guard_nseen) - 1;
        if (i < 64) { g_guard_seen[i][0] = 3; g_guard_seen[i][1] = (DWORD)ret; }
        if (InterlockedIncrement(&g_guard_logs) <= 64) {
            addr_name((DWORD)ret, who, sizeof who);
            log_line("D3D GUARD: SetSamplerState stage %lu state %lu value 0x%08lx out of range, from %s",
                     stage, st, v, who);
        }
    }
pass:
    return o_SetSamplerState(d, stage, st, v);
}

static void log_states(const CONTEXT *c)
{
    static const char *kinds[] = { "?", "RenderState", "TextureStageState", "SamplerState" };
    DWORD regs[7] = { c->Eax, c->Ebx, c->Ecx, c->Edx, c->Esi, c->Edi, c->Ebp };
    char who[MAX_PATH + 32];
    LONG last = g_st_pos, k;
    int r, shown = 0;
    for (k = 0; k < 256; k++) {           /* calls whose value is in a register */
        volatile DWORD *e = g_st_ring[(DWORD)(last - k) & 255];
        if (!e[0] || e[3] < 0x10000) continue;
        for (r = 0; r < 7; r++)
            if (e[3] == regs[r] || (e[3] & ~0xF) == (regs[r] & ~0xF)) {
                addr_name(e[4], who, sizeof who);
                log_line("  %s stage %lu state %lu = 0x%08lx (in a register at the crash), %ld calls ago, from %s",
                         kinds[e[0] & 3], e[1], e[2], e[3], (long)k, who);
                shown++;
                break;
            }
    }
    for (k = 0; k < 24; k++) {            /* the last calls */
        volatile DWORD *e = g_st_ring[(DWORD)(last - k) & 255];
        if (!e[0]) continue;
        addr_name(e[4], who, sizeof who);
        log_line("  state call -%ld: %s stage %lu state %lu = 0x%08lx from %s", (long)k, kinds[e[0] & 3], e[1], e[2], e[3], who);
    }
    (void)shown;
}

typedef HRESULT (WINAPI *DrawPrim_t)(void *, DWORD, UINT, UINT);
typedef HRESULT (WINAPI *DrawIdx_t)(void *, DWORD, INT, UINT, UINT, UINT, UINT);
typedef HRESULT (WINAPI *DrawPrimUP_t)(void *, DWORD, UINT, const void *, UINT);
typedef HRESULT (WINAPI *DrawIdxUP_t)(void *, DWORD, UINT, UINT, UINT, const void *, DWORD, const void *, UINT);
static DrawPrim_t o_DrawPrimitive;
static DrawIdx_t o_DrawIndexedPrimitive;
static DrawPrimUP_t o_DrawPrimitiveUP;
static DrawIdxUP_t o_DrawIndexedPrimitiveUP;

static HRESULT WINAPI g_DrawPrimitive(void *d, DWORD t, UINT s0, UINT n)
{ check_bound(d, __builtin_return_address(0)); return o_DrawPrimitive(d, t, s0, n); }
static HRESULT WINAPI g_DrawIndexedPrimitive(void *d, DWORD t, INT b, UINT mn, UINT nv, UINT si, UINT pc)
{ check_bound(d, __builtin_return_address(0)); return o_DrawIndexedPrimitive(d, t, b, mn, nv, si, pc); }
static HRESULT WINAPI g_DrawPrimitiveUP(void *d, DWORD t, UINT n, const void *v, UINT st)
{ check_bound(d, __builtin_return_address(0)); return o_DrawPrimitiveUP(d, t, n, v, st); }
static HRESULT WINAPI g_DrawIndexedPrimitiveUP(void *d, DWORD t, UINT mn, UINT nv, UINT pc, const void *i, DWORD f, const void *v, UINT st)
{ check_bound(d, __builtin_return_address(0)); return o_DrawIndexedPrimitiveUP(d, t, mn, nv, pc, i, f, v, st); }
static HRESULT WINAPI g_SetStreamSource(void *d, UINT n, void *vb, UINT off, UINT stride)
{ if (!d3d_check("SetStreamSource", n, vb, __builtin_return_address(0), 1)) vb = NULL; return o_SetStreamSource(d, n, vb, off, stride); }
static HRESULT WINAPI g_SetIndices(void *d, void *ib)
{ if (!d3d_check("SetIndices", 0, ib, __builtin_return_address(0), 1)) ib = NULL; return o_SetIndices(d, ib); }
static HRESULT WINAPI g_SetVertexDeclaration(void *d, void *v)
{ if (!d3d_check("SetVertexDeclaration", 0, v, __builtin_return_address(0), 1)) v = NULL; return o_SetVertexDeclaration(d, v); }
static HRESULT WINAPI g_SetVertexShader(void *d, void *v)
{ if (!d3d_check("SetVertexShader", 0, v, __builtin_return_address(0), 1)) v = NULL; return o_SetVertexShader(d, v); }
static HRESULT WINAPI g_SetPixelShader(void *d, void *v)
{ if (!d3d_check("SetPixelShader", 0, v, __builtin_return_address(0), 1)) v = NULL; return o_SetPixelShader(d, v); }
static HRESULT WINAPI g_SetRenderTarget(void *d, DWORD i, void *v)
{ d3d_check("SetRenderTarget", i, v, __builtin_return_address(0), 0); return o_SetRenderTarget(d, i, v); }
static HRESULT WINAPI g_SetDepthStencil(void *d, void *v)
{ d3d_check("SetDepthStencilSurface", 0, v, __builtin_return_address(0), 0); return o_SetDepthStencil(d, v); }

static void vt_patch(void **vt, int i, void *hook, void **orig)
{
    DWORD old;
    if (vt[i] == hook) return;
    if (!VirtualProtect(&vt[i], 4, PAGE_EXECUTE_READWRITE, &old)) return;
    *orig = vt[i];
    vt[i] = hook;
    VirtualProtect(&vt[i], 4, old, &old);
}

static void d3d_guard(void)
{
    void **dev, **vt;
    if (GetCurrentThreadId() != g_game_thread) return;
    if (g_guard_state == 2) { memset(g_okpage, 0, sizeof g_okpage); return; }
    if (g_guard_state == 0) {
        /* the code may still be encrypted early on (probe 28's run looked
           at 0.19 s): look again every 2 s for 10 minutes */
        static DWORD next, tries;
        int n = 0;
        BYTE *f;
        if (GetTickCount() < next) return;
        next = GetTickCount() + 2000;
        f = find_sig(SIG_FLUSH, &n);
        if (!f || n != 1 || f[0x78] != 0xA1) {
            if (++tries >= 300) {
                log_line("D3D guard: batch flush not found (%d matches) after 10 minutes - guard off", n);
                g_guard_state = 2;
            }
            return;
        }
        log_line("D3D guard: batch flush found after %lu tries", tries);
        g_devglobal = *(void ****)(f + 0x79);
        g_flush_draw_ret = f + 0xBA;    /* after the flush's call [DrawIndexedPrimitive] (exe 0x13D2E7A) */
        {
            char path[MAX_PATH], *slash;
            GetModuleFileNameA(NULL, path, sizeof path);
            slash = strrchr(path, '\\');
            if (slash) lstrcpyA(slash + 1, "severed_novtf.on");
            g_novtf = GetFileAttributesA(path) != INVALID_FILE_ATTRIBUTES;
            log_line("D3D guard: vertex textures %s before dynamic-geometry draws%s", g_novtf ? "UNBOUND" : "left as they are",
                     g_novtf ? " (severed_novtf.on)" : "");
        }
        g_guard_state = 1;
    }
    if (!mem_ok(g_devglobal, 4) || !*g_devglobal || !mem_ok(*g_devglobal, 4)) return;
    dev = (void **)*g_devglobal;
    vt = (void **)*dev;
    if (!mem_ok(vt, 108 * 4)) return;
    vt_patch(vt, 37, (void *)g_SetRenderTarget, (void **)&o_SetRenderTarget);
    vt_patch(vt, 39, (void *)g_SetDepthStencil, (void **)&o_SetDepthStencil);
    vt_patch(vt, 57, (void *)g_SetRenderState, (void **)&o_SetRenderState);
    vt_patch(vt, 65, (void *)g_SetTexture, (void **)&o_SetTexture);
    vt_patch(vt, 67, (void *)g_SetTextureStageState, (void **)&o_SetTextureStageState);
    vt_patch(vt, 69, (void *)g_SetSamplerState, (void **)&o_SetSamplerState);
    vt_patch(vt, 81, (void *)g_DrawPrimitive, (void **)&o_DrawPrimitive);
    vt_patch(vt, 82, (void *)g_DrawIndexedPrimitive, (void **)&o_DrawIndexedPrimitive);
    vt_patch(vt, 83, (void *)g_DrawPrimitiveUP, (void **)&o_DrawPrimitiveUP);
    vt_patch(vt, 84, (void *)g_DrawIndexedPrimitiveUP, (void **)&o_DrawIndexedPrimitiveUP);
    vt_patch(vt, 87, (void *)g_SetVertexDeclaration, (void **)&o_SetVertexDeclaration);
    vt_patch(vt, 92, (void *)g_SetVertexShader, (void **)&o_SetVertexShader);
    vt_patch(vt, 100, (void *)g_SetStreamSource, (void **)&o_SetStreamSource);
    vt_patch(vt, 104, (void *)g_SetIndices, (void **)&o_SetIndices);
    vt_patch(vt, 107, (void *)g_SetPixelShader, (void **)&o_SetPixelShader);
    g_guard_state = 2;
    log_line("D3D guard: device %p, Set* methods checked from now on", dev);
}

/* a loaded mesh: header 'MGAE'; header 0x20 = model name (offset, or pointer after relocation) */
static int mesh_name(DWORD q, char *out, int n)
{
    DWORD off;
    const char *s;
    int i;
    if (q < 0x10000 || (q & 3) || !mem_ok((void *)q, 0x24) || memcmp((void *)q, "MGAE", 4) != 0) return 0;
    off = *(DWORD *)(q + 0x20);         /* file offset, or a pointer once relocated */
    if (off < 0x24) return 0;
    s = off < 0x4000000 ? (const char *)(q + off) : (const char *)off;
    for (i = 0; i < n - 1 && mem_ok(s + i, 1) && s[i] >= 32 && s[i] < 127; i++) out[i] = s[i];
    out[i] = 0;
    return i > 0;
}

/* meshes reachable from a register: the pointed object and the objects its
   first 64 words point to (data only) */
static void log_meshes_near(const char *reg, DWORD p)
{
    char name[96];
    DWORD i, j, q, r, found = 0;
    if (mesh_name(p, name, sizeof name)) { log_line("  %s -> mesh %s", reg, name); return; }
    if (p < 0x10000 || !mem_ok((void *)p, 256)) return;
    for (i = 0; i < 64 && found < 4; i++) {
        q = ((DWORD *)p)[i];
        if (mesh_name(q, name, sizeof name)) { log_line("  %s+0x%02lx -> mesh %s", reg, i * 4, name); found++; continue; }
        if (q < 0x10000 || (q & 3) || !mem_ok((void *)q, 128)) continue;
        for (j = 0; j < 32; j++) {
            r = ((DWORD *)q)[j];
            if (mesh_name(r, name, sizeof name)) { log_line("  %s+0x%02lx+0x%02lx -> mesh %s", reg, i * 4, j * 4, name); found++; break; }
        }
    }
}

static LONG WINAPI crash_handler(EXCEPTION_POINTERS *e)
{
    static LONG count;
    static volatile DWORD seen[32];             /* addresses already reported */
    EXCEPTION_RECORD *r = e->ExceptionRecord;
    CONTEXT *c = e->ContextRecord;
    char where[MAX_PATH + 32], ra[MAX_PATH + 32];
    DWORD *sp, i, found = 0;
    if (r->ExceptionCode < 0xC0000000 || r->ExceptionCode == 0xC0000027 /* unwind */ ||
        r->ExceptionCode == 0xE06D7363 /* C++ throw */ || !g_added /* start-up: the DRM uses exceptions */)
        return EXCEPTION_CONTINUE_SEARCH;
    /* an exception the game handles itself can repeat: report each address
       once, so the budget is left for the crash */
    for (i = 0; i < 32; i++)
        if (seen[i] == (DWORD)r->ExceptionAddress) return EXCEPTION_CONTINUE_SEARCH;
    if (InterlockedIncrement(&count) > 20) return EXCEPTION_CONTINUE_SEARCH;
    seen[(count - 1) & 31] = (DWORD)r->ExceptionAddress;
    g_crash_thread = GetCurrentThreadId();
    addr_name((DWORD)r->ExceptionAddress, where, sizeof where);
    log_line("EXCEPTION 0x%08lx at %s thread %lu%s", r->ExceptionCode, where, GetCurrentThreadId(),
             r->ExceptionCode == 0xC0000005 ? "" : "");
    if (r->ExceptionCode == 0xC0000005 && r->NumberParameters >= 2)
        log_line("  %s address 0x%08lx", r->ExceptionInformation[0] == 0 ? "reading" : r->ExceptionInformation[0] == 1 ? "writing" : "executing",
                 (DWORD)r->ExceptionInformation[1]);
    log_line("  eax %08lx ebx %08lx ecx %08lx edx %08lx esi %08lx edi %08lx ebp %08lx esp %08lx",
             c->Eax, c->Ebx, c->Ecx, c->Edx, c->Esi, c->Edi, c->Ebp, c->Esp);
    {
        LONG k, last = g_batch_pos;
        char who[MAX_PATH + 32];
        for (k = 0; k < 16; k++) {               /* unset slots are 0; wraps safely */
            volatile DWORD *b = g_batch_ring[(DWORD)(last - k) & 15];
            if (!b[0]) continue;
            addr_name(b[0], who, sizeof who);
            log_line("  geometry batch %ld started from %s (prim %lu, verts %lu, stride %lu, %08lx, count %lu, %lu)",
                     (long)k, who, b[1], b[2], b[3], b[4], b[5], b[6]);
        }
    }
    if (GetCurrentThreadId() == g_game_thread) check_heaps("at the crash");
    {
        int k;
        char who[MAX_PATH + 32];
        for (k = 0; k < 20; k++) {
            if (!g_bound[k]) continue;
            addr_name((DWORD)g_boundby[k], who, sizeof who);
            log_line("  texture stage %d: %p%s, set from %s", k < 16 ? k : 257 + k - 16, g_bound[k],
                     mem_ok(g_bound[k], 4) ? "" : " (NOT readable)", who);
        }
        log_states(c);
    }
    log_meshes_near("eax", c->Eax); log_meshes_near("ebx", c->Ebx); log_meshes_near("ecx", c->Ecx);
    log_meshes_near("edx", c->Edx); log_meshes_near("esi", c->Esi); log_meshes_near("edi", c->Edi);
    log_meshes_near("ebp", c->Ebp);
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
    g_crash_thread = 0;
    return EXCEPTION_CONTINUE_SEARCH;
}

static DWORD WINAPI hotkey_thread(LPVOID p)
{
    (void)p;
    for (;;) {
        Sleep(200);
        /* with Alt, Ctrl or Shift held the keys belong to other programs
           (Alt+F9 records in the Nvidia overlay) */
        if ((GetAsyncKeyState(VK_MENU) | GetAsyncKeyState(VK_CONTROL) | GetAsyncKeyState(VK_SHIFT)) & 0x8000) {
            while ((GetAsyncKeyState(VK_F7) | GetAsyncKeyState(VK_F8) | GetAsyncKeyState(VK_F9) |
                    GetAsyncKeyState(VK_F10) | GetAsyncKeyState(VK_F11)) & 0x8000) Sleep(100);
            continue;
        }
        if (GetAsyncKeyState(VK_F9) & 0x8000) {
            add_severed();
            while (GetAsyncKeyState(VK_F9) & 0x8000) Sleep(100);
        }
        if (GetAsyncKeyState(VK_F8) & 0x8000) {
            if (!g_game_thread) log_line("F8: game thread not known yet (start a level first)");
            else queue_messages(g_handover, (int)(sizeof g_handover / sizeof g_handover[0]));
            while (GetAsyncKeyState(VK_F8) & 0x8000) Sleep(100);
        }
        if (GetAsyncKeyState(VK_F7) & 0x8000) {
            if (!g_game_thread) log_line("F7: game thread not known yet (start a level first)");
            else queue_message_file();
            while (GetAsyncKeyState(VK_F7) & 0x8000) Sleep(100);
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
    g_main_thread = GetCurrentThreadId();
    g_tls = TlsAlloc();
    g_tick0 = GetTickCount();
    GetModuleFileNameA(NULL, path, sizeof path);
    slash = strrchr(path, '\\');
    if (slash) lstrcpyA(slash + 1, "severed_probe.log");
    g_log = CreateFileA(path, GENERIC_WRITE, FILE_SHARE_READ, NULL, CREATE_ALWAYS, FILE_ATTRIBUTE_NORMAL, NULL);

    GetModuleFileNameA(NULL, path, sizeof path);
    log_line("severed probe 30 - process %s", path);
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
    install("PeekMessageA", (void *)h_PeekMessageA, (void **)&o_PeekMessageA);
    install("PeekMessageW", (void *)h_PeekMessageW, (void **)&o_PeekMessageW);
    log_line("--- hooks installed ---");
    CloseHandle(CreateThread(NULL, 0, hotkey_thread, NULL, 0, NULL));
    CloseHandle(CreateThread(NULL, 0, menu_hook_thread, NULL, 0, NULL));
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
