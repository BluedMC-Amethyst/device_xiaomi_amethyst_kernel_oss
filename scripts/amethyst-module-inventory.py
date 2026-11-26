#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-only
"""Inventory the stock Amethyst kernel modules against this tree's build.

For every stock .ko (vendor_boot, vendor_dlkm, system_dlkm) record its hash,
modinfo, device-tree compatibles, firmware names, imports and exports, the
load lists that use it, and whether a module of the same name is built from
source. For modules that are built, diff the interfaces that userspace, the
device tree and other modules see: compatibles and aliases, module
parameters, exported symbols, imported symbols and firmware names. A missing
item in the source build is a lead to investigate, not proof of a bug.

Writes INVENTORY.md and inventory.json to the output directory. Stock binaries
are only read; nothing from them is copied.

Requires pyelftools.
"""

import argparse
import hashlib
import json
import re
from pathlib import Path

from elftools.elf.elffile import ELFFile

FW_RE = re.compile(rb"[\w./+-]{3,}\.(?:bin|fw|img|mbn|elf|ucode|hex|cfg|ini|dat|txt)\x00")
COMPAT_RE = re.compile(r"^of:N\*T\*C(.+?)(?:C\*)?$")


def read_elf(path):
    data = path.read_bytes()
    info = {"modinfo": {}, "imports": [], "exports": [], "firmware_strings": []}
    with path.open("rb") as stream:
        elf = ELFFile(stream)
        sec = elf.get_section_by_name(".modinfo")
        if sec is not None:
            for item in sec.data().split(b"\0"):
                if b"=" in item:
                    key, value = item.decode(errors="replace").split("=", 1)
                    info["modinfo"].setdefault(key, []).append(value)
        symtab = elf.get_section_by_name(".symtab")
        exports, undefined = set(), set()
        if symtab is not None:
            for sym in symtab.iter_symbols():
                if sym.name.startswith("__ksymtab_"):
                    exports.add(sym.name[len("__ksymtab_"):])
                elif (sym["st_shndx"] == "SHN_UNDEF" and sym.name
                      and sym["st_info"]["bind"] in ("STB_GLOBAL", "STB_WEAK")):
                    undefined.add(sym.name)
        info["exports"] = sorted(exports)
        info["imports"] = sorted(undefined)
    fws = {m.group(0)[:-1].decode() for m in FW_RE.finditer(data)}
    fws |= set(info["modinfo"].get("firmware", []))
    info["firmware_strings"] = sorted(fws)
    info["sha256"] = hashlib.sha256(data).hexdigest()
    info["size"] = len(data)
    info["signed"] = data.endswith(b"~Module signature appended~\n")
    return info


def compatibles(modinfo):
    out = set()
    for alias in modinfo.get("alias", []):
        m = COMPAT_RE.match(alias)
        if m:
            out.add(m.group(1))
    return sorted(out)


def params(modinfo):
    return sorted({p.split(":", 1)[0] for p in modinfo.get("parmtype", [])})


def norm(name):
    return name.replace("-", "_")


def load_list(path):
    if not path.exists():
        return []
    return [Path(line.strip()).name for line in path.read_text().splitlines() if line.strip()]


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("stock", type=Path, help="stock modules dir (vendor_boot/, vendor_dlkm/, system_dlkm/)")
    ap.add_argument("built", type=Path, nargs="+",
                    help="dirs searched recursively for source-built .ko files")
    ap.add_argument("--lists", type=Path,
                    help="device modules/ dir with modules.list.* to report current load lists")
    ap.add_argument("--out", type=Path, required=True, help="output directory")
    args = ap.parse_args()

    stock = {}
    for part in ("vendor_boot", "vendor_dlkm", "system_dlkm"):
        for ko in sorted((args.stock / part).rglob("*.ko")):
            entry = stock.setdefault(norm(ko.stem), {"name": ko.stem, "copies": []})
            entry["copies"].append({"partition": part, "path": str(ko)})
    stock_lists = {
        "stock_first_stage": load_list(args.stock / "vendor_boot/modules.load"),
        "stock_recovery": load_list(args.stock / "vendor_boot/modules.load.recovery"),
        "stock_vendor_dlkm": load_list(args.stock / "vendor_dlkm/modules.load"),
    }
    sysdirs = sorted((args.stock / "system_dlkm").glob("*/modules.load"))
    stock_lists["stock_system_dlkm"] = load_list(sysdirs[0]) if sysdirs else []
    cur_lists = {}
    if args.lists:
        for f in sorted(args.lists.glob("modules.list.*")):
            cur_lists["now_" + f.name.split(".")[-1]] = load_list(f)

    built = {}
    for root in args.built:
        for ko in root.rglob("*.ko"):
            if "/scripts/" in str(ko) or ko.is_symlink():
                continue
            built.setdefault(norm(ko.stem), ko)

    report = []
    for key in sorted(stock):
        entry = stock[key]
        first = Path(entry["copies"][0]["path"])
        info = read_elf(first)
        hashes = {read_elf(Path(c["path"]))["sha256"] for c in entry["copies"][1:]}
        mi = info["modinfo"]
        rec = {
            "name": entry["name"],
            "partitions": sorted({c["partition"] for c in entry["copies"]}),
            "copies_identical": not hashes or hashes == {info["sha256"]},
            "sha256": info["sha256"],
            "size": info["size"],
            "signed": info["signed"],
            "license": (mi.get("license") or [""])[0],
            "author": mi.get("author", []),
            "description": (mi.get("description") or [""])[0],
            "depends": [d for d in (mi.get("depends") or [""])[0].split(",") if d],
            "compatibles": compatibles(mi),
            "aliases": sorted(mi.get("alias", [])),
            "params": params(mi),
            "firmware": info["firmware_strings"],
            "exports": info["exports"],
            "imports": info["imports"],
            "stock_lists": [k for k, v in stock_lists.items() if first.name in v],
            "current_lists": [k for k, v in cur_lists.items() if first.name in v],
        }
        src = built.get(key)
        if src is None:
            rec["status"] = "missing"
        else:
            b = read_elf(src)
            bmi = b["modinfo"]
            rec["status"] = "built"
            rec["built_path"] = str(src)
            diff = {}
            for label, s_items, b_items in (
                ("compatibles", rec["compatibles"], compatibles(bmi)),
                ("aliases", rec["aliases"], sorted(bmi.get("alias", []))),
                ("params", rec["params"], params(bmi)),
                ("exports", rec["exports"], b["exports"]),
                ("imports", rec["imports"], b["imports"]),
                ("firmware", rec["firmware"], b["firmware_strings"]),
            ):
                s_set, b_set = set(s_items), set(b_items)
                if s_set != b_set:
                    diff[label] = {"stock_only": sorted(s_set - b_set),
                                   "source_only": sorted(b_set - s_set)}
            rec["diff"] = diff
        report.append(rec)

    args.out.mkdir(parents=True, exist_ok=True)
    (args.out / "inventory.json").write_text(json.dumps(report, indent=1) + "\n")

    missing = [r for r in report if r["status"] == "missing"]
    built_recs = [r for r in report if r["status"] == "built"]
    # Interface gaps that matter most: what the DT, userspace and other
    # modules can observe.
    def gap(r, key):
        return r.get("diff", {}).get(key, {}).get("stock_only", [])

    lines = [
        "# Amethyst stock kernel module inventory",
        "",
        "Generated by `scripts/amethyst-module-inventory.py`; do not edit by hand.",
        "Stock binaries are not tracked; their SHA-256 hashes identify them.",
        "",
        f"- Stock modules (unique names): {len(report)}",
        f"- Built from source: {len(built_recs)}",
        f"- Missing (no source build): {len(missing)}",
        "",
        "Load lists overlap; their sizes do not add up to the module count.",
        "",
        "| List | Entries |",
        "| --- | --- |",
    ]
    for k, v in list(stock_lists.items()) + list(cur_lists.items()):
        lines.append(f"| {k} | {len(v)} |")
    lines += ["", "## Missing modules", "",
              "| Module | Stock lists | Depends | Compatibles | Firmware | Exports | Description |",
              "| --- | --- | --- | --- | --- | --- | --- |"]
    for r in missing:
        lines.append("| {} | {} | {} | {} | {} | {} | {} |".format(
            r["name"], ", ".join(x.replace("stock_", "") for x in r["stock_lists"]) or "-",
            ", ".join(r["depends"]) or "-", ", ".join(r["compatibles"]) or "-",
            ", ".join(r["firmware"]) or "-", len(r["exports"]),
            r["description"].replace("|", "/") or "-"))
    lines += ["", "## Users of missing modules' exports", "",
              "Stock modules that import a symbol exported only by a missing module.", ""]
    owner = {}
    for r in missing:
        for sym in r["exports"]:
            owner[sym] = r["name"]
    users = {}
    for r in report:
        for sym in r["imports"]:
            if sym in owner and owner[sym] != r["name"]:
                users.setdefault(owner[sym], set()).add(r["name"])
    for name in sorted(users):
        lines.append(f"- **{name}** used by: {', '.join(sorted(users[name]))}")
    if not users:
        lines.append("None.")
    lines += ["", "## Interface differences in source-built modules", "",
              "Items present in the stock module but not in the source build.", "",
              "| Module | Compatibles | Params | Exports | Firmware | Imports |",
              "| --- | --- | --- | --- | --- | --- |"]
    for r in built_recs:
        g = {k: gap(r, k) for k in ("compatibles", "params", "exports", "firmware", "imports")}
        if any(g.values()):
            def fmt(items, limit=6):
                if not items:
                    return "-"
                s = ", ".join(items[:limit])
                return s + (f" (+{len(items) - limit})" if len(items) > limit else "")
            lines.append(f"| {r['name']} | {fmt(g['compatibles'])} | {fmt(g['params'])} | "
                         f"{fmt(g['exports'])} | {fmt(g['firmware'])} | {len(g['imports'])} |")
    lines += ["", "## All stock modules", "",
              "| Module | Status | Partitions | SHA-256 | License |",
              "| --- | --- | --- | --- | --- |"]
    for r in report:
        lines.append(f"| {r['name']} | {r['status']} | {', '.join(r['partitions'])} | "
                     f"`{r['sha256'][:16]}` | {r['license'] or '-'} |")
    (args.out / "INVENTORY.md").write_text("\n".join(lines) + "\n")
    print(f"{len(report)} stock modules: {len(built_recs)} built, {len(missing)} missing")
    print(f"wrote {args.out}/INVENTORY.md and inventory.json")


if __name__ == "__main__":
    main()
