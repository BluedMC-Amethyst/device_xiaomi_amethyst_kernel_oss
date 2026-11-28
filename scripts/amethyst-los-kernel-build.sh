#!/usr/bin/env bash
# SPDX-License-Identifier: GPL-2.0-only
# Build the amethyst kernel and external modules the way LineageOS's
# vendor/lineage/build/tasks/kernel.mk does, without a full ROM build.
#
# Usage: amethyst-los-kernel-build.sh <LineageOS tree> [stage...]
#   stages: config kernel modules ext (all external modules)
#           ext=<module> (only that one) ext@<module> (from that one on)
#           install (modules_install of the kernel and every external
#             module into $OUT/staging, stripped and signed like kernel.mk)
#           preflight (split $OUT/staging by the device's module lists into
#             $OUT/preflight and run scripts/amethyst-preflight-modules.py)
#           (default: config kernel modules ext)
# Output: $OUT (default <LineageOS>/out-amethyst-kernel)/KERNEL_OBJ, with
# external module objects in $OUT/sm7635-modules, as in a ROM build.
# Environment:
#   AMETHYST_KERNEL_CLANG  clang directory (default: the kernel's declared
#                          r487747c under prebuilts/clang/kernel/linux-x86)
#   AMETHYST_DEVICE_DIR    device tree whose modules/modules.list.* the
#                          preflight stage uses (default:
#                          <LineageOS>/device/xiaomi/amethyst)
# Run scripts/amethyst-los-setup.sh first.
set -euo pipefail

if [[ $# -lt 1 ]]; then
    sed -n '3,22p' "$0" >&2
    exit 2
fi
los=$(realpath "$1")
shift
stages=("$@")
((${#stages[@]})) || stages=(config kernel modules ext)

kernel_src=kernel/xiaomi/amethyst
ext_root=kernel/xiaomi/sm7635-modules
list=$los/$kernel_src/scripts/amethyst-ext-modules.txt
out=${OUT:-$los/out-amethyst-kernel}
kout=$out/KERNEL_OBJ
clang=${AMETHYST_KERNEL_CLANG:-$los/prebuilts/clang/kernel/linux-x86/clang-r487747c}
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

# External module projects selected by a stage (see usage), in list order.
ext_list() {
    local stage=$1 i
    mapfile -t mods < <(grep -Ev '^\s*(#|$)' "$list")
    if [[ $stage == ext=* ]]; then
        mods=("${stage#ext=}")
    elif [[ $stage == ext@* ]]; then
        for i in "${!mods[@]}"; do [[ ${mods[$i]} == "${stage#ext@}" ]] && break; done
        mods=("${mods[@]:$i}")
    fi
}

# Same invocation as kernel.mk's make-external-module-target.
emake() {
    local m=$1 rpath
    shift
    rpath=$(python3 -c 'import os,sys;print(os.path.relpath(*sys.argv[1:]))' "$ext_root" "$kernel_src")
    "$bt/bin/make" "${flags[@]}" -C "$ext_root/$m" M="$rpath/$m" \
        KERNEL_SRC="$los/$kernel_src" OUT_DIR="$kout" O="$kout" "$@"
}

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
        ext_list "$stage"
        for m in "${mods[@]}"; do
            printf '==> %s\n' "$m"
            emake "$m"
        done
        ;;
    install)
        # kernel.mk: modules_install with INSTALL_MOD_STRIP=1 for the kernel,
        # then for each external module. With MODULE_SIG_ALL this signs them.
        rm -rf "$out/staging"
        kmake INSTALL_MOD_PATH="$out/staging" INSTALL_MOD_STRIP=1 modules_install > /dev/null
        ext_list ext
        for m in "${mods[@]}"; do
            emake "$m" INSTALL_MOD_PATH="$out/staging" INSTALL_MOD_STRIP=1 \
                KERNEL_UAPI_HEADERS_DIR="$kout" modules_install > /dev/null
        done
        release=$(< "$kout/include/config/kernel.release")
        dups=$(find "$out/staging/lib/modules/$release" -name '*.ko' -printf '%f\n' | sort | uniq -d)
        if [[ -n $dups ]]; then
            printf 'Duplicate module %s\n' $dups >&2
            exit 1
        fi
        ;;
    preflight)
        release=$(< "$kout/include/config/kernel.release")
        python3 "$los/$kernel_src/scripts/amethyst-preflight-stage.py" \
            "$out/staging/lib/modules/$release" \
            "${AMETHYST_DEVICE_DIR:-$los/device/xiaomi/amethyst}/modules" "$out/preflight"
        python3 "$los/$kernel_src/scripts/amethyst-preflight-modules.py" "$out/preflight" "$kout" \
            --vendor-boot-load "$out/preflight/vendor_boot/modules.load" \
            --vendor-dlkm-load "$out/preflight/vendor_dlkm/modules.load"
        ;;
    *) printf 'Unknown stage %s\n' "$stage" >&2; exit 2 ;;
    esac
done
