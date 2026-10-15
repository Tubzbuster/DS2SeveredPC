"""Learned byte-permutation templates for record-based formats.

Each 4-byte word of a 360 record maps to the PC word by one of a few byte
permutations (identity for raw bytes/strings/IDs, reversal for 32-bit
values, pairwise swap for 16-bit pairs, mixed for byte+u16 fields). For
each word position of a record class, a template counts how many training
pairs each permutation fits, and picks the best. Positions where raw and
32-bit-swapped both occur in quantity are union fields (a name, an ID, or
numbers depending on the record), decided per record at conversion.
"""
import itertools

PERMS = list(itertools.permutations(range(4)))
PREF = [(0, 1, 2, 3), (3, 2, 1, 0), (1, 0, 3, 2), (0, 1, 3, 2), (1, 0, 2, 3), (2, 3, 0, 1)]
PERMS.sort(key=lambda p: PREF.index(p) if p in PREF else 99)
RAW, SWAP = 0, 1
UNION = 'union'
Q64, Q64B = 'q64', 'q64b'      # first / second word of an 8-byte value


def fitting(w, q):
    m = 0
    for i, p in enumerate(PERMS):
        if w[p[0]] == q[0] and w[p[1]] == q[1] and w[p[2]] == q[2] and w[p[3]] == q[3]:
            m |= 1 << i
    return m


class Template:
    def __init__(self, nwords):
        self.n = nwords
        self.counts = [[0] * len(PERMS) for _ in range(nwords)]
        self.informative = [0] * nwords   # samples where the word did not fit everything
        self.samples = 0
        self.q8 = [0] * nwords            # words i, i+1 fit only as one 8-byte value
        self.not32 = [0] * nwords         # word i or i+1 fits no single 32-bit swap

    def train(self, x, q):
        self.samples += 1
        n = min(self.n, len(x) // 4, len(q) // 4)
        for i in range(n - 1):
            a, b = x[4 * i:4 * i + 8], q[4 * i:4 * i + 8]
            if a[::-1] == b and a[0:4][::-1] + a[4:8][::-1] != b:
                self.not32[i] += 1
                self.q8[i] += 1
            elif a[0:4][::-1] + a[4:8][::-1] != b and a != b:
                self.not32[i] += 1
        for i in range(n):
            m = fitting(x[4 * i:4 * i + 4], q[4 * i:4 * i + 4])
            if m == (1 << len(PERMS)) - 1:
                continue   # e.g. all-zero word: says nothing
            self.informative[i] += 1
            c = self.counts[i]
            for j in range(len(PERMS)):
                if m >> j & 1:
                    c[j] += 1

    def perms(self, union_share=0.02, swap_default_words=0, q64=False):
        """swap_default_words: positions below this that no sample decided
        default to a 32-bit swap instead of raw"""
        out = []
        for i in range(self.n):
            c, inf = self.counts[i], self.informative[i]
            if inf == 0:
                out.append(PERMS[SWAP] if i < swap_default_words else PERMS[RAW])
                continue
            best = max(range(len(PERMS)), key=lambda j: (c[j], -j))
            raw_only = c[RAW] - min(c[RAW], c[SWAP])
            if c[best] < inf * (1 - union_share) and c[RAW] >= inf * union_share and c[SWAP] >= inf * union_share:
                out.append(UNION)
            else:
                out.append(PERMS[best])
        # 8-byte values: where the only consistent reading is one u64
        i = 0
        while q64 and i < self.n - 1:
            if self.q8[i] >= 2 and self.q8[i] >= 0.9 * self.not32[i]:
                out[i], out[i + 1] = Q64, Q64B
                i += 2
            else:
                i += 1
        return out


def _texty(field):
    """NUL-terminated printable text of at least 3 characters at the start."""
    n = 0
    for c in field:
        if c == 0:
            break
        if not 32 <= c < 127:
            return False
        n += 1
    return n >= 3


def apply(perms, x):
    out = bytearray(x)
    i, n = 0, len(perms)
    while i < n:
        p = perms[i]
        if p == Q64:
            out[4 * i:4 * i + 8] = x[4 * i:4 * i + 8][::-1]
            i += 2
            continue
        if p == Q64B:
            i += 1
            continue
        if p != UNION:
            w = x[4 * i:4 * i + 4]
            if len(w) == 4:
                out[4 * i:4 * i + 4] = bytes((w[p[0]], w[p[1]], w[p[2]], w[p[3]]))
            i += 1
            continue
        j = i
        while j < n and perms[j] == UNION:
            j += 1
        field = x[4 * i:4 * j]
        words = [field[k:k + 4] for k in range(0, len(field), 4)]
        nz = [w for w in words if w != b'\0\0\0\0']
        # hashes repeat (e.g. the same hash in 3 slots); IDs are 16 random bytes; names are text
        numbers = not _texty(field) and len(nz) > len(set(nz))
        if numbers:
            for k in range(i, j):
                out[4 * k:4 * k + 4] = x[4 * k:4 * k + 4][::-1]
        i = j
    return bytes(out)
