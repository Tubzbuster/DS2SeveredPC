"""Finds the Dead Space 2 folder: Steam (every library in
libraryfolders.vdf, app 47780), then the EA / Origin registry keys, then the
usual install folders. Each candidate must hold deadspace2.exe.

    folders = gamefind.find()          # best first; [] when none is found
"""
import os
import re
import sys

EXE = 'deadspace2.exe'
STEAM_APP = '47780'
COMMON = ('Dead Space 2',)

FALLBACK = (r'C:\Program Files (x86)\Steam\steamapps\common\Dead Space 2',
            r'C:\Program Files\Steam\steamapps\common\Dead Space 2',
            r'C:\Program Files (x86)\Origin Games\Dead Space 2',
            r'C:\Program Files\EA Games\Dead Space 2',
            r'C:\Program Files (x86)\EA Games\Dead Space 2',
            r'C:\Program Files (x86)\Electronic Arts\Dead Space 2')

# (hive, key, value) holding an install folder, 32- and 64-bit views
REG = (('HKLM', r'SOFTWARE\WOW6432Node\EA Games\Dead Space 2', 'Install Dir'),
       ('HKLM', r'SOFTWARE\EA Games\Dead Space 2', 'Install Dir'),
       ('HKLM', r'SOFTWARE\WOW6432Node\Electronic Arts\Dead Space 2', 'Install Dir'),
       ('HKLM', r'SOFTWARE\Electronic Arts\Dead Space 2', 'Install Dir'),
       ('HKLM', r'SOFTWARE\WOW6432Node\Microsoft\Windows\CurrentVersion\Uninstall\Steam App 47780', 'InstallLocation'))


def _reg(hive, key, value):
    if sys.platform != 'win32':
        return None
    import winreg
    h = {'HKLM': winreg.HKEY_LOCAL_MACHINE, 'HKCU': winreg.HKEY_CURRENT_USER}[hive]
    try:
        with winreg.OpenKey(h, key) as k:
            return str(winreg.QueryValueEx(k, value)[0])
    except OSError:
        return None


def steam_roots():
    """Steam's own folder (registry, then the default)"""
    out = []
    for hive, key, value in (('HKCU', r'Software\Valve\Steam', 'SteamPath'),
                             ('HKLM', r'SOFTWARE\WOW6432Node\Valve\Steam', 'InstallPath'),
                             ('HKLM', r'SOFTWARE\Valve\Steam', 'InstallPath')):
        p = _reg(hive, key, value)
        if p:
            out.append(os.path.normpath(p))
    out.append(r'C:\Program Files (x86)\Steam')
    return out


def steam_libraries(vdf_text):
    """library folders listed in a libraryfolders.vdf, those holding app
    47780 first (old and new file layouts both use "path" or numbered keys)"""
    libs, holding = [], []
    blocks = re.split(r'\n\s*"\d+"\s*\n', '\n' + vdf_text)
    for b in blocks:
        m = re.search(r'"path"\s*"([^"]+)"', b)
        paths = [m.group(1)] if m else re.findall(r'^\s*"\d+"\s*"([^"]+)"', b, re.M)
        for p in paths:
            p = p.replace('\\\\', '\\')
            libs.append(p)
            if re.search(r'"%s"' % STEAM_APP, b):
                holding.append(p)
    return holding + [p for p in libs if p not in holding]


def find():
    cands = []
    for root in steam_roots():
        libs = [root]
        vdf = os.path.join(root, 'steamapps', 'libraryfolders.vdf')
        if os.path.exists(vdf):
            try:
                libs = steam_libraries(open(vdf, encoding='utf-8', errors='replace').read()) + libs
            except OSError:
                pass
        for lib in libs:
            for name in COMMON:
                cands.append(os.path.join(lib, 'steamapps', 'common', name))
    for r in REG:
        p = _reg(*r)
        if p:
            cands.append(p)
    cands += FALLBACK
    out = []
    for p in cands:
        p = os.path.normpath(p)
        if p not in out and os.path.isfile(os.path.join(p, EXE)):
            out.append(p)
    return out
