#!/bin/sh
# Builds bin/dinput8.dll and bin/SeveredPC.asi (the same hook as an ASI
# plugin, e.g. for Marker Patch) for 32-bit Windows with Zig's C compiler.
#   pip install ziglang==0.13.0
set -e
cd "$(dirname "$0")"
mkdir -p bin
python3 -m ziglang cc -target x86-windows-gnu -shared -O2 -Wall -s \
    -o bin/dinput8.dll probe.c dinput8.def
python3 -m ziglang cc -target x86-windows-gnu -shared -O2 -Wall -s -DSEVERED_ASI \
    -o bin/SeveredPC.asi probe.c
rm -f bin/*.lib bin/*.pdb
