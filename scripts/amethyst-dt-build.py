#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0
"""Build the Amethyst base DTBs and dtbo.img from source.

The pipeline is the one Qualcomm's kernel platform uses to produce stock
images:

  1. preprocess every .dts with "cpp -nostdinc -undef -D__DTS__
     -x assembler-with-cpp" and compile it with "dtc -@ -b 0"
     (scripts/Makefile.lib + build.config.msm.common, DTC_FLAGS="-@");
  2. hand the kernel-platform outputs (base .dtb and board .dtbo) and the
     techpack .dtbo files to merge_dtbs.py, which merges each techpack into
     every base whose msm-id/board-id it intersects, splitting bases when
     needed (fdtoverlay for .dtb, fdtoverlaymerge for .dtbo);
  3. concatenate the selected merged .dtb files into dtb.img (vendor_boot
     --dtb), and pack every merged .dtbo, sorted by name, into dtbo.img.

The source set is described by a JSON manifest (see
arch/arm64/boot/dts/vendor/amethyst/amethyst-dt.json).

Host tools needed in --tools (or PATH): dtc, fdtoverlay, fdtoverlaymerge,
fdtget, fdtput and ufdt_apply_overlay. The dtc must be the CAF/AOSP one that
ships fdtoverlaymerge (external/dtc).
"""

import argparse
import json
import os
import re
import shutil
import struct
import subprocess
import sys

DTC_WARN = ["-Wno-interrupt_provider", "-Wno-unit_address_vs_reg",
            "-Wno-avoid_unnecessary_addr_size", "-Wno-alias_paths",
            "-Wno-graph_child_address", "-Wno-simple_bus_reg",
            "-Wno-unique_unit_address"]
DTBO_MAGIC = 0xD7B7AB1E


def log(msg):
    sys.stderr.write(msg + "\n")
    sys.stderr.flush()


def run(cmd, env=None, **kw):
    r = subprocess.run([str(c) for c in cmd], env=env, stdout=subprocess.PIPE,
                       stderr=subprocess.STDOUT, text=True, **kw)
    if r.returncode != 0:
        sys.stderr.write(r.stdout)
        raise SystemExit("command failed (%d): %s" % (r.returncode, " ".join(map(str, cmd))))
    return r.stdout


def compile_one(ent, root, out_dir, args, env, kind):
    src = os.path.join(root, ent["src"])
    ext = ".dtb" if kind == "base" else ".dtbo"
    name = ent.get("out") or os.path.splitext(os.path.basename(src))[0] + ext
    out = os.path.join(out_dir, name)
    pp = os.path.join(args.obj, name + ".pp")
    dep = os.path.join(args.obj, name + ".d")
    incs = [os.path.dirname(src)] + [os.path.join(root, i) if not os.path.isabs(i) else i
                                     for i in args.manifest_data.get("include", []) + ent.get("include", [])]
    cpp = [args.cpp, "-E", "-Wp,-MMD," + dep, "-nostdinc"] + ["-I" + i for i in incs] + \
          ["-undef", "-D__DTS__", "-x", "assembler-with-cpp"] + \
          ["-D%s" % d for d in ent.get("defines", [])] + ["-o", pp, src]
    run(cpp, env)
    e2 = dict(env)
    e2["DTC_PHREF_OUT"] = out + ".phrefs"
    run([args.dtc, "-q", "-@", "-b", "0", "-I", "dts", "-O", "dtb"] +
        sum((["-i", i] for i in incs), []) + DTC_WARN + ["-o", out, pp], e2)
    if os.path.exists(out + ".phrefs") and os.path.getsize(out + ".phrefs") == 0 and \
            not args.keep_phrefs:
        pass
    return out


def pack_dtbo(files, out, page_size, align):
    """Android DTBO image, entries aligned to `align` (stock: 8)."""
    blobs = [open(f, "rb").read() for f in files]
    hdr_size, ent_size = 32, 32
    off = hdr_size + ent_size * len(blobs)
    entries, body = [], b""
    for i, b in enumerate(blobs):
        entries.append(struct.pack(">8I", len(b), off, 0, 0, 0, 0, 0, 0))
        pad = b""
        if i != len(blobs) - 1 and align > 1:
            pad = b"\0" * ((-len(b)) % align)
        body += b + pad
        off += len(b) + len(pad)
    total = hdr_size + ent_size * len(blobs) + len(body)
    img = struct.pack(">8I", DTBO_MAGIC, total, hdr_size, ent_size, len(blobs), hdr_size,
                      page_size, 0) + b"".join(entries) + body
    img += b"\0" * ((-len(img)) % page_size)
    with open(out, "wb") as f:
        f.write(img)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--manifest", required=True)
    ap.add_argument("--out", required=True, help="output directory (dtb.img, dtbo.img, dtbs/)")
    ap.add_argument("--tools", help="directory with dtc, fdtoverlay, fdtoverlaymerge, fdtget, fdtput, ufdt_apply_overlay")
    ap.add_argument("--cpp", default=os.environ.get("AMETHYST_DT_CPP", "clang"),
                    help="C preprocessor driver (clang or cpp)")
    ap.add_argument("--merge-script", default=os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                                           "amethyst-merge_dtbs.py"))
    ap.add_argument("--keep-phrefs", action="store_true")
    args = ap.parse_args()

    args.manifest = os.path.abspath(args.manifest)
    root = os.path.dirname(args.manifest)
    with open(args.manifest) as f:
        args.manifest_data = m = json.load(f)
    out = os.path.abspath(args.out)
    args.obj = os.path.join(out, "obj")
    base_dir = os.path.join(out, "base")
    tp_dir = os.path.join(out, "techpack")
    merged = os.path.join(out, "merged")
    for d in (args.obj, base_dir, tp_dir, merged):
        shutil.rmtree(d, ignore_errors=True)
        os.makedirs(d)

    env = os.environ.copy()
    if args.tools:
        env["PATH"] = os.path.abspath(args.tools) + os.pathsep + env["PATH"]
    args.dtc = shutil.which("dtc", path=env["PATH"]) or "dtc"
    for t in ("fdtoverlay", "fdtoverlaymerge", "fdtget", "fdtput", "ufdt_apply_overlay"):
        if not shutil.which(t, path=env["PATH"]):
            raise SystemExit("missing host tool: %s" % t)

    for ent in m["bases"]:
        log("  DTC     %s" % ent["src"])
        compile_one(ent, root, base_dir, args, env, "base")
    for ent in m.get("base_overlays", []):
        log("  DTC     %s" % ent["src"])
        compile_one(ent, root, base_dir, args, env, "overlay")
    for ent in m.get("techpacks", []):
        log("  DTC     %s" % ent["src"])
        sub = os.path.join(tp_dir, ent.get("group", "misc"))
        os.makedirs(sub, exist_ok=True)
        compile_one(ent, root, sub, args, env, "overlay")

    # merge_dtbs.py reads every .dtb/.dtbo it finds; keep sidecars elsewhere.
    side = os.path.join(out, "phrefs")
    shutil.rmtree(side, ignore_errors=True)
    for d in (base_dir, tp_dir):
        for dp, _, fs in os.walk(d):
            for fn in fs:
                if fn.endswith(".phrefs"):
                    rel = os.path.relpath(os.path.join(dp, fn), out)
                    os.makedirs(os.path.join(side, os.path.dirname(rel)), exist_ok=True)
                    os.replace(os.path.join(dp, fn), os.path.join(side, rel))

    log("  MERGE   %s" % args.merge_script)
    mlog = run([sys.executable, args.merge_script, "--base", base_dir, "--techpack", tp_dir,
                "--out", merged, "--loglevel", "debug"], env)
    with open(os.path.join(out, "merge.log"), "w") as f:
        f.write(mlog)
    # Record each merge chain so the comparison tool can replay it with
    # phandle positions (fdtoverlay output drops them).
    chains = {}
    for line in mlog.splitlines():
        mm = re.search(r"DEBUG:\s+(fdtoverlay|fdtoverlaymerge|cp) (.*)$", line)
        if not mm:
            continue
        argv = mm.group(2).split()
        if mm.group(1) == "cp":
            chains[os.path.basename(argv[1])] = [argv[0]]
        else:
            i = argv.index("-i")
            o = argv.index("-o")
            inputs = [argv[i + 1]] + [a for a in argv[i + 2:o]]
            chains[os.path.basename(argv[o + 1])] = inputs
    with open(os.path.join(out, "merge-chains.json"), "w") as f:
        json.dump({"phrefs_root": side, "out_root": out, "chains": chains}, f, indent=1)

    names = sorted(os.listdir(merged))
    dtbs = [n for n in names if n.endswith(".dtb")]
    want = m.get("dtb_image")
    if want:
        missing = [w for w in want if w not in dtbs]
        if missing:
            raise SystemExit("merged DTBs missing: %s (have %s)" % (missing, dtbs))
        dtbs = want
    with open(os.path.join(out, "dtb.img"), "wb") as f:
        for n in dtbs:
            f.write(open(os.path.join(merged, n), "rb").read())
    dtbs_dir = os.path.join(out, "dtbs")
    shutil.rmtree(dtbs_dir, ignore_errors=True)
    os.makedirs(dtbs_dir)
    for n in dtbs:
        shutil.copy(os.path.join(merged, n), dtbs_dir)
    dtbos = [os.path.join(merged, n) for n in names if n.endswith(".dtbo")]
    pack_dtbo(dtbos, os.path.join(out, "dtbo.img"), m.get("page_size", 4096), m.get("dtbo_align", 8))
    log("  IMAGE   dtb.img: %s" % " ".join(dtbs))
    log("  IMAGE   dtbo.img: %s" % " ".join(os.path.basename(d) for d in dtbos))


if __name__ == "__main__":
    main()
