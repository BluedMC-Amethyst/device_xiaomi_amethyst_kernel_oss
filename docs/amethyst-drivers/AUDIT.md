# Amethyst source-built module audit

This audit compares the vendor modules that build from source against Xiaomi's
stock OS3.0.306.0 binaries. It looks for functionality that the source build
lost without any error. Its starting point is the "Interface differences in
source-built modules" table in [INVENTORY.md](INVENTORY.md). It goes beyond
that table: the defined-symbol sets of every built module were diffed against
stock, and so were the strings, firmware names, and ioctl constants of the
subsystems listed in the task.

The inputs were:

- the stock modules in `EvolutionX/device/xiaomi/amethyst-kernel/modules`;
- the stock DTB and DTBO in `LineageOS/device/xiaomi/amethyst-kernel/images`;
- the build in `LineageOS/out-amethyst-kernel` (kernel and external modules);
- the device tree and vendor blobs in `LineageOS/device/xiaomi/amethyst` and
  `vendor/xiaomi/amethyst`.

## Summary by user impact

1. **Wi-Fi cannot be started by the HAL (patch proposed).** In the
   Kbuild/make build of qcacld-3.0, `WLAN_CTRL_NAME` is never set, so
   `/dev/wlan` is not created. The `volcano_gki_qca6750` profile only sets
   `CONFIG_WLAN_CTRL_NAME="wlan"`, and only Xiaomi's Bazel/DDK build maps it,
   through `configs/config_to_feature.h`. BoardConfig sets
   `WIFI_DRIVER_STATE_CTRL_PARAM := "/dev/wlan"`, and libwifi-hal's
   `wifi_load_driver()` fails when it cannot write `ON` there. The same gap
   drops `MULTI_IF_NAME` (stock uses `qca6750`), which changes the procfs,
   debugfs and sysfs names (`cldqca6750`, `/sys/kernel/qca6750`, `boot_qca6750`).
   It also drops `ENABLE_CE4_COMP_DISABLE_HTT_HTC_MISC_LIST` and
   `WLAN_OPEN_SOURCE`.
2. **Goodix touch: wrong firmware and THP config on the second panel source
   (fixed).** The port reported `warsaw_gtp_thp_config.ini` to the touch HAL
   and always loaded the primary CSOT firmware. Stock detects the "hill"
   panel (`qcom,mdss_dsi_o16u_42_02_0a_hill_dsc_vid`) and switches to
   `goodix_sec_firmware_csot`, `goodix_sec_cfg_group_csot`,
   `goodix_sec_test_limits` and `o16u_goodix_thp_config_01.ini`. The port also
   asked for `goodix_test_limits_aftersale_*.csv`, which is not shipped. With
   the primary firmware, a hill-panel phone's touch IC could be flashed with
   the wrong image.
3. **Power-key wake boost missing (fixed).** The device's
   `init.kernel.post_boot-volcano_default_4_3_1.sh` writes
   `/proc/sys/walt/input_boost/powerkey_input_boost_{freq,ms}`. Those sysctls
   exist only in Xiaomi's sched-walt. Every other `/proc/sys/walt` path the
   script writes now exists.
4. **GPU memory backend differs (needs device test).** The FP6 KGSL builds
   with `CONFIG_QCOM_KGSL_USE_SHMEM` plus process reclaim, through
   `config/gki_pineapple.conf`. Stock uses KGSL page pools, configured by the
   DT node `qcom,gpu-mempools` that our KGSL ignores. Both are valid upstream
   modes, so check for GPU performance or jank regressions.
5. **Xiaomi-only features with no source or a missing dependency (ignore).**
   These are MiEV telemetry (`cdev_tevent_*`, stubbed in
   `include/miev/mievent.h`), the metis, mist, migt and mi_schedule
   scheduler/DDR tuners, and the mi_ufs core with UFS host-initiated defrag.
   They also include the camera dma-heap reserve pool, the display
   hwmonitor/disp_count, the fastrpc dspmonitor, the zram "mfz" extensions,
   and battery-health sysfs attributes. None of these are needed by AOSP or
   LineageOS userspace.

## Module table

| Module | Difference vs stock | Cause | User-visible impact | Action |
| --- | --- | --- | --- | --- |
| qca_cld3_qca6750 | no `wlan_hdd_state_ctrl_*` / `/dev/wlan`; no `MULTI_IF_NAME`; HTT misc list on | Kbuild tests `WLAN_CTRL_NAME`, `MULTI_IF_NAME`, `ENABLE_CE4_...`, `WLAN_OPEN_SOURCE`; profile sets only the `CONFIG_` forms (DDK maps them) | Wi-Fi HAL cannot load or start the driver; driver node names differ from stock | patch proposed (`wlan/0002`) |
| qca_cld3_qca6750 | `wlan_objmgr_*` exports become `*_debug`; `wlan_print_*_info` | profile has `CONFIG_WLAN_OBJMGR_DEBUG`/`REF_ID_TRACE`; stock build had them off | none (debug refcount tracing, small CPU and memory cost) | ignore |
| qca_cld3_qca6750 | no WEXT (`iw_*`, `hdd_we_*`, hostapd private ioctls, Hastings BT WAR, btcoex/NSS via iwpriv) | volcano profile lacks `CONFIG_WLAN_WEXT_SUPPORT_ENABLE`; stock built it | `iwpriv` only; HAL uses nl80211 | ignore (can enable later; kernel has `WEXT_PRIV`) |
| qca_cld3_qca6750 | no `p2phc`/`dlhc` (P2P header compression), no `rx_inet_hook`, no `nf_register_net_hooks` import | Xiaomi code (and `minet/mixdp`) not in MiCode source | Xiaomi P2P/MiShare tuning | ignore |
| qca_cld3_qca6750 | firmware and ini paths | same (`qca6750/*.bin`, `wlan/qca_cld/qca6750/WCNSS_qcom_cfg.ini`) | none | ok |
| goodix_core | thp config `warsaw_gtp_thp_config.ini`; no sec-panel firmware; limit CSV `_aftersale` | port from another project | wrong THP config for HAL; wrong firmware on hill panel; self-test fails | **fixed** |
| goodix_core | `goodix_htc_set_game_mode`, `goodix_send_camera_report_rate` commented out | port (stock is o16u goodix_9916k) | game-mode tuning and camera report rate not applied | needs device test |
| goodix_core | `xiaomi_touch_mievent_report_*` imports | MiEV | none | ignore |
| sched-walt | power-key boost sysctls missing | Xiaomi addition | slower screen wake; post_boot writes fail | **fixed** |
| sched-walt | 20 exports (`find_target_boost`, `cluster_head`, `walt_rq`, oem hooks...), volkey and double-click boost, metis hooks | used only by `migt`/`metis`/`mi_schedule` (missing) | none without those modules | ignore |
| memlat | param `dflt_debug`, `mi_dflt_*` hooks | Xiaomi DFLT (needs `mist`) | none | ignore |
| bwmon | `mi_dflt_*` imports | `mist` | none | ignore |
| qcom-dcvs | `boost_dcvs_freq`, `get_ddr_freq` | used by `mist` only | none | ignore |
| clk-qcom | `clk_debug_mc_cc_get`, `clk_debug_suspend_atomic_enable`, `clk_mc_cc_debug_register`, `clock_debug_print_enabled_clocks` exports | used by `mist`, `migt`, `mi_power`, `debugcc-pineapple` (not volcano) | none | ignore |
| qcom_stats, qcom-spmi-pmic | `register_mi_*`, `mi_power_regmap_register` imports | `mi_power` missing | none | ignore |
| ufs_qcom | `mi_*`, `ufshid_*`, `get_ufs_data` exports; 178 extra imports | stock embeds Xiaomi's `mi_ufs` ufshcd fork (HID defrag, YMTC CLD, FFU); ours uses GKI ufshcd | no host-initiated defrag, so possible long-term storage slowdown | ignore (no source) |
| phy-qcom-ufs | `of_obtain_ebuffphyha_info` | `/memory/ebuff` PHY override, used only by the pineapple PHY; amethyst uses `qcom,ufs-phy-qmp-v4-crow` | none | ignore |
| msm_drm | `hw_monitor`/`hw_component_info` exports, `disp_count`, `mi_kernel_recoder_*`, `metis_set_common_persist_vip` | not in MiCode display source; Xiaomi telemetry; metis | `MI_DISP_IOCTL_SET_COUNT_INFO` unsupported (stats only); no HBM/AOD/DC/FOD code missing | ignore |
| msm_drm | panels, compatibles | same DT compatibles; all six o16u panel nodes handled by DT | none | needs device test (both panels) |
| msm_kgsl | `mi_soc_gov_update_gpufreq`, `perfmgr_gpu_status`, metis/mist imports | Xiaomi GPU governor, mist | none | ignore |
| msm_kgsl | page pools vs shmem; DT `qcom,gpu-mempools` ignored | FP6 graphics-kernel, pineapple GKI config (`CONFIG_SHMEM` selects shmem) | different GPU allocation and reclaim behaviour | needs device test |
| frpc-adsprpc | `dspmonitor_*` (char device and exports), `fastrpc_handle_ssr_request` | Xiaomi CDSP monitor; FP6 dsp-kernel | none (no importer) | ignore |
| msm_video | none missing; FP6 adds `volcano_data_v2` | FP6 video-driver (newer) | none; same `qcom,volcano-vidc` and `vpu20_2v` firmware | ok |
| video (FP6) | second module binding `qcom,volcano-vidc` | FP6 builds both `msm_video` and `video` | none while only `msm_video` is in the load list | ignore |
| btpower | none missing; same ioctls (0xbfad/e1/e4/e5) | FP6 bt-kernel (superset) | none | ok |
| bt_fm_slim | MiEV imports | MiEV | none | ignore |
| bluetooth, rfcomm, btqca, usb-net, can, cdc-acm, ftdi_sio, r8152 | newer exports, USB IDs | system_dlkm built from ACK 6.1.68; stock is GKI 6.1.138 | a few USB adapters not auto-bound | ignore |
| camera | param `mipi_error_flag` became `ife_mipi_error_flag`; adds `ife_crc_error_cnt`, `trigger_backupeq`, p16u CSIPHY tables | newer MiCode camera-kernel | none (no vendor blob references the param) | ignore |
| camera | sensors, actuator, OIS, flash, EEPROM | identical compatible set; no component compiled out | none | needs device test |
| qcom_dma_heaps | camera reserve pool (`reserve_pool`, `config`/`pid`/`scene` sysfs) | Xiaomi addition, not in tree | possibly slower camera start | ignore |
| zram | `mfz` and idle-stat extensions | Xiaomi addition | none | ignore |
| qti_battery_charger | `batt_sn`, `batt_sox`, `qmax`, `isc`, life stats, `xmfg_fw_*`, second-panel notifier | in-tree source is from another project; Xiaomi health attributes absent | none for LineageOS (`charge_control_en`, `input_suspend`, `fastchg_mode` are present) | ignore |
| machine, mbhc, audpkt_ion, wcd_usbss_i2c | MiEV imports; `wcd_usbss_switch_update` vs pinctrl path | MiEV; newer audio-kernel | none seen; DSP routing (dai links) identical | needs device test (headset) |
| aw8697-haptic, si_haptic, qcom-hv-haptics | MiEV imports; `xm_hap_exception_*` | MiEV | none | ignore |
| xiaomi_touch | `tp_current_log_level`, mievent exports | renamed in port; MiEV | none | ignore |
| hwid | `/sys/hwid` kept (stock deletes its kobject) | reconstructed driver | none; `project` param is 12 (O16U) | ok |
| tz_log, qcrypto, debug_symbol, charger_partition, mac802154, slcan, stm_* | small import differences | compiler or ACK differences | none | ignore |
| aw882xx, tfa986x | smart-PA | owned by another workstream | - | skipped |

## Device-tree coverage

All 343 compatibles in the three stock DTBs and both DTBO entries were
checked; 331 of them are on nodes with `status = "okay"`. The DTBO is a
`0xd7b7ab1e` container, so it was split first. Each compatible was then
matched against:

- `of:` aliases in every built `.ko`;
- strings in built `.ko` files, since many Qualcomm drivers lack
  `MODULE_DEVICE_TABLE`;
- strings in our `vmlinux`.

The same checks were run on stock to separate regressions from nodes that
nothing binds even on stock.

- Every compatible that stock binds through a module alias is bound by a
  module in our load lists. No built module that stock loads outside recovery
  is missing from our `modules.list.*`.
- `xiaomi,touch-spi` is claimed by `focaltech_touch` on stock and by our
  `goodix_core`. This is intended: the FocalTech source is missing, and
  amethyst ships CSOT with Goodix.

Compatibles bound by nothing in our build:

| Compatible | Status | Stock | Note |
| --- | --- | --- | --- |
| `qcom,gpu-mempools` | okay | read by stock `msm_kgsl` | ignored by FP6 KGSL in shmem mode (see table) |
| `qcom,qpnp-vibrator-ldo` (pm7550ba `vibrator@df00`) | okay | not bound | haptics are aw8697 or si_haptic |
| `focaltech,fts_ts` (i2c `focaltech@38`) | okay | not bound | stock FocalTech uses SPI `xiaomi,touch-spi` |
| `slim217,221` (btfmslim) | okay | not bound by alias | `bt_fm_slim` matches by slimbus id |
| `qcom,coresight-tpda`, `arm,coresight-cti`, `arm,coresight-dynamic-funnel`, `arm,embedded-trace-extension` | okay | not bound | CoreSight tracing only |
| `qcom,gh-dbl`, `qcom,gh-msgq-test`, `qcom,gh-qtmr`, `qcom,tlmm-vm-test` | okay | not bound | Gunyah test nodes |
| `qcom,limits-stat` | okay | not bound | `limits_stat` is blocklisted |
| `qcom,ipcc-self-ping` | okay | not bound | debug |
| `qcom,gpu-pwrlevels-bins`, `qcom,msm-imem`, `qcom,pil-tz-generic` (disabled), `qcom,volcano-pdc` (falls back to `qcom,pdc`) | - | not bound | parsed by their parent or fallback |
| `qcom,kryo`, `arm,arch-cache`, `qcom,volcano*`, `qcom,mtp` | - | - | machine or CPU nodes |

## Fixes in this branch

- `input: goodix_berlin: select amethyst firmware by panel source`:
  - The driver matches the active panel through the touch node's `panel`
    phandles. If msm_drm has not registered a panel yet, it falls back to
    `msm_drm.dsi_display0=` in `/chosen/bootargs`. Stock instead polls for up
    to 10 s in probe, but msm_drm loads after goodix_core in both load lists.
  - It selects the sec firmware, config and limits plus THP config 01 for the
    hill panel, and THP config 00 otherwise.
  - The panel match now runs before the IC version read, so the firmware name
    is also set on the forced-upgrade path.
  - It uses the stock test-limit names.
  - Compile-checked as an external module.
- `sched/walt: add the power key input boost amethyst's post_boot sets`:
  - Adds the two sysctls.
  - On a `KEY_POWER` press it boosts with them, and a following touch boost
    cannot cut it short.
  - Compile-checked.
- No config-fragment change was needed. Every gap found is in source or in
  an external Kbuild, so the GKI KMI and CRCs are untouched.

## Patches proposed for synced projects

- `scripts/amethyst-patches/los/kernel/xiaomi/sm7635-modules/qcom/opensource/wlan/0002-qcacld-map-profile-strings-for-the-make-build.patch`
  maps `CONFIG_WLAN_CTRL_NAME`, `CONFIG_MULTI_IF_NAME`,
  `CONFIG_ENABLE_CE4_COMP_DISABLE_HTT_HTC_MISC_LIST` and
  `CONFIG_WLAN_OPEN_SOURCE` to the variables that the qcacld Kbuild tests.
  It applies with `git apply --check` after `0001`. Compiled in scratch: the
  linked object now contains `wlan_hdd_state_ctrl_param_create` and the
  `cldqca6750` name, and `htt_htc_misc_pkt_list_add` is gone, as in stock.
  modpost failed only because of the scratch directory layout. The FP6 qcacld Kbuild
  already uses `$(CONFIG_WLAN_CTRL_NAME)` for the same purpose.
  `PANIC_ON_BUG` and `WLAN_WARN_ON_ASSERT` are left off on purpose: stock
  panics on `QDF_BUG`.

## Needs a physical device

- Wi-Fi after patch 0002:
  - `/dev/wlan` exists and is owned by `wifi` (ueventd already has the rule);
  - toggling Wi-Fi works, hotspot works, SSR recovery works
    (`echo` to `/sys/kernel/qca6750/...` or a forced firmware crash);
  - regulatory and country code are correct, and power save works.
- Goodix touch on both panel sources:
  - the dmesg line `drm_panel name:` or `panel from bootargs:` appears;
  - the firmware update uses the sec images on a hill panel;
  - the touch HAL loads `o16u_goodix_thp_config_0{0,1}.ini`;
  - FOD, double-tap and wake gestures work, and suspend/resume works;
  - the self-test finds `goodix_{,sec_}test_limits_255.csv`.
- WALT: after boot, `powerkey_input_boost_freq` reads `1804800 0 0 0 2400000 0 0 0`.
- Display: both panel variants, HBM/LHBM for FOD, AOD/doze brightness, and
  every refresh rate.
- Camera: every sensor, OIS, flash, and EEPROM calibration.
- GPU: performance and memory behaviour with shmem KGSL versus stock pools.
- Audio: headset detection and USB-C audio, because `wcd_usbss` takes a
  different path from stock.
- Bluetooth: firmware download, coexistence with Wi-Fi, and suspend.

## Integration requests

- Rebuild the qcacld external module after patch 0002 is applied (the setup
  script applies it). The module list and BoardConfig need no change.
- Optional: for `iwpriv` parity with stock, add
  `CONFIG_WLAN_WEXT_SUPPORT_ENABLE=y` to the qcacld build. This needs a
  qcacld patch or a `WLAN_CFG_OVERRIDE` in the module Makefile.
- Optional: decide between KGSL shmem (FP6 default) and pools (stock). Pools
  need `CONFIG_QCOM_KGSL_USE_SHMEM` cleared in a graphics-kernel patch.
- FP6's `video-driver/video/video.ko` also binds `qcom,volcano-vidc`. Keep it
  out of the load lists, or stop installing it.
- This branch was cut before the `sched_param` commit on `los24-baseline`.
  It touches different files.

## Method notes

The scratch scripts used for this audit are not committed:

- `fdtcompat.py` walks the FDT for compatibles and status;
- `dtcov.py` matches compatibles against aliases and strings;
- `allsym.py` diffs normalized defined symbols for all built modules against
  stock;
- `wlan_cfgcheck.py` cross-checks the qcacld profile, `config_to_feature.h`
  and Kbuild.

Re-derive the results with `llvm-nm`, `strings` and `dtc` when the stock
images change.
