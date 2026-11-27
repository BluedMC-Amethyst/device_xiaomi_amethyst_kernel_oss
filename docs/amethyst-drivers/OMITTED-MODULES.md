# Amethyst stock modules without a source build

This document classifies the 41 modules in the "Missing modules" table of
`INVENTORY.md`. Stock binaries come from OS3.0.306.0 and are not tracked.
The evidence comes from:

- stock `modinfo`, strings, exported and imported symbols, and the function
  list and call relocations (`llvm-nm` / `llvm-objdump -dr`);
- the stock DTB and DTBO (`device/xiaomi/amethyst-kernel/images/`);
- LineageOS userspace: `device/xiaomi/amethyst` (rc, sepolicy, Parts) and
  `vendor/xiaomi/amethyst` (rc files and binary strings);
- GitHub code search and MiCode's releases (`MiCode/Xiaomi_Kernel_OpenSource`,
  `MiCode/MTK_kernel_device_modules`).

The amethyst release, `flourite-v-oss`, contains none of these drivers. Of
Xiaomi's own trees, only `mm/launch_boost` (lb) has source in this kernel.

## Summary

| Module | Class | Donor | Recommendation |
| --- | --- | --- | --- |
| mi_thermal_interface | Xiaomi feature driver | MiCode ziyi-s-oss (+malachite-u-oss) | **reconstructed** (`techpack/amethyst/mi_thermal_interface`) |
| miev | debug/logging | MiCode MTK dash-w-oss (exact) | **reconstructed** (`techpack/amethyst/miev`) |
| swinfo | debug/logging | MiCode onyx-v-oss (exact) | **reconstructed** (`techpack/amethyst/swinfo`) |
| mi_memory | factory diagnostic | MiCode MTK malachite-u-oss (MTK UFS/DRAM variant) | reconstruct later |
| lb | Xiaomi feature driver | in-tree `mm/launch_boost` (older subset) | omit; it can be enabled later (it builds) |
| metis | kernel integration module | MiCode ziyi-s-oss `drivers/mihw/metis` (5.10, far smaller) | omit-with-evidence |
| mist | kernel integration module | none official | omit-with-evidence |
| mi_schedule | kernel integration module | MiCode ziyi-s-oss `drivers/mihw/mi_sched` (5.10) | omit-with-evidence |
| migt | Xiaomi feature driver | MiCode ziyi-s-oss `drivers/mihw/game` (5.10) | omit-with-evidence |
| mi_power | debug/logging | none official | omit-with-evidence |
| millet_core | Xiaomi feature driver | MiCode ziyi-s-oss/zeus-s-oss `drivers/mihw/millet` | omit-with-evidence |
| millet_binder | Xiaomi feature driver | same | omit-with-evidence |
| millet_hs | Xiaomi feature driver | same | omit-with-evidence |
| millet_pkg | Xiaomi feature driver | same | omit-with-evidence |
| millet_sig | Xiaomi feature driver | same | omit-with-evidence |
| millet_oem_cgroup | Xiaomi feature driver | same (`oem_cgroup.c`) | omit-with-evidence |
| binder_gki | Xiaomi feature driver | same (`binder_gki.c`) | omit-with-evidence |
| binder_prio | Xiaomi feature driver | none | omit-with-evidence |
| proc_exit | Xiaomi feature driver | none | omit-with-evidence |
| perf_helper | Xiaomi feature driver | community copies only, provenance unclear | omit-with-evidence |
| mi_mempool | Xiaomi feature driver | none official | omit-with-evidence |
| mi_async_reclaim | Xiaomi feature driver | none | omit-with-evidence |
| mi_rmap_efficiency | Xiaomi feature driver | none | omit-with-evidence |
| io_monitor | debug/logging | none official | omit-with-evidence |
| debug_ext | debug/logging | none (a community copy is decompiled; rejected) | omit-with-evidence |
| bootinfo | debug/logging | old in-kernel `arch/arm64/kernel/bootinfo.c` (msm8996 era) | reconstruct later (low value) |
| hardwareinfo | factory diagnostic | none official | omit-with-evidence |
| ufs_ffu | factory diagnostic (UFS firmware updater) | none, and must not be | omit-with-evidence |
| minet | Xiaomi feature driver (network) | none | omit-with-evidence |
| miwill | Xiaomi feature driver (network) | none | omit-with-evidence |
| miicmpfilter | Xiaomi feature driver (network) | none | omit-with-evidence |
| sla | Xiaomi feature driver (network) | none | omit-with-evidence |
| nxp-nci | obsolete/absent hardware | NXP nfcandroid driver | omit-with-evidence |
| tef668x_dlkm | obsolete/absent hardware | none needed | omit-with-evidence |
| tlv320aic3x_dlkm | obsolete/absent hardware | upstream `sound/soc/codecs/tlv320aic3x.c` | omit-with-evidence |
| focaltech_touch | hardware driver | owned by another workstream | - |
| cs35l41_dlkm | hardware driver (absent on amethyst: no DT node) | owned by another workstream | - |
| cs35l43_dlkm | hardware driver (absent on amethyst: no DT node) | owned by another workstream | - |
| fs19xx_dlkm | hardware driver (absent on amethyst: no DT node) | owned by another workstream | - |
| sia91xx_dlkm | hardware driver (absent on amethyst: no DT node) | owned by another workstream | - |
| sia91xx_tuning_dlkm | hardware driver (absent on amethyst) | owned by another workstream | - |

**Boot impact:** none of the 41 is needed to boot. A missing module cannot
fail first-stage init, because the source lists never name it. The
userspace references listed below fail softly: init logs an error for a
`chmod`, `chown`, `restorecon`, `write` or `writepid` on a missing path and
carries on. The real losses are **functional** (thermal policy, charger
thermal input, MIUI performance features). They are not boot failures.

## How the source-built users compile without the missing exports

The inventory lists stock modules that import from missing modules. The
source builds of those users get by in three ways:

- **miev users** (audpkt_ion, aw8697/si/qcom-hv haptics, aw882xx, tfa986x,
  cs35l4x, fs19xx, sia91xx, bt_fm_slim, machine/mbhc, msm_drm, msm_kgsl,
  msm_video, qti_battery_charger, ufs_qcom, wcd_usbss_i2c, xiaomi_touch):
  `include/miev/mievent.h` in this tree, as shipped by Xiaomi, is a stub.
  `cdev_tevent_alloc()` is a `static inline` that returns NULL, and the
  other functions return 0. Every call site compiles, and every event is
  silently dropped. **Lost:** the MiSight kernel event reports (touch, audio,
  display, GPU, video, UFS, charger, haptics and BT faults). LineageOS has
  no reader for `/dev/miev` (the MiSight daemon is MIUI system software), so
  nothing on LOS consumes them. See miev below.
- **metis / mist / mi_schedule users** (sched-walt, msm_kgsl, msm_drm,
  bwmon, memlat): the call sites **are not in the released source at all**.
  `grep` over the kernel tree and `sm7635-modules` finds no reference to any
  metis/mist/mi_schedule symbol (for example `metis_sched_enable`,
  `mi_dflt_schedule_hook`, `trigger_mist_load_tracking`, `mi_task_fork`,
  `metis_set_common_persist_vip`). They are not disabled by config, `#ifdef`
  or weak stubs: Xiaomi stripped them from the release. **Lost:** Xiaomi's
  scheduler extensions in WALT (VIP/render/UI task placement, cold-start
  spreading, the metis load balancer, the pkg load tracking from
  mi_schedule) and the mist GPU/DDR frame-load governors in kgsl, bwmon and
  memlat. The QCOM default governors still work. The inventory's "Interface
  differences" table shows the matching gap the other way: stock
  sched-walt exports 20 extra symbols and stock kgsl exports
  `mi_soc_gov_update_gpufreq` for these modules.
- **mi_power users** (qcom-spmi-pmic, qcom_stats): their calls to
  `mi_power_regmap_register` and `register_mi_{cx,ddr}_stats_get_ss_vote_info`
  / `subsystem_sleep_stats_dbg_*` are likewise absent from the release.
  **Lost:** Xiaomi's PMIC register dumps and sleep-vote debug statistics
  (`/sys/class/mi_power`, `/sys/class/power_debug`). These are debug only.
- **millet_* / binder_gki users** are all missing modules themselves.

## Userspace and init references

There is no `insmod` or `modprobe` of any omitted module in the device or
vendor rc/sh files. `vendor_modprobe.sh` loads the built list. These
references point at nodes of omitted modules:

| Reference | Provider | Effect while missing |
| --- | --- | --- |
| `vendor/bin/mi_thermald` (service `mi_thermald`, class main) reads/writes `/sys/class/thermal/thermal_message/*` (sconfig, cpu_limits, board_sensor_temp, screen_state, usb_online, charger_temp, display_therm_temp, ...) and `/sys/class/thermal/power_save/powersave_mode` | mi_thermal_interface | **Degraded thermal policy.** mi_thermald cannot apply its CPU caps (the `cpu_limits` freq_qos path), publish the board temperature or see scene changes. Only the QTI thermal HAL and kernel trip points remain. Reconstructed. |
| `init.target.rc`: chown/chmod of `thermal_message/{sconfig,balance_mode,boost,torch_real_level,flash_state,charger_temp,board_sensor_temp_comp,cpu_nolimit_temp}`, `power_save/{powersave_mode,power_level}`; `write .../thermal_message/sconfig 20` on boot_completed | mi_thermal_interface | init errors; the boot-time thermal mode is not set. Reconstructed. |
| LineageOS Parts `ThermalUtils.kt` writes `thermal_message/sconfig` (per-app thermal profiles) | mi_thermal_interface | **The Parts thermal profiles feature does nothing.** Reconstructed. |
| qti_battery_charger's `charger_notifier` (THERMAL_BOARD_TEMP, THERMAL_SCENE → ADSP `XM_PROP_THERMAL_*`) | mi_thermal_interface (sconfig and board_sensor_temp stores) | **The charger firmware never gets the board temperature or thermal scene**, so smart-charging thermal limits fall back to defaults. Reconstructed. |
| Camera (`com.qti.chi.override.so`, `libchifeature2.so`, `libcamlog.so`), `displayfeature.default.so`, `libqcodec2_*filter.so` read `thermal_message/board_sensor_temp` | mi_thermal_interface | These read an empty node and fall back to their default behaviour (temperature-based camera, display and codec scaling). Reconstructed. |
| `libmisight.so` (audio HAL, AGM/PAL, touchfeature, vibratorfeature, citsensorservice, mlipay, camera) opens `/dev/miev`; `hal_camera` sepolicy; `init.target.rc` chmod `/dev/miev` | miev | It logs `report:no open miev` and drops the event. No functional effect. Reconstructed. |
| `init.target.rc`: about 100 chmod/chown/restorecon on `/dev/migt`, `/dev/metis`, `/dev/metis_link`, `/sys/module/{migt,metis}/parameters/*` | migt, metis | init error spam only. These are consumers of MIUI's Joyose/perf framework, which LOS does not ship. |
| `libsdmcore.so` (`TurboSchedStub`) opens `/dev/metis` | metis | The composer's optional VIP hint fails; no functional effect. |
| `init.target.rc`: chown `/sys/module/perf_helper/mimd/mimdtrigger` | perf_helper | init error only (a MIUI BoostFramework node). |
| `vendor.qti.hardware.display.composer-service_amethyst.rc`: `writepid ... /sys/kernel/mi_mempool/pids` | mi_mempool | The writepid fails and is logged. The composer still starts. |
| `init.qcom.rc`: chown `/sys/class/power_debug/*`, `/sys/class/mi_power/temp_aware` | mi_power | init errors only. |
| `ueventd-odm.rc` `/dev/launch_boost` | lb | No LOS client opens it. |
| `odm/etc/camera/xiaomi/DSACSettings.json` `"UfsCapacityFile": "/proc/mv"` | mi_memory | The camera's storage-capacity hint is unavailable. Minor. |
| `init.target.rc` `service ufs_ffu_service /vendor/bin/ufs_ffu.sh` (disabled; start commented out; script not shipped) | ufs_ffu | None. |
| BoardConfig cmdline `swinfo.fingerprint=` | swinfo | The parameter for an unloaded module is ignored. Reconstructed. |

## Per-module notes

### Reconstructed

**mi_thermal_interface** (`recovery`, `vendor_dlkm`; depends
panel_event_notifier, qti_battery_charger). This is Xiaomi's thermal message
bus. It creates `/sys/class/thermal/thermal_message` (34 nodes) and
`/sys/class/thermal/power_save`, caps CPU frequency through freq_qos on
`cpu_limits`, tracks the screen through panel events and USB online state,
and forwards sconfig and board temperature to qti_battery_charger. It has
the most userspace consumers of any omitted module (see the table above).
The donor is MiCode `ziyi-s-oss` drivers/thermal/mi_thermal_interface.c (a
Qualcomm build) plus `thermal_max_brightness` from MTK `malachite-u-oss`.
The nodes that stock has and the donors lack are plain integer slots: the
stock relocations show they call only snprintf and simple_strtol. The
charger forwarding follows the in-tree consumer's contract. The result's
function list, attribute list and modinfo match stock. See
`techpack/amethyst/mi_thermal_interface/ORIGIN`.

**miev** (`first_stage`, `recovery`). This is the MiSight exception-event
char device (`/dev/miev`, major 520, 64 KiB kfifo) with five exports
(`cdev_tevent_*`) that build a JSON event and queue it. The source is MiCode
MTK `dash-w-oss`, unchanged; author, description and function set match
stock, and **the export CRCs equal the CRCs stock users import** (checked
against stock `xiaomi_touch.ko`). It does not affect boot, and LOS has no
reader. Its value is that the vendor `libmisight` stops failing, and any
stock prebuilt user (for example xiaomi_touch) could load. For source-built
users to send events, the shared header must change (see the integration
requests).

**swinfo** (`first_stage`, `recovery`; depends minidump). It provides
`/proc/swinfo/platform_config.gz` (the gzipped kernel .config) and adds the
`fingerprint` parameter to minidump. The source is MiCode `onyx-v-oss`
drivers/xiaomi/swinfo, an exact match. The only change is the incbin path,
for the out-of-tree build.

### Xiaomi performance stack (omit-with-evidence)

These modules all serve MIUI framework services (Joyose, PowerKeeper,
GreezeManager, MiuiBoosterService) that LineageOS does not ship.

- **metis** (133 exports): "metis-driver by David". It does VIP task
  scheduling, frame boost, cluster affinity, the WALT load-balancer hooks,
  `/dev/metis` and `/dev/metis_link`. Its stock users (WALT, kgsl, drm,
  mi_mempool, migt) are built without the hooks.
- **mist** (44 exports): "soc performance tuner". It runs the GPU (gflt) and
  DDR (dflt) frame-load governors that hook kgsl, bwmon and memlat.
- **mi_schedule** (16 exports): per-task `mi_task_struct` and package load
  tracking. It is the base for metis and migt.
- **migt**: game turbo (`/dev/migt`, glk frequency limits, super-task boost).
- **binder_gki**, **millet_core/binder/hs/pkg/sig/oem_cgroup**: the millet
  app freezer. A netlink link to MIUI's GreezeManager tells it about binder
  traffic, signals, packets and cgroup moves to frozen apps.
- **binder_prio**: raises binder priority for a hard-coded list of
  apps/threads (SurfaceFlinger, RenderThread, com.miui.home, ...) through
  vendor hooks.
- **proc_exit**: `set_user_nice` on exiting tasks through an mmput hook.
- **perf_helper**: the MIUI BoostFramework sysfs (`/sys/module/perf_helper/mimd`),
  perflock records and memcg reclaim triggers.
- **mi_mempool**, **mi_async_reclaim**, **mi_rmap_efficiency**: MIUI memory
  tuning (a reserved page pool for whitelisted apps, an async lruvec shrink
  thread, rmap mapcount bypass).
- **lb**: app cold-launch page pre-read (`/dev/launch_boost`, class `lb`). Its source is in-tree under
  `CONFIG_MI_LAUNCH_BOOST` and **builds cleanly** as `lb.ko` against the
  current config. It is an older subset of stock: the stock `mps_*` swap
  pre-read and `lb_hot_*` functions are missing. Its only client is MIUI's
  launch boost service, so on LOS it would be inert.

Donors: MiCode `ziyi-s-oss`/`zeus-s-oss` `drivers/mihw/{metis,mi_sched,game,millet}`
are official 5.10 GPL sources. They are generations older than the 6.1
stock interfaces (for example, metis has 3 files there against stock's 133
exports). A useful port would also have to put the stripped hooks back into
WALT, kgsl, bwmon and memlat. Several community repositories contain
"reconstructed" or "final" versions of these modules. They look like
decompiler output or have no clear licence, so they were **not** used.

### Debug, diagnostic and factory modules

- **mi_power**: power-debug sysfs (`/sys/class/mi_power`, `power_debug`),
  wakeup-reason logging, sleep-stats and PMIC register dumps. It is debug
  only. Omit.
- **debug_ext**: "Xiaomi Kernel Debug Extensions". It provides `/proc`
  dma_buf per-process accounting, reserved-memory statistics and
  panic-on-reboot/shutdown triggers. Omit. The only public copy
  (`klarnet2009/dada-closed-modules/reconstructed`) is a reconstruction, so
  it was rejected.
- **io_monitor**: block, f2fs and UFS latency statistics in `/proc` and a
  misc device for MIUI's IO telemetry. Omit.
- **bootinfo**: `powerup_reason`/`poweroff_reason` sysfs, driven by the
  `pureason`/`pdreason` parameters that Xiaomi's bootloader sets. Nothing on
  LOS reads it. The old in-kernel `bootinfo.c` (for example
  LineageOS/android_kernel_xiaomi_msm8996) is a related donor. Reconstruct
  later if a reboot-reason UI wants it.
- **hardwareinfo**: puts the hardware-info string into minidump. Omit.
- **mi_memory** ("Interface for xiaomi memory"; depends ufs_qcom): DDR and
  UFS info (`/sys/class/.../memory`, `/proc/mv`) and vendor UFS health
  commands. Its only consumer is the camera DSAC capacity hint. MiCode MTK
  `malachite-u-oss` `drivers/misc/xiaomi/mi_memory` is an official
  MTK-side donor, but its UFS paths would need porting to `ufs_qcom`'s
  `get_ufs_data`/`mi_ufshcd_*` exports, which the source-built ufs_qcom
  lacks (see the inventory). Reconstruct later.
- **ufs_ffu** (27 MB): an embedded UFS firmware updater with emergency
  restart paths. Commit `017ef439f` already excluded it on purpose. It must
  not be reconstructed: flashing UFS firmware is a stock-ROM job.

### Network feature modules (omit-with-evidence)

**minet** (per-app flow stats and a TC limiter over genetlink),
**miwill** (a MiWiLL dual-band Wi-Fi bonding netdev), **miicmpfilter**
(it reports ICMP-unreachable to userspace over genetlink) and **sla**
(VoIP packet stats in `/proc`, netfilter): all of them have MIUI-only
clients (the MiWiLL and network-boost services). Nothing in the LOS vendor
or device trees opens their genetlink families or nodes. No public source.

### Absent hardware (DT evidence)

The stock DTB (volcano, volcano6, volcano6p) and DTBO have 0 matches for:

- `qcom,sn-nci` and `nxp,sn`. Amethyst uses ST NFC (`st,st21nfc` and
  `st,st54*` match in the DTBO), and those are already ported. nxp-nci is
  the NXP SN1xx driver, built for a different SKU.
- `nxp,tef668x`: an FM tuner that is not fitted.
- `ti,tlv320aic3*` and `ti,tas5411`: a codec/amp that is not fitted.
- `cirrus,cs35l4*`, `foursemi,fs16xx` and `si,sia*`: the smart-PA family,
  owned by another workstream. Amethyst's amp is AW882xx (`awinic,aw882`
  matches in the DTBO).

Xiaomi's build ships these modules for every board in the platform family.

## Integration requests

These need edits that are outside this workstream's remit.

1. **Add the reconstructed modules to the ext-module build**
   (`scripts/amethyst-ext-modules.txt` / `TARGET_KERNEL_EXT_MODULES`),
   following the aw882xx layout (`xiaomi/<name>` once copied by
   `setup-amethyst-sources.py`):
   - `miev` and `swinfo` have no ext-module dependencies. Put them under
     "Providers".
   - `mi_thermal_interface` depends only on in-tree modules
     (qti_battery_charger, panel_event_notifier). Put it under "Users".
2. **Module lists**, in stock load-order positions:
   - `modules.list.first_stage` and `modules.list.recovery`: `miev.ko`
     directly after `qcom-scm.ko`.
   - `modules.list.first_stage`: `swinfo.ko` at the end (stock: after
     debug_ext, the last entry). `modules.list.recovery`: `swinfo.ko` after
     `smcinvoke_dlkm.ko`.
   - `modules.list.vendor_dlkm` and `modules.list.recovery`:
     `mi_thermal_interface.ko` between `gpu_dump_skip_cdev.ko` and
     `qcom_edac.ko`.
   Priority: mi_thermal_interface is high (mi_thermald, Parts thermal
   profiles, charger thermal input). swinfo and miev are low.
3. **Optional, miev for source-built users.** To get kernel MiSight events
   from the source-built drivers, replace the stub
   `include/miev/mievent.h` with the real one in
   `techpack/amethyst/miev/include/miev/mievent.h` (struct layout plus
   prototypes under `#if IS_ENABLED(CONFIG_MIEV)`). Change its `#else`
   branch to `static inline` (the release header defines non-static
   functions there), and add `config MIEV` (tristate). This makes about 20
   modules hard-depend on miev in first stage, where a load failure is
   fatal. With no LOS reader of `/dev/miev`, this is **not recommended**
   for now. Keep the stub header and load miev only for `libmisight`.
4. **lb (optional):** `CONFIG_MI_LAUNCH_BOOST=m` in
   `arch/arm64/configs/vendor/amethyst_GKI.config`, plus `lb.ko` in
   `modules.list.vendor_dlkm`/`recovery` (stock order: vendor_dlkm). It
   builds, but no LOS client uses it, so leaving it off costs nothing.
5. **Init clean-up (device tree, optional):** drop the migt, metis,
   perf_helper, mi_power/power_debug and mi_mempool `writepid` lines from
   `init.target.rc`, `init.qcom.rc` and the composer rc overlay, so that
   init logs stay readable. No functional effect.
6. No new kernel exports are required by the reconstructed modules. All
   their imports (charger_notifier_call_chain, panel_event_notifier_*,
   msm_minidump_add_region, kernfs/freq_qos/power_supply) are in the
   current `Module.symvers`.
