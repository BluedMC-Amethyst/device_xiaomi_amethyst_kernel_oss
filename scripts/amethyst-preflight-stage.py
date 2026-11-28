#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-only
"""Lay out installed modules the way the ROM ships them, for preflight.

Usage: amethyst-preflight-stage.py <staging lib/modules/<release>> \
           <device modules dir> <out dir>

Mirrors LineageOS kernel.mk with TARGET_AUTO_COLLECT_KERNEL_MODULE_DEPS:
  system_dlkm/<release>/  modules.list.system_dlkm and their dependencies
  vendor_boot/            modules.list.first_stage + modules.list.recovery
                          and their dependencies (BOOT_KERNEL_MODULES)
  vendor_dlkm/            every module that is not in system_dlkm
Each directory gets the modules.load the ROM uses (vendor_boot also gets
modules.load.recovery). The result is the "stock" argument of
amethyst-preflight-modules.py. Modules named in a list but not built are
reported, as kernel.mk would fail on them.
"""

import shutil
import subprocess
import sys
from pathlib import Path


def depends(ko):
    out = subprocess.run(["modinfo", "-F", "depends", str(ko)],
                         capture_output=True, text=True, check=True).stdout
    return [d for d in out.strip().split(",") if d]


def norm(name):
    return Path(name).stem.replace("-", "_")


def main():
    staging, devmods, out = map(Path, sys.argv[1:4])
    release = staging.name
    pool = {}
    for ko in staging.rglob("*.ko"):
        pool[norm(ko.name)] = ko

    def lst(name):
        p = devmods / f"modules.list.{name}"
        return [l.strip() for l in p.read_text().splitlines() if l.strip() and not l.startswith("#")]

    missing = []

    def closure(names):
        seen, stack = {}, [norm(n) for n in names]
        while stack:
            n = stack.pop()
            if n in seen:
                continue
            ko = pool.get(n)
            if ko is None:
                missing.append(n)
                continue
            seen[n] = ko
            stack.extend(norm(d) for d in depends(ko))
        return seen

    first, recovery = lst("first_stage"), lst("recovery")
    vdlkm, sysd = lst("vendor_dlkm"), lst("system_dlkm")
    sys_set = closure(sysd)
    boot_set = closure(first + recovery)

    if out.exists():
        shutil.rmtree(out)
    dirs = {"system_dlkm": out / "system_dlkm" / release,
            "vendor_boot": out / "vendor_boot", "vendor_dlkm": out / "vendor_dlkm"}
    for d in dirs.values():
        d.mkdir(parents=True)
    for ko in sys_set.values():
        shutil.copy2(ko, dirs["system_dlkm"])
    for ko in boot_set.values():
        shutil.copy2(ko, dirs["vendor_boot"])
    sys_names = set(sys_set)
    for n, ko in pool.items():
        if n not in sys_names:
            shutil.copy2(ko, dirs["vendor_dlkm"])
    (dirs["system_dlkm"] / "modules.load").write_text("".join(f"{m}\n" for m in sysd))
    (dirs["vendor_boot"] / "modules.load").write_text("".join(f"{m}\n" for m in first))
    (dirs["vendor_boot"] / "modules.load.recovery").write_text("".join(f"{m}\n" for m in recovery))
    (dirs["vendor_dlkm"] / "modules.load").write_text("".join(f"{m}\n" for m in vdlkm))
    print(f"staged {len(pool)} modules: system_dlkm {len(sys_set)}, "
          f"vendor_boot {len(boot_set)}, vendor_dlkm {len(pool) - len(sys_names)}")
    if missing:
        print("NOT BUILT (listed or depended on):", " ".join(sorted(set(missing))))
    return 1 if missing else 0


sys.exit(main())
