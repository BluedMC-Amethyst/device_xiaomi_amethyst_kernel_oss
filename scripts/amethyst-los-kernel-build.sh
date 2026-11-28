#!/usr/bin/env bash
# SPDX-License-Identifier: GPL-2.0-only
# Build the amethyst kernel and external modules the way LineageOS's
# vendor/lineage/build/tasks/kernel.mk does, without a full ROM build.
#
# Usage: amethyst-los-kernel-build.sh <LineageOS tree> [stage...]
#   stages: config kernel modules ext (all external modules)
#           ext=<module> (only that one) ext@<module> (from that one on)
#           (default: config kernel modules ext)
# Output: $OUT (default <LineageOS>/out-amethyst-kernel)/KERNEL_OBJ, with
# external module objects in $OUT/sm7635-modules, as in a ROM build.
# Sync the BluedMC-Amethyst local manifest first.
set -euo pipefail

if [[ $# -lt 1 ]]; then
    sed -n '3,10p' "$0" >&2
    exit 2
fi
los=$(realpath "$1")
shift
stages=("$@")
((${#stages[@]})) || stages=(config kernel modules ext)

kernel_src=kernel/xiaomi/sm7635
ext_root=kernel/xiaomi/sm7635-modules
list=$los/$kernel_src/scripts/amethyst-ext-modules.txt
out=${OUT:-$los/out-amethyst-kernel}
kout=$out/KERNEL_OBJ
clang=$los/prebuilts/clang/kernel/linux-x86/clang-r487747c
tools=$los/prebuilts/kernel-build-tools/linux-x86
bt=$los/prebuilts/build-tools/linux-x86
sysroot=$los/prebuilts/gcc/linux-x86/host/x86_64-linux-glibc2.17-4.8/sysroot
mkdir -p "$kout"

export PATH=$los/prebuilts/tools-lineage/linux-x86/bin:$bt/bin:$clang/bin:$PATH
export HIP_PATH=none PERL5LIB=$los/prebuilts/tools-lineage/common/perl-base
export BISON_PKGDATADIR=$los/prebuilts/build-tools/common/bison
flags=(
    -j"$(nproc)" LLVM=1 LLVM_IAS=1 ARCH=arm64 CLANG_TRIPLE=aarch64-linux-gnu-
    HOSTCFLAGS="--sysroot=$sysroot -I$tools/include"
    HOSTLDFLAGS="--sysroot=$sysroot -Wl,-rpath,$tools/lib64 -L $tools/lib64 -fuse-ld=lld --rtlib=compiler-rt"
    LZ4="$tools/bin/lz4" LEX="$bt/bin/flex" YACC="$bt/bin/bison" M4="$bt/bin/m4"
    PAHOLE="$tools/bin/pahole" DTC_FLAGS=-@
)
kmake() { "$bt/bin/make" "${flags[@]}" -C "$los/$kernel_src" O="$kout" "$@"; }

configs=(gki_defconfig vendor/pineapple_GKI.config vendor/amethyst_GKI.config
         vendor/amethyst_standalone.config)
[[ ${FIRSTBOOT:-0} == 1 ]] && configs+=(vendor/amethyst_firstboot.config)

cd "$los"
for stage in "${stages[@]}"; do
    case $stage in
    config)
        # Same steps as kernel.mk's make-kernel-config.
        cp "$kernel_src/arch/arm64/configs/${configs[0]}" "$kout/.config"
        kmake olddefconfig
        for c in "${configs[@]:1}"; do
            (cd "$kout" && "$los/$kernel_src/scripts/kconfig/merge_config.sh" -m -O "$kout" \
                "$kout/.config" "$los/$kernel_src/arch/arm64/configs/$c")
            kmake olddefconfig
        done
        ;;
    kernel) kmake Image ;;
    modules) kmake modules ;;
    ext | ext=* | ext@*)
        rpath=$(python3 -c 'import os,sys;print(os.path.relpath(*sys.argv[1:]))' "$ext_root" "$kernel_src")
        mapfile -t mods < <(grep -Ev '^\s*(#|$)' "$list")
        if [[ $stage == ext=* ]]; then
            mods=("${stage#ext=}")
        elif [[ $stage == ext@* ]]; then
            for i in "${!mods[@]}"; do [[ ${mods[$i]} == "${stage#ext@}" ]] && break; done
            mods=("${mods[@]:$i}")
        fi
        for m in "${mods[@]}"; do
            printf '==> %s\n' "$m"
            # Same invocation as kernel.mk's make-external-module-target.
            "$bt/bin/make" "${flags[@]}" -C "$ext_root/$m" M="$rpath/$m" \
                KERNEL_SRC="$los/$kernel_src" OUT_DIR="$kout" O="$kout"
        done
        ;;
    *) printf 'Unknown stage %s\n' "$stage" >&2; exit 2 ;;
    esac
done
