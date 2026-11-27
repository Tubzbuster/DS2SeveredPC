#define WIN32_LEAN_AND_MEAN
#define NOMINMAX
#include "plugin_support.hpp"
#include "safetyhook/safetyhook.hpp"
#include <algorithm>
#include <array>
#include <atomic>
#include <bcrypt.h>
#include <limits>
#include <string>
#include <vector>

namespace {
constexpr char holdName[] = "pc_2h_aim_cbeam_firehold";
constexpr unsigned nameOffset = 0xA70;
constexpr std::array<uint32_t, 11> suits = {
    0x040B61F4, 0x13103924, 0x15A33D4B, 0x177F0697, 0x4CD4067E, 0x723D4C35,
    0x78416FE9, 0x83D8BD12, 0xDF248CA0, 0xE23DAB1A, 0xEDEC388B,
};
using Offsets = std::array<uint64_t, suits.size()>;
struct Bank {
    const char* name;
    uint32_t size;
    uint32_t id;
    const char* sha256;
};
constexpr Bank normal = {"pc_nolegs.bnk", 224956, 0x2DF9F37B,
    "f8fb66529d81d4083cae9263536136a0c653a7afc49ad1ead08dedd42eaf5675"};
constexpr Bank patrol = {"pc_nolegs_patrol.bnk", 225084, 0x254C43F2,
    "03cfb71d4e9617facd348c677169bb6c56feaf6c52ef7624276e52aa13195149"};

plugin_support::Log diagnostic;
safetyhook::InlineHook readHook;
Offsets offsets{};
BY_HANDLE_FILE_INFORMATION archiveIdentity{};
std::atomic<unsigned> patchedSlots{0};
std::atomic<bool> pendingLogged{false};

uint32_t be32(const BYTE* p) {
    return (uint32_t(p[0]) << 24) | (uint32_t(p[1]) << 16) | (uint32_t(p[2]) << 8) | p[3];
}

uint32_t le32(const BYTE* p) {
    uint32_t value;
    memcpy(&value, p, sizeof(value));
    return value;
}

bool read_at(HANDLE file, uint64_t offset, void* into, DWORD count) {
    LARGE_INTEGER distance{};
    distance.QuadPart = offset;
    DWORD received = 0;
    return SetFilePointerEx(file, distance, nullptr, FILE_BEGIN) &&
           ReadFile(file, into, count, &received, nullptr) && received == count;
}

bool has_sha256(const std::vector<BYTE>& input, const char* expected) {
    BCRYPT_ALG_HANDLE algorithm = nullptr;
    if (BCryptOpenAlgorithmProvider(&algorithm, BCRYPT_SHA256_ALGORITHM, nullptr, 0) < 0) return false;
    BYTE digest[32]{};
    NTSTATUS status = BCryptHash(algorithm, nullptr, 0, const_cast<BYTE*>(input.data()),
        static_cast<ULONG>(input.size()), digest, sizeof(digest));
    BCryptCloseAlgorithmProvider(algorithm, 0);
    if (status < 0) return false;
    char asHex[65]{};
    for (unsigned i = 0; i < sizeof(digest); ++i)
        sprintf_s(asHex + 2*i, 3, "%02x", unsigned(digest[i]));
    return strcmp(asHex, expected) == 0;
}

bool find_bank(HANDLE file, uint64_t start, uint64_t end, const Bank& expected, uint64_t& output) {
    BYTE magic[12];
    if (!read_at(file, start, magic, sizeof(magic)) || memcmp(magic, "3slo", 4)) return false;
    std::vector<BYTE> bank(expected.size);
    size_t assembled = 0;
    bool selected = false;
    for (uint64_t cursor = start + 12; cursor + 12 <= end;) {
        BYTE chunk[12];
        if (!read_at(file, cursor, chunk, sizeof(chunk))) return false;
        uint32_t length = le32(chunk + 4);
        if (length < 8 || length > end - cursor) return false;
        if (!memcmp(chunk, "COHS", 4) && !memcmp(chunk + 8, "RDHS", 4)) {
            if (selected) return false;
            BYTE head[80]{};
            if (length >= 44 + strlen(expected.name) + 1) {
                DWORD need = static_cast<DWORD>(44 + strlen(expected.name) + 1);
                if (!read_at(file, cursor, head, need)) return false;
                selected = le32(head + 12) == 0x3D074740 && le32(head + 20) == 0x30B00ADF &&
                    le32(head + 24) == expected.id && le32(head + 40) == expected.size &&
                    !memcmp(head + 44, expected.name, strlen(expected.name) + 1);
            }
        } else if (selected && !memcmp(chunk, "COHS", 4)) {
            if (length < 12 || memcmp(chunk + 8, "TADS", 4)) return false;
            size_t count = std::min<size_t>(length - 12, expected.size - assembled);
            if (assembled <= nameOffset && nameOffset + sizeof(holdName) <= assembled + count)
                output = cursor + 12 + nameOffset - assembled;
            if (!read_at(file, cursor + 12, bank.data() + assembled, static_cast<DWORD>(count))) return false;
            assembled += count;
            if (assembled == expected.size)
                return output && !memcmp(bank.data() + nameOffset, holdName, sizeof(holdName)) &&
                    has_sha256(bank, expected.sha256);
        }
        cursor += length;
    }
    return false;
}

bool inspect_archive(HANDLE file, BY_HANDLE_FILE_INFORMATION& identity, Offsets& result) {
    if (!GetFileInformationByHandle(file, &identity) || identity.nFileSizeHigh) return false;
    uint64_t bytes = identity.nFileSizeLow;
    BYTE header[16];
    if (bytes < 16 || !read_at(file, 0, header, sizeof(header)) ||
        memcmp(header, "BIGH", 4) || le32(header + 4) != bytes) return false;
    uint32_t count = be32(header + 8);
    uint32_t dataStart = be32(header + 12);
    if (!count || count > 65536 || 16 + count * 12 > dataStart || dataStart > bytes) return false;
    std::vector<BYTE> table(count * 12);
    if (!read_at(file, 16, table.data(), static_cast<DWORD>(table.size()))) return false;
    for (uint32_t i = 0; i < count; ++i) {
        const BYTE* row = table.data() + 12*i;
        auto suite = std::find(suits.begin(), suits.end(), be32(row + 8));
        if (suite == suits.end()) continue;
        size_t index = suite - suits.begin();
        uint64_t start = be32(row);
        uint64_t end = start + be32(row + 4);
        const Bank& bank = *suite == 0x83D8BD12 ? patrol : normal;
        if (result[index] || start < dataStart || end > bytes || end <= start ||
            !find_bank(file, start, end, bank, result[index])) return false;
    }
    return std::all_of(result.begin(), result.end(), [](uint64_t position) { return position; });
}

bool same_archive(HANDLE file) {
    BY_HANDLE_FILE_INFORMATION info{};
    return GetFileInformationByHandle(file, &info) &&
        info.dwVolumeSerialNumber == archiveIdentity.dwVolumeSerialNumber &&
        info.nFileIndexLow == archiveIdentity.nFileIndexLow &&
        info.nFileIndexHigh == archiveIdentity.nFileIndexHigh &&
        info.nFileSizeLow == archiveIdentity.nFileSizeLow &&
        info.nFileSizeHigh == archiveIdentity.nFileSizeHigh &&
        CompareFileTime(&info.ftLastWriteTime, &archiveIdentity.ftLastWriteTime) == 0;
}

bool covers(uint64_t pos, size_t size, uint64_t target) {
    return target >= pos && target - pos <= size && sizeof(holdName) <= size - (target - pos);
}

bool could_cover(uint64_t pos, size_t size) {
    return std::any_of(offsets.begin(), offsets.end(), [=](uint64_t target) {
        return covers(pos, size, target);
    });
}

unsigned patch_completed_read(BYTE* buffer, size_t bytes, uint64_t position) {
    unsigned result = 0;
    for (size_t i = 0; i < offsets.size(); ++i) {
        uint64_t target = offsets[i];
        if (!covers(position, bytes, target)) continue;
        BYTE* field = buffer + (target - position);
        if (memcmp(field, holdName, sizeof(holdName))) continue;
        field[sizeof(holdName) - 2] = 'x';
        result |= 1u << i;
    }
    return result;
}

BOOL WINAPI read_file(HANDLE file, LPVOID buffer, DWORD requested, LPDWORD bytes, LPOVERLAPPED overlapped) {
    DWORD incomingError = GetLastError();
    uint64_t position = UINT64_MAX;
    if (buffer && requested >= sizeof(holdName)) {
        if (overlapped)
            position = (uint64_t(overlapped->OffsetHigh) << 32) | overlapped->Offset;
        else {
            LARGE_INTEGER distance{}, current{};
            if (SetFilePointerEx(file, distance, &current, FILE_CURRENT))
                position = current.QuadPart;
        }
    }
    bool eligible = position != UINT64_MAX && could_cover(position, requested) && same_archive(file);
    SetLastError(incomingError);
    BOOL result = readHook.stdcall<BOOL>(file, buffer, requested, bytes, overlapped);
    DWORD error = GetLastError();
    if (eligible && result) {
        size_t completed = bytes ? *bytes : overlapped ? overlapped->InternalHigh : 0;
        if (completed <= requested) {
            unsigned changed = patch_completed_read(static_cast<BYTE*>(buffer), completed, position);
            if (changed && (patchedSlots.fetch_or(changed) & changed) != changed)
                diagnostic.write("Contact Beam standing state overridden in a completed suit-stream read.");
        }
    } else if (eligible && overlapped && error == ERROR_IO_PENDING && !pendingLogged.exchange(true)) {
        diagnostic.write("A matching read is pending asynchronously. That buffer was left unchanged.");
    }
    SetLastError(error);
    return result;
}

bool attach(const wchar_t* filename) {
    HANDLE file = CreateFileW(filename, GENERIC_READ, FILE_SHARE_READ | FILE_SHARE_DELETE,
        nullptr, OPEN_EXISTING, FILE_ATTRIBUTE_NORMAL, nullptr);
    if (file == INVALID_HANDLE_VALUE) return false;
    bool supported = inspect_archive(file, archiveIdentity, offsets);
    CloseHandle(file);
    if (!supported) return false;
    FARPROC target = GetProcAddress(GetModuleHandleW(L"kernel32.dll"), "ReadFile");
    if (!target) return false;
    plugin_support::PatchGuard guard;
    if (!guard.ready()) return false;
    auto created = safetyhook::InlineHook::create(reinterpret_cast<void*>(target),
        reinterpret_cast<void*>(&read_file), safetyhook::InlineHook::StartDisabled);
    if (!created) return false;
    readHook = std::move(*created);
    return readHook.enable().has_value();
}

#ifndef CONTACT_BEAM_TEST
DWORD WINAPI start(void*) {
    diagnostic.open(reinterpret_cast<void*>(&start), L"SeveredContactBeamFix.log");
    wchar_t exe[MAX_PATH]{};
    DWORD length = GetModuleFileNameW(nullptr, exe, MAX_PATH);
    if (!length || length >= MAX_PATH) return 0;
    wchar_t* last = wcsrchr(exe, L'\\');
    if (!last || wcscpy_s(last + 1, MAX_PATH - (last + 1 - exe), L"DS2DAT2.DAT")) return 0;
    diagnostic.write(attach(exe) ? "Contact Beam read filter active. Eleven original suit banks verified."
        : "Archive or hook unavailable. Game data unchanged.");
    return 0;
}
#endif
}

#ifndef CONTACT_BEAM_TEST
BOOL WINAPI DllMain(HINSTANCE module, DWORD reason, LPVOID) {
    if (reason == DLL_PROCESS_ATTACH) {
        DisableThreadLibraryCalls(module);
        if (plugin_support::game_host()) {
            HANDLE worker = CreateThread(nullptr, 0, start, nullptr, 0, nullptr);
            if (worker) CloseHandle(worker);
        }
    }
    return TRUE;
}
#else
int wmain(int argc, wchar_t** argv) {
    if (argc < 2 || !attach(argv[1])) return 1;
    HANDLE file = CreateFileW(argv[1], GENERIC_READ, FILE_SHARE_READ, nullptr, OPEN_EXISTING, 0, nullptr);
    if (file == INVALID_HANDLE_VALUE) return 2;
    for (uint64_t position : offsets) {
        BYTE buffer[sizeof(holdName)]{};
        if (!read_at(file, position, buffer, sizeof(buffer)) ||
            strcmp(reinterpret_cast<const char*>(buffer), "pc_2h_aim_cbeam_fireholx")) return 3;
        if (!read_at(file, position + 1, buffer, sizeof(buffer)) ||
            strcmp(reinterpret_cast<const char*>(buffer), holdName + 1)) return 4;
    }
    CloseHandle(file);
    if (patchedSlots != ((1u << suits.size()) - 1)) return 5;
    puts("PASS real ReadFile hook patched all eleven complete windows and preserved partial reads");
    return 0;
}
#endif
