# FocalTech touch (`focaltech_touch.ko`) on amethyst

Status: **builds, untested**. Nobody has loaded this module on a device.
Source: `sm7635-modules/xiaomi/focaltech_touch/`. Provenance: `ORIGIN` in that
directory.

## 1. Stock module analysis

Reference: `EvolutionX/device/xiaomi/amethyst-kernel/modules/vendor_dlkm/focaltech_touch.ko`
(vermagic 6.1.68, GPL v2, 722 KB, 275 text symbols). The behaviour below
comes from symbols, strings, relocations and disassembly. It is written as
specification, not as decompiled code.

The embedded source path is
`vendor/xiaomi/proprietary/touch/touchfeature_v2/touch_driver/o16u/focaltech_3683/`.
That is Xiaomi's touchfeature_v2 tree for the O16U project (amethyst). The
driver identifies itself as "Focaltech V3.4 20211214" and its HAL driver
version is `FT3683G-2025.02.20-01`.

### Bus, chip, IDs
- SPI only (`__spi_register_driver`, `spi_setup`, `spi_sync`). The driver
  has no I2C path. Probe sets SPI mode 0 and 8 bits per word, and keeps the
  DT clock (`spi-max-frequency` = 15 MHz).
- The OF match is `xiaomi,touch-spi`, with SPI id `focaltech_ts`. Modalias:
  `of:N*T*Cxiaomi,touch-spi[C*]`.
- Controller: **FT3683G**, chip-type entry `{type 0x90, chip id 0x56 0x72,
  bootloader id 0x36 0xB3}`. The application firmware answers 0x56 in
  register 0xA3. The driver also reads 0x9F. If the firmware is invalid it
  reads the boot ID with command 0x55 followed by 0x90.
- The upgrade descriptor (`upgrade_func_ft5008`) is: ctype 0x90, fw version
  at 0x10E, fw cfg at 0x1F80, upgrade spec 1.0, reset-to-boot through
  register 0xFC, no pramboot. The lockdown record is at flash 0x3F000
  (0x20 bytes read, 8 used).
- The factory test is FT5672-family (`test_func_ft5672`: short, open, panel
  differ, noise and CB tests). The test ini files are
  `Conf_MultipleTest_TianMa_00/01.ini`.

### Panel-based selection (coexistence with Goodix)
`module_init` runs before any driver registration. It sets legacy GPIOs 483
and 484 (TLMM 139 and 140, base 344) to input and reads them. The pins are
not requested. Stock logs `gpio_139 = %d, gpio_140 = %d`.
- `[139,140] = [0,1]`: it logs "TP is focaltech, panel is TianMa!" and
  registers the SPI driver.
- Any other value: it logs "panel is not tianma, ic is not focal, return".
  It returns 0 and leaves the module loaded but inert.

Stock `goodix_core.ko` does the inverse ("panel is tianma, ic is focal,
return"). The released Goodix source carries the same check, commented out,
with the legend `[1,0]` = CSOT + Goodix 9916R and `[0,1]` = TianMa + FocalTech
3683. The DT has **one** node, `xiaomi_touch@0` on SPI SE0. Its compatible is
`xiaomi,touch-spi`, and it holds both `goodix,*` and `focaltech,*`
properties. No DT property selects the controller; only the panel-ID GPIOs
do. Stock load order (vendor_dlkm `modules.load`) is `xiaomi_touch`, then
`goodix_core`, then `focaltech_touch`.

### DT properties parsed
`focaltech,display-coords` (4 cells, here 0 0 122000 271200),
`focaltech,have-key` (with `key-number`, `keys`, `key-x/y-coords`; absent on
amethyst), `focaltech,reset-gpio` (GPIO 87), `focaltech,irq-gpio` (GPIO 70),
`focaltech,super-resolution-factors`, `focaltech,max-touch-number` (clamped
to 2..10), `focaltech,touch-def-array` (4), `focaltech,touch-range-array` (5)
and `focaltech,touch-expert-array` (12). A missing array is reported through
MiEvent "TpParamParseFail" (code 2027). The `focaltech,fod-*` and
`mi_tp,*-array` properties in the node are not read by this module.

### Power, GPIO, pinctrl sequence
1. Request the IRQ GPIO (input) and the reset GPIO.
2. Get the `avdd` regulator (2.8 to 3.3 V) and the `iovdd` regulator
   (1.8 V). The voltage is set only when the regulator reports voltages.
3. Look up the pinctrl states: `pmx_ts_active` and `pmx_ts_suspend` are
   required; `pmx_ts_release`, `pmx_ts_spi_mode`, `pmx_ts_dvdd_enable` and
   `pmx_ts_dvdd_disable` are optional. Select active, then spi_mode.
4. Power on: reset low, 1 ms, dvdd pinctrl if present, enable avdd, enable
   iovdd.
5. Wait 1 ms, drive reset high, wait 100 ms, then read the chip ID. On
   failure probe ends with "not focal IC".

Power-off order: write 0x01 to register 0xB6 (host reset flag, which
protects AVDD), wait 20 ms, reset low, 1 ms, avdd off, dvdd pinctrl, iovdd
off. A soft reset (`fts_reset_proc`) is 0xB6 = 1, 20 ms, a reset pulse of
1 ms, then an optional delay.

### IRQ path
The handler is a threaded IRQ, falling edge plus ONESHOT, named
`xiaomi_tpfocaltech_ts`. The first time it runs, it raises its own thread to
SCHED_FIFO. If the system is in PM suspend, it waits up to 700 ms for resume.
It takes a PM QoS request for the duration and kicks the point-report-check
work. Then:
- **THP mode** (raw enabled and not suspended): it reads a 3120-byte frame
  from address 0x01 into the xiaomi_touch raw buffer (`get_raw_data_base`)
  and validates the header CRC and length words. It stamps time, frame
  counter and FOD state, optionally reads the TIC debug block (0x3D), and
  calls `notify_raw_data_update`. The userspace THP HAL computes the
  touches.
- **Otherwise**: it reads the touch buffer and parses either 6-byte (legacy)
  or 8-byte (v2, hi-res) point records. It reports type-B MT slots on its
  own input device. It handles gesture events (double tap gives KEY_WAKEUP,
  single tap and FOD go through `KEY_GOTO`/`update_fod_press_status`) and
  recovers the firmware if the buffer reads all 0xFF.

### Input device
The driver allocates its own device (it does not use
`register_xiaomi_input_dev`). The device is named `focaltech_ts`, bus SPI.
It reports MT slots for max-touch-number contacts, INPUT_MT_DIRECT, X/Y from
display-coords, TOUCH_MAJOR 0..255, WIDTH_MAJOR/MINOR (FOD), KEY_WAKEUP,
KEY_GOTO, KEY_POWER and the KEY_GESTURE_* keys.

### xiaomi_touch integration
After the (stock) firmware-upgrade work finishes, the driver fills
`hardware_param`: 1220 x 2712, RX 17, TX 38, super-resolution 100, frame
pages 2/10, raw pages 5/5. The THP config is `o16u_fts_thp_config_01.ini`
when lockdown bytes 0..1 are 0x71 0x45 ("qE"), and
`o16u_fts_thp_config_00.ini` otherwise. It also fills the lockdown bytes and
firmware version, then `hardware_operation`: self test, data collect,
lockdown, set_mode_value, switch_mode, cmd_update (game mode), enable_raw,
panel vendor/color/display, touch vendor, doze analysis, log level v2,
htc get/set, resume_suspend, charge state, FOD test, thermal temperature and
DFS test. It then calls `register_touch_panel(dev, 0, ...)` and
`xiaomi_register_panel_notifier(dev, 0, PRIMARY, PRIMARY_TOUCH)`, and enables
THP output (register for THP vs TIC mode).

Imported framework symbols: `register_touch_panel`, `unregister_touch_panel`,
`xiaomi_[un]register_panel_notifier`, `driver_get_touch_mode`,
`driver_update_touch_mode`, `add_common_data_to_buf`, `get_raw_data_base`,
`notify_raw_data_update`, `schedule_resume_suspend_work`,
`update_fod_press_status`, `get_xiaomi_touch_class`,
`enable_temperature_detection_func`, `get_bms_temp_common` and
`xiaomi_touch_mievent_report_int/str`.

### Suspend and resume
Display events arrive through xiaomi_touch's panel notifier, then
`ic_resume_suspend`, then `fts_ts_suspend`/`fts_ts_resume`.
- **Suspend**: read the FOD, AOD and double-tap modes. If any is on, enter
  gesture mode (registers 0xD0 and 0xCF); otherwise disable the IRQ and
  write 0xA5 = 3 (sleep). Release all fingers.
- **Resume**: unless a finger is in the FOD area, do a reset (40 ms), wait
  for the chip ID, and restore the charger, gesture, report-rate, game-mode,
  idle-refresh and FOD state. Then re-enable the IRQ.
- System PM ops only set and clear a `pm_suspend` flag. SPI transfers are
  refused while it is set.

### ESD, gestures
ESD check is compiled in but `esd_support` = 0. It can be toggled through
sysfs `fts_esd_mode`. Gesture support defaults off and is switched on at
suspend from the xiaomi_touch modes (double tap 14, AOD 11, FOD 10).

### Char devices, sysfs, debugfs
- procfs: `ftxxxx-debug` (Focaltech APK tool: raw read/write, reset, SPI
  configuration), `fts_ta`, `tp_lockdown_info_v0`, `tp_fw_version_v0`,
  `tp_selftest_v0` and `tp_data_dump_v0`.
- debugfs: `tp_debug/switch_state`.
- sysfs on the SPI device: `fts_fw_version`, `fts_wr_reg`, `fts_upgrade_bin`,
  `fts_force_upgrade`, `fts_driver_info`, `fts_dump_reg`, `fts_hw_reset`,
  `fts_irq`, `fts_boot_mode`, `fts_touch_point`, `fts_log_level`, `fts_pen`,
  `fts_touch_size`, `fts_ta_mode`, `fts_lockdown`, `fts_monitor_mode`,
  `fts_htc_cmd`, `fts_prc`, glove/cover/charger mode, gesture
  mode/buf/bm, `fts_esd_mode` and the test group `fts_test`.
- The driver has no ioctls of its own. The HAL uses xiaomi_touch's device.

### Firmware
At probe, a work item requests `focaltech_ts_fw_tianma_00.bin` or `_01.bin`
(format `%s%s_00.bin`). The inventory shows these as "s_00.bin"/"s_01.bin".
The work compares versions and erases and rewrites the flash when they
differ (ft5008 upgrade). Afterwards it does the xiaomi_touch registration
described above. `fts_upgrade_bin` and `fts_force_upgrade` flash from sysfs.

## 2. Donor selection

| Candidate | Result |
| --- | --- |
| **MiCode `vendor_xiaomi_proprietary_touch-driver`, branch `popsicle-w-oss`, `q200/focaltech_3383`, commit `c286ab85f4982c9b5967e18405f4e2da0332ce4d`** | **Chosen.** Official Xiaomi touchfeature_v2 FocalTech THP SPI driver. Contains 261 of stock's 275 text symbols, with the same file structure (core/spi/ex_fun/ex_mode/gesture/esd/prc/test). It even keeps the amethyst `PANEL_ID_DET (344+139/140)` macros. Missing: the ft5008 upgrade, the ft5672 test, the DFS test and thermal. GPL-2.0 (file headers and MODULE_LICENSE). |
| MiCode `songyuan-w-oss`, `songyuan/focaltech_3685g` (eb2df9b7) | 203 of 275 symbols. Separate SPI-v3 layer, proximity, newer framework ABI. Further from stock. |
| `lolipuru/android_kernel_xiaomi_sm8850-modules`, `focaltech_touch_3683` | Community port of the same popsicle code to an sm8850 FT3683. Includes code "reverse engineered" from another device's stock binary. The repository has no licence file. Not used. |
| Generic Focaltech FT3683G drivers (Motorola, Nothing, Google gs) | Not Xiaomi-THP. Lower priority, not needed. |

No public source exists for `o16u/focaltech_3683` itself. Checked: all
branches of the MiCode touch repository, and GitHub code search for
`upgrade_func_ft5008`, `o16u_fts_thp_config` and
`fts_thp_ic_write_interfaces_reg`.

## 3. The port

Layout: `Kbuild`, `Makefile` (no `KBUILD_EXTRA_SYMBOLS` is needed, because
xiaomi_touch is an in-tree module) and `ORIGIN`. The first commit imports
the donor verbatim. The second commit holds every amethyst change, each
marked `amethyst:` in the source.

### Implemented
- **Binding and selection (P0)**: `xiaomi,touch-spi`. `module_init` reads
  TLMM 139/140 and registers only on `[0,1]`, as stock does. It finds TLMM
  with `gpiochip_find()` by compatible `qcom,volcano-pinctrl`, instead of
  trusting a fixed base of 344. If TLMM is missing it does not register, so
  it fails safe toward Goodix.
- **Chip (P0)**: FT3683G chip-type table, ID 0x56 and boot ID 0x36B3, from
  stock.
- **Power, reset, pinctrl, IRQ (P0)**: donor code, the same sequence as
  stock (section 1).
- **Input (P0)**: own `focaltech_ts` input device. X/Y come from
  `focaltech,display-coords`. MT type B.
- **xiaomi_touch (P1)**: touch id 0, PRIMARY panel notifier, stock
  `hardware_param` values, `o16u_fts_thp_config_00/01.ini` selection, and
  the hardware_operation callbacks the donor provides. The donor's
  `DATA_MODE_<n>`/`IC_MODE_<n>` identifiers are mapped onto the in-tree
  enumerators with the same numeric value (`focaltech_amethyst_compat.h`).
  The compiler flags `TOUCH_FOD_SUPPORT TOUCH_THP_SUPPORT` match the
  in-tree framework, which keeps `hardware_operation_t`'s layout the same.
- **Suspend/resume, gestures (double tap, single tap, FOD), report rate,
  game mode, charger mode (P1)**: donor code.
- **ESD (P1)**: compiled in and off by default, as stock.
- **Lockdown read**: read-only flash read at 0x3F000 in bootloader mode
  (`focaltech_flash_ro.c`). It sends only 0xFC=AA/55, 0x55, 0x90, 0xAC,
  0x03 and 0x07. The IRQ is disabled around it.

### Flash writing: disabled
- `focaltech_flash.c` and the IC upgrade file are not built. No erase,
  flash-mode, write or ECC command exists in the binary, and the module
  does not import `request_firmware`.
- `fts_upgrade_bin()` (sysfs `fts_upgrade_bin`/`fts_force_upgrade`) returns
  `-EPERM`.
- Raw userspace writes are filtered by `fts_user_write_allowed()`. This
  covers `ftxxxx-debug` WRITE_REGISTER/WRITE_DATA/WRITE_DATA_DIRECT, sysfs
  `fts_wr_reg` and `fts_htc_cmd`, and the HAL's IC_MODE_44 path. The filter
  refuses a first byte of 0xFC, 0xBC, 0x55 or 0xAA, which are the only ways
  into the bootloader, where flash commands are accepted.
- The controller therefore runs whatever firmware is already in its flash,
  which is stock's latest. If that firmware is invalid, probe fails and does
  not attempt recovery.

### Returns an error (documented, no fake success)
| Function | Behaviour | Reason |
| --- | --- | --- |
| `fts_ic_self_test` (xiaomi_touch self test) | result 0 ("invalid"), `-EOPNOTSUPP` | FT3683G (FT5672) test not ported; the donor's FT3383 test targets the wrong IC |
| `ic_data_collect` | NULL (framework skips it) | lives in the test library |
| `fts_enter_test_environment` | `-EOPNOTSUPP` | it was an empty stub in the donor |
| `update_weak_doubletap_value` | `-EOPNOTSUPP` | the in-tree framework has no such export; mode 44 reads -1, so sensor tap stays off |
| `fts_upgrade_bin` | `-EPERM` | flash writing disabled |

### Not implemented or unknown
- Stock `set_thermal_temp`, `touch_dfs_test`, `enable_temperature_detection_func`
  and `get_bms_temp_common` (thermal-adaptive firmware parameters): the
  donor has no code for them.
- MiEvent reporting: `CONFIG_MIEV` is off in this kernel, and the in-tree
  xiaomi_touch omits those exports.
- Whether stock's HTC get/set (`htc_ic_get/setModeValue`) does more than the
  donor's, which returns 0 and never sets `htc_ic_mode`, so the IC_MODE_44
  "open data" path is dead.
- Whether the THP HAL for amethyst (vendor `o16u_fts_thp_config_*.ini`
  consumer) works with the in-tree xiaomi_touch build.

### Known donor weaknesses kept as is
- A failure after the procfs/sysfs nodes are created (for example IRQ
  request) does not remove them.
- `fts_parse_dt` failure and workqueue-allocation failure are only logged.

## 4. Build status
`modcheck.sh sm7635-modules/xiaomi/focaltech_touch` builds clean: no warnings,
and modpost resolves every symbol against `out-amethyst-kernel/KERNEL_OBJ`.

The result `focaltech_touch.ko` has name `focaltech_touch`, depends on
`xiaomi_touch`, and has alias `of:N*T*Cxiaomi,touch-spi[C*]`. Its
description and licence match stock (`GPL v2`).

Import difference against stock:
- **Stock only**: `request_firmware`/`release_firmware`/`vmalloc`/`vfree`
  (upgrade), the seq_file functions (test data dump), thermal and MiEvent
  symbols, and `cpu_latency_qos_*`.
- **Ours only**: `gpiochip_find`, `of_device_is_compatible`,
  `dev_pm_qos_*`, `device_wakeup_enable`, `strscpy` and
  `of_property_read_string`.
- No exports, the same as stock.

## 5. Integration requests

1. **`scripts/amethyst-ext-modules.txt`**: add `xiaomi/focaltech_touch`
   under "Users". The same entry goes into `TARGET_KERNEL_EXT_MODULES` in
   `device/xiaomi/amethyst/BoardConfig.mk`. The modules repository already
   carries it under `xiaomi/`.
2. **vendor_dlkm load list**: place `focaltech_touch.ko` right after
   `goodix_core.ko`, as stock does (`xiaomi_touch`, `goodix_core`,
   `focaltech_touch`; all after `panel_event_notifier`). Do not put it in
   vendor_boot.
3. **Goodix must gate itself too (required before shipping both)**: the
   in-tree `goodix_ts_core_init()` has stock's panel-ID check commented out.
   On a TianMa phone goodix_core would therefore register first on the
   shared `xiaomi,touch-spi` device, and `focaltech_touch` could never bind.
   Re-enable the check with the inverse condition (skip registration when
   `[139,140] == [0,1]`), preferably using the same TLMM lookup. On CSOT
   phones (the main panel) this port never registers, so Goodix behaviour is
   unchanged.
4. **First boot**: `scripts/amethyst-filter-firstboot-modules.sh` already
   excludes `focaltech_touch`. Keep it excluded until request 3 is done and
   a TianMa unit has been tested.
5. **DT**: no change needed. The stock overlay already carries every
   `focaltech,*` property, `avdd-supply`/`iovdd-supply`, and the pinctrl
   states `pmx_ts_active`/`pmx_ts_suspend`. Do not add a separate FocalTech
   node, because both drivers must share the one SPI device.
6. **Vendor files**: the HAL needs `o16u_fts_thp_config_00/01.ini` (and
   `Conf_MultipleTest_TianMa_*.ini` only if the self test is ported later).
   The module itself loads no firmware.

## 6. Open questions for a physical device
- Which panel does the test phone have? Read TLMM 139/140 (stock logs
  `gpio_139 = , gpio_140 =`). Every unit inspected so far is CSOT/Goodix.
- Does `gpiochip_find` match TLMM, and is its base 344? Is reading the pins
  without requesting them still accepted?
- On a TianMa unit: chip ID 0x5672, boot ID 0x36B3, and the lockdown bytes
  that select `_00` vs `_01`.
- Does the lockdown read (bootloader entry, then reset) return the
  application firmware to a valid state without a further reset?
- Does THP mode work end to end with the in-tree xiaomi_touch and the
  vendor HAL? Does legacy (non-THP) reporting work when the HAL is absent?
- Suspend/resume with FOD and double tap, the AOD single tap, and the
  report-rate switch (0x92).
- Thermal behaviour without stock's temperature hooks.
