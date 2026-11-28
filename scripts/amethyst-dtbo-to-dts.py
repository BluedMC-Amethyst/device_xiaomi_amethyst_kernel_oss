#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0
"""Turn fragments of a compiled overlay back into maintainable DTS source.

Used to reconstruct device-tree sources that were never published (the
Amethyst audio and WLAN overlays) from the stock dtbo.img. Every label is
recovered from __symbols__, every external reference from __fixups__ and
every local reference from __local_fixups__, so recompiling the output with
"dtc -@" reproduces the same fragments, symbols and fixups.

  amethyst-dtbo-to-dts.py dtbo.img:1 --fragments 36-45 -o out.dtsi
  amethyst-dtbo-to-dts.py dtbo.img:1 --fragments 90 --split DIR

Output is one "&label { ... };" block per fragment, in fragment order, which
dtc compiles back to one fragment each.
"""

import argparse
import importlib.util
import os
import re
import struct
import sys

_spec = importlib.util.spec_from_file_location(
    "dtcompare", os.path.join(os.path.dirname(os.path.abspath(__file__)), "amethyst-dtcompare.py"))
dc = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(dc)

NAME_RE = re.compile(r"^[A-Za-z0-9,._+#?-]+$")


def parse_ranges(s, n):
    out = []
    for part in s.split(","):
        if "-" in part:
            a, b = part.split("-")
            out.extend(range(int(a), int(b) + 1))
        else:
            out.append(int(part))
    return [i for i in out if 0 <= i < n]


class Emitter:
    def __init__(self, t):
        self.t = t
        self.ph = t.phandle_map()
        self.labels = {}
        for lbl, p in t.symbols().items():
            self.labels.setdefault(p, []).append(lbl)
        for v in self.labels.values():
            v.sort()
        # external refs: (path, prop, offset) -> label
        self.ext = {}
        fx = t.root.children.get("__fixups__")
        if fx:
            for lbl, v in fx.props.items():
                for ent in dc.strlist(v) or []:
                    p, pn, off = ent.rsplit(":", 2)
                    self.ext[(p, pn, int(off))] = lbl

    def ref(self, path, pn, off, val):
        lbl = self.ext.get((path, pn, off))
        if lbl:
            return "&" + lbl
        n = self.ph.get(val)
        if n is None:
            raise SystemExit("%s:%s+%d: phandle %#x not found" % (path, pn, off, val))
        lb = self.labels.get(n.path())
        if lb:
            return "&" + lb[0]
        return "&{%s}" % n.path()

    @staticmethod
    def num(v):
        return "%d" % v if v < 1024 else "0x%x" % v

    def value(self, path, pn, b):
        if len(b) == 0:
            return None
        pos = self.t.phrefs.get((path, pn), set())
        if pos and len(b) % 4 == 0:
            cells = struct.unpack(">%dI" % (len(b) // 4), b)
            parts = []
            for i, c in enumerate(cells):
                parts.append(self.ref(path, pn, i * 4, c) if i * 4 in pos else self.num(c))
            return "<" + " ".join(parts) + ">"
        sl = dc.strlist(b)
        if sl is not None and (len(b) % 4 != 0 or all(len(s) >= 2 and re.search(r"[A-Za-z_]", s) for s in sl)):
            return ", ".join('"%s"' % s.replace("\\", "\\\\").replace('"', '\\"') for s in sl)
        if len(b) % 4 == 0:
            cells = struct.unpack(">%dI" % (len(b) // 4), b)
            return "<" + " ".join(self.num(c) for c in cells) + ">"
        return "[" + " ".join("%02x" % x for x in b) + "]"

    def node(self, n, path, ind, out, name=None):
        pad = "\t" * ind
        lbls = "".join("%s: " % l for l in self.labels.get(path, []))
        out.append("%s%s%s {" % (pad, lbls, name if name is not None else n.name))
        # libfdt's merge stores overlay properties in reverse; emit them in
        # source order so a rebuild stores them exactly as stock does.
        for pn, b in reversed(list(n.props.items())):
            if pn in ("phandle", "linux,phandle"):
                continue
            v = self.value(path, pn, b)
            out.append("%s\t%s;" % (pad, pn) if v is None else "%s\t%s = %s;" % (pad, pn, v))
        for cn, c in n.children.items():
            if n.props:
                out.append("")
            self.node(c, path + "/" + cn, ind + 1, out)
        out.append("%s};" % pad)

    def fragment(self, frag):
        key = dc.fragment_key(self.t, frag)
        ov = frag.children["__overlay__"]
        base = "/%s/__overlay__" % frag.name
        if key.startswith("&"):
            head = key
        elif key.startswith("path:"):
            head = "&{%s}" % key[5:]
        else:
            raise SystemExit("unsupported fragment target %s" % key)
        out = []
        self.node(ov, base, 0, out, name=head)
        return "\n".join(out) + "\n"


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("blob")
    ap.add_argument("--fragments", required=True, help="indices, e.g. 36-45,90")
    ap.add_argument("-o", "--output", default="-")
    a = ap.parse_args()
    t = dc.load(a.blob, sidecar=False)
    frs = t.fragments()
    e = Emitter(t)
    text = "\n".join(e.fragment(frs[i]) for i in parse_ranges(a.fragments, len(frs)))
    if a.output == "-":
        sys.stdout.write(text)
    else:
        with open(a.output, "w") as f:
            f.write(text)


if __name__ == "__main__":
    main()
