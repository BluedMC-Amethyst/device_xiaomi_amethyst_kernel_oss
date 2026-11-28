#!/usr/bin/env bash
# SPDX-License-Identifier: GPL-2.0-only
# Amethyst touch A/B test: runs on the PC, drives the phone over adb.
#
# Phases (each collects dmesg, logcat, getevent, input/sysfs/proc state and
# IRQ counts, and asks you to touch the screen):
#   1 rom      the touch modules the ROM booted with (expected: no touch)
#   2 source   rebuilt source goodix_core + xiaomi_touch from this kit
#   3 mixed-a  stock goodix_core + source xiaomi_touch (expected: refused)
#   4 mixed-b  source goodix_core + stock xiaomi_touch (expected: refused)
#   5 stock    stock goodix_core + stock xiaomi_touch (reference)
# Phase 5 is last on purpose: stock goodix_core does not unregister from
# xiaomi_touch on unload, so it is never unloaded. Reboot afterwards.
#
# Usage: ./run-touch-ab.sh [-s SERIAL] [--secs N] [--only rom,source,...]
set -uo pipefail

kit=$(cd "$(dirname "$0")" && pwd)
secs=15
only=rom,source,mixed-a,mixed-b,stock
adb=(adb)
while (($#)); do
    case $1 in
    -s) adb+=(-s "$2"); shift 2 ;;
    --secs) secs=$2; shift 2 ;;
    --only) only=$2; shift 2 ;;
    *) sed -n '3,16p' "$0"; exit 2 ;;
    esac
done
want() { [[ ",$only," == *",$1,"* ]]; }

out=$kit/logs/$(date +%Y%m%d-%H%M%S)
mkdir -p "$out"
exec > >(tee -a "$out/run.log") 2>&1

D=/data/local/tmp/touchkit
sh_() { "${adb[@]}" shell "sh $D/dev.sh $*"; }
pull() { "${adb[@]}" pull "$D/out/$1" "$out/" >/dev/null 2>&1 || echo "(pull $1 failed)"; }

touch_round() {
    local tag=$1 what=$2
    echo
    echo ">>> $what"
    read -r -p ">>> Press Enter, then touch and swipe the screen for $secs seconds..." _
    sh_ touch "$D/out/$tag" "$secs"
}

screen_cycle() {
    local tag=$1
    echo ">>> Turning the screen off for 5 s, then on again."
    "${adb[@]}" shell input keyevent KEYCODE_POWER; sleep 5
    "${adb[@]}" shell input keyevent KEYCODE_WAKEUP; sleep 3
    touch_round "$tag-after-screen-cycle" "Screen is back on (lock screen is fine)."
}

phase() {
    local name=$1
    sh_ mark "phase $name collect"
    sh_ collect "$D/out/$name"
    touch_round "$name" "Phase $name: touch test"
    screen_cycle "$name"
    sh_ collect "$D/out/$name-end"
    pull "$name"; pull "$name-after-screen-cycle"; pull "$name-end"
    read -r -p ">>> Did touch work in phase $name (y/n/partly)? " ans
    echo "phase $name tester verdict: $ans" | tee -a "$out/verdicts.txt"
}

echo "== adb root"
"${adb[@]}" root >/dev/null; sleep 2; "${adb[@]}" wait-for-device
"${adb[@]}" shell id | grep -q 'uid=0' || { echo "adb root failed; a debuggable build is required"; exit 1; }
"${adb[@]}" shell "rm -rf $D; mkdir -p $D/out $D/modules"
"${adb[@]}" push "$kit/dev.sh" "$D/" >/dev/null
"${adb[@]}" push "$kit/modules/." "$D/modules/" >/dev/null
sh_ info | tee "$out/info.txt"

if grep -q 'focaltech_ts' "$out/info.txt" || ! grep -q 'goodix_ts' "$out/info.txt"; then
    echo "This phone does not show goodix_ts (FocalTech panel or Goodix not probed)."
    read -r -p "Continue anyway (y/N)? " a; [[ $a == y ]] || exit 1
fi

if want rom; then
    echo "== phase rom (booted modules)"
    phase rom
fi

if want source; then
    echo "== phase source"
    sh_ mark "phase source unload rom pair"
    sh_ unload || { echo "Could not unload the ROM pair safely; stopping (reboot and retry)."; exit 1; }
    sh_ insmod "$D/modules/source/xiaomi_touch.ko" && sh_ insmod "$D/modules/source/goodix_core.ko" && sh_ waitprobe
    sh_ start
    sleep 5
    phase source
    sh_ mark "phase source unload"
    sh_ unload || { echo "Could not unload the source pair safely; stopping (reboot and retry)."; exit 1; }
fi

if want mixed-a; then
    echo "== phase mixed-a (stock goodix_core + source xiaomi_touch)"
    sh_ mark "phase mixed-a"
    sh_ unload || { echo "Could not unload the loaded pair safely; stopping (reboot and retry)."; exit 1; }
    if sh_ insmod "$D/modules/source/xiaomi_touch.ko"; then
        if sh_ insmod "$D/modules/stock/goodix_core.ko"; then
            echo "UNEXPECTED: stock goodix_core loaded on source xiaomi_touch. Not unloading it."
            echo "Collecting state, then stop: reboot before running again."
            sh_ collect "$D/out/mixed-a"; pull mixed-a
            exit 1
        fi
        sh_ collect "$D/out/mixed-a"; pull mixed-a
        sh_ rmmod xiaomi_touch
    fi
fi

if want mixed-b || want stock; then
    sh_ unload || { echo "Could not unload the loaded pair safely; stopping (reboot and retry)."; exit 1; }
    sh_ insmod "$D/modules/stock/xiaomi_touch.ko" || { echo "stock xiaomi_touch refused; cannot run stock phases"; exit 1; }
fi

if want mixed-b; then
    echo "== phase mixed-b (source goodix_core + stock xiaomi_touch)"
    sh_ mark "phase mixed-b"
    if sh_ insmod "$D/modules/source/goodix_core.ko"; then
        echo "UNEXPECTED: source goodix_core loaded on stock xiaomi_touch."
        sh_ waitprobe; sh_ start; sleep 5
        phase mixed-b
        echo "Stopping here; reboot before running again."
        exit 1
    fi
    sh_ collect "$D/out/mixed-b"; pull mixed-b
fi

if want stock; then
    echo "== phase stock (stock goodix_core + stock xiaomi_touch)"
    sh_ mark "phase stock"
    sh_ insmod "$D/modules/stock/goodix_core.ko" && sh_ waitprobe
    sh_ start
    sleep 5
    phase stock
fi

tar -C "$(dirname "$out")" -czf "$out.tar.gz" "$(basename "$out")"
echo
echo "Done. Send this file back: $out.tar.gz"
echo "Reboot the phone now (adb reboot): the stock modules are left loaded on purpose."
