"""Triangle strip index buffers: 360 -> PC.

The 360 restarts a strip with index 0xFFFF (primitive restart); Direct3D 9
on the PC has none, so the PC meshes join the strips with degenerate
triangles: the last index of a strip and the first of the next, plus that
first index once more when the next strip would otherwise start at the
wrong parity (which would flip its winding). A 360 strip that begins with a
repeated index (a parity fix of its own) is joined as the rest of the strip
started at the opposite parity. Reproduces all 9,150 restart strip tables
of the base-game PC/360 mesh pairs exactly.
"""


def join_map(indices):
    """360 strip indices (with 0xFFFF restarts) -> (PC strip indices,
    {360 position: PC position}); a restart or a dropped repeat maps to
    where the next strip's join starts"""
    out = []
    pos = {}
    cur = []
    for i, v in enumerate(list(indices) + [0xFFFF]):
        if v != 0xFFFF:
            cur.append((v, i))
            continue
        if cur:
            if out:
                parity = 0
                while len(cur) > 1 and cur[0][0] == cur[1][0]:
                    pos[cur[0][1]] = len(out)
                    cur, parity = cur[1:], parity ^ 1
                out += [out[-1], cur[0][0]]
                if len(out) % 2 != parity:
                    out.append(cur[0][0])
            for v2, i2 in cur:
                pos[i2] = len(out)
                out.append(v2)
        if i < len(indices):
            pos[i] = len(out)
        cur = []
    return out, pos


def join(indices):
    return join_map(indices)[0]
