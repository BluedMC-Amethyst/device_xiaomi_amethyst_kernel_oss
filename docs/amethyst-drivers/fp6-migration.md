# Migrating amethyst to the FP6 SM7635 kernel (6.1.68 to 6.1.182)

Branch `integ/fp6-rebase`. FP6's history is kept unchanged, and the amethyst
work sits on top as logical commits. This document was written before the
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
| techpack/amethyst: aw882xx(+fs19xx), st-nfc, st-ese, focaltech_touch, miev, swinfo, mi_thermal_interface | this tree | **Keep** |
| touch-drivers, nxp nfc, samsung nfc, FP6 wlan variants | FP6 | Not used (FP6 hardware) |

Local patches in `scripts/amethyst-patches/los/`:

| Patch | On FP6 base |
| --- | --- |
| amethyst-qcom-modules/0001 bt-kernel local scope | **Still needed** with r487747c (clang 17 rejects a declaration right after a `case` label). Harmless with newer clang |
| amethyst-qcom-modules/0002 video MIN/MAX | **Dropped.** FP6 6.1.182 `linux/minmax.h` defines `MIN`/`MAX`, which is what FP6's video driver expects. The fallback could also clash as a redefinition |
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
5. techpack/amethyst modules, scripts, docs and config fragments.

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

(filled in as phases complete)

## 8. DT binding changes for the DT agent

(filled in after the build and binding comparison)

## 9. Integration and testing

(filled in after the baseline builds)
