#!/usr/bin/env bash
# SPDX-License-Identifier: GPL-2.0-only
# Remove optional Xiaomi blobs from a stock modules.load for an initial boot.
set -euo pipefail

if [[ $# != 2 ]]; then
	printf 'Usage: %s <modules.load input> <modules.load output>\n' "$0" >&2
	exit 2
fi

input=$1
output=$2
moddir=$(dirname "$input")
base=$(basename "$moddir")/$(basename "$input")

# ponytail: This is a conservative first-boot profile, not a permanent module
# policy. Revisit each entry once the module is known to work.
#
# Do not list modules that a kept module depends on (for example metis, mist
# and mi_power, which sched-walt and qcom-spmi-pmic import from): modprobe
# loads dependencies from modules.dep regardless of modules.load, so such an
# entry has no effect. The check at the end of this script enforces that.
#
# ufs_ffu: isolate the stock UFS firmware updater's delayed emergency-restart
# paths during bring-up. ufs_qcom is the storage driver and must remain.
case "$base" in
vendor_boot/modules.load)
	exclude='^(mi_memory|ufs_ffu)\.ko$'
	;;
vendor_boot/modules.load.recovery)
	exclude='^(mi_memory|ufs_ffu|mi_mempool|binder_gki|millet_pkg|millet_hs|millet_binder|millet_sig|migt)\.ko$'
	;;
vendor_dlkm/modules.load)
	exclude='^(mi_mempool|binder_gki|millet_pkg|millet_hs|millet_binder|millet_sig|migt|aw882xx_dlkm|cs35l41_dlkm|cs35l43_dlkm|fs19xx_dlkm|sia91xx_dlkm|focaltech_touch)\.ko$'
	;;
*)
	printf 'Unsupported manifest path: %s\n' "$input" >&2
	exit 2
	;;
esac

mkdir -p "$(dirname "$output")"
grep -Ev -e "$exclude" "$input" > "$output"

# Core modules must not be accidentally removed by a first-boot filter.
for required in ufs_qcom.ko sched-walt.ko qcom-spmi-pmic.ko; do
	if grep -qxF "$required" "$input" && ! grep -qxF "$required" "$output"; then
		printf 'Refusing to remove required module: %s\n' "$required" >&2
		exit 1
	fi
done

# An excluded module that a kept module (transitively) depends on would be
# loaded anyway. Look up dependencies in this and the sibling stock module
# directories, since vendor_dlkm modules depend on vendor_boot ones.
find_ko() {
	local dir
	for dir in "$moddir" "$moddir/../vendor_boot" "$moddir/../vendor_dlkm"; do
		if [[ -f $dir/$1.ko ]]; then
			printf '%s\n' "$dir/$1.ko"
			return
		fi
	done
}

if command -v modinfo > /dev/null; then
	declare -A seen=()
	queue=()
	while read -r ko; do
		queue+=("${ko%.ko}")
	done < "$output"
	while ((${#queue[@]})); do
		name=${queue[0]}
		queue=("${queue[@]:1}")
		[[ -n ${seen[$name]:-} ]] && continue
		seen[$name]=1
		path=$(find_ko "$name")
		[[ -n $path ]] || continue
		IFS=, read -ra deps <<< "$(modinfo -F depends "$path")"
		for dep in "${deps[@]}"; do
			[[ -n $dep ]] || continue
			if grep -qE "$exclude" <<< "$dep.ko"; then
				printf 'Excluded module %s.ko is a dependency of %s.ko\n' \
					"$dep" "$name" >&2
				exit 1
			fi
			queue+=("$dep")
		done
	done
else
	printf 'warning: modinfo not found, dependency check skipped\n' >&2
fi
