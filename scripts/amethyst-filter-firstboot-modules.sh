#!/usr/bin/env bash
# SPDX-License-Identifier: GPL-2.0-only
# Remove known ABI-incompatible optional Xiaomi blobs for an initial boot.
set -euo pipefail

if [[ $# != 2 ]]; then
	printf 'Usage: %s <modules.load input> <modules.load output>\n' "$0" >&2
	exit 2
fi

input=$1
output=$2
base=$(basename "$(dirname "$input")")/$(basename "$input")

# ponytail: This is a conservative first-boot profile, not a permanent module
# policy. Revisit each entry after its source or ABI-compatible exporter exists.
case "$base" in
vendor_boot/modules.load)
	exclude='^(mi_power|mi_memory|io_monitor|metis|mist)\.ko$'
	;;
vendor_boot/modules.load.recovery)
	exclude='^(mi_power|mi_memory|io_monitor|metis|mist|lb|mi_mempool|binder_gki|millet_pkg|millet_hs|millet_binder|millet_sig|migt)\.ko$'
	;;
vendor_dlkm/modules.load)
	exclude='^(lb|mi_mempool|binder_gki|millet_pkg|millet_hs|millet_binder|millet_sig|migt|aw882xx_dlkm|cs35l41_dlkm|cs35l43_dlkm|fs19xx_dlkm|sia91xx_dlkm|focaltech_touch)\.ko$'
	;;
*)
	printf 'Unsupported manifest path: %s\n' "$input" >&2
	exit 2
	;;
esac

mkdir -p "$(dirname "$output")"
# ponytail: isolate the stock UFS firmware updater's delayed emergency-restart
# paths during bring-up; restore after its compatibility is established.
# ufs_qcom is the storage driver and must remain enabled.
grep -Ev -e "$exclude" -e '^ufs_ffu\.ko$' "$input" > "$output"

# Core modules must not be accidentally removed by a first-boot filter.
for required in ufs_qcom.ko sched-walt.ko qcom-spmi-pmic.ko; do
	if grep -qxF "$required" "$input" && ! grep -qxF "$required" "$output"; then
		printf 'Refusing to remove required module: %s\n' "$required" >&2
		exit 1
	fi
done
