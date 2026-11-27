#!/system/bin/sh
# SPDX-License-Identifier: GPL-2.0-only
# Device side of the amethyst touch A/B kit. Run as root (adb root) from
# run-touch-ab.sh; each subcommand prints its result and exits non-zero on
# refusal. Nothing here forces a module out or bypasses a load check.

KIT=/data/local/tmp/touchkit
SVC_LIST="touchfeature-service toucheventcheck"

log() { echo "touchkit: $*"; echo "touchkit: $*" > /dev/kmsg 2>/dev/null; }

loaded() { grep -q "^$1 " /proc/modules; }

refcnt() { cat /sys/module/$1/refcnt 2>/dev/null || echo -; }

holders() { ls /sys/module/$1/holders 2>/dev/null | tr '\n' ' '; }

# Processes that hold /dev/xiaomi-touch open (each pins xiaomi_touch).
dev_users() {
	for p in /proc/[0-9]*; do
		for f in $p/fd/*; do
			case "$(readlink $f 2>/dev/null)" in
			/dev/xiaomi-touch) echo "${p#/proc/} $(cat $p/cmdline 2>/dev/null | tr '\0' ' ')"; break ;;
			esac
		done
	done
}

stop_services() {
	for s in $SVC_LIST; do
		stop $s 2>/dev/null
	done
	i=0
	while [ $i -lt 20 ]; do
		[ -z "$(dev_users)" ] && break
		sleep 0.5; i=$((i + 1))
	done
	for s in $SVC_LIST; do
		echo "$s: $(getprop init.svc.$s)"
	done
	u=$(dev_users)
	if [ -n "$u" ]; then
		echo "still open by: $u"
		return 1
	fi
	return 0
}

start_services() {
	start touchfeature-service
	sleep 1
	echo "touchfeature-service: $(getprop init.svc.touchfeature-service)"
}

# Unload one module only if nothing holds it.
safe_rmmod() {
	m=$1
	loaded $m || { echo "$m: not loaded"; return 0; }
	h=$(holders $m)
	r=$(refcnt $m)
	if [ -n "$h" ] || [ "$r" != 0 ]; then
		echo "$m: in use (refcnt $r, holders: $h), not unloading"
		return 1
	fi
	rmmod $m || { echo "$m: rmmod failed"; return 1; }
	echo "$m: unloaded"
}

unload_pair() {
	stop_services || return 1
	safe_rmmod focaltech_touch || return 1
	safe_rmmod goodix_core || return 1
	safe_rmmod xiaomi_touch || return 1
}

# insmod and report the kernel's verdict; a refusal is a valid result.
try_insmod() {
	f=$1
	log "insmod $f"
	if insmod "$f"; then
		echo "loaded $f"
		return 0
	fi
	echo "REFUSED $f"
	dmesg | tail -n 8 | grep -iE 'disagrees|unknown symbol|version|invalid|insmod'
	return 1
}

wait_probe() {
	i=0
	while [ $i -lt 60 ]; do
		if grep -q 'Name="goodix_ts"' /proc/bus/input/devices && [ -e /sys/class/touch/touch_dev ]; then
			echo "goodix_ts registered after $((i / 2))s"
			# firmware/config check runs in the later-init work
			sleep 5
			return 0
		fi
		sleep 0.5; i=$((i + 1))
	done
	echo "goodix_ts did not register within 30s"
	return 1
}

collect() {
	d=$1
	mkdir -p $d
	{
		echo "## uname"; uname -a
		echo "## modules"; grep -E '^(goodix|xiaomi_touch|focaltech|panel_event|miev|goodix_fod)' /proc/modules
		for m in goodix_core xiaomi_touch focaltech_touch; do
			loaded $m && echo "$m refcnt=$(refcnt $m) holders=$(holders $m) srcversion=$(cat /sys/module/$m/srcversion 2>/dev/null)"
		done
		echo "## services"
		for s in $SVC_LIST; do echo "$s=$(getprop init.svc.$s)"; done
		ps -A -o PID,NAME | grep -iE 'touch|thp'
		echo "## /dev/xiaomi-touch users"; dev_users
		echo "## spi0.0"; ls -l /sys/bus/spi/devices/spi0.0/driver 2>&1
		echo "## interrupts"; grep -iE 'tp|goodix|focal' /proc/interrupts
	} > $d/state.txt 2>&1
	cat /proc/bus/input/devices > $d/input-devices.txt 2>&1
	getevent -p > $d/getevent-p.txt 2>&1
	ls -l /sys/class/touch/touch_dev/ > $d/sys-touch_dev.txt 2>&1
	for n in resolution_factor enable_touch_raw touch_vendor panel_vendor panel_color panel_display touch_finger_status abnormal_event; do
		echo "$n: $(cat /sys/class/touch/touch_dev/$n 2>&1)"
	done > $d/sys-touch_dev-values.txt
	ls -l /proc/ | grep -E 'tp_|goodix' > $d/proc-list.txt 2>&1
	for n in tp_fw_version tp_lockdown_info; do
		echo "$n: $(cat /proc/$n 2>&1)"
	done > $d/proc-values.txt
	dumpsys input > $d/dumpsys-input.txt 2>&1
	dmesg > $d/dmesg.txt 2>&1
	logcat -d -b main,system,crash -v threadtime > $d/logcat.txt 2>&1
	getprop > $d/getprop.txt 2>&1
}

# getevent while the tester touches; IRQ counts before/after show whether
# the controller interrupts at all.
touchtest() {
	d=$1; secs=${2:-15}
	mkdir -p $d
	grep -iE 'tp|goodix|focal' /proc/interrupts > $d/irq-before.txt
	timeout $secs getevent -lt > $d/getevent-lt.txt 2>&1
	grep -iE 'tp|goodix|focal' /proc/interrupts > $d/irq-after.txt
	echo "events: $(grep -c ABS_MT_POSITION $d/getevent-lt.txt) MT position lines"
}

case "$1" in
info)
	echo "kernel: $(uname -r)"
	echo "fingerprint: $(getprop ro.build.fingerprint)"
	echo "debuggable: $(getprop ro.debuggable) selinux: $(getenforce)"
	echo "id: $(id)"
	echo "input: $(grep -o 'Name="[^"]*"' /proc/bus/input/devices | tr '\n' ' ')"
	echo "spi0.0 driver: $(readlink /sys/bus/spi/devices/spi0.0/driver)"
	grep -E '^(goodix|xiaomi_touch|focaltech)' /proc/modules
	for f in $KIT/modules/*/*.ko; do
		echo "$f: $(strings $f 2>/dev/null | grep -m1 '^vermagic=')"
	done
	;;
mark) shift; log "$*" ;;
stop) stop_services ;;
start) start_services ;;
unload) unload_pair ;;
insmod) try_insmod "$2" ;;
rmmod) safe_rmmod "$2" ;;
waitprobe) wait_probe ;;
collect) collect "$2" ;;
touch) touchtest "$2" "$3" ;;
*) echo "usage: dev.sh info|mark|stop|start|unload|insmod|rmmod|waitprobe|collect|touch"; exit 2 ;;
esac
