# Amethyst touch: Goodix 9916R + xiaomi_touch

Status (2026-11-28): the source modules build. A tester's ROM boots with no
touch. The differences below were found offline by comparing against stock;
**none of the runtime effects are verified yet.** Verification is the A/B
kit in `scripts/amethyst-touch-testkit/` (see "Test kit").

Background and port history: `TOUCHSCREEN.amethyst.md` (repo root).

## ORIGIN

| Module | Path | Donor |
| --- | --- | --- |
| `goodix_core.ko` | `drivers/input/touchscreen/goodix_berlin_driver` | MiCode/vendor_xiaomi_proprietary_touch-driver, branch `warsaw-w-oss`, commit `57d9a0225b` (the branch's only commit), path `warsaw/goodix_9916k`, driver "gt9916-2025.8.19-01" |
| `xiaomi_touch.ko` | `drivers/input/touchscreen/xiaomi` | same commit, path `warsaw/xiaomi` |

Stock reference: `goodix_core.ko` is built from
`vendor/xiaomi/proprietary/touch/touchfeature_v2/touch_driver/o16u/goodix_9916k/`,
driver "gt9916-2025.02.20-01". Its xiaomi_touch reports "2024.09.02-01".

### Search for a closer donor (2026-11-28)

- MiCode/vendor_xiaomi_proprietary_touch-driver: all 11 branches were
  checked (bixi-v, dada-v, darwin-w, main, piano-w, popsicle-w, shuntian-w,
  songyuan-w, warsaw-w, xuanyuan-v, yupei-w). Each has one commit and no
  tags. None has o16u/Amethyst. Warsaw is still the only `goodix_9916k`.
- GitHub code search turned up no "gt9916-2025.02.20" and no
  `goodix_htc_dump_tic`. The closest other Goodix is "gt9916-2025.07.24-01"
  (rexprjkt/android_kernel_device_modules-6.6, MTK). The stock-only
  functions `goodix_htc_set_game_mode`, `goodix_send_camera_report_rate` and
  `goodix_reset_charge_state` exist only in lolipuru/android_kernel_xiaomi_sm8850-modules
  `goodix_9615v`, which is a different controller.
- The xiaomi_touch frameworks of xiaomi-onyx-dev/android_kernel_xiaomi_sm8735-modules
  (lineage-23.2) and others export `xiaomi_touch_mievent_report_*`. Like
  Warsaw, they use the newer mmap "report point v2" path, not stock's
  `touch_event_data` write path.

Warsaw therefore stays the donor. The Amethyst differences were
reconstructed from the stock binaries below.

## Stock references (outside git)

SHA-256 values. The RE databases (BTF dumps, annotated disassembly) are in
the session scratch dir, not in git.

| File | SHA-256 |
| --- | --- |
| stock `vendor_dlkm/goodix_core.ko` | `5e2e6d30f19097d329d3ca98f3ee4dcfb7646d39010f6d89f1e171265858dc4a` |
| stock `vendor_dlkm/xiaomi_touch.ko` | `c793db9c7468e28de655159c4c41bedc21736985a2a91bab6de6b65a9432cfbc` |
| stock `vendor_dlkm/focaltech_touch.ko` | `420b89ce82bc247d934cb3dc60387105fb103341efe7010170c0f72ab5477786` |
| stock `panel_event_notifier.ko` | `2afe4002711a1de73ef90f8427baad7e866655d568b2811890d15ead805005a4` |
| stock `goodix_fod.ko` | `a05731e0c420974776e7de29b596642a5e4a344c45e6d60f238b07bc7a9206a7` |
| `odm/bin/hw/vendor.xiaomi.hw.touchfeature-service` | `66bdad9a80923810d86bdb3d2dcff7cdaecec8dc1583cce8bd8c338827741d08` |
| `odm/lib64/libtouchreport_hal.so` | `08106065561c44eaa6b5c4081d770b000ff95e07b063edd191d3ce0aa15b4840` |
| `odm/lib64/libtouchreport.so` | `40abc88d9def6e8328a44ff48435bebfee9c6239a50de082350956781b3137ba` |
| `odm/lib64/libtouchreport_alg_goodix.so` | `6c6987ab8606ef73b9d62b7357f798dce1329a960985e17149dce5098232e64e` |
| `odm/bin/toucheventcheck` | `3afb59edc8f95d1a9e10a49270df9144b259ab0a7f0f0dc92cf22d570b08cc73` |
| `odm/firmware/goodix_firmware_csot.bin` | `ac6ab64e562dfbf720c0d88680e19e3b53b98819c14e913bfbd1835359fdfc5d` |
| `odm/firmware/goodix_cfg_group_csot.bin` | `0f1b22649d643769b4009c702650d02a5efe356d5a4ee95a210a866a0685ccd0` |
| `odm/firmware/o16u_goodix_thp_config_00.ini` (= `_01`) | `d8d8507ed6b8e707d0acdc36a4a590e62fb77c6a19f4f1800a6ecf9b9dda69e4` |
| ROM (pre-fix) `goodix_core.ko`, 6.1.68-g463696c9b | `16d1c73563e5804df9d6b1f90d587466b559e77fb11865ca35c1028b39a2db1c` |
| ROM (pre-fix) `xiaomi_touch.ko` | `15bc4e4f413af59d241a34edd04054cd908c2a676fb39ab396082b283e4b90f4` |

Method: the stock modules carry split BTF but no DWARF. The base (vmlinux)
BTF of the stock build is unavailable, so base-type and base-string names
show as unresolved. Every module-local struct, member offset, enum and
function prototype is exact. Code was compared with `llvm-objdump -dr`,
with relocations and .rodata strings folded in. For the userspace side,
the HAL's `xiaomi_touch_ioctl`, `find_touch_device` and
`copy_frame_data_from_mmap` were disassembled.

## How THP touch works on Amethyst (from the binaries)

1. goodix_core reads a 2500-byte frame per IRQ into xiaomi_touch's frame
   buffer (`get_raw_data_base`, slot = `frame_data_page_size` pages = 8 KiB)
   and calls `notify_raw_data_update`. This wakes poll(POLLPRI) on
   `/dev/xiaomi-touch`.
2. touchfeature-service (libtouchreport_hal.so) mmaps the frame buffer
   (ioctl 'T' nr 2 selects area 1, then mmap). It decodes the frame and
   runs the Goodix algorithm.
3. Report path. The HAL first tries "report point v2": select mmap area 4
   and mmap one page. Stock xiaomi_touch has no area 4, so v2 fails and the
   HAL uses "v1". The in-tree framework has area 4, but backs it only once
   `register_xiaomi_input_dev()` runs. Neither controller driver calls it, so
   v2 also fails here and the HAL falls back to v1 as on stock.
4. In v1 (`find_touch_device`, 0x18ef0..0x19250), the HAL scans `/dev/input`
   for a device with all of:
   - EV_ABS, ABS_MT_POSITION_X/Y and BTN_TOOL_FINGER;
   - ABS_MT_POSITION_X max == `x_resolution * super_resolution_factor - 1`;
   - ABS_MT_POSITION_Y max == `y_resolution * super_resolution_factor - 1`.

   The resolution values come from the HARDWARE_PARAM ioctl (nr 1,
   214 bytes). The HAL then writes MT events into that evdev.

## Behavioural differences, ranked by likelihood of "no touch at all"

1. **Input device never matched by the HAL (P0).**
   - Stock `goodix_ts_stage2_init` sets ABS_MT_POSITION_X/Y max to
     `panel_max - 1` (`sub w3, w8, #1` at 0x2f0c and 0x2f2c): 121999 and
     271199.
   - Stock `goodix_start_later_init` stores the THP resolution as the
     constant 1220 x 2712 (`mov w10, #0x4c4; movk #0xa98` at 0xa688).
   - The Warsaw port set the max to `panel_max` (122000) and took the
     resolution from IC info (`ic_info.misc.panel_x`, value unknown).
   - The HAL's equality test therefore cannot match `goodix_ts`. It retries
     forever ("can't get touch device"), frames are decoded, and nothing
     reaches Android.
   - **Fixed:** max = `panel_max - 1`, and resolution = DT
     `panel-max / super-resolution` = 1220 x 2712.
2. **Frame-output enable command format (P1).**
   - Stock `goodix_htc_enable` sends `90 <mode>` with len 5. `<mode>` comes
     from a sync-mode table (`0x18811101`: 01/11/81/18).
   - Warsaw sends `90 02 01` with len 6, the THP 4.0 form of its P11
     firmware.
   - It is used through the `enable_touch_raw` sysfs node and the TUI hooks.
     The IC streams frames by default, so this is not the boot path, but a
     write would misprogram the O16U firmware.
   - **Fixed.**
3. **`struct tp_frame` layout (P1, HAL ABI).**
   - Stock BTF: 5728 bytes, `thp_frame[2500]` at 24, `dump_type` at 2524,
     `tic_raw[1600]` at 2528, `tic_base[1600]` at 4128.
   - Warsaw: `thp_frame[4096]`, with `dump_type` at 4120.
   - The HAL reads `dump_type` at frame + 0x9dc and the TIC block at 0x9e0
     (libtouchreport_hal.so 0x1f42c, 0x1f470).
   - With dump off, the stale bytes at 2524 are zero, so this is not fatal.
     Any dump request would misparse.
   - **Fixed:** stock layout, frames always read as 2500 bytes, and
     `goodix_htc_dump_tic` reconstructed (0xfa20).
4. **Commands Warsaw sends but stock does not (P1).** Each would send a
   command the O16U firmware may not implement:
   - `THP_HAL_REPORT_RATE` (1011): stock only records it (0xbd1c). Warsaw
     sent `9D <hz-mapped index>`.
   - `THP_HAL_DISPLAY_FPS` (1012) and `THP_GLOVE_STATUS` (1092): both hit
     stock's default case (jump table `.rodata+0x13894`). Warsaw sent `2A`
     (FPS) and a glove command.
   - `THP_HAL_IDLE_RATE` and `THP_REF_HOPPING_SET`: not in stock's enum.
   - **Fixed:** the dispatch follows stock.
5. **Smaller command and behaviour fixes (P2), all fixed:**
   - `goodix_htc_set_active_scan_rate` sends the index unchanged (stock
     0x1020c).
   - `goodix_htc_start_calibration` uses len 5 (stock `0xa805`).
   - The THP game mode `C2 <on>` is sent again (stock
     `goodix_game_mode_update` 0x44d8).
   - `Touch_THP_Dump` accepts DUMP_BASE (100).
   - FOD down/up only forwards to xiaomi_touch. It no longer injects
     BTN_INFO/WIDTH into the HAL-owned device (stock 0xed78).
   - Charging status is 0/1 (stock `xiaomi_power_supply_work`).
     `WIRELESS_CHARGING` = 3.
6. **xiaomi_touch userspace ABI. Checked, matches:**
   - ioctl magic 'T'. Commands 0..5 match stock: COMMON_DATA, HARDWARE_PARAM
     (214 bytes), SELECT_MMAP, SELECT_TOUCH_ID, GET_FRAME_DATA_INDEX,
     RAW_DATA_INDEX. The in-tree framework adds 6 (UPDATE_REPORT_POINT).
   - mmap areas 1..3 match. The in-tree framework adds area 4.
   - poll masks match: POLLPRI frame, POLLRDNORM command, POLLRDBAND raw.
   - `common_data_t` is 1032 bytes and `hardware_param_t` is 214, with the
     same offsets.
   - The `common_data_mode` values that both define are equal, from 0 to
     1105. The only exception is 1105 itself, THP_TRACE_LEVEL in the
     in-tree enum and THP_HAL_STYLUS_STATIC_STATE in stock; neither driver
     acts on it.
   - The sysfs nodes the HAL opens exist: `abnormal_event`,
     `touch_finger_status` and `touch_thp_ic_cmd_data`.
   - **Restored:** the stock `touch_event_data` write path. A write of
     N x 28 bytes to `/dev/xiaomi-touch` reports N contacts, with enum
     `touch_event_classification` (stock `xiaomi_touch_dev_write` 0x4c74,
     `report_touch_event` 0xa734). Like stock, it reports nothing unless a
     Xiaomi input device is registered.
7. **goodix to xiaomi_touch interface (not a runtime issue for source+source):**
   - Stock `hardware_operation_t` is 248 bytes. The Warsaw one is 272: it
     moves `get_limit_csv_version` and adds `ic_enable_irq`,
     `ic_set_fod_value` and the FOD attn tests.
   - Stock `xiaomi_touch_driver_param` is 624 bytes, the Warsaw one 648.
   - Stock `register_xiaomi_input_dev` takes 3 arguments, the Warsaw one 4.
   - Both source modules are built from the same headers, so they agree with
     each other. The difference only makes the mixed stock/source pairs
     unloadable (modversions CRC mismatch on `register_touch_panel` and
     `add_common_data_to_buf`), which is the intended, safe outcome.

## Not reconstructed / unknown

- **MiEvent:** stock `xiaomi_touch_mievent_report_int/str` (cdev_tevent_*
  from miev), goodix `goodix_touch_dfs_test` and the `touch_mievent_code`
  values (912001001..912002002). An in-tree module cannot link against
  external `miev.ko`. Restoring this needs xiaomi_touch and goodix_core
  moved to external modules built after `xiaomi/miev`. It is telemetry only.
- **`goodix_send_camera_report_rate`, `goodix_reset_charge_state`,
  `goodix_sleep_to_gesture`, `goodix_short_open_test`:** stock-only helpers,
  not compared in detail. The last one is factory test code.
- **Not compared instruction by instruction:**
  - suspend/resume (`goodix_resume_suspend`). The call graphs match, except
    that stock calls `goodix_ts_power_off/on` where the in-tree build calls
    `hw_ops`, and the in-tree build also releases all MT slots on suspend;
  - the power-on sequence (`brl_power_on`);
  - the firmware/config update path. Firmware selection was checked earlier
    and matches.
- **IC info `panel_x`:** the value is unknown, and the driver no longer
  depends on it.
- **Runtime:** probe, IRQs, frames reaching the HAL, MT events, and
  suspend/resume behaviour are all unverified.

## FocalTech

`techpack/amethyst/focaltech_touch` is unchanged. It already registers its
device with `x_max - 1`. The ROM's `focaltech_touch.ko` passes the module
preflight against the new `xiaomi_touch.ko`: no CRC or symbol errors, and
`register_touch_panel` keeps CRC `0xaf080eab`. The exported log level was
renamed `tp_current_log_level` (the stock name); FocalTech does not import it.

## Build

The modules are built in-tree as before. Module names, dependencies
(`goodix_core` -> `xiaomi_touch` -> `panel_event_notifier`) and load order
are unchanged. The feature flags are `-DTOUCH_FOD_SUPPORT
-DTOUCH_THP_SUPPORT` (`drivers/input/touchscreen/Makefile`).

Out-of-tree check build used for the kit (no writes to ~/AndroidBuilds):
copy `out/target/product/amethyst/obj/KERNEL_OBJ` to a scratch dir. Remove
the in-tree xiaomi_touch/goodix entries from its `Module.symvers`, set the
kernel release, then build:

```sh
make -C <tree> O=<copy> LLVM=1 LLVM_IAS=1 ARCH=arm64 \
  KCFLAGS="-DTOUCH_FOD_SUPPORT -DTOUCH_THP_SUPPORT" \
  M=drivers/input/touchscreen/xiaomi modules
make ... M=drivers/input/touchscreen/goodix_berlin_driver \
  KBUILD_EXTRA_SYMBOLS=<copy>/drivers/input/touchscreen/xiaomi/Module.symvers modules
```

Between 5153e1402 and 463696c9b only `techpack/` and `docs/` changed, so
vmlinux CRCs are identical. With modversions, the kernel ignores the
release part of vermagic.

## Preflight of the four combinations

Run with `scripts/amethyst-preflight-modules.py` against the ROM's module
set, swapping in the given `goodix_core.ko`/`xiaomi_touch.ko`:

| goodix_core | xiaomi_touch | Result |
| --- | --- | --- |
| stock | stock | loads (the ROM's focaltech_touch would not: CRC mismatch, so it is not loaded in this pair) |
| source | stock | refused: CRC `register_touch_panel`, `add_common_data_to_buf` |
| stock | source | refused: same CRCs, plus missing `xiaomi_touch_mievent_report_int/str` |
| source | source | loads, together with the ROM's focaltech_touch |

The other errors the script prints are about system_dlkm signing (the ROM's
system_dlkm is unsigned from the script's point of view). They are the same
for every pair.

## Test kit

- Scripts: `scripts/amethyst-touch-testkit/`. `make-kit.sh` assembles a kit
  dir with the source and stock modules. The kit contains stock binaries,
  so it is kept outside git.
- Live swapping is safe for the source pair: its `goodix_ts_remove`
  unregisters from xiaomi_touch.
- Stock `goodix_core` does **not** import `unregister_touch_panel` or
  `xiaomi_unregister_panel_notifier`. Unloading it would leave xiaomi_touch
  holding function pointers into freed module memory, which the panel
  notifier, power-supply notifier and temperature thread call. The kit
  therefore runs the stock pair last, never unloads it, and asks for a
  reboot.
- The mixed pairs are attempted only to record the kernel's refusal.
- The kit unloads a module only when its refcount is 0 and it has no
  holders, after stopping touchfeature-service and toucheventcheck. It never
  uses `rmmod -f`.

## Integration notes

- No module list, BoardConfig, sepolicy or firmware change is needed: the
  names, dependencies and files are the same as before.
- After merging, rebuild the ROM and check that `getevent -p` shows
  `goodix_ts` ABS_MT_POSITION_X max 121999 and Y max 271199.
