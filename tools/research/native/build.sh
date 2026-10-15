#!/bin/sh
# Builds the XAS encoder: libxasenc.so (Linux) and xasenc.dll (64-bit
# Windows, with Zig's C compiler: pip install ziglang==0.13.0).
set -e
cd "$(dirname "$0")"
gcc -O2 -shared -fPIC -o libxasenc.so xas_enc.c
python3 -m ziglang cc -target x86_64-windows-gnu -shared -O2 -s -o xasenc.dll xas_enc.c
rm -f xasenc.lib xasenc.pdb
