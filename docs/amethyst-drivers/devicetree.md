# Amethyst device tree: source-built DTB and DTBO

The ROM used to ship Xiaomi's prebuilt base DTBs (vendor_boot `--dtb`) and
`dtbo.img`. Both are now rebuilt from source in this tree:
`arch/arm64/boot/dts/amethyst/`. The rebuilt images match stock as follows:

| Image | Result |
| --- | --- |
| `volcano.dtb`, `volcano6.dtb`, `volcano6p.dtb` | **byte-identical** to stock |
| `dtb.img` (vendor_boot, all three bases concatenated) | **byte-identical** to stock |
| `dtbo.img` table: magic, header, page size, entry count/order/offsets, id/rev/custom | identical |
| `dtbo.img` entry 0 (msm-id 657/658, board 8) | **byte-identical** |
| `dtbo.img` entry 1 (msm-id 640/641/636, board 8) | **semantically identical**. Bytes differ only in packaging; see [Remaining differences](#remaining-differences) |
| Effective trees: each entry applied to each base with libfdt (`fdtoverlay`) and with libufdt (`ufdt_apply_overlay`, ABL's applier) | identical, 0 differences |

Building is not the same as validating on hardware. The tester procedure is
in [Hardware validation](#hardware-validation).

## Stock images

These come from stock OS3.0.306.0, the copy in
`device/xiaomi/amethyst-kernel/images` (the LineageOS and EvolutionX copies
are identical). They are not in git.

| File | SHA-256 |
| --- | --- |
| `dtbo.img` | `06deec9ec79cf7c9c31b59cd404c824ef5b924428f17d2ec57067881f16f4964` |
| `dtbs/01_…Volcano_SoC.dtb` | `5e13b14f124935ea64030fa01aa17a7b6694e37e559df3a69e52a2e052b44d5b` |
| `dtbs/02_…Volcano6_SoC.dtb` | `372435669a6645f1a9665173bb8895fee46ab12f18d77eaf3b456e566b1ce960` |
| `dtbs/03_…Volcano6P_SoC.dtb` | `d2e2066c9f71db736051406cd7b2a7a91482324c3becada4c0bc28dfd11a9999` |
| `dtbo.img` entry 0 | `ba2128ff22f2f8af180cc5e2b49f2cbc6d8ff0551118a6ed0a94fbf07ceea1af` |
| `dtbo.img` entry 1 | `3613a08be79ee2f3e70509ffb157eae03f01ec53966b74241cb677b9c78e5065` |

### Catalogue

`scripts/amethyst-dtcompare.py info dtbo.img volcano*.dtb` prints the full
catalogue as JSON: IDs, compatibles, status, fragments and targets, external
labels, and reserved memory.

| | model | msm-id | board-id | nodes | props | phandles | symbols | fragments |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| volcano.dtb | Volcano SoC | 0x27c (636) | 0 0 | 2641 | 11252 | 1211 | 1284 | – |
| volcano6.dtb | Volcano6 SoC | 0x280 (640) | 0 0 | 2639 | 11232 | 1211 | 1284 | – |
| volcano6p.dtb | Volcano6P SoC | 0x281 (641) | 0 0 | 2629 | 11124 | 1206 | 1279 | – |
| dtbo entry 0 | Amethyst based on SM7635 | 0x291, 0x292 (657, 658) | 8 0 | 354 | 927 | 48 | 48 | 36 |
| dtbo entry 1 | Amethyst based on SM7635 | 0x280, 0x281, 0x27c | 8 0 | 1349 | 6461 | 327 | 327 | 91 |

Details:
- **Entries.** Both entries carry `qcom,pmic-id-size = <8>` and
  `qcom,pmic-id = <0 … 0x4c>`. Their roots also have `xiaomi,miboard-id = <0xc 0>`.
- **DTBO table.** Header version 0, page size 4096, and id/rev/custom all 0.
  Entries sit at offsets 96 and 40888: every entry except the last is padded
  to 8 bytes. Neither AOSP mkdtboimg variant does this, so the build packs
  the table itself.
- **Entry selection.**
  - The socinfo IDs are 636 VOLCANO, 640 VOLCANO6, 641 VOLCANO6P, and 657/658
    for volcano6i/6ip.
  - Stock ships no volcano6i base, so ABL can only ever pick entry 1.
  - Entry 0 is the board overlay without techpacks, which merge_dtbs.py split
    off for 657/658 because no techpack covers those IDs.
  - The msm-id order in entry 1 (640, 641, 636) is Python frozenset order
    from merge_dtbs.py.
  - Testers can confirm with `cat /sys/devices/soc0/soc_id` and
    `androidboot.dtbo_idx` (see below).
- **Base variants.** volcano/6/6p differ only in the root model and msm-id,
  the GPU power levels and SKU codes (`qcom,kgsl-3d0` pwrlevel bins), and
  the IPA nodes, which Volcano6P (APQ) lacks.
- **Reserved memory.** All three bases have 51 `/reserved-memory` nodes, and
  they are byte-identical to stock.
- **Entry 1 hardware.** Entry 1 adds 53 distinct compatibles:
  - the techpack overlays: WCD939x/WCD9378, WSA883x, LPASS RX/TX/VA/WSA
    macros, SoundWire masters, AW882xx x2, FSA4480, AW8697 and SIH688x
    haptics, WL2866D camera PMIC, camera sensors/EEPROM/actuator/OIS/flash,
    DSI and WB displays, WCN6750;
  - the board overlay: xiaomi,touch-spi, Goodix and FPC fingerprint, ST21NFC,
    ST54 eSE, and others.

## How stock was built

The stock images come from the Qualcomm kernel-platform pipeline, and that
pipeline is now reproduced exactly:

1. **Compile.** `cpp -nostdinc -undef -D__DTS__ -x assembler-with-cpp` with
   clang r487747c, then `dtc -@ -b 0` (scripts/Makefile.lib,
   build.config.msm.common `DTC_FLAGS="-@"`).
2. **Merge.** `merge_dtbs.py --base <kernel DTBs + board overlay> --techpack
   <techpack dtbos>`. Each techpack DTBO is merged into every base, or
   board overlay, whose msm-id/board-id/pmic-id it intersects:
   - `fdtoverlay` for `.dtb`, `fdtoverlaymerge` for `.dtbo`;
   - techpacks with board-id `<0 0>` land in the base DTBs, and those with
     board-id 8 land in the board overlay;
   - the board overlay is split, so 657/658 keep a techpack-free copy.
3. **Package.** The merged DTBs are concatenated into `dtb.img`, and the
   merged DTBOs, sorted by name, are packed into `dtbo.img`.

Findings needed to reproduce the bytes:
- **Merge order.** Stock merged techpacks in plain walk order: gpu, audio,
  ipa, video, dsp, camera, camera-qrd, bt, display, and for the board
  overlay audio, camera, display, wlan.
  - libfdt appends merged nodes, so the order sets node order, and the
    phandle numbering follows merge order too.
  - QCOM's graphlib wave ordering would move WLAN to the front.
  - `scripts/amethyst-merge_dtbs.py` (QCOM's script) therefore walks in sorted
    order with a stable topological sort, and the manifest numbers the
    techpack groups.
- **Camera QRD.** Xiaomi's camera Kbuild also builds `volcano-camera-qrd.dtbo`
  with board-id `<0 0>`, so it is merged into the bases after
  `volcano-camera.dtbo`. It is the origin of `qcom,i2c_pull` on the CCI pins
  and of the stock camera phandle numbers.
- **libfdt.** The host tools must use LineageOS `external/dtc`'s libfdt.
  A distro `fdtoverlay` that dynamically links a newer system libfdt places
  merged nodes differently.

## Sources

`arch/arm64/boot/dts/amethyst/` holds only the files the build reads,
collected from the preprocessor dependency output.

| Path | Origin |
| --- | --- |
| `qcom/` | MiCode `kernel_devicetree` flourite-v-oss `4a44b8da9f6a9b9e66c61e640d090b421f9d71be` (SoC base, PMICs, pinctrl, reserved memory, thermal, board overlay `amethyst-sm7635-overlay.dts` with touch, fingerprint, NFC/eSE, charger) |
| `camera/` | MiCode `vendor_qcom_proprietary_camera-devicetree` `7b049cbf7e84572740f822bc2714a2bca9f3d91b` (`volcano-camera`, `volcano-camera-qrd`, `amethyst-sm7635-camera-sensor`) |
| `display/` | MiCode `vendor_qcom_proprietary_display-devicetree` `8662dec8ec58dd07503c7d71e98362a810c6bd2b` (`volcano-sde`, `amethyst-sde-display-mtp-overlay`, O16U panels) |
| `techpack/{audio,bt,data,dsp,graphics,video,wlan}/` | Qualcomm volcano techpack DTs from `LineageOS/android_kernel_fairphone_sm7635-devicetrees` lineage-23.2 `74222dbe129509eae6f85639f482e5b4ce321f9a` |
| `techpack/audio/amethyst-*` | **reconstructed** from stock dtbo.img (see below) |
| `techpack/bt/amethyst-bt.dts`, `techpack/wlan/amethyst-wlan.dts` | wrappers with Xiaomi's IDs around the QCOM dtsi |
| `include/` | dt-bindings headers from this kernel, audio-kernel `include/bindings` and camera-kernel `dt-bindings`, stored under their include names |
| `amethyst-dt.json` | build manifest |
| `amethyst-dt.mk` | LineageOS build hook |
| `amethyst-dt-parity.json` | explanations for the remaining differences |

The commit history separates the pristine import (`dts: amethyst: import
pristine …`, `… import volcano-camera-qrd …`) from every change.

### Changes against the imported sources

Every change is a difference that the semantic comparison found against stock:

| File | Change | Evidence |
| --- | --- | --- |
| `display/dsi-panel-o16u-*.dtsi` (5 panels) | `qcom,dsi-supported-dfps-list` 120/90/60 instead of 120/90/60/30 | stock entry 1 |
| `camera/amethyst-sm7635-camera-sensor.dtsi` | `qcom,ires-ua = <5000>` on `&pmxr2230_torch0` | stock entry 1 fragment 54 |
| `qcom/volcano.dtsi` | no `/mem-offline` | stock bases |
| `techpack/audio/volcano-audio.dtsi` | no `lpass_bt_swr`/`swr3` (newer QCOM release) | stock bases |
| `techpack/data/volcano-ipa.dtsi` | no `qcom,gfp-no-retry` (newer QCOM release) | stock bases |
| `techpack/wlan/volcano-qca6750.dtsi` | `use-nv-mac` | stock entry 1 fragment 90 |

### Reconstructed audio overlay

No audio-devicetree exists for this board. Stock merged Xiaomi's board audio
overlay into dtbo.img entry 1 as fragments 36–45, and
`scripts/amethyst-dtbo-to-dts.py` turns those fragments back into DTS:
- every label comes from `__symbols__`, external references from `__fixups__`
  and local references from `__local_fixups__`, so all phandles are symbolic
  and no labels were invented;
- properties are emitted in source order, which libfdt stores reversed.

Recompiling the output reproduces the stock fragments exactly
(`amethyst-dtcompare.py subset` / `diff`).

| File | Content |
| --- | --- |
| `amethyst-audio-lpi-pinctrl.dtsi` | LPI TLMM: DMIC0–7, WSA/RX/TX/VA SoundWire clock/data, LPI I2S/MI2S, speaker enable |
| `amethyst-audio-codec.dtsi` | LPASS RX/TX/VA/WSA macros and SWR masters, WSA883x 0221/0222, WCD939x (disabled) and WCD9378 codecs with supplies and micbias, pineapple sound card (routing, DMIC GPIOs, MBHC over USB-C, `fsa4480-i2c-handle`, SBU UART switch), LPASS core clocks, cdc pinctrl wrappers, ADSP loader variant |
| `amethyst-audio-tlmm-pinctrl.dtsi` | TLMM pin states for AW882xx IRQs, Awinic/SIH haptics reset/IRQ, SBU UART enable |
| `amethyst-audio-amp.dtsi` | SE12 I2C: AW882xx top (0x34) and bottom (0x35), FSA4480 (0x42) |
| `amethyst-haptics.dtsi` | SE7 I2C: AW8697 (0x5A) and SIH6887 (0x6B) |

Stock DT describes no FS1945 amplifier: there are only the two AW882xx
nodes.

To regenerate a piece:

```
amethyst-dtbo-to-dts.py dtbo.img:1 --fragments 37-42 -o amethyst-audio-codec.dtsi
```

### Display, touch and camera

These come from the flourite sources unchanged, apart from the two changes in
the table above. The comparison shows them equal to stock:
- **Panels.** All five O16U panels are listed in the primary DSI display,
  with their timings, brightness/HBM, ESD and FOD properties:
  - `o16u_42_02_0a_dsc_vid` and its `…_hill` variant;
  - `o16u_36_0d_0b_dsc_vid` and `…_P11`;
  - `o16u_36_02_0c_dsc_vid`.
- **Panel selection.** TLMM 139/140 appear nowhere in stock DT: ABL picks the
  panel.
- **Touch.** `xiaomi,touch-spi` carries both the Goodix 9916R and the
  FocalTech properties.
- **Camera.** The camera sensors, EEPROM, actuators, OIS, flash and WL2866D
  PMIC match stock.

## Building

Inside the ROM, `amethyst-dt.mk` runs as part of the kernel build (see
[Integration](#integration)). By hand, use host tools from LineageOS
`external/dtc` (statically linked libfdt), `ufdt_apply_overlay` and
clang r487747c:

```
scripts/amethyst-dt-build.py --manifest arch/arm64/boot/dts/amethyst/amethyst-dt.json \
    --out OUT --tools <dir with dtc fdtoverlay fdtoverlaymerge fdtget fdtput ufdt_apply_overlay> \
    --cpp <clang-r487747c>/bin/clang
```

This produces `OUT/dtb.img`, `OUT/dtbo.img`, `OUT/dtbs/*.dtb`, the merge log
and `OUT/merge-chains.json`.

## Comparison tool

`scripts/amethyst-dtcompare.py` has no dependencies. It contains an FDT
parser, an Android DTBO table parser and a libfdt-equivalent overlay applier.
On every stock base/entry pair the applier's output is byte-identical to
fdtoverlay's.

Phandle cells are compared by the node they resolve to, never by number.
Their positions come from overlay `__local_fixups__`/`__fixups__`, from a
`.phrefs` sidecar, or from replaying the merge chain (`--chains`).
- The sidecar comes from a dtc patched to dump every phandle reference when
  `DTC_PHREF_OUT` is set. The build script sets it; stock dtc ignores it.
- A cell-wise heuristic exists, but the final run used it 0 times; every
  phandle cell was compared exactly.

```
amethyst-dtcompare.py info  dtbo.img volcano.dtb ...      # catalogue (JSON)
amethyst-dtcompare.py table dtbo.img                      # DTBO table
amethyst-dtcompare.py diff  A B [--chains merge-chains.json]
amethyst-dtcompare.py subset dtbo.img:1 --fragments 36-45 -o audio.dtbo
amethyst-dtcompare.py apply volcano.dtb dtbo.img:1 -o merged.dts
amethyst-dtcompare.py parity --all-bases --ufdt ufdt_apply_overlay \
    --explain arch/arm64/boot/dts/amethyst/amethyst-dt-parity.json \
    --chains OUT/merge-chains.json \
    --base stock/volcano.dtb OUT/dtbs/volcano.dtb \
    --base stock/volcano6.dtb OUT/dtbs/volcano6.dtb \
    --base stock/volcano6p.dtb OUT/dtbs/volcano6p.dtb \
    --dtbo stock/dtbo.img OUT/dtbo.img --report parity.txt
```

`parity` compares the following, and exits 1 if any difference is not
matched by the explain file:
- node paths, property names and values with resolved phandles,
  `__symbols__`, reserved memory and `/memreserve/`, and raw bytes, for each
  base;
- the DTBO table: header, entry layout and ids;
- each entry at overlay level: fragment targets by label, merged contents,
  labels, root IDs and the order of repeated targets;
- each entry applied to every base, through the Python applier and through
  `ufdt_apply_overlay`.

**Negative test.** These mutations were each caught (`ovl`/`eff`/`base`
lines):
- swapping a phandle target with identical raw structure;
- changing an amp `reg`;
- retargeting the haptics fragment;
- dropping `use-nv-mac`;
- resizing a reserved-memory region.

## Remaining differences

The final run reported 0 unexplained differences. The explained ones are all
packaging of dtbo.img entry 1 (`amethyst-dt-parity.json`):
- **Entry 1 bytes** (dt_size 249404 → 250484). Stock's `fdtoverlaymerge` was
  a newer QCOM revision than LineageOS `external/dtc`. The LineageOS tool
  differs from stock in three ways, none of which overlay application uses:
  - it names merged fragments `fragment@(2i+n)` instead of `fragment@(n+i)`;
  - it adds a placeholder `phandle` to each copied fragment node;
  - as a result, it shifts overlay-local phandle numbers.

  Targets, contents, labels and fixups are identical. So are the trees after
  `fdtoverlay` or `ufdt_apply_overlay`.
- **Image size.** `dtbo.img` `total_size` 290292 → 291372 and file size
  290816 → 294912, which follow from the larger entry 1. Both are still padded
  to 4096.

## Integration

The device-tree changes are in
`scripts/amethyst-dt-integration/device_xiaomi_amethyst-source-dt.patch`
(against device/xiaomi/amethyst `BoardConfig.mk` and `amethyst-kernel.mk`;
`patch -p1` dry-run is clean). To apply them:

1. **Kernel.** Re-run `scripts/amethyst-los-setup.sh <LineageOS>`. It
   copies the kernel, including `arch/arm64/boot/dts/amethyst` and the
   scripts. No other setup changes are needed.
2. **Device.** Apply the patch in `device/xiaomi/amethyst`. It does three
   things:
   - **`AMETHYST_DT`.** amethyst-kernel.mk gains `AMETHYST_DT` (`source` or
     `prebuilt`; it defaults to `source` when the source kernel ships
     `amethyst-dt.mk`).
   - **Source mode.** `TARGET_NEEDS_DTBOIMAGE := true` and
     `BOARD_CUSTOM_DTBIMG_MK` / `BOARD_CUSTOM_DTBOIMG_MK` are set to
     `amethyst-dt.mk`; `BOARD_PREBUILT_DTBIMAGE_DIR` / `BOARD_PREBUILT_DTBOIMAGE`
     are dropped. `BOARD_PREBUILT_DTBOIMAGE` then takes its BoardConfigKernel
     default, `$(TARGET_OUT_INTERMEDIATES)/DTBO_OBJ/arch/arm64/boot/dtbo.img`,
     which `amethyst-dt.mk` writes.
   - **Prebuilt mode.** It keeps the stock images. A prebuilt kernel always
     uses them, and `AMETHYST_DT=prebuilt` forces them with the source
     kernel.
3. **Build.** Run `m bacon`, or `m amethyst-dt` for just the images.
   `out/target/product/amethyst/dtb.img` must have SHA-256
   `2efec97692ffdfbca62977d4c79a9047d8ed2fe0a370a0be5717bdf685660b01`.
   `dtbo.img` gets the AVB footer, so check it with the parity command
   instead, using `obj/AMETHYST_DT_OBJ/dtbo.img`.

What `amethyst-dt.mk` needs from the ROM build:
- host tools from `HOST_OUT_EXECUTABLES`: dtc, fdtoverlay, fdtoverlaymerge,
  fdtget, fdtput, ufdt_apply_overlay;
- `TARGET_KERNEL_CLANG_PATH`, for clang r487747c;
- `python3`, version 3.9 or later.

kernel.mk includes the file from both hooks, and a guard makes the second
include a no-op. A make harness that sets the kernel.mk variables builds
images identical to the reference build, and a second run does nothing.

## Hardware validation

The `dtb.img` built from source is byte-identical to stock, so
**vendor_boot does not change**. Only `dtbo.img` changes, and only in
packaging. Even so, it has to be tested on a phone.

### Non-destructive install

Install the source-DT ROM to the inactive slot with a recovery sideload
(`adb sideload lineage-…zip`). The running slot is left untouched:
- if the new slot fails to boot, A/B retries fall back to the old slot;
- otherwise switch back by hand: `fastboot getvar current-slot`, then
  `fastboot --set-active=<old slot>`.

Do not `fastboot flash` the bare `AMETHYST_DT_OBJ/dtbo.img` onto a device
whose vbmeta verifies dtbo. Use the ROM's `dtbo.img`, which has the AVB
footer, or the zip. If dtbo alone has to be swapped back:
`fastboot flash dtbo_<slot> <stock or previous dtbo.img>`.

`fastboot boot` cannot test DT changes: the DTB lives in vendor_boot and
the DTBO in dtbo.

### Checks

Collect on both builds:
- `adb root`, then `adb pull /sys/firmware/fdt fdt-<build>.dtb`. This is the
  final tree ABL handed the kernel.
- `cat /sys/devices/soc0/soc_id`. Expect 636, 640 or 641; report the value.
- `cat /proc/bootconfig /proc/cmdline | grep -o 'dtbo_idx=[0-9]*'`. Expect
  entry 1.
- `cat /proc/device-tree/model`.

Then compare `amethyst-dtcompare.py diff fdt-stock.dtb fdt-source.dtb`. Only
`/chosen` (bootargs, kaslr/rng seeds) and other values ABL fills at boot
should differ. This is the decisive check.

Functional checklist: run each item on the source-DT build and compare it
with the stock-DT build.

1. Bootloader accepts the images; device boots to the home screen; no
   `dtbo`/`DTB` errors in `dmesg | grep -i -E 'dtb|overlay|of:'`.
2. Display on all panel variants you have (CSOT, CSOT hill, TianMa);
   brightness range and HBM; 120/90/60 Hz switching; AOD/FOD icon.
3. Touch: Goodix 9916R and FocalTech variants. Taps, edges and gestures
   (double-tap wake).
4. Fingerprint enrolment and unlock (under-display).
5. Speakers: top and bottom, stereo; earpiece; all mics (call, camcorder,
   voice recorder); headset over USB-C, including mic and buttons (FSA4480).
6. Haptics: AW8697 and SIH6887 variants.
7. USB charging and data (MTP/ADB), USB-C audio accessory.
8. Wi-Fi 2.4/5 GHz with the correct MAC (`use-nv-mac`); Bluetooth audio and
   calls; FM if present.
9. NFC tag read, payment/eSE (ST21NFC, ST54).
10. Camera: all rear sensors and front, flash, torch (torch current comes
    from `qcom,ires-ua` 5000), OIS, autofocus.
11. Thermal: sustained load, then `cat /sys/class/thermal/*/temp`; no early
    throttling.
12. Suspend/resume: screen off for 10 minutes, wake by power key and by
    fingerprint; check `cat /sys/kernel/debug/wakeup_sources` or
    `dumpsys batterystats` for anomalies.

Report `soc_id`, `dtbo_idx`, the `/sys/firmware/fdt` diff, and each
checklist item as pass or fail.

## Kernel-version notes (FP6 6.1.182 migration)

- **Kernel independence.** The DT sources do not read kernel headers: the
  `include/` copies are used. The Fairphone 6 kernel's copies of these
  dt-bindings headers are identical, or add definitions only, with one
  exception: `qcom,rpmh-regulator-levels.h` drops
  `RPMH_REGULATOR_CONSUMER_LEVEL_MAX`, which `volcano-regulators.dtsi` uses.
  The vendored header keeps it. Clock, interconnect, GIC and IPCC IDs are
  identical.
- **Bindings tied to driver versions.** The FP6 tree carries newer QCOM
  techpack bindings that stock lacks and the reconstruction drops:
  `qcom,lpass-bt-swr` (`lpass_bt_swr`, alias `swr3`) and IPA
  `qcom,gfp-no-retry`. Newer FP6 module sources ignore their absence. The
  6.1.68 drivers have never seen them.
- **Version-dependent nodes.** The DT describes the stock 6.1.68 vendor
  drivers, through compatibles and properties of the QCOM 2024 release:
  - `qcom,pineapple-asoc-snd`, `qcom,wcd9378-codec`, `qcom,adreno-gpu-gen8-3-0`
    and the WCN6750 `qcom,wcn6750` ICNSS2 node;
  - the Xiaomi touch/fingerprint/haptics/amp nodes.

  When moving to FP6 modules, check each probing driver against these
  compatibles, especially audio-kernel, camera-kernel, display-drivers and
  wlan.

## Open risks

- **No hardware testing yet.** Equality with stock is proven at the DT
  level, and the dtb.img bytes are identical. Booting has not been checked.
- **Entry 1 tool difference.** Entry 1 is not byte-identical, because the
  LineageOS fdtoverlaymerge differs from Xiaomi's. If some ABL path depended
  on fragment names or fragment-node phandles, entry 1 could behave
  differently. libufdt and libfdt both ignore them.
- **Entry 0 IDs.** Entry 0 lists only volcano6i IDs; no shipped base matches
  it. This is the stock behaviour, kept as is.
- **FS1945.** Stock DT describes no FS1945 amplifier. If a hardware revision
  fits FS1945, the stock DT gives it no node either.
- **Host tools.** The build needs the CAF `fdtoverlaymerge` from LineageOS
  `external/dtc`, statically linked against its libfdt. A distro libfdt
  changes the node order (still semantically equal).
