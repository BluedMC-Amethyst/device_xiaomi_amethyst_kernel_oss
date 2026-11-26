#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-only
"""Check offline whether stock Amethyst modules will load on a rebuilt kernel.

Repeats the kernel's load-time checks (kernel/module/main.c) for each module
that will actually be loaded: the modules.load lists plus everything they
depend on through modinfo "depends". Like modprobe, it follows dependencies
even when a module is left out of modules.load.

  * vermagic (with modversions only the text after the release must match)
  * sizeof(struct module) (.gnu.linkonce.this_module)
  * every import exists, from vmlinux or from a module loaded with it
  * every import's CRC matches its provider
  * no export duplicates vmlinux or another loaded module
  * GKI MODULE_SIG_PROTECT: unsigned modules may not export protected symbols,
    nor use a signed module's export unless it is on an unprotected list
  * first stage: vendor_boot modules may depend only on vendor_boot modules

First-stage init calls LOG(FATAL) if any vendor_boot module fails to load, so
every error in the vendor_boot stage means a boot stuck at the logo.

Requires pyelftools. Exit status is 1 if any error is found.
"""

import argparse
import struct
import sys
from pathlib import Path

from elftools.elf.elffile import ELFFile

SIG_MAGIC = b"~Module signature appended~\n"


class Module:
    def __init__(self, path):
        self.path = path
        self.name = path.stem
        self.imports = {}
        self.exports = {}
        self.modinfo = {}
        with path.open("rb") as stream:
            data = stream.read()
            stream.seek(0)
            elf = ELFFile(stream)
            self.this_module_size = None
            sec = elf.get_section_by_name(".gnu.linkonce.this_module")
            if sec is not None:
                self.this_module_size = sec["sh_size"]
            sec = elf.get_section_by_name("__versions")
            if sec is not None:
                raw = sec.data()
                for off in range(0, len(raw), 64):
                    crc = struct.unpack_from("<Q", raw, off)[0]
                    name = raw[off + 8:off + 64].split(b"\0", 1)[0].decode()
                    self.imports[name] = crc & 0xFFFFFFFF
            sec = elf.get_section_by_name(".modinfo")
            if sec is not None:
                for item in sec.data().split(b"\0"):
                    if b"=" in item:
                        key, value = item.decode(errors="replace").split("=", 1)
                        self.modinfo.setdefault(key, value)
            symtab = elf.get_section_by_name(".symtab")
            crcs = {}
            names = set()
            for sym in symtab.iter_symbols():
                if sym.name.startswith("__ksymtab_"):
                    names.add(sym.name[len("__ksymtab_"):])
                elif sym.name.startswith("__crc_") and isinstance(sym["st_shndx"], int):
                    target = elf.get_section(sym["st_shndx"])
                    crcs[sym.name[len("__crc_"):]] = struct.unpack_from(
                        "<I", target.data(), sym["st_value"])[0]
            for name in names:
                self.exports[name] = crcs.get(name)
        self.signed = data.endswith(SIG_MAGIC)
        self.depends = [d for d in self.modinfo.get("depends", "").split(",") if d]

    @property
    def vermagic_tail(self):
        magic = self.modinfo.get("vermagic", "")
        return magic[magic.find(" "):] if " " in magic else magic


def read_symvers(path):
    vmlinux = {}
    for line in path.read_text().splitlines():
        fields = line.split("\t")
        if len(fields) >= 3 and fields[2] == "vmlinux":
            vmlinux[fields[1]] = int(fields[0], 16)
    return vmlinux


def read_list(path):
    if not path.exists():
        return set()
    names = set()
    for line in path.read_text().splitlines():
        line = line.strip()
        if line and not line.startswith(("#", "[")):
            names.add(line.split()[0])
    return names


def load_dir(path, kind):
    mods = {}
    for ko in sorted(path.rglob("*.ko")):
        mod = Module(ko)
        mod.kind = kind
        mods[mod.name] = mod
        mods.setdefault(mod.name.replace("-", "_"), mod)
    return mods


def manifest(path):
    if not path.exists():
        return []
    return [Path(line.strip()).stem for line in path.read_text().splitlines() if line.strip()]


def closure(names, pool, errors, stage):
    order, seen = [], set()
    stack = list(names)
    while stack:
        name = stack.pop()
        mod = pool.get(name) or pool.get(name.replace("-", "_"))
        if mod is None:
            errors.append(f"{stage}: {name}.ko is listed or depended on but not present")
            continue
        if mod.name in seen:
            continue
        seen.add(mod.name)
        order.append(mod)
        stack.extend(mod.depends)
    return order


def main():
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("stock", type=Path,
                        help="stock module dir with vendor_boot/, vendor_dlkm/, system_dlkm/")
    parser.add_argument("out", type=Path, help="kernel build output dir")
    parser.add_argument("--system-dlkm", type=Path,
                        help="system_dlkm release dir to use instead of the stock one "
                             "(e.g. from amethyst-stage-system-dlkm.sh)")
    parser.add_argument("--vendor-boot-load", type=Path,
                        help="vendor_boot modules.load to check (e.g. a filtered one)")
    parser.add_argument("--vendor-dlkm-load", type=Path,
                        help="vendor_dlkm modules.load to check (e.g. a filtered one)")
    args = parser.parse_args()

    kernel = Path(__file__).resolve().parent.parent
    vmlinux = read_symvers(args.out / "Module.symvers")
    if not vmlinux:
        sys.exit(f"{args.out}/Module.symvers has no vmlinux exports")
    release = (args.out / "include/config/kernel.release").read_text().strip()
    protected = read_list(kernel / "android/abi_gki_protected_exports_aarch64")
    unprotected = set()
    for path in (kernel / "android").glob("abi_gki_aarch64_*"):
        unprotected |= read_list(path)

    # Reference vermagic and struct module size from a module of this build.
    ref = next((p for p in args.out.rglob("*.ko") if "/scripts/" not in str(p)), None)
    ref_mod = Module(ref) if ref else None

    vendor_boot = load_dir(args.stock / "vendor_boot", "vendor_boot")
    vendor_dlkm = load_dir(args.stock / "vendor_dlkm", "vendor_dlkm")
    if args.system_dlkm:
        sysdir = args.system_dlkm
    else:
        dirs = sorted((args.stock / "system_dlkm").glob("*/"))
        sysdir = dirs[0] if dirs else args.stock / "system_dlkm"
    system_dlkm = load_dir(sysdir, "system_dlkm")
    # A module's signature is only trusted if this build signed it.
    trusted_sys = sysdir.name == release

    errors, warnings = [], []
    vb_list = manifest(args.vendor_boot_load or args.stock / "vendor_boot/modules.load")
    vd_list = manifest(args.vendor_dlkm_load or args.stock / "vendor_dlkm/modules.load")
    sys_list = manifest(sysdir / "modules.load")

    # Stage 1 (first-stage init): only vendor_boot is reachable.
    stage1 = closure(vb_list, vendor_boot, errors, "vendor_boot")
    # Stage 2: system_dlkm first (gki.modprobe), then vendor_dlkm, which can
    # use anything already loaded.
    pool2 = dict(vendor_boot)
    pool2.update(system_dlkm)
    pool2.update(vendor_dlkm)
    stage_sys = closure(sys_list, system_dlkm, errors, "system_dlkm")
    stage2 = closure(vd_list, pool2, errors, "vendor_dlkm")

    def sig_ok(mod):
        return mod.kind == "system_dlkm" and trusted_sys and mod.signed

    def check(stage, mods, loaded_before):
        owners = {}
        for mod in loaded_before + mods:
            for sym in mod.exports:
                owners.setdefault(sym, []).append(mod)
        for mod in mods:
            where = f"{stage}: {mod.name}.ko"
            if ref_mod:
                if mod.vermagic_tail != ref_mod.vermagic_tail:
                    errors.append(f"{where}: vermagic '{mod.vermagic_tail.strip()}' != "
                                  f"'{ref_mod.vermagic_tail.strip()}'")
                if mod.this_module_size != ref_mod.this_module_size:
                    errors.append(f"{where}: struct module size {mod.this_module_size} != "
                                  f"{ref_mod.this_module_size}")
            for sym, crc in mod.imports.items():
                provider = None
                if sym in vmlinux:
                    want = vmlinux[sym]
                else:
                    cands = [o for o in owners.get(sym, []) if o is not mod]
                    if not cands:
                        errors.append(f"{where}: unknown symbol {sym}")
                        continue
                    provider = cands[0]
                    want = provider.exports[sym]
                if want is not None and want != crc:
                    errors.append(f"{where}: CRC mismatch {sym} module 0x{crc:08x} "
                                  f"provider {'vmlinux' if provider is None else provider.name} "
                                  f"0x{want:08x}")
                if (provider is not None and not sig_ok(mod) and sig_ok(provider)
                        and sym not in unprotected):
                    errors.append(f"{where}: unsigned use of {provider.name}'s protected "
                                  f"export {sym}")
            for sym in mod.exports:
                if not sig_ok(mod) and sym in protected:
                    errors.append(f"{where}: unsigned module exports protected symbol {sym}")
                if sym in vmlinux:
                    errors.append(f"{where}: exports duplicate symbol {sym} (owned by vmlinux)")
                others = sorted({o.name for o in owners[sym] if o.name != mod.name})
                if others:
                    warnings.append(f"{where}: export {sym} also in {', '.join(others)}")

    check("vendor_boot", stage1, [])
    check("system_dlkm", stage_sys, stage1)
    done = {m.name for m in stage1 + stage_sys}
    check("vendor_dlkm", [m for m in stage2 if m.name not in done], stage1 + stage_sys)

    print(f"kernel {release}: {len(vmlinux)} vmlinux exports")
    print(f"vendor_boot: {len(vb_list)} listed, {len(stage1)} loaded with dependencies")
    print(f"system_dlkm: {sysdir} ({'signed by this build' if trusted_sys else 'NOT signed by this build'})")
    print(f"vendor_dlkm: {len(vd_list)} listed, {len(stage2)} in dependency closure")
    for line in sorted(set(warnings)):
        print("warning: " + line)
    for line in sorted(set(errors)):
        print("ERROR: " + line)
    fatal = [e for e in errors if e.startswith("vendor_boot")]
    print(f"\n{len(set(errors))} errors ({len(set(fatal))} in vendor_boot: "
          f"{'first-stage init will FAIL' if fatal else 'first stage OK'})")
    return int(bool(errors))


if __name__ == "__main__":
    raise SystemExit(main())
