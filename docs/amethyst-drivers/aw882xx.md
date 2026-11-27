# Amethyst smart PA (aw882xx / tfa986x / fs19xx)

Status of the source port: **it builds but has not been tested.** Nothing in
this document has been checked on hardware. Speaker safety comes first. Follow
the test procedure at the end before raising the volume.

The behaviour of the stock modules described here comes from these sources:

- the stock OS3.0.306.0 modules in
  `EvolutionX/device/xiaomi/amethyst-kernel/modules/vendor_dlkm`: symbol
  tables, relocations, strings and disassembly
- the stock DTBO, entry 1, fragments 43/44
- the vendor blobs in `LineageOS/vendor/xiaomi/amethyst`

No decompiled code was copied. Where stock behaviour is described, it is a
behavioural specification.

## 1. Hardware, from the stock DTBO

Both amps are on `qupv3_se12_i2c` (DTBO fragment 44). Both nodes use
`compatible = "awinic,aw882xx_smartpa"`.

| Node | reg | Role | reset-gpio | irq-gpio | spksw-gpio | sound-channel | Other properties |
| --- | --- | --- | --- | --- | --- | --- | --- |
| `aw882xx_smartpa@34` | 0x34 | top speaker, and earpiece through the switch | tlmm 54 | tlmm 38 (pull-up) | tlmm 35 | 0 | `fade-flag = 1`, `dc-flag = 0`, `pll-check-disable`, `aw-cali-mode = "aw_none "` |
| `aw882xx_smartpa@35` | 0x35 | bottom speaker | tlmm 146 | tlmm 52 (pull-up) | none | 1 | `dc-flag = 0`, `pll-check-disable`, `aw-cali-mode = "aw_none "`, `aw-re-min = 4000`, `aw-re-max = 30000` |

The properties not set are `monitor-mode`, `sync-flag`, `sync-load`,
`rename-flag`, `spin-mode`, the topo/port IDs and `aw-cali-check`.

Note the trailing space in `"aw_none "`. The driver compares this value with
`"none"`, so calibration mode stays **enabled**: the sysfs and class nodes are
created. This happens in both stock and source.

The board is **second-sourced**. The vendor partition ships both
`odm/firmware/aw882xx_acf.bin` (AW88261) and `odm/firmware/fs19xx.fsm`, and
both `odm/etc/audio/sku_volcano/` and `.../sku_volcano/foursemi/`, which
holds the mixer paths, the resource manager and a separate
`Mise_acdb_cal_fs.acdb`. A FourSemi FS1945 can sit behind the same
`awinic,aw882xx_smartpa` nodes.

## 2. Stock module structure and dispatch

| Stock module | Contents | Registers | Binds on amethyst? |
| --- | --- | --- | --- |
| `aw882xx_dlkm` | Awinic driver **Dv1.14.2**, plus the full FourSemi fs19xx driver (`fsm_*`, `fs19xx_*`) | one `i2c_driver` named `aw882xx_smartpa`, matched through its i2c id table. Not MODULE_DEVICE_TABLE'd for OF. Its `foursemi,fs16xx` OF alias belongs to the bundled FourSemi tables, which are never registered | **yes, both amps** |
| `tfa986x_dlkm` | a second Awinic driver **V2.0.4.3** (algo auth, iv_output, ramp, vol_offset), plus the NXP/Goodix TFA98xx driver | one `i2c_driver` named `aw884xx_smartpa` (`awinic,aw884xx_smartpa`); TFA9865 parts go to `extfa_i2c_probe()` | no: there is no node |
| `fs19xx_dlkm` | standalone FourSemi v4.0.7 | `foursemi,fs16xx` | no: there is no node |
| `sia91xx_dlkm`, `cs35l41/43_dlkm` | other vendors | their own compatibles | no |

All smart-PA modules depend on `machine_dlkm`, which provides
`check_smartpa_type`, `set_smartpa_type` and `set_smartpa_codec`. They also
depend on `miev`, Xiaomi's exception reporting: `cdev_tevent_*` and
`mievent_report`.

The exported cross-module symbols (`exfsm_i2c_probe`, `exfsm_i2c_remove`,
`fsm_get_config`, `extfa_i2c_probe`, `extfa_i2c_remove`) are **imported by no
stock module**. Dispatch happens inside each module through direct calls.

### Stock aw882xx_dlkm probe flow

The probe runs once per amp.

1. `check_smartpa_type("aw882xx")`. If another PA type is already latched,
   the probe calls the bundled `exfsm_i2c_probe()` and returns its result.
2. Allocate the device. Parse `reset-gpio`, `irq-gpio`, `spksw-gpio`,
   `dc-flag`, `sync-flag`, `rename-flag` and `sync-load`.
3. Request the GPIOs: rst, then int, then spksw. Hardware reset: low 1 ms,
   then high 2 ms.
4. Read chip ID register 0x00, with up to 5 retries 5 ms apart. Supported IDs
   are 0x1852, 0x2013, 0x2032, 0x2055 (2055/2055A), 0x2071 and 0x2113. On an
   I2C error or an unknown ID, read register **0x03**. If that returns
   **0x2900**, the part is an FS1945: release the GPIOs (reset driven low
   first) and call `exfsm_i2c_probe()`. If both reads fail, report the miev
   event "PA internal exception" and fail.
5. `set_smartpa_type("aw882xx")`. Then run the per-PID init, set up the IRQ,
   register the codec (see the naming rules below) and create the sysfs
   group.
6. The machine driver collects the codec through `set_smartpa_codec()` and
   attaches every registered smart PA to the TDM RX0/RX1/TX dai links. It
   publishes the latched type at `/sys/kernel/smartpa/smartpa_type`.

The amethyst amp is an **AW88261, PID 0x2113**: every entry in the ACF says
`aw88261`.

### Codec, DAI and naming

- DAI `aw882xx-aif`, with streams `Speaker_Playback` and `Speaker_Capture`.
  When `rename-flag` is 0 the names get suffixes:
  `aw882xx-aif-<bus decimal>-<addr hex>` and
  `Speaker_Playback_<bus>_<addr>`.
- When `rename-flag` is set, stock suffixes the channel instead and briefly
  renames the device. Amethyst does not set it.
- The i2c driver has no dev_pm_ops: **no suspend/resume hooks**. The amp is
  powered up and down only through the DAI path (startup, mute_stream,
  shutdown) and `i2c shutdown`, which stops the device.

## 3. Firmware and register init

- `aw882xx_acf.bin`, from `/odm/firmware`. Its header is v0.0.0.1, project
  `O16U`, customer `XM`, with 10 entries of type `AW_DEV_DEFAULT_TYPE_ID`:

  | dev_index | Sections |
  | --- | --- |
  | 0 | Bypass, Music, Receiver, Voice (each `HDR_REG`, 292 bytes) + Music `MONITOR` (168 bytes) |
  | 1 | the same |

  There is no DSP section. The entries are matched to an amp by
  **`aw_dev->channel` (DT `sound-channel`)** in stock, not by probe order.
- Profile names are fixed by the driver: Music, Voice, Voip, Ringtone,
  Ringtone_hs, Lowpower, Bypass, Mmi, Fm, Notification, Receiver. The mixer
  paths use Music, Voice and Receiver.
- `aw882xx_pid_<pid>_monitor.bin` is requested only by the sysfs
  `monitor_update` node. Amethyst does not ship it: the monitor tables come
  from the ACF.
- The ACF loads from a workqueue at codec probe, with no delay. With
  `sync-load` it loads synchronously. A failed load is retried 5 times, 1 s
  apart.
- Register init writes the profile `HDR_REG` block when the amp powers on.
  After that it records the resulting volume register as `init_volume`. If
  the profile changed, it resets the user attenuation to 0. On `fade-flag`
  amps, it parks the volume at `init + mute_volume`.
- FourSemi (stock only): `fs19xx.fsm` or `fs16xx.fsm`.

## 4. Mixer controls

The names matter: `mixer_paths_overlay_static.xml` uses `aw_dev_{0,1}_switch`,
`aw_dev_{0,1}_prof` and `aw882xx_spk_sw_gpio_switch`. PAL (`libar-pal.so`)
also uses `aw_dev_%d_monitor`, `aw_dev_%u_hal_mon_work`,
`aw882xx_hal_monitor_time`, `aw_dev_%d_iv_output` and `aw_dev_%d_offset`. The
last two belong to the aw884xx driver, which has no node on amethyst.

| Control | Stock | Source before | Source now |
| --- | --- | --- | --- |
| `aw882xx_rx_switch`, `_tx_switch`, `_copp_switch` (enum Disable/Enable) | yes | yes | yes |
| `aw882xx_fadein_us`, `aw882xx_fadeout_us` (0..1000000) | yes | yes | yes |
| `aw882xx_hal_monitor_time` (0..100000; read returns monitor period ms; writes accepted and ignored) | yes | **missing** | yes, **read-only** |
| `aw882xx_spk_sw_gpio_switch` (0..3, non-zero → GPIO high) | yes, global list | added after FW load, range 0..1 | global list, 0..3; -ENODEV without GPIO |
| `aw882xx_spin_switch` | only if `spin-mode` | same | same (not on amethyst) |
| `aw_dev_<ch>_prof` / `_switch` / `_monitor` | named by **sound-channel** | named by probe index | by sound-channel |
| `aw_dev_<ch>_volume` (0..mute_volume, attenuation in 0.125 dB) | yes | **missing** | yes |
| `aw_dev_<ch>_hal_mon_work` (read: run one monitor cycle, return vmax; 0xffffffff if not in hal mode) | yes | **missing** | yes, read-only/volatile |
| `aw882xx_fadein_us_top/_bottom`, `aw882xx_rcv_en`, `aw_dev_*_ramp/_attenuate` | no | compiled out (Moto ifdefs) | compiled out |

The global controls are added by the amp with `sound-channel == 0`. The
per-amp controls are added after the ACF loads.

The handset path selects `aw_dev_0_prof = Receiver` and
`aw882xx_spk_sw_gpio_switch = 1`, which routes the top amp to the earpiece.
The music paths set it back to 0.

FourSemi units use `FSM_Scene`, `FSM_Volume`, `FSM_Ramp_Volume`,
`FSM_SW_GPIO`, `FSM_Stop` and `FSM_Ultrasound_Enable` from the `foursemi/`
mixer paths. None of these exist in the source build.

## 5. Calibration and the ADSP

- **The ADSP runs the Awinic speaker-protection algorithm** (AWDSP module,
  topologies 0x1000FF00 and 0x1000FF01) in the AudioReach graph. Userspace
  configures it: ACDB data through AGM, and PAL/`libawcal.so`
  (`aw_audioreach_*`, `aw_tmixer_*`) for algo enable, Re, F0, Te and vmax
  messages.
- **Calibrated Re** is stored in `/mnt/vendor/persist/factory/audio/aw_cali.bin`.
  PAL reads it and sends it to the DSP. The kernel never reads it.
- The kernel module has **no DSP transport** on AudioReach, in either stock
  or source. The q6afe-v2/ADM APIs behind `AW_QCOM_PLATFORM` do not exist on
  volcano. MTK messaging is excluded, and nothing on this platform needs it.
- In stock, every kernel DSP accessor still "succeeds": writes are no-ops,
  and reads return uninitialised buffers. The nvram Re hooks return 0
  without doing anything.
- The source now returns `-EOPNOTSUPP` from all of these. As a result:
  - `cali_re`, `cali_f0` and the misc ioctls that need the DSP fail cleanly.
    They no longer report garbage.
  - The startup copp/afe enables are skipped quietly.
  - The kernel's `cali_re` stays 0. That makes `aw_dev_cali_re_update` log
    "cali re is out of range", which stock also logs.
- DC protection (`dc-flag`) is off on both amps. Calibration check
  (`aw-cali-check`) is off, so the amp is never held muted because of a
  calibration result.
- Re limits (DT): 4000–30000 mΩ on @35. @34 uses the driver defaults.

**No calibration value is invented or replaced.** The source has no Re
values of its own.

## 6. Thermal, voltage and over-current protection, and gain limits

The kernel "monitor" (`monitor-mode` absent → **kernel_monitor**) runs every
`monitor_time` while the amp is on. It reads the chip's battery voltage and
temperature over I2C, then looks up the ACF tables and applies ipeak (the
peak-current limit register) and gain. The vmax value is meant for the DSP,
which is a no-op from the kernel.

The ACF monitor section is identical for both amps: AW88261, period
1000 ms, count 1, logic OR. The enable bits switch on ipeak, gain, vmax and
voltage, and switch **temperature off**.

| Table | Range | ipeak | gain (atten.) |
| --- | --- | --- | --- |
| vbat | 4400–5000 mV | 0x7000 | 0 |
| vbat | 3700–4000 mV | 0x7000 | 0 |
| vbat | 3510–3600 mV | 0x7000 | 0x04 → 0.5 dB |
| vbat | 0–3500 mV | 0x5000 | 0x0c → 1.5 dB |
| temp (disabled) | 7–100 / 2–5 / -50 to -5 °C | 0xa000 / 0x6000 / 0x4000 | 0 / 3 dB / 8 dB |

The gaps between the ranges act as hysteresis: the previous entry is kept.

**Gain rule (stock, now in source):** the volume register gets
`init_volume + max(user attenuation, monitor attenuation)`. The table gain is
converted from register format with `aw_reg_val_to_db`. The volume control
therefore cannot undo a monitor cut. Before this change, the source monitor
overwrote the volume with `gain + init` and ignored the user value.

The volume scale for PID 2113 is 0.125 dB per step, and mute_volume is 720
(90 dB). The ACF sets the 0 dB point, `init_volume`. The source sets no gain
of its own.

**Fade:** this applies only to amps with `fade-flag`, which means the top
amp. Mute walks the attenuation up to 400 (50 dB), then sets the mute bit and
waits 5 ms. Unmute clears the mute bit, then walks down from 400. The step is
15 above 250, 10 above 200, 7 above 150, 6 above 120, 5 above 48, and 1
below that. There is no sleep between steps. If `aw882xx_fadein_us` or
`aw882xx_fadeout_us` is 0, the walk is skipped and the volume jumps straight
to the end value. Amps without `fade-flag` only toggle the mute bit.

The source differs from stock in two places, both on purpose:

- Stock fades in all the way to 0 dB attenuation. The source stops at the
  effective attenuation.
- Stock fades out starting from the user attenuation. The source starts from
  the effective attenuation, so there is never even a brief increase.

**Startup checks:** `pll-check-disable` (set on both amps) skips the PLL-lock
check and the I2S/sysst check during power-up. This is stock behaviour, and
the source now matches it. The interrupt path is the same as before: on an
interrupt it masks the source, reads the status, and recovers the amp from
the work handler.

## 7. Remaining differences between the source module and stock

1. **No FourSemi support.** On an FS1945 unit the source logs
   "FourSemi FS1945 detected: not supported by this build", leaves the part
   in reset and fails the probe with -ENODEV. The smart-PA type stays
   "none", and the speakers are silent but safe. Stock drives such a unit.
2. If another PA type is already latched, the source returns -ENODEV. Stock
   dispatches to the FourSemi code instead.
3. `miev` exception events are not sent: there is no source for `miev`.
   Kernel log lines replace them.
4. Driver base version: v1.11.01 (Motorola) against stock Dv1.14.2.
   - The register tables and monitor logic are the same family.
   - Source-only sysfs nodes: `sync_flag` and a few renamed attributes.
   - Source-only DT properties: `vcalb_half` and `rcv-gpio`. Neither is
     present on amethyst.
5. `rename-flag` is parsed but not implemented. The driver logs an error if
   it is ever set.
6. DSP accessors return -EOPNOTSUPP instead of fake success (§5).
7. `aw882xx_hal_monitor_time` is read-only. Stock silently ignores writes.
8. The fade differs as described in §6.
9. Stock binds through the i2c id table. The source also has an OF match
   table. Both bind the same nodes.
10. `tfa986x_dlkm` from source is MiCode's
    `audio-kernel/asoc/codecs/tfa986x` (pure TFA98xx, `tfa,*` compatibles).
    It does not contain the Awinic V2.0.4.3 (`aw884xx`) code or
    `extfa_i2c_probe`, which stock bundles. Neither variant binds on
    amethyst, so this only matters for the inventory diff.
11. The stock `fs19xx_dlkm`, `sia91xx_dlkm` and `cs35l41/43_dlkm` have no DT
    node on amethyst. Dropping them is correct.

## 8. Integration requests

These are outside this worktree's scope. The shared files were not edited.

- **FourSemi support:** obtain the GPL source of Xiaomi's FourSemi fs19xx
  v4.0.7 driver, which ships inside `aw882xx_dlkm` and `fs19xx_dlkm`. The
  modules are licensed GPL, so a source request to Xiaomi/MiCode is
  justified. Mirror the stock structure: link the FourSemi objects into
  `aw882xx_dlkm` and call `exfsm_i2c_probe()` from the probe at the two
  stock dispatch points ("type already latched" and "chip ID 0x2900 in reg
  0x03"). Until that happens, FS1945 units have no speaker audio.
- Keep `aw882xx_dlkm` in `scripts/amethyst-ext-modules.txt` and in the
  vendor_dlkm load list **after** `machine_dlkm`. The source module has no
  `miev` dependency, so `miev` does not need to load first.
- Do not ship `fs19xx_dlkm`, `sia91xx_dlkm` or `cs35l4x_dlkm` from stock
  next to the source `aw882xx_dlkm`. Their vermagic and symbol CRCs come
  from the stock build, and they also need `miev`.
- The device tree, vendor or HAL side must keep `aw882xx_acf.bin` in
  `/odm/firmware`, and the mixer paths and ACDB from the stock vendor image.
  The kernel does not need `aw_cali.bin`.
- No BoardConfig or kernel-header changes are needed.

## 9. On-device test procedure

Do this before any listening test at normal or high volume.

### Preparation

- Use a root shell over adb. Keep the phone away from your ear, and keep the
  earpiece off your face.
- Turn the media volume to **minimum**. Close every app that plays audio.
- Have `dmesg -w` running in a second shell.

### Step 1: probe, with no audio

```
dmesg | grep -iE 'awinic|aw882xx|smartpa|FS1945'
cat /sys/kernel/smartpa/smartpa_type        # expect: aw882xx
ls /sys/bus/i2c/drivers/aw882xx_smartpa/    # expect: N-0034, N-0035
```

Expect "aw882xx 2113 detected" twice, `set_smartpa_type smartpa_type:
aw882xx`, `set_smartpa_codec ... aw882xx-aif-<bus>-34/35`, and
"load [aw882xx_acf.bin] , file size: [3392]".

If you see "FS1945 detected", stop: this unit needs FourSemi support.

### Step 2: profiles and monitor tables were parsed per channel

In the log, check "sound-channel value is : 0/1" and "fade-flag: 1" (for @34
only). Check that "pll check disable" appears for both amps and that the
monitor reports "monitor_switch:1".

```
tinymix -D0 | grep -E 'aw_dev|aw882xx'
```

Expect the following, with no `aw_dev_*_ramp` controls:

- `aw_dev_0_prof` and `aw_dev_1_prof` with the values Bypass, Music, Receiver
  and Voice
- `_switch`, `_monitor`, `_volume` (0..720) and `_hal_mon_work` for each amp
- `aw882xx_hal_monitor_time` reading 1000
- `aw882xx_spk_sw_gpio_switch`

### Step 3: quiet playback, bottom amp first

- Play a 1 kHz tone at about -30 dBFS, or a quiet ringtone, at the
  **lowest** volume step.
- Watch dmesg for the start sequence:
  - "load Music done"
  - **no** "check fail" and **no** "pll check failed"
  - the monitor log "chip voltage is ..." followed by
    "set_ipeak = 0x7000 ..."
- Log `tinymix -D0 aw_dev_1_switch aw_dev_1_prof aw_dev_1_volume`.
- Read the volume register through sysfs: `cat .../N-0035/reg` and record
  register 0x05 (SYSCTRL2; the volume field is bits 9:0, in 6 dB and 0.125 dB
  fields). Also record 0x21 (VBAT) and 0x22 (TEMP). Confirm the volume
  matches `init_volume` from the ACF, plus any attenuation.

### Step 4: protection before loud tests

- Set `aw_dev_1_volume` to 80 (10 dB). Confirm the playback level drops.
  Then set it to 0.
- Battery: compare `dumpsys battery` voltage with the monitor log line
  "chip voltage is". Below 3600 mV the log must show gain 0x04 or 0x0c, and
  `aw_dev_*_volume` must not be able to lower the attenuation below the
  monitor value. Read it back with `cat .../reg`.
- Check the IRQ: there must be no repeated "aw882xx_interrupt_work" storms
  during playback.
- Mute and unmute by stopping and starting playback on the top amp. Expect a
  smooth fade with no pop, and no "set volume failed" messages.

### Step 5: top amp and earpiece switch

- Start a call or the handset path at minimum volume. Confirm the following:
  - `aw882xx_spk_sw_gpio_switch` reads 1
  - `aw_dev_0_prof` is Receiver
  - the earpiece plays quietly
- When you return to media, the switch must read 0 and the profile Music.
  **Never** play the Music profile with the switch at 1: that would drive the
  earpiece with speaker power.

### Step 6: only then, raise the volume

Raise it in steps up to normal listening level. Watch for distortion and for
heat at the speaker grilles. Do not run sustained full-scale tests before
checking that the ADSP protection is active: PAL logs "enabling awinic
smartpa for device ..." in logcat, and `aw_cali.bin` is present in persist.

### What to collect for any report

- `dmesg` from boot, filtered with `grep -iE 'awinic|aw882xx|smartpa|tdm'`
- `tinymix -D0` (full output) while idle and during playback
- `cat /sys/kernel/smartpa/smartpa_type`
- `logcat -b all | grep -iE 'awinic|smartpa|PAL|AGM'` during playback
- the register dump at `/sys/bus/i2c/devices/*-003{4,5}/reg`, idle and
  playing
