# Migrating amethyst to the FP6 SM7635 kernel (6.1.68 to 6.1.182)

Branches: `integ/fp6-rebase` (single-tree layout) and `fp6/seventeen`
(`integ/fp6-rebase` plus the LineageOS kernel-layout split from `seventeen`).
The FP6-only module changes go on an `fp6` branch of
`android_kernel_xiaomi_sm7635-modules`. FP6's history is kept unchanged, and
the amethyst work sits on top as logical commits. This document was written before the
port started. The results sections at the end are filled in as phases finish.

## 1. Upstream being adopted

| Item | Value |
| --- | --- |
| Repository | `https://github.com/LineageOS/android_kernel_fairphone_sm7635`, branch `lineage-23.2` (remote `fp6`) |
| Commit | `9e4375a1c643881987eebdb815a6d249ac8a1cfc` (2026-11-13, "Merge remote-tracking branch 'sm8650/lineage-22.2' into lineage-23.2") |
| Version | 6.1.182 (`Makefile`); last ACK merge `android14-6.1-lts` at 6.1.159+ (2132f747a118), then LineageOS SM8650 common-kernel merges |
| QCOM base | CLO `KERNEL.PLATFORM.3.0.r1-12700-kernel.0` (d8c98e62dff5, 2025-11) |
| ACK branch / KMI | `BRANCH=android14-6.1`, `KMI_GENERATION=11` (unchanged from Xiaomi's tree) |
| Declared compiler | `build.config.constants`: `CLANG_VERSION=r487747c` (clang 17.0.2) |
| Compiler FP6 really builds with | LineageOS 23.2 `kernel.mk` default (no `TARGET_KERNEL_CLANG_*` in FP6's BoardConfig) = `clang-r563880c` (clang 21) |
| FP6 device config | `android_device_fairphone_FP6` `lineage-23.2` @ `bbd5af1ac5dd`: `gki_defconfig vendor/fps_GKI.config`, module lists `modules/modules.list.{first_stage,second_stage,vendor_dlkm,system_dlkm}` |
| FP6 module repo | `android_kernel_fairphone_sm7635-modules` `lineage-23.2` @ `9d8594b7a4d0` (the same revision the LOS tree already syncs) |

The phase-6 baseline uses **r487747c**. It is the compiler this tree declares,
the one the current amethyst build and Xiaomi's module sources were built
with, and it is already installed in the LineageOS tree. FP6's LineageOS
build shows that the kernel and the FP6 modules also build with clang 21.
That is useful evidence for phase 7 (clang 20, `clang-r547379`, also present
in the LOS tree under `prebuilts/clang/host/linux-x86`).

### Where Xiaomi's tree came from

Xiaomi's import (`sixteen` root `2467e3b38`) has no history. Scanning FP6's
history for the commit with the smallest diff in the QCOM driver directories
gives **`e60961957ca9`** (QCOM `kernel.lnx.6.1.r2`, 2024-06-10, 6.1.68). It is
the closest QCOM base: about 16k changed lines in soc/clk/pinctrl/usb/power/
thermal/remoteproc/iommu, compared with 40k+ for the neighbouring QCOM merges.
That commit is an ancestor of FP6, so every amethyst change can be expressed
as `e60961957ca9..integ/reconstruction` and replayed onto FP6 with a real
three-way merge (`git apply -3`). Nothing is cherry-picked from Xiaomi's
squashed history by hand.

The amethyst delta over that base is 949 paths: 740 added, 209 modified and
2 deleted. 345 of them are C files. Compared with the objects of the current
ROM kernel build, 161 of those C files are compiled for amethyst and 184 are
never built. The unbuilt ones are other Xiaomi devices' drivers, listed in
section 4.

## 2. Xiaomi 6.1.68 (QCOM 2024-06) compared with FP6 6.1.182 (QCOM 2025-11)

Change size from the common base `e60961957ca9`, as files and added/removed
lines:

| Area | Base to FP6 | Base to amethyst | Decision |
| --- | --- | --- | --- |
| WALT `kernel/sched/walt` | 6f +132 -23 | 14f +2211 -112 | **Keep Xiaomi additions** (sched-penalty, power-key boost, cpufreq_walt tweaks) on top of FP6's WALT. FP6 barely changed WALT, so this merges cleanly |
| sched core | 3f +256 -112 | 1f +1 -2 | Inherit FP6. Re-apply the `sched_param` UAPI move only if still needed (it is upstream b7f749a2e2f7; check FP6) |
| cpufreq | 35f +1069 -424 | 0 | **Inherit FP6** unchanged |
| cpuidle (qcom-lpm) | 14f +2941 -25 | 1f +1 | Inherit FP6, plus Xiaomi's one-line change |
| soc/qcom | 140f +27361 -2506 | 23f +384 -78 | Inherit FP6, replay Xiaomi hunks three-way (socinfo, pmic_glink, altmode, wdt, sleepmon, wcd939x/usbss, fsa4480, dcvs, panel notifier) |
| dcvs (bwmon/memlat) | 18f +3509 -42 | 4f +12 -4 | Inherit FP6, plus Xiaomi hooks |
| remoteproc / rpmsg | 18f +1274 -240 / 9f +379 -152 | 2f +254 / 1f +2 | Inherit FP6, replay Xiaomi's q6v5 SSR/crash reporting |
| thermal | 36f +2224 -218 | 1f +1 | **Inherit FP6**. `mi_thermal_interface` stays an external techpack module |
| power/supply | 38f +10340 -218 | 9f +10337 -1134 | **Keep Xiaomi** `qti_battery_charger.c` (it must match Xiaomi's ADSP battery firmware protocol: Xiaomi property IDs, SoC/health). FP6's version carries Fairphone-only features (FPS-* battery protect, charge speeds, water detection) that would talk to the wrong firmware. Port FP6's generic QCOM fixes to it where they apply |
| USB / Type-C | 279f +28233 -3483 | 25f +1347 -81 | Inherit FP6 (newer dwc3-msm, eUSB2 repeater, ucsi), replay Xiaomi hunks (dwc3-msm, eusb2 repeater tuning, PD/altmode, gadget accessory) |
| clk / pinctrl / iommu | +21876 / +7851 / +625 | 3f / 2f / 1f | Inherit FP6, replay tiny Xiaomi hunks |
| dma-buf heaps | 25f +1144 -205 | 5f +322 -2 | Inherit FP6, replay Xiaomi's heap changes |
| in-tree GPU / display | 700f (DRM core) | 0 | Inherit FP6. `msm_drm` and `msm_kgsl` are external modules |
| UFS | 13f +5258 -177 | 8f +319 -276 | Inherit FP6, replay Xiaomi hunks (ufs-qcom, phy). Xiaomi's mi_ufs core is not in any source |
| regulator | 31f +9850 -262 | 7f +2528 -14 | Inherit FP6, add the Xiaomi wl2866d/wl28661d camera PMIC drivers |
| mm | 89f +5225 -1598 | 24f +2192 -2 | Inherit FP6, replay amethyst's mm exports/vendor hooks (used by Xiaomi modules) |
| trace hooks | 26f +1026 -49 | 4f +56 -1 | Replay Xiaomi's mm/rwsem/vmscan hooks; keep the KMI-protected ones unchanged |
| configs | 42f +4805 -97 | 8f +94 -5 | Use FP6's `vendor/pineapple_GKI.config`, and move Xiaomi's pineapple changes into `vendor/amethyst_GKI.config` |

### GKI exports and ABI

Both trees are `android14-6.1`, KMI generation 11, and use `gki_defconfig`
with `CFI_CLANG`, `MODVERSIONS`, `MODULE_SIG` and `MODULE_SIG_PROTECT`. The
amethyst ROM already builds every module from source, system_dlkm included,
so it does not rely on the Google-signed GKI 6.1.138 system_dlkm or on stock
vendor modules. KMI compatibility with stock binaries is therefore **not** a
goal. What matters is that this tree, its in-tree modules and the external
modules are built together with one `Module.symvers`, which the build
guarantees. `TRIM_UNUSED_KSYMS` is off in the amethyst config, so the
`android/abi_gki_aarch64_*` symbol lists have no effect on the make build.
Xiaomi's symbol-list edits are not carried.

### Configs

Final config = `gki_defconfig` + FP6's `vendor/pineapple_GKI.config` +
`vendor/amethyst_GKI.config` + `vendor/amethyst_standalone.config`, in the
same order and with the same merge as today. Changes:

- FP6's `pineapple_GKI.config` differs from Xiaomi's QCOM copy by +AT803X_PHY,
  +BHS_IRQ, +MMC_CRYPTO_QTI, +QCOM_BWPROF, +QTI_THERMAL_VENDOR_HOOK and
  -QCOM_MEM_OFFLINE. Stock amethyst loads `mem-offline.ko`, so
  `CONFIG_QCOM_MEM_OFFLINE=m` is added back in `amethyst_GKI.config`.
- Xiaomi's own pineapple edits move to `amethyst_GKI.config`:
  `REGMAP_QTI_DEBUGFS_ALLOW_WRITE=y`, `LEDS_QPNP_VIBRATOR_LDO` off,
  `REGULATOR_WL2866D/WL28661D=m`, `MI_DUMP_DISPLAY=m`, and
  `MTD/MTD_BLOCK/MTD_BLOCK2MTD/MTD_OOPS=m` (mtdoops pmsg ramoops).
- `fps_GKI.config` (FP6 device drivers) is not used.

### External module dependencies

| Project | Source | Decision |
| --- | --- | --- |
| bt, dataipa, datarmnet, datarmnet-ext/*, dsp, eva, graphics (kgsl), mm-drivers (hw_fence, msm_ext_display, sync_fence), mm-sys-kernel/ubwcp, mmrm, securemsm, spu, synx, video | FP6 modules `9d8594b7a4d0` | **Inherit unchanged.** They are written for this exact kernel. |
| audio-kernel | MiCode `flourite-v-oss` `26d5a555078f` | **Keep Xiaomi**: aw882xx/fs19xx machine integration, amethyst dai links, msm_stub rates. FP6's copy differs by about 64k lines and lacks them |
| display-drivers | MiCode `f60c37c2d736` | **Keep Xiaomi**: mi_disp (HBM/DC/FOD/LHBM), O16U panels. FP6's copy differs by about 25k lines |
| camera-kernel | MiCode `017ae73901de` | **Keep Xiaomi**: amethyst sensors, OIS, actuators, EEPROM, cam_msger/cameralog |
| wlan (platform, qcacld-3.0, cmn, fw-api) | MiCode `a4da9e3b4386` | **Keep Xiaomi**: matches stock qca6750 firmware, ini and profile. FP6's is newer, about 16k lines in qcacld, and could replace it later only after a firmware-compatibility test |
| aw882xx(+fs19xx), st-nfc, st-ese, focaltech_touch, miev, swinfo, mi_thermal_interface | techpack/amethyst, now `xiaomi/` in the modules repo | **Keep** |
| touch-drivers, nxp nfc, samsung nfc, FP6 wlan variants | FP6 | Not used (FP6 hardware) |

Local patches in `scripts/amethyst-patches/los/`. Since the split, these are commits on the modules repo's `seventeen` branch:

| Patch | On FP6 base |
| --- | --- |
| amethyst-qcom-modules/0001 bt-kernel local scope | **Still needed** with r487747c (clang 17 rejects a declaration right after a `case` label). Harmless with newer clang |
| amethyst-qcom-modules/0002 video MIN/MAX | **Dropped** (modules `fp6` 0001). FP6 6.1.182 `linux/minmax.h` defines `MIN`/`MAX`, which is what FP6's video driver expects. The fallback could also clash as a redefinition |
| audio-kernel/0001 build selects volcano + symvers | Still needed (LineageOS kernel.mk build) |
| audio-kernel/0002 msm_stub 96 kHz/8 ch | Still needed (amethyst speaker graph) |
| camera-kernel/0001 cam_msger frame size | Still needed |
| camera-kernel/0002 build selects volcano + symvers | Still needed |
| display-drivers/0001 provider symvers | Still needed |
| display-drivers/0002 mi_disp FOD UI ready UAPI | Still needed |
| wlan/0001 qca6750 make build | Still needed |
| wlan/0002 profile strings (`/dev/wlan`) | Still needed |

## 3. Amethyst work carried onto FP6

Each item lists its source and how it is ported. Status is in section 7.

1. Xiaomi in-tree drivers that amethyst builds: hwid, mi_sw_sync,
   xiaomi_wifi_gpio, gpio-mi-t1, gpio-tiantong, dump_display, mi_mpam,
   hyperframe (`drivers/hyperenhance`), cpq (`block/cpq`), goodix_fod and
   fpc_fod fingerprint, aw86927/si/aac haptics, wl2866d/wl28661d regulators,
   charger_partition, sched-penalty. These are new files, copied unchanged,
   with Kconfig/Makefile hooks.
2. Touch: `drivers/input/touchscreen/goodix_berlin_driver` (9916R, stock THP
   ABI) and `drivers/input/touchscreen/xiaomi` (xiaomi_touch with stock event
   injection and status ABI). New files.
3. Modifications to QCOM/ACK files (about 150 files): replayed three-way from
   `e60961957ca9..integ/reconstruction`, one commit per subsystem. Conflicts
   are resolved by hand and noted in the commit messages.
4. Changes from los24-baseline and integ: the mm exports/hooks (1457ab630),
   the hwid/ipa_usb identifiers (3291ae047), the panel_event_notifier client
   ABI (855b12f3d), qseecom smcinvoke listener dispatch (b9e29acad), the WALT
   power-key boost (0a527d807), and the `sched_param` UAPI move (83d94cd16).
   The last one is dropped if FP6 already has it.
5. techpack/amethyst modules (now in the modules repo), scripts, docs and
   config fragments.

## 4. Not carried (and why)

Xiaomi drivers that are never compiled for amethyst (verified: no object in
the current ROM kernel build):

- `drivers/net/wireless/bcmdhd`, `drivers/pci/brcm_xgbe`, `spi-brcm-core`,
  `spidev-brcm`: Broadcom Wi-Fi/Ethernet on other devices.
- `drivers/media/platform/xiaomi` (ispv4) and the ispv4 headers: the ISP
  co-processor on other devices.
- `drivers/nfc/{pn560,tmsdrv,p73-spi}`, `drivers/ntag`: NXP/TMS NFC; amethyst
  uses ST.
- `drivers/input/fingerprint/{fpc_1553,goodix_cap,mi_fp,mi_fp_ultra,xiaomi_fp}`,
  `drivers/input/stmvl53l5`, `aw8622x_haptic`.
- `drivers/sandbox`, `drivers/hdbds`, `drivers/staging/speed_ui`,
  `mm/launch_boost`, `gpio-jingshang*`, `gpio_control`, `hl7603`, `wl2868c`,
  `xm-extcon-usb-gpio`, `repeater-i2c-eusb2`.
- Xiaomi edits to files that amethyst does not build: `fs/smb/client/*`,
  `venus`, `spidev.c`, `f_diag.c`, `f_rndis.c`, `tools/lib/bpf/libbpf.c`.
- Bazel/Kleaf files (`*.bzl`, `build.config.msm.*`, `modules.list.msm.*`,
  `build.targets`): LineageOS builds with make, and the module lists are in
  the device tree.
- `android/abi_gki_aarch64_{qcom,xiaomi}` edits (no effect without
  `TRIM_UNUSED_KSYMS`), `include/linux/wakelock.h` (unused), and
  `include/uapi/media/synx.h` (unused; the synx UAPI comes from synx-kernel).

## 5. Device tree

The ROM keeps booting the **stock DTB and DTBO**. All 331 compatibles on
enabled nodes in the stock DTBs and DTBO were checked against the Xiaomi tree,
the FP6 tree and all module sources (`work/fp6/bin/dt-compat.py`). Every
compatible that the Xiaomi tree binds and FP6 lacks belongs to a Xiaomi driver
that this port carries: awinic/sih haptics, fpc/goodix fingerprint,
`mdm,mi_t1_chip`, pmk8350 pwrkey bark (pm8941-pwrkey hunk),
`xiaomi,dump_display`, `xiaomi,mtdoops_pmsg` (mtdoops hunk), xiaomi touch,
wl2866d, st21nfc/st54 (techpack), aw882xx (techpack). No new compatible is
needed. Binding changes the newer FP6 drivers require are listed in
section 8.

## 6. Phases

- **Phase 6 (functional baseline):** FP6 kernel plus the items in section 3,
  `r487747c`, FP6's `pineapple_GKI.config` plus amethyst fragments, and every
  external module from section 2 built against it. Success means everything
  compiles, the full module set passes `amethyst-preflight-modules.py`, and
  KCFI, modversions and signing are all left on.
- **Phase 7 (clang 20):** `clang-r547379` from the LOS tree's
  `prebuilts/clang/host/linux-x86`. Rebuild everything, fix real source
  problems, and keep r487747c selectable as a fallback
  (`AMETHYST_KERNEL_CLANG`).
- **Phase 8 (AmethystGKI items, one revertible commit each):** LZ4 1.10 + NEON
  decompressor (benefit: zram/erofs decompression throughput, measure with
  zram swap-in benchmarks), BBRv3 (measure with network throughput and
  latency), `-mtune=cortex-a720` (needs clang 18+; measure with benchmarks),
  and the opt-in "lean" config is rejected because it weakens hardening.
  Not wanted: KernelSU/SUSFS (not requested), WildKernels scheduler tweaks
  (WALT owns placement), global -O3 (unproven, larger image).
- **Phase 9 (AutoFDO):** record a new LineageOS profile on device (simpleperf
  cycles; no ETM on amethyst), keep the unstripped `vmlinux` and its build ID
  with the profile, and backport the `CONFIG_AUTOFDO_CLANG` build flags.
  `bluedmc.afdo` is not used, since it was recorded on a different kernel.

## 7. Results

### What was carried, and how

Each of the decisions above is a commit on `integ/fp6-rebase` (see
`git log fp6/lineage-23.2..integ/fp6-rebase`). That branch keeps the old
single-tree layout. `fp6/seventeen` adds one commit on top (d7ad170dd1d2),
which ports `seventeen`'s split into the LineageOS kernel layout. The
FP6-only module changes are four patches for an `fp6` branch of the modules
repo (section 9). Changes that FP6 already has were dropped instead of being
applied twice:

- The mm exports and vendor hooks from 1457ab630 (vm_normal_page,
  walk_page_range, read_swap_cache_async, folio_mapcount, shrink_slab,
  reclaim_pages, osq_lock/unlock, the filemap/rwsem/vmscan/rmap hooks) are
  all in FP6's ACK 6.1.159+ merge.
- The `struct sched_param` UAPI move (b7f749a2e2f7) is in FP6.
- qseecom smcinvoke listener dispatch (b9e29acad) is in FP6's
  qseecom_proxy.
- ipa_usb/hwid identifiers (3291ae047) are already in FP6's headers.
- The four ACK hooks Xiaomi still declared and ACK has since removed
  (`android_vh_cache_show`, `nf_conn_alloc/free`, `freq_table_limits`,
  `gic_v3_affinity_init`) have no users among the source-built modules.

Conflicts were resolved in favour of FP6's newer QCOM code wherever both
sides changed the same lines, with three exceptions. `qti_battery_charger`
and `qcom-reboot-reason` are Xiaomi's versions, because they must match the
ADSP firmware and the bootloader. `arm-smmu` runtime PM follows stock. Other
choices:

- Not carried, as debug-only edits to GKI core: printk additions in usb/core,
  hid, sound/usb/card.c and udc/core; `dump_stack()` in ufshcd shutdown.
- Not carried, as security-weakening: `FACTORY_BUILD` in commoncap.
- Not carried, as ispv4-only: pci-msm's ispv4 exports.

Adaptations to 6.1.182 APIs:

- `calc_vm_flag_bits(file, flags)` in three RichTap mmap handlers.
- `<linux/minmax.h>` now defines `MIN`/`MAX`, so the local copies in the
  aw86927/si ring buffers, goodix_ts_inspect and fs19xx are dropped.

Per component:

| Component | State |
| --- | --- |
| FP6 kernel 6.1.182 + amethyst configs | builds (r487747c and clang 20) |
| Xiaomi in-tree drivers (hwid, touch, fingerprint, haptics, regulators, charger_partition, dump_display, mi_mpam, hyperframe, cpq, sched-penalty, mi_sw_sync, wifi_gpio, gpio-mi-t1/tiantong) | builds |
| WALT with Xiaomi sched_opt and power-key boost | builds; needs device test (scheduler) |
| Xiaomi battery charger, reboot reason, PON log | builds; needs device test (charging, reboot reasons) |
| USB/eUSB2/QMP Xiaomi tuning | builds; needs device test (USB 2/3, OTG, DP alt mode) |
| modules repo `xiaomi/`: aw882xx+fs19xx, st-nfc, st-ese, focaltech_touch, miev, swinfo, mi_thermal_interface | builds (fs19xx with modules `fp6` 0002) |
| FP6 external modules (bt, data*, dsp, eva, kgsl, mm-drivers, ubwcp, mmrm, securemsm, spu, synx, video) | builds unchanged |
| MiCode audio, display, camera, wlan | builds; qcacld with modules `fp6` 0003/0004 |
| Device tree sources | `sm7635-devicetrees` `seventeen`, unchanged and independent of the kernel |

### Modules and preflight

The module set is identical to the current 6.1.68 ROM build: 475 modules,
102 of them external, and no module is missing. FP6 adds four modules that
stay unlisted: at803x, bhs-irq-controller, bwprof and qti_thermal_vendor_hooks.
Every module is signed by the build key. CFI_CLANG, MODVERSIONS, MODULE_SIG,
MODULE_SIG_PROTECT and SHADOW_CALL_STACK are on, and CFI_PERMISSIVE is off.

`kernel/xiaomi/sm7635/scripts/amethyst-los-kernel-build.sh <los> install preflight` lays the modules out
the way kernel.mk ships them, using the device's `modules.list.*`, and runs
`amethyst-preflight-modules.py`. The result is **0 errors** for vendor_boot,
system_dlkm and vendor_dlkm, with both compilers. These results come from
`fp6/seventeen` in the LineageOS layout plus the modules `fp6` patches
(`work/fp6/bin/mklos17.sh` and `fullbuild17.sh`):

- 475 modules were staged: system_dlkm 60, vendor_boot 317 and
  vendor_dlkm 415, with overlap because vendor_boot includes recovery.
- The kernel has 15712 vmlinux exports.
- vendor_boot lists 115 modules and loads 116 once dependencies are
  included.
- system_dlkm is signed by this build.
- vendor_dlkm lists 285 modules, 331 with their dependency closure.

Interfaces lost compared with the current ROM modules
(`work/fp6/bin/ifacediff.py`):

- pci-msm ispv4 exports: intended.
- `qcom_q6v5_pas` `rproc_set_state`: FP6 gates it behind SOCCP, which volcano
  lacks.
- `mem_buf_vmperm_release`: upstream change, with no importer.
- Some USB serial/ethernet IDs in ftdi_sio/r8152, and cfg80211's
  regulatory.db firmware hint: upstream ACK changes.

### Phase 7: clang 20

`AMETHYST_KERNEL_CLANG=<LOS>/prebuilts/clang/host/linux-x86/clang-r547379`
builds the kernel and every module. r487747c stays the default and the
fallback. clang 20 raised three `-Wenum-compare` errors (`-Werror`). All
three are fixed in the source, and no warning is suppressed:

- Xiaomi mtdoops compared its own dump-reason enum against `KMSG_DUMP_*`.
  The values are equal, and the fix is cosmetic.
- MiCode qcacld compared the reason code against a disconnect-source enum.
  This was a real bug: MLO link-switch disconnects were sent over the air.
  It is fixed by modules `fp6` 0003, as in newer qcacld.
- qcacld's sanity check compares the WMI and MLME hw-mode counts, which
  belong to different enum types. It is fixed by modules `fp6` 0004, which
  casts both sides to `int32_t`; the check itself is unchanged.

The other clang 20 diagnostics are `-Wformat` warnings: 665 unique sites.
Most are `%d`/`%u`/`%lx` used with `long`, `size_t` or `u64`. They are in
FP6/QCOM code, such as dataipa, adsprpc, ubwcp, mmrm, hw_fence, WALT,
gunyah, geni and mhi. The kernel's `scripts/Makefile.extrawarn` turns
`-Wformat` off below clang 18, so r487747c reports none of them. They are
warnings, not errors, and the same code builds with clang 21 for FP6. They
are left alone and not suppressed. Fixing them belongs upstream, or in a
later cleanup series.

## 8. DT binding changes for the DT agent

**None are required.** The kernel needs no DT change to boot with the stock
DTB/DTBO. All 331 compatibles on enabled nodes are bound by a driver in this
tree or its modules (section 5). The new properties that FP6's drivers read
(`work/fp6/ref/dt-props.txt`) are all optional, so a missing property keeps
the old behaviour:

- btpower: `qcom,bt-debug-gpio`, `qcom,xo-reset-gpio`
- hci_qca: `qcom,local-bd-address-broken`
- geni i2c/uart: `qcom,ssr-enable`, `qcom,msm-geni-one-wire-serial`,
  `qcom,push-pull`
- adc5-gen3: `qcom,adc5-gen4`
- q6v5_pas: `rproc-ddr-set-icc-low-svs`, `soccp-tcsr` (SOCCP only)
- bcl_pmic5: `qcom,ibat-ccm-*`
- dwc3-msm: `orientation-override`, `qcom,disable-wakeup`,
  `qcom,enable_host_slow_suspend`, `qcom,force-suspend`; "fw-managed"
  variants of the dwc3/eUSB2/QMP compatibles
- gunyah vm loader: `qcom,rebootable`

The DT must keep these **Xiaomi** property names that the carried drivers
read. They differ from QCOM/FP6 names:

- eUSB2 repeater: `qcom,param-override-seq-host` (FP6/QCOM uses
  `qcom,host-param-override-seq`).
- QMP USB3 PHY: `usb3,eyegram-tuning`.
- `qcom,pmk8350-pwrkey-bark` / `-resin-bark` pwrkey nodes,
  `xiaomi,mtdoops_pmsg`, `xiaomi,dump_display`, `xiaomi,touch-spi`,
  `xiaomi,wl2866d-pmic`, `mdm,mi_t1_chip`, `fpc,fpc16xx`,
  `goodix,fingerprint`, `awinic,awinic_haptic`, `silicon,sih_haptic_688X`.

Unchanged from the 6.1.68 build: KGSL ignores `qcom,gpu-mempools` (shmem
backend), and WLAN uses icnss2 with qca6750.

## 9. Integration and testing

### Building in a LineageOS tree (integration agent)

The tree uses the LineageOS kernel layout (`10-amethyst-kernel-sources.xml`):
`kernel/xiaomi/sm7635`, `kernel/xiaomi/sm7635-devicetrees` and
`kernel/xiaomi/sm7635-modules`. There is no setup script any more.

1. **Kernel.** Sync `android_kernel_xiaomi_sm7635` at the FP6 branch
   `fp6/seventeen`. It is `seventeen`'s split (a0fe9f763e2c) ported onto
   `integ/fp6-rebase`: the device trees and the amethyst-only drivers live
   in the other two repos, and `arch/arm64/boot/dts/vendor` points at
   `../../../../../sm7635-devicetrees`.
2. **Modules.** Sync `android_kernel_xiaomi_sm7635-modules` at an `fp6`
   branch: `seventeen` plus the four FP6-only commits in
   `~/KERNELNONGKI/work/fp6/modules-fp6-patches/`:
   - `0001` drops the video-driver MIN/MAX fallback.
   - `0002` drops fs19xx's private `MIN()`.
   - `0003` is qcacld's MLO link-switch disconnect source (a real bug fix).
   - `0004` is qcacld's hw-mode count check (needed for clang 20).

   Create the branch with:

       git -C ~/KERNELNONGKI/work/android_kernel_xiaomi_sm7635-modules switch -c fp6 seventeen
       git -C ~/KERNELNONGKI/work/android_kernel_xiaomi_sm7635-modules am ~/KERNELNONGKI/work/fp6/modules-fp6-patches/*.patch

   `0003` and `0004` are also correct on 6.1.68 and could go onto
   `seventeen` itself. `0001` and `0002` must stay off it: 6.1.68 has no
   `MIN`/`MAX` in `<linux/minmax.h>`.
3. **Device trees.** `android_kernel_xiaomi_sm7635-devicetrees` stays on
   `seventeen` with no change. `amethyst-dt.mk` builds from its own
   `include/`, not from the kernel's headers, so the kernel change does not
   affect it.
4. **Before the first build**, remove the 6.1.68 objects:
   `rm -rf out/target/product/amethyst/obj/KERNEL_OBJ out/target/product/amethyst/obj/PACKAGING/depmod_*`.
5. **Device (`configs/kernel/amethyst-kernel.mk`, `BoardConfig.mk`).**
   - Baseline: no change. `TARGET_KERNEL_CONFIG`, the r487747c compiler,
     `modules/modules.list.*` and `amethyst-ext-modules.txt` all stay as
     they are. The four new FP6 modules (at803x, bhs-irq-controller, bwprof,
     qti_thermal_vendor_hooks) are not in any list, so they end up in
     vendor_dlkm without being loaded. system_dlkm is built from this
     kernel (release `6.1.182-g<sha>`), and nothing pins 6.1.68.
   - The comment above `AMETHYST_KERNEL_CLANG_PATH` ("newer clangs reject
     mm/shmem.c and WALT") is true for 6.1.68 only. FP6 builds with
     r487747c and with clang 20.
   - clang 20 needs a device change. Today `AMETHYST_KERNEL_CLANG_PATH` is
     assigned with `:=`, and the file checks for `bin/clang-17`. Make the
     path overridable (`?=`) and check for `bin/clang` instead. Then build
     with
     `AMETHYST_KERNEL_CLANG_PATH=prebuilts/clang/host/linux-x86/clang-r547379`.
     The same clang also preprocesses the DTS (`AMETHYST_DT_CPP`). The DT
     parity check was done with r487747c, so re-run it, or pin
     `AMETHYST_DT_CPP` to r487747c.
6. **Verify before `m bacon`.** Run this in the LOS tree:
   `kernel/xiaomi/sm7635/scripts/amethyst-los-kernel-build.sh <los> config kernel modules ext install preflight`.
   It must end with `0 errors`. For clang 20, also set
   `AMETHYST_KERNEL_CLANG=<los>/prebuilts/clang/host/linux-x86/clang-r547379`
   and `OUT=<los>/out-clang20`.
   `~/KERNELNONGKI/work/fp6/bin/mklos17.sh` builds the same layout in a
   scratch tree, for checks outside the ROM tree.

### Tester procedure (non-destructive first)

1. Keep the current 6.1.68 LineageOS build installed and working, and back
   up `boot`, `vendor_boot`, `dtbo` and `vendor_dlkm`/`system_dlkm`, or
   keep the previous ROM zip at hand.
2. **RAM boot first** (`scripts/amethyst-make-test-boot.sh`):
   `fastboot boot` the FP6 boot image with a matching vendor_boot. This
   only works if the bootloader accepts `fastboot boot`; otherwise flash
   to the inactive slot.
3. **Inactive slot**: sideload the FP6 ROM zip, which installs to the other
   slot. If it does not reach the home screen, `fastboot --set-active=<old
   slot>` (or let A/B rollback trigger after the failed boot count) returns
   to the working build. Recovery path: recovery from the old zip, then
   adb sideload the previous ROM zip.
4. Collect `dmesg`, `/proc/last_kmsg` or pstore, and `logcat -b all` from
   the first boot, plus `lsmod | wc -l` (compare with 6.1.68) and
   `dmesg | grep -iE 'cfi|module verification|Unknown symbol|disagrees'`
   (expected: empty).

Hardware checklist:

- display on both panels (CSOT/TianMa): HBM, DC, AOD, FOD and LHBM
- touch: Goodix and FocalTech panels, game mode, fingerprint (FOD)
- Wi-Fi 2.4/5 GHz (and MLO if the AP supports it), Bluetooth audio, NFC
  and eSE payment applet presence
- speakers (aw882xx and FS1945 units, 96 kHz path), earpiece, mic, headset
  and USB-C audio
- modem: calls, data, SMS, VoLTE; IPA tethering
- cameras: all sensors, flash, OIS, video record; GPU benchmark and video
  playback (KGSL, video, mm-drivers)
- charging: wired PD/fast charge, charge limit, battery stats; USB 2/3
  data, OTG, DisplayPort alt mode
- thermal (mi_thermal_interface sysfs), power-key wake boost
  (`/proc/sys/walt/input_boost/powerkey_*`), haptics
- suspend/resume: 30 min screen-off drain; reboot reasons (normal, reboot
  recovery/bootloader, forced panic `echo c` gives panic code 0x21)
- `dmesg` free of WALT-BUG and watchdog bark messages under load

### Open risks

- None of this has run on a device yet. Everything above is build-time
  evidence: compiles, MODPOST, CRCs, signing and load-list closure.
- WALT carries Xiaomi's sched_opt on top of FP6's newer WALT. It needs
  scheduler testing under load, including the AMETHYST-12603 workaround.
- The Xiaomi `qti_battery_charger` replaces FP6's. FP6's `state_sem` fix in
  that driver is not ported yet.
- KGSL keeps the shmem backend (`qcom,gpu-mempools` ignored), as on 6.1.68.
- WLAN stays on MiCode qcacld to match the stock qca6750 firmware. FP6's
  newer qcacld is a later option.

## 10. Phases 8 and 9 (planned, not started)

FP6 has none of the AmethystGKI items. It uses the upstream LZ4, cubic
congestion control (no BBR), no `-mtune`, no AutoFDO, and `LTO_NONE` in the
make build (Kleaf enables ThinLTO). Candidates, one revertible commit each,
in this order:

1. ThinLTO (`CONFIG_LTO_CLANG_THIN=y`), which matches how QCOM/Google ship
   GKI. Benefit: code size and speed. Measure Image size, boot time and
   Geekbench/PCMark. It needs clang 20 to be stable and a check that
   CFI/modpost still pass.
2. `-mtune=cortex-a720` (clang 18+). Measure the same way; drop it if the
   difference is below noise.
3. LZ4 1.10 + arm64 NEON decompressor (`~/AmethystGKI/repo/patches`).
   Measure zram/erofs decompression throughput. `LZ4_*` prototypes are
   unchanged.
4. BBRv3 as a selectable congestion control, with cubic still the default
   unless benchmarks justify a change. Measure throughput and latency on
   Wi-Fi/LTE.

Rejected: the "lean" hardening-off config, global `-O3`,
KernelSU/SUSFS, and WildKernels scheduler patches (WALT owns placement).

Phase 9 (AutoFDO):

- Backport `CONFIG_AUTOFDO_CLANG`.
- Record a new LineageOS profile on device with simpleperf cycle sampling
  (amethyst has no ETM/SPE), covering boot, app launch, scrolling and
  camera.
- Convert the profile against the exact unstripped `vmlinux`, keeping it
  and its build ID next to `profiles/amethyst-los.afdo`.
- Rebuild, then re-run preflight and benchmarks. `bluedmc.afdo` is not used.
