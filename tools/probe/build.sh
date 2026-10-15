#!/bin/sh
# Builds bin/dinput8.dll (32-bit Windows) with Zig's C compiler.
#   pip install ziglang==0.13.0
set -e
cd "$(dirname "$0")"
mkdir -p bin
python3 -m ziglang cc -target x86-windows-gnu -shared -O2 -Wall -s \
    -o bin/dinput8.dll probe.c dinput8.def
rm -f bin/*.lib bin/*.pdb
