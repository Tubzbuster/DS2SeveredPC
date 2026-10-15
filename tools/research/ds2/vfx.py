"""VFX: a header, then components each introduced by a fourcc marker such
as '.fnc' '.bem' '.snd' (stored as a 32-bit value, so '.fnc' on 360 and
'cnf.' on PC), a u32 version and a u32 field, then fixed fields."""
import re, struct

MARK = re.compile(rb'\.[a-z]{3}')


SEP = b'####'


def segments(x):
    """Split a 360 VFX into (key, start, end) segments: the header (before
    the first component), each component (from its marker to the next
    marker), and each '####' separator word that directly precedes a
    marker."""
    marks = [m.start() for m in MARK.finditer(x) if m.start() % 4 == 0 and m.start() >= 16]
    cuts = []
    for m in marks:
        if m >= 4 and x[m - 4:m] == SEP:
            cuts.append((m - 4, 'sep'))
        cuts.append((m, 'comp'))
    out = []
    bounds = [c for c, _ in cuts] + [len(x)]
    if not cuts:
        return [(('header', len(x)), 0, len(x))]
    out.append((('header', bounds[0]), 0, bounds[0]))
    for (c, kind), e in zip(cuts, bounds[1:]):
        if kind == 'sep':
            out.append((('sep', 4), c, c + 4))
        else:
            key = (x[c:c + 4].decode('latin1'), struct.unpack_from('>I', x, c + 4)[0], e - c)
            if key[0] in LAYOUT_WORD and e - c >= LAYOUT_WORD[key[0]] + 4:
                key += (struct.unpack_from('>I', x, c + LAYOUT_WORD[key[0]])[0],)
            out.append((key, c, e))
    return out


# components whose internal layout depends on a word at this offset
LAYOUT_WORD = {'.prt': 0x14}
