Amethyst touch A/B kit
======================

What it does
------------
It swaps the touch kernel modules on a running phone and records, for each
combination, what the kernel, the touch service and Android see while you
touch the screen. Nothing is flashed and nothing is written outside
/data/local/tmp/touchkit. A reboot puts the phone back to normal.

Combinations, in this order:
  1 rom      modules the ROM booted with
  2 source   new source-built goodix_core + xiaomi_touch (the fix to test)
  3 mixed-a  stock goodix_core + source xiaomi_touch
  4 mixed-b  source goodix_core + stock xiaomi_touch
  5 stock    stock goodix_core + stock xiaomi_touch (reference)
The kernel is expected to refuse 3 and 4 (their internal interfaces differ).
The script records the refusal and moves on. A refusal is a valid result.

Requirements
------------
- The LineageOS test build (debuggable, so "adb root" works), with the
  Goodix (CSOT) panel. The script stops if it sees no goodix_ts device.
- A PC with adb and bash (Linux, macOS, WSL or Git Bash).
- USB debugging enabled and this PC authorized.
- Phone unlocked, screen on, charger unplugged.

Run it
------
  cd <this folder>
  ./run-touch-ab.sh            (or: ./run-touch-ab.sh -s <serial>)

For each phase the script:
  - stops the touch service, swaps the modules and restarts the service;
  - asks you to press Enter, then touch and swipe all over the screen for
    15 seconds (use several fingers at times);
  - turns the screen off and on, and asks you to touch again;
  - asks whether touch worked (answer y, n or partly).
It takes about 5 minutes. If the screen does not respond, keep touching
anyway during the 15-second windows: the kernel logs are what matter.

Afterwards
----------
- Send back the file printed at the end: logs/<date>.tar.gz
- Reboot the phone ("adb reboot"). The stock modules stay loaded until
  then on purpose: unloading stock goodix_core is not safe.

If something goes wrong
-----------------------
- "Could not unload ... safely": something still uses the touch modules.
  The script stops without forcing anything. Reboot and run it again.
- If the phone freezes or reboots, send the logs folder anyway, plus the
  output of "adb shell cat /sys/fs/pstore/console-ramoops*" after it boots.
- To run single phases: ./run-touch-ab.sh --only source,stock
