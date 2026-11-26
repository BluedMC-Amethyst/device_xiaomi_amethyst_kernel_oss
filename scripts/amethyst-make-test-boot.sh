#!/usr/bin/env bash
# SPDX-License-Identifier: GPL-2.0-only
# Build a RAM-boot test image: a working boot.img with only the kernel replaced.
#
# Amethyst's boot.img (header v4) holds just the kernel; the ramdisk lives in
# init_boot and the device cmdline/bootconfig in vendor_boot. Swapping only
# the kernel keeps every other partition stock, so a failed test is undone by
# a reboot. Test with `fastboot boot`; do not flash until it reaches the UI.
set -euo pipefail

if [[ $# != 3 ]]; then
    printf 'Usage: %s <working boot.img> <Image> <output boot.img>\n' "$0" >&2
    printf 'Env: AOSP_HOST_BIN (dir with unpack_bootimg/mkbootimg), CMDLINE\n' >&2
    exit 2
fi

stock=$1
image=$2
output=$3
bin=${AOSP_HOST_BIN:-"$HOME/AndroidBuilds/EvolutionX/out/host/linux-x86/bin"}
# Extra kernel cmdline, appended to vendor_boot's. Verbose logs survive a
# warm reset in pstore (/sys/fs/pstore/console-ramoops-0); permissive
# SELinux (userdebug only) keeps a policy denial from looking like a kernel
# hang. Set CMDLINE= to add nothing.
cmdline=${CMDLINE-"loglevel=8 printk.devkmsg=on androidboot.selinux=permissive"}

for tool in unpack_bootimg mkbootimg; do
    [[ -x $bin/$tool ]] || { printf 'Missing %s/%s (set AOSP_HOST_BIN)\n' "$bin" "$tool" >&2; exit 1; }
done
# An arm64 Image carries "ARM\x64" at offset 0x38.
[[ $(od -An -tx1 -j56 -N4 "$image" | tr -d ' \n') == 41524d64 ]] ||
    { printf '%s is not an uncompressed arm64 Image\n' "$image" >&2; exit 1; }
strings "$image" | grep -m1 '^Linux version' >&2 || true

work=$(mktemp -d)
trap 'rm -rf "$work"' EXIT
"$bin/unpack_bootimg" --boot_img "$stock" --out "$work/unpacked" --format=mkbootimg -0 \
    > "$work/args"
[[ -s $work/unpacked/kernel ]] || { printf '%s has no kernel\n' "$stock" >&2; exit 1; }
cp "$image" "$work/unpacked/kernel"

# Rebuild with the same header arguments; append to the existing cmdline.
mapfile -d '' args < "$work/args"
for i in "${!args[@]}"; do
    if [[ ${args[$i]} == --cmdline ]]; then
        args[i + 1]="${args[$i + 1]:+${args[$i + 1]} }$cmdline"
        cmdline=
    fi
done
[[ -z $cmdline ]] || args+=(--cmdline "$cmdline")
"$bin/mkbootimg" "${args[@]}" --output "$output"

printf 'Wrote %s\n' "$output"
printf 'Test (RAM only): fastboot boot %s\n' "$output"
