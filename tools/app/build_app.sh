#!/bin/sh
# Linux build of the same app, to check the packaging (the release is built
# on Windows with build_app.bat or the GitHub Actions workflow).
set -e
cd "$(dirname "$0")"
R=../research
${PYTHON:-python3} -m PyInstaller --noconfirm --clean --onedir --windowed --name DS2SeveredPC \
  --paths ../test --paths $R --hidden-import make_severed_test --collect-submodules ds2 \
  $(for f in $R/ds2/*.pkl $R/ds2/*.json $R/ds2/*.txt; do printf -- '--add-data %s:ds2 ' "$f"; done) \
  --add-binary $R/native/libxasenc.so:native \
  --add-data ../probe/bin/dinput8.dll:hook --add-data icon.ico:. --add-data icon.png:. \
  severed_installer.py
if [ -x ffmpeg/ffmpeg ] || [ -f ffmpeg/ffmpeg.exe ]; then cp -r ffmpeg dist/DS2SeveredPC/; fi
cp ../../LICENSE dist/DS2SeveredPC/LICENSE.txt
cp "Keep all files together in the same folder.txt" dist/DS2SeveredPC/
