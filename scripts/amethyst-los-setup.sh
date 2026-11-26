#!/usr/bin/env bash
# SPDX-License-Identifier: GPL-2.0-only
# Install this kernel and its module/DT sources into a LineageOS tree.
#
# The LineageOS tree must already contain the projects from
# .repo/local_manifests/10-amethyst-kernel-sources.xml. This script:
#   1. copies this kernel checkout to kernel/xiaomi/amethyst. It must be a
#      real directory: Kbuild resolves the relative M= paths that Lineage's
#      kernel.mk uses against the kernel's physical location;
#   2. installs clang r487747c (the compiler this 6.1.68 tree and Xiaomi's
#      modules were built with; newer clangs reject core files) under
#      prebuilts/clang/kernel/linux-x86;
#   3. links this tree's amethyst-only modules into the module root;
#   4. applies scripts/amethyst-patches/los/<project path>/*.patch.
# Re-run it after changing this checkout.
set -euo pipefail

if [[ $# != 1 ]]; then
    printf 'Usage: %s <LineageOS tree>\n' "$0" >&2
    exit 2
fi

kernel=$(realpath "$(dirname "${BASH_SOURCE[0]}")/..")
los=$(realpath "$1")
modroot=$los/kernel/xiaomi/sm7635-modules
[[ -d $modroot/qcom/opensource ]] ||
    { printf '%s: missing; sync 10-amethyst-kernel-sources.xml first\n' "$modroot" >&2; exit 1; }

# 1. Kernel.
mkdir -p "$los/kernel/xiaomi/amethyst"
rsync -a --delete --exclude=/.git --exclude=/out "$kernel/" "$los/kernel/xiaomi/amethyst/"
# Record the source commit, since the copy has no .git for setlocalversion.
printf -- '-g%s\n' "$(git -C "$kernel" describe --always --dirty 2> /dev/null || echo unknown)" \
    > "$los/kernel/xiaomi/amethyst/.scmversion"

# 2. Compiler.
clang_dir=$los/prebuilts/clang/kernel/linux-x86/clang-r487747c
clang_url=https://android.googlesource.com/platform/prebuilts/clang/host/linux-x86/+archive/refs/heads/android14-release/clang-r487747c.tar.gz
clang_sha=e6b88a46f5cbe0ef5d49b4a4fe07111dd42bc3194b327bae7f9565c29f67d1cf
if [[ ! -x $clang_dir/bin/clang ]]; then
    mkdir -p "$clang_dir"
    if [[ -n ${CLANG_SRC:-} ]]; then
        cp -a "$CLANG_SRC/." "$clang_dir/"
    else
        tmp=$(mktemp)
        curl -fL "$clang_url" -o "$tmp"
        echo "$clang_sha  $tmp" | sha256sum -c -
        tar -xzf "$tmp" -C "$clang_dir"
        rm -f "$tmp"
    fi
fi
"$clang_dir/bin/clang" --version | head -1

# 3. Amethyst-only modules kept in this tree.
mkdir -p "$modroot/xiaomi"
for module in "$kernel"/techpack/amethyst/*/; do
    name=$(basename "$module")
    ln -sfn "../../amethyst/techpack/amethyst/$name" "$modroot/xiaomi/$name"
done

# Module sources are built by kernel.mk, not Soong/Kati. Hide their
# Android.mk/Android.bp files (DLKM rules, header genrules, FP6's namespace
# import of kernel/fairphone/sm7635) from the Android build.
touch "$modroot/.find-ignore" "$los/kernel/xiaomi/amethyst-qcom-modules/.find-ignore"

# 4. Patches for synced projects. Skip a patch that is already applied.
patches=$kernel/scripts/amethyst-patches/los
if [[ -d $patches ]]; then
    while IFS= read -r -d '' patch; do
        rel=${patch#"$patches/"}
        project=$los/$(dirname "$rel")
        if git -C "$project" apply --check "$patch" 2> /dev/null; then
            git -C "$project" apply "$patch"
            printf 'applied %s\n' "$rel"
        elif git -C "$project" apply --check --reverse "$patch" 2> /dev/null; then
            printf 'already applied %s\n' "$rel"
        else
            printf 'FAILED %s\n' "$rel" >&2
            exit 1
        fi
    done < <(find "$patches" -name '*.patch' -print0 | sort -z)
fi
printf 'Kernel sources installed in %s\n' "$los"
