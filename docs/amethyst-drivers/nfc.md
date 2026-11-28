# ST NFC (`stm_nfc_i2c`) and ST54 eSE GPIO (`stm_st54se_gpio`): stock vs source

Status: **builds, untested** (nothing has been run on hardware).

This document compares the stock Xiaomi modules for amethyst (Redmi Note 14
Pro+ 5G, SM7635 "volcano", 6.1.68 GKI) with the source-built ones in
`sm7635-modules/xiaomi/st-nfc` and `sm7635-modules/xiaomi/st-ese`. It then
describes what was changed to close the gap. The descriptions are
behavioural specifications, written from strings, relocations, symbol
tables and disassembly of the stock `.ko` files. No decompiled code is
reproduced here or in the tree.

## Inputs

| Item | Location / reference |
| --- | --- |
| Stock modules (read-only) | `~/AndroidBuilds/EvolutionX/device/xiaomi/amethyst-kernel/modules/vendor_dlkm/{stm_nfc_i2c,stm_st54se_gpio}.ko` |
| Stock DTBO | `~/AndroidBuilds/LineageOS/device/xiaomi/amethyst-kernel/images/dtbo.img` (2 entries, both carry the same NFC/eSE nodes) |
| Stock userspace | `vendor/xiaomi/amethyst/proprietary`: `odm/bin/hw/android.hardware.nfc-service-st`, `odm/lib64/nfc_nci.st21nfc.st.so`, `vendor/lib64/hw/libEseUtils.so`, `vendor/lib64/libstnfc-streset.so`, `vendor/lib64/libstnfc-auth.so` |
| Source base (NFC) | STMicroelectronics/ST54-android-kernel-nfc-i2c `st_dev_kernel_5.15` @ 24ee578 (driver 2.2.0.19) |
| Source base (eSE) | STMicroelectronics/ST54-android-kernel-se-gpio `st_dev_kernel_5.10` @ f6722b6 |
| NFC donor (chosen) | Xiaomi `sm6225-dev/kernel_xiaomi_sm6225-modules` branch `16`, `st/opensource/driver` (QTI tree, 2.2.0.19), subtree commit 8f94cf63 |
| Secure-zone reference | Xiaomi `xiaomi-8550-kernel/android_kernel_xiaomi_sm8550-modules` branch `uvite`, `st/opensource/driver` (2.2.0.15, smcinvoke built in), commit 0cce8308 |
| st54spi callback consumer | ST `st54spi.c` SPI driver, e.g. NothingOSS `android_kernel_msm-6.1_nothing_sm7635` `drivers/misc/st54spi.c` |

The stock NFC module embeds the path `../../vendor/st/opensource/driver/nfc/st21nfc.c`,
version `2.2.0.19` and scmversion `g70a53a637150`. That matches QTI's
`vendor/st/opensource/driver` project, which Xiaomi ships in its
`*-modules` trees. Several Xiaomi, OnePlus and Motorola trees carry the
same 2.2.0.19 QTI file. The Xiaomi sm6225 copy was chosen because it is a
Xiaomi tree and its active code matches the stock binary. Its build
switches are `NFC_SECURE_PERIPHERAL_ENABLED` (only for `sun`/`canoe`
targets) and `CONFIG_NFC_BOB1` (`malabar`/`canoe`/`chora`). The stock
amethyst binary was built with neither.

No newer ST release with these features is public:
`ST54-android-kernel` and `ST54-android-kernel-se-spi` contain only a
README. Google's `google-modules/nfc` ST drivers don't have the QTI
secure-zone or MPM code.

## Device tree (stock DTBO)

`qupv3_se1_i2c` (fragment@33), `qcom,clk-freq-out = <1000000>`:

| Property | Value | Used by stock | Used by ST base |
| --- | --- | --- | --- |
| `compatible` | `st,st21nfc` | yes | yes |
| `reg` | `0x08` | I2C address | same |
| `irq-gpios` | `<&tlmm 31 0>` | input, IRQ source (`gpiod_to_irq`) | same |
| `reset-gpios` | `<&tlmm 7 0>` | output, driven high at probe | same |
| `clkreq-gpios` | `<&tlmm 6 0>` | input; **cell 1 (=6) passed to `msm_gpio_mpm_wake_set(6, true)`** | input only (no MPM) |
| `interrupts`, `interrupt-names = "nfc_irq"` | `<31 0>` | not read (IRQ comes from irq-gpios) | same |
| `pinctrl-names = "nfc_active","nfc_suspend"` | | **not applied** by either driver (no `default` state, no pinctrl lookups) | same |
| `pidle-gpios`, `st,pidle_active_low`, `st,clk_pinctrl`, `i2c-retry` | absent | optional, parsed | same |
| clocks (`nfc_ref_clk`) | absent | never requested | requested via `clk_get()` only when clkreq-gpios is missing |

`soc` (fragment@32): `st54spi_gpio { compatible = "st,st54spi_gpio"; gpio-power_nreset = <&tlmm 14 0>; }`.

There is no SPI `st,st54spi` node in the DTBO or the base DTBs, so no
kernel SPI eSE driver is bound on amethyst.

## `stm_nfc_i2c` behavioural specification

### Identity
- Module `stm_nfc_i2c`, description "NFC ST21NFC driver", version 2.2.0.19,
  licence GPL. Aliases `of:N*T*Cst,st21nfc[C*]`. `depends=pinctrl-msm`
  (from `msm_gpio_mpm_wake_set`). The I2C id table is `st21nfc`. Probe
  type is asynchronous.
- Character device: misc device `/dev/st21nfc` (dynamic minor). One open
  at a time; a second `open()` returns `-EBUSY`.
- sysfs, on the I2C client device: `i2c_addr` (rw; reads `0x%.2x`, writes a
  decimal address), `version` (ro, `2.2.0.19`), and `power_stats` (ro;
  idle/active/active-RW counters, only meaningful with `pidle-gpios`).
  The stock and source builds are identical here.
- Exports: none. `st21nfc_register_st54spi_cb()` and
  `st21nfc_unregister_st54spi_cb()` are global symbols, but they aren't
  `EXPORT_SYMBOL`ed in either build (see below).

### Probe
1. Requires `I2C_FUNC_I2C`. Allocates the device state.
2. `irq-gpios` is required (input). `reset-gpios` is required and driven
   high. A missing reset GPIO fails probe with `-ENODEV`.
3. Stock (QTI): `secure_zone` is set to false and logged
   (`st21nfc_dev->secure_zone = false`). There is no QTEE query (no
   smcinvoke imports).
4. Optional `pidle-gpios`: power-statistics IRQ on both edges, plus a
   workqueue `st_pstate_work`.
5. `clkreq-gpios`:
   - present: stock reads the GPIO number (cell index 1) and calls
     `msm_gpio_mpm_wake_set(gpio, true)`. A failure to read or set it
     **fails probe**. Then `st,clk_pinctrl` is parsed.
   - absent: stock logs `CLK_REQ not present`. The ST base instead
     enables `clk_get("nfc_ref_clk")` voting on SET_POLARITY_HIGH.
6. IRQ number comes from `gpiod_to_irq(irq-gpio)`. The adapter retry
   count comes from `i2c-retry` (default 0).
7. The misc device, sysfs group and wakeup source `st21nfc` are created,
   and stock logs `probing nfc i2c success`.
8. The IRQ is not requested at probe. It is requested by the first
   SET_POLARITY ioctl.

### read / write / poll / release
- `read`: at most 260 bytes. If the IRQ line is low, the buffer is filled
  with `0x7E` (idle) and the requested count is returned without I2C
  traffic. Otherwise it does one `i2c_master_recv()` under `read_mutex`.
  The `ST54J_PWRSTATS` filtering is compiled out in both builds.
  Instruction streams are identical.
- `write`: at most 260 bytes, `memdup_user` then `i2c_master_send`.
  Returns `-EIO` on a short send.
- `poll`: reports `POLLIN|POLLRDNORM` if the IRQ line is high, otherwise
  re-enables the IRQ (under `irq_dir_mutex`).
- IRQ handler: holds the wakeup source for 500 ms, disables the IRQ
  (one-shot until the next poll) and wakes readers.
- `release`: disables and frees the IRQ and clears the open flag.
- PM: suspend arms `enable_irq_wake` if the IRQ is enabled and samples
  pidle. Resume undoes it and requeues the pidle work if the state
  changed. Identical in both builds.

### ioctls (magic `0xEA`)

| Cmd | Number | Arg | Stock | ST base | Now |
| --- | --- | --- | --- | --- | --- |
| GET_WAKEUP | `_IO 0x01` / legacy `_IOR 0x01` | none | returns IRQ level 0/1 | same | same |
| PULSE_RESET | `0x02` / legacy | none | reset low 20 ms, high 10–11 ms, low 20 ms, high; st54spi cb RESET_START/END around it; reset writes skipped if `secure_zone` | same, no secure_zone gating | same as stock |
| SET_POLARITY_RISING | `0x03` / legacy | none | (re)request IRQ, edge rising | same | same |
| SET_POLARITY_HIGH | `0x05` / legacy | none | (re)request IRQ, level high, **no clock vote** | votes `nfc_ref_clk` if no clkreq | same as stock |
| GET_POLARITY | `0x07` / legacy | none | returns polarity mode | same | same |
| RECOVERY | `0x08` / legacy | none | frees IRQ, reset low, IRQ pin driven as output high, reset high, IRQ toggled 0/1/0 at 20 ms, IRQ pin back to input, IRQ re-requested and disabled | same | same |
| USE_ESE | `_IOW 0x09, u32` | u32 | st54spi cb ESE_USED/ESE_NOT_USED | same | same |
| CLK_DISABLE_UNPREPARE | `_IO 0x0A` | none | **not handled → `-EINVAL`** ("bad ioctl") | `clk_disable_unprepare` if voting, returns 0 | `-EINVAL` |
| NFC_SECURE_ZONE (QTI) | `_IO 0x0B` | 0/1 in arg | **not handled → `-EINVAL`** | not handled → `-EINVAL` | explicit `-EINVAL` with log |
| ST21NFC_ON_OFF (QTI BOB1) | `_IOR 0x14, u32` | | not handled | not handled | not handled |

Other `0xEA` numbers return `-EINVAL`. A foreign magic returns `-ENOTTY`.

### Firmware download mode
No GPIO or ioctl in the kernel is dedicated to firmware download. The
ST HAL (`nfc_nci.st21nfc.st.so`) resets the chip with PULSE_RESET or
RECOVERY. It detects loader mode from `NCI_CORE_RESET_NTF` ("Loader
Mode", "Loader V3 Mode", "Router Mode") and streams firmware over
`read`/`write`. RECOVERY is the only path that forces the CLF into its
loader: it holds the IRQ line high while reset is released. The behaviour
is the same in both builds.

### Logging-only differences (not reproduced)
Stock removed several `enable_debug_log` guards: open (`%s:%d dev_open`),
release (`device_open = false`), callback register/unregister. It also
logs `enter`/`exit` in remove. These are cosmetic and were left as ST
has them.

## `stm_st54se_gpio` behavioural specification

- Module `stm_st54se_gpio`, "ST54SPI GPIO driver", GPL v2. Aliases
  `of:N*T*Cst,st54spi_gpio[C*]` and `st54spi_gpio`. Platform driver
  `st54spi_gpio`.
- Device node: char device region `st54spi_gpio`, class `st54spi_gpio`,
  device `/dev/st54spi_gpio`.
- Probe: reads `gpio-power_nreset` (`of_get_named_gpio`; an invalid GPIO
  gives `-EFAULT`), requests it at probe (ST `ESE_CONF_GPIO_PROBE_REMOVE`
  mode) and drives it **high**. Stock initialises `power_count = 0`.
  There is no regulator, clock or PM ops. Remove frees everything.
- open/release: no GPIO handling; set and clear `private_data`.
- fops: stock has `unlocked_ioctl` only. The ST base also sets
  `compat_ioctl` and `llseek`. This was kept: the argument is a plain
  integer, so 32-bit callers behave the same.

### ioctls (magic `0xEB`)

| Cmd | Number | Stock | ST base | Now |
| --- | --- | --- | --- | --- |
| GET_GPIO | `_IOW 0x01, u32` | returns raw nRESET level | same | same |
| SET_GPIO | `_IOW 0x02, u32` | **reference-counted**, see below | arg 1: drive high + 10 ms only if low; arg 0: ignored | stock behaviour |
| RESET_GPIO | `_IOW 0x03, u32` | **unsupported → `-ENOIOCTLCMD`** | low 3 ms, high, 10 ms | `-ENOIOCTLCMD` |
| other | | `-ENOIOCTLCMD` | same | same |

The argument is passed by value, not as a pointer.

### eSE power management (stock SET_GPIO)
- arg > 1: `bad arg`, returns `-ENOIOCTLCMD`.
- arg 1: count += 1. nRESET is driven high (even if already high), then
  `usleep_range(10000, 10001)`. Returns 0.
- arg 0: count -= 1, clamped at 0. If the count is still non-zero, logs
  `No execution power count` and returns 0 without touching the line.
  Otherwise nRESET is driven low, then `usleep_range(3000, 3001)`.
- The count starts at 0 while the line starts high, so the first
  `SET_GPIO(0)` with no prior `SET_GPIO(1)` resets the SE.
- Stock has no lock around the counter. The port adds a mutex (the only
  import difference: `__mutex_init`, `mutex_lock`, `mutex_unlock`).

Userspace: `libEseUtils.so` (`eseIoctl`) opens `/dev/st54spi_gpio`, or
`/dev/nq-nci` on NXP. It issues `0x4004EB02` (SET_GPIO) with 0/1 for
power. It never uses RESET_GPIO.

## st54spi callback and secure zone

### `st21nfc_register_st54spi_cb(cb, data)`
- **Who registers:** only ST's SPI eSE driver `st54spi.c`, in probe, when
  its GPIO mode is `POWER_MODE_ST54H` and **only when built-in**
  (`#ifndef MODULE`). As a module it logs "st54spi as module cannot use
  ST54H fully" and does not register. amethyst has no `st,st54spi` SPI
  node and ships no st54spi module. Both NFC builds leave the symbol
  unexported, so no module could link to it anyway. No stock module
  references it.
- **Who calls:** `stm_nfc_i2c` itself. RESET_START (1) before the
  PULSE_RESET double pulse and RESET_END (0) after it. ESE_USED (3) or
  ESE_NOT_USED (2) from the USE_ESE ioctl.
- **Inputs/outputs:** `cb(int event, void *data)` returns void. The SPI
  driver uses it to power the SE down across a CLF reset and restore it,
  and to keep SE power on while the NFCC routes to the eSE.
- **Dependencies:** none on QTEE or smcinvoke. On amethyst it is inert
  in stock and in source: the pointer stays NULL and the calls are
  skipped. The HAL still issues USE_ESE. This is harmless and returns 0.

### Secure zone (`secure_zone`, `NFC_SECURE_ZONE`)
- QTI feature: dynamic protection of the NFC peripheral by TrustZone.
  - With `NFC_SECURE_PERIPHERAL_ENABLED`, probe calls `nfc_hw_secure_check()`.
    That uses smcinvoke: `get_client_env_object` →
    `IClientEnv_open(HW_STATE_UID 0x108)` → `Object_invoke(HW_OP_GET_STATE,
    in: u32 HW_NFC_UID 0x506, out: u8 state)`. State 1 means secure.
  - In the secure state the driver doesn't take `reset-gpios`, gates all
    reset writes, and rejects every ioctl except `NFC_SECURE_ZONE`
    (`_IO(0xEA,0x0B)`). Arg 1 enters the secure zone (reset low, flag
    set); arg 0 leaves it (reset GPIO acquired or re-raised).
  - The ioctl is driven by the vendor NFC HAL. TZ errors
    `FEATURE_NOT_SUPPORTED` (12) and `PERIPHERAL_NOT_FOUND` (10) are
    treated as non-secure.
- **Stock amethyst:** built **without** it.
  - There are no smcinvoke imports, `secure_zone` is constant false, the
    log prints "false", and 0x0B falls into "bad ioctl" (`-EINVAL`).
  - In userspace, `checkNfcSecureStatus_HAL()` in
    `nfc_nci.st21nfc.st.so` is a stub that returns 0, and no blob issues
    `0xEA0B`.
  - So the feature depends on smcinvoke (`smcinvoke_dlkm`) and a TZ
    HW-state service, but amethyst uses neither.
- **Port:** `secure_zone` exists (always false) with the same reset
  gating. `NFC_SECURE_ZONE` returns `-EINVAL` with an explicit log line.
  Nothing fakes a secure state or success.

## Changes made

NFC (`ST21NFC_XIAOMI_COMPAT`, in `Kbuild`):
- `st21nfc_xiaomi.[ch]` (new): `st21nfc_xm_clkreq_wake_setup()`. It reads
  `clkreq-gpios` cell 1 and calls `msm_gpio_mpm_wake_set(gpio, true)`. A
  failure fails probe, as in stock.
- `st21nfc.c` `XIAOMI-COMPAT` blocks:
  - `secure_zone` field and gated `gpiod_set_value_t`
  - `clk_get()` voting and `ST21NFC_CLK_DISABLE_UNPREPARE` compiled out
  - explicit `NFC_SECURE_ZONE` → `-EINVAL`
  - stock probe log lines (`enter`, `secure_zone = false`,
    `CLK_REQ not present`, `probing nfc i2c success`)

eSE (`ST54SPI_XIAOMI_COMPAT`, in `Kbuild`):
- Reference-counted `SET_GPIO` (`st54spi_gpio_xm_set_power()`) with the
  stock timings, with a mutex.
- `RESET_GPIO` compiled out.

With the compat flags undefined, both drivers build as plain ST code.

## Verification (llvm-nm / modinfo vs stock)

| | Imports | Exports | modinfo (alias/depends/license/version/description/author) |
| --- | --- | --- | --- |
| `stm_nfc_i2c` before | +`clk_get`,`clk_prepare`,`clk_enable`; −`msm_gpio_mpm_wake_set`,`of_property_read_u32_index` | none | `depends=` differed (no pinctrl-msm) |
| `stm_nfc_i2c` now | **identical** | none (stock: none) | **identical** |
| `stm_st54se_gpio` before | +`msleep`; −`usleep_range_state` | none | identical |
| `stm_st54se_gpio` now | stock set + `__mutex_init`,`mutex_lock`,`mutex_unlock` (intentional) | none | identical |

ioctl dispatch was checked in the disassembly.
- NFC: `_IO` 0x01..0x08 and the legacy `_IOR` 0x01..0x08 go through jump
  tables, `0x4004EA09` is compared separately, and everything else gives
  `-EINVAL`. The port's table spans 0x01..0x0B; 0x0A and 0x0B return
  `-EINVAL`.
- eSE: only `0x4004EB01` and `0x4004EB02` are accepted.

Remaining non-exported global symbols (`clk_pin_voting`,
`st21nfc_xm_clkreq_wake_setup`) don't affect linking.

## What cannot be reproduced
- **QTI secure zone:** not present in stock, so not reproduced.
  Enabling it would need `NFC_SECURE_PERIPHERAL_ENABLED`, smcinvoke
  headers, a dependency on `smcinvoke_dlkm`, and a TZ HW-state app that
  amethyst firmware may not provide. The HAL never uses it.
  `NFC_SECURE_ZONE` returns `-EINVAL`.
- **st54spi callback:** cannot be used with modules or without an SPI
  eSE node. Kept as an inert hook, as in stock.

## Integration requests
No shared headers, module lists or BoardConfig were touched. Requests:
1. **Module dependency:** `stm_nfc_i2c` now imports
   `msm_gpio_mpm_wake_set` from `pinctrl-msm` (`depends=pinctrl-msm`,
   same as stock). `pinctrl-msm.ko` must load first. It is a
   vendor_boot module in stock, and depmod derives the order. Check
   that the regenerated `modules.dep` lists it and that
   `scripts/amethyst-ext-modules.txt` builds `xiaomi/st-nfc` against
   `KERNEL_OBJ/Module.symvers`, which already exports the symbol.
2. **No `KBUILD_EXTRA_SYMBOLS`** is needed for either module (no
   smcinvoke dependency).
3. **Device tree (device repo, not kernel):** the ueventd entries exist
   (`/dev/st21nfc` nfc:nfc 0660, `/dev/st54spi_gpio` system:system
   0660). Confirm that the SE HAL domain using `libEseUtils` can open
   `/dev/st54spi_gpio` under the device sepolicy.
4. **Rebuild** both modules from this branch and re-run
   `scripts/check-prebuilt-module-crcs.py` and the inventory script.

## Device tests needed
- Probe: dmesg shows `clkreq gpio 6 successfully setup for wakeup
  capable`, `secure_zone = false` and `probing nfc i2c success`.
  `/dev/st21nfc` and `/sys/bus/i2c/devices/*-0008/{version,i2c_addr}`
  exist.
- NFC on/off cycling; HAL log shows a CORE_RESET_NTF after
  PULSE_RESET. `ioctl(ST21NFC_CLK_DISABLE_UNPREPARE) failed` is expected,
  as on stock.
- Tag read/write (NDEF type 2/4), P2P/beam, if used.
- HCE: a payment test app works with the screen on, the screen off and
  the device locked. This exercises the CLK_REQ MPM wake.
- Suspend/resume: tag detection and HCE wake the device from deep sleep.
  Check `/sys/kernel/wakeup_sources` for `st21nfc`.
- OMAPI/eSE: open a logical channel to the eSE (e.g. OMAPI CTS or
  `SecureElement` test app). Check dmesg for the
  `Original/Updated power count` sequence. Close and reopen, check that
  the SE powers off only when the count reaches 0, and run concurrent
  NFC-HAL and SE-HAL use.
- Factory reset / `persist.vendor.nfc.streset` SE cold reset through
  `libstnfc-streset` (PULSE_RESET + SET_POLARITY_HIGH).
- Firmware update path (HAL loader mode via RECOVERY), if a CLF update
  is pending.
