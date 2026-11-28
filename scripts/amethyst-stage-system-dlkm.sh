#!/usr/bin/env bash
# SPDX-License-Identifier: GPL-2.0-only
# Stage this build's signed GKI modules as a system_dlkm module directory.
#
# Stock system_dlkm modules are signed by the stock GKI kernel's build key.
# A kernel built here does not trust that key, so protected GKI modules such
# as rfkill, bluetooth and libarc4 refuse to load, and cfg80211, mac80211 and
# btpower fail after them. Ship the modules built with this kernel instead.
set -euo pipefail

if [[ $# -lt 2 || $# -gt 3 ]]; then
    printf 'Usage: %s <build out dir> <dest dir> [stock system_dlkm modules.load]\n' "$0" >&2
    exit 2
fi

kernel=$(realpath "$(dirname "${BASH_SOURCE[0]}")/..")
workspace=$(dirname "$kernel")
clang_bin=${CLANG_BIN:-"$workspace/prebuilts/clang/host/linux-x86/clang-r487747c/bin"}
out=$(realpath "$1")
dest=$2
stock_load=${3:-}

release=$(cat "$out/include/config/kernel.release")
grep -qx 'CONFIG_MODULE_SIG_ALL=y' "$out/.config" ||
    { printf '%s: CONFIG_MODULE_SIG_ALL is not set; rebuild with build-amethyst-standalone.sh\n' "$out" >&2; exit 1; }

export PATH="$clang_bin:$PATH"
stage=$(mktemp -d)
trap 'rm -rf "$stage"' EXIT

# modules_install signs every module with this build's key.
make -C "$kernel" O="$out" ARCH=arm64 LLVM=1 INSTALL_MOD_PATH="$stage/install" \
    INSTALL_MOD_STRIP=1 modules_install > /dev/null
src=$stage/install/lib/modules/$release

if [[ -z $stock_load ]]; then
    # Default to the GKI protected module list plus the unprotected GKI
    # modules shipped by stock system_dlkm.
    { sed 's|^|kernel/|' "$kernel/android/gki_aarch64_protected_modules"
      printf 'kernel/%s\n' kernel/kheaders.ko mm/zsmalloc.ko drivers/block/zram/zram.ko
    } > "$stage/wanted"
else
    cp "$stock_load" "$stage/wanted"
fi

dst=$stage/system_dlkm/lib/modules/$release
mkdir -p "$dst"
: > "$dst/modules.load"
missing=0
while read -r rel; do
    [[ -n $rel ]] || continue
    if [[ -f $src/$rel ]]; then
        install -D -m 0644 "$src/$rel" "$dst/$rel"
        printf '%s\n' "$rel" >> "$dst/modules.load"
    else
        printf 'warning: not built: %s\n' "$rel" >&2
        missing=$((missing + 1))
    fi
done < "$stage/wanted"
cp "$src"/modules.builtin* "$src"/modules.order "$dst"/ 2> /dev/null || true
depmod -b "$stage/system_dlkm" "$release"

mkdir -p "$dest"
rm -rf "${dest:?}/$release"
cp -a "$dst" "$dest/"
printf 'Staged %s modules (%s missing) in %s/%s\n' \
    "$(wc -l < "$dst/modules.load")" "$missing" "$dest" "$release"
printf 'Set GKI_VERSION := %s in the device tree.\n' "$release"
