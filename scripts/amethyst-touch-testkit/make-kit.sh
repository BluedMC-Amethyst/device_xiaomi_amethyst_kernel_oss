#!/usr/bin/env bash
# SPDX-License-Identifier: GPL-2.0-only
# Assemble the touch A/B kit for a tester. The kit holds stock Xiaomi
# binaries, so build it outside the git tree and do not commit it.
#
# Usage: make-kit.sh <kit dir> <source module dir> <stock module dir>
#   source module dir: goodix_core.ko + xiaomi_touch.ko built from this tree
#   stock module dir:  stock goodix_core.ko + xiaomi_touch.ko (OS3.0.306.0)
set -euo pipefail
if [[ $# -ne 3 ]]; then
    sed -n '3,9p' "$0" >&2
    exit 2
fi
here=$(cd "$(dirname "$0")" && pwd)
kit=$1 src=$2 stock=$3
mkdir -p "$kit/modules/source" "$kit/modules/stock"
cp "$here/run-touch-ab.sh" "$here/dev.sh" "$here/README.txt" "$kit/"
chmod +x "$kit/run-touch-ab.sh"
for m in goodix_core xiaomi_touch; do
    cp "$src/$m.ko" "$kit/modules/source/"
    cp "$stock/$m.ko" "$kit/modules/stock/"
done
(cd "$kit" && find . -type f ! -name SHA256SUMS ! -path './logs/*' | sort | xargs sha256sum > SHA256SUMS)
cat "$kit/SHA256SUMS"
