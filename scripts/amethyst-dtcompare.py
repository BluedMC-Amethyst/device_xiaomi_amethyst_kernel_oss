#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0
"""Semantic device-tree comparison for the Amethyst DT reconstruction.

No third-party modules: this file carries its own FDT parser, Android DTBO
table parser and an overlay applier that follows libfdt's fdt_overlay_apply()
(the algorithm ABL and ufdt_apply_overlay use), while tracking which property
cells hold phandles so values are compared by the node they point at instead
of by raw phandle number.

Inputs
  foo.dtb / foo.dtbo        a flattened tree
  dtbo.img:N                entry N of an Android DTBO image
  dtb.img:N                 Nth FDT of a concatenated DTB image

Phandle positions come from, in order: the blob's own __local_fixups__ /
__fixups__ (overlays), a "<blob>.phrefs" sidecar written by the patched dtc
(DTC_PHREF_OUT=<file>, see docs/amethyst-drivers/devicetree.md), and as a
last resort a cell-wise heuristic that is flagged as such in the report.

Sub-commands
  info   BLOB...                       catalogue IDs, fragments, symbols, ...
  table  DTBO.IMG                      DTBO table metadata
  diff   A B                           semantic diff of two trees/overlays
  apply  BASE OVERLAY -o OUT.dts       apply an overlay, print the result
  parity --base S R --dtbo S R ...     full stock-vs-rebuilt parity report

Every sub-command that diffs accepts --explain FILE (JSON list of
{"match": regex over the difference line, "reason": text}); differences that
match are reported as explained. The exit status is 1 when any unexplained
difference remains.
"""

import argparse
import json
import os
import re
import struct
import sys
from collections import OrderedDict

FDT_MAGIC = 0xD00DFEED
DTBO_MAGIC = 0xD7B7AB1E
FDT_BEGIN_NODE, FDT_END_NODE, FDT_PROP, FDT_NOP, FDT_END = 1, 2, 3, 4, 9
SPECIAL = ("__symbols__", "__fixups__", "__local_fixups__")


# --------------------------------------------------------------------------
# FDT model
# --------------------------------------------------------------------------
class Node:
    __slots__ = ("name", "props", "children", "parent")

    def __init__(self, name, parent=None):
        self.name = name
        self.props = OrderedDict()
        self.children = OrderedDict()
        self.parent = parent

    def path(self):
        if self.parent is None:
            return "/"
        pp = self.parent.path()
        return (pp if pp != "/" else "") + "/" + self.name

    def walk(self):
        yield self
        for c in self.children.values():
            yield from c.walk()

    def child(self, name, create=False):
        c = self.children.get(name)
        if c is None and create:
            c = Node(name, self)
            self.children[name] = c
        return c


class Tree:
    def __init__(self, root, label="?"):
        self.root = root
        self.label = label
        # (path, prop) -> set(byte offsets of phandle cells)
        self.phrefs = {}
        self.phref_source = {}
        self.header = {}

    # lookup helpers -------------------------------------------------------
    def lookup(self, path):
        if path in ("", "/"):
            return self.root
        n = self.root
        for comp in path.strip("/").split("/"):
            n = n.children.get(comp)
            if n is None:
                return None
        return n

    def phandle_map(self):
        m = {}
        for n in self.root.walk():
            for pn in ("phandle", "linux,phandle"):
                v = n.props.get(pn)
                if v is not None and len(v) == 4:
                    m[struct.unpack(">I", v)[0]] = n
        return m

    def max_phandle(self):
        m = self.phandle_map()
        return max(m) if m else 0

    def symbols(self):
        s = self.root.children.get("__symbols__")
        if not s:
            return {}
        return {k: cstr(v) for k, v in s.props.items()}

    def fragments(self):
        return [c for c in self.root.children.values() if "__overlay__" in c.children]

    def is_overlay(self):
        return bool(self.fragments())


def cstr(b):
    return b.split(b"\0")[0].decode("latin-1")


def strlist(b):
    if not b or b[-1:] != b"\0":
        return None
    parts = b[:-1].split(b"\0")
    out = []
    for p in parts:
        if not p:
            return None
        try:
            s = p.decode("ascii")
        except UnicodeDecodeError:
            return None
        if not all(32 <= ord(ch) < 127 for ch in s):
            return None
        out.append(s)
    return out


def parse_fdt(blob, label="?"):
    magic, totalsize, off_struct, off_strings, off_rsv, version, last_comp, boot_cpu, size_strings, size_struct = \
        struct.unpack_from(">10I", blob, 0)
    if magic != FDT_MAGIC:
        raise ValueError("%s: not an FDT (magic %#x)" % (label, magic))
    strings = blob[off_strings:off_strings + size_strings]
    pos = off_struct
    root = None
    stack = []
    while True:
        tok = struct.unpack_from(">I", blob, pos)[0]
        pos += 4
        if tok == FDT_BEGIN_NODE:
            end = blob.index(b"\0", pos)
            name = blob[pos:end].decode("latin-1")
            pos = (end + 4) & ~3
            if not stack:
                root = Node("", None)
                stack.append(root)
            else:
                n = Node(name, stack[-1])
                stack[-1].children[name] = n
                stack.append(n)
        elif tok == FDT_END_NODE:
            stack.pop()
        elif tok == FDT_PROP:
            ln, nameoff = struct.unpack_from(">II", blob, pos)
            pos += 8
            pname = strings[nameoff:strings.index(b"\0", nameoff)].decode("latin-1")
            stack[-1].props[pname] = bytes(blob[pos:pos + ln])
            pos = (pos + ln + 3) & ~3
        elif tok == FDT_NOP:
            continue
        elif tok == FDT_END:
            break
        else:
            raise ValueError("%s: bad FDT token %d at %#x" % (label, tok, pos - 4))
    rsv = []
    p = off_rsv
    while True:
        a, s = struct.unpack_from(">QQ", blob, p)
        p += 16
        if a == 0 and s == 0:
            break
        rsv.append((a, s))
    t = Tree(root, label)
    t.header = {"totalsize": totalsize, "version": version, "last_comp_version": last_comp,
                "boot_cpuid_phys": boot_cpu, "memreserve": rsv}
    collect_overlay_phrefs(t)
    return t


def collect_overlay_phrefs(t):
    """Phandle positions recorded by dtc in __local_fixups__ / __fixups__."""
    lf = t.root.children.get("__local_fixups__")
    if lf:
        def rec(fnode, path):
            for pn, v in fnode.props.items():
                offs = struct.unpack(">%dI" % (len(v) // 4), v)
                t.phrefs.setdefault((path, pn), set()).update(offs)
                t.phref_source[(path, pn)] = "local_fixups"
            for cn, c in fnode.children.items():
                rec(c, (path if path != "/" else "") + "/" + cn)
        rec(lf, "/")
    fx = t.root.children.get("__fixups__")
    if fx:
        for lbl, v in fx.props.items():
            for ent in strlist(v) or []:
                path, pn, off = ent.rsplit(":", 2)
                t.phrefs.setdefault((path, pn), set()).add(int(off))
                t.phref_source[(path, pn)] = "fixups"


def load_sidecar(t, fn):
    with open(fn) as f:
        for line in f:
            line = line.rstrip("\n")
            if not line:
                continue
            path, pn, off = line.split("\t")
            t.phrefs.setdefault((path, pn), set()).add(int(off))
            t.phref_source.setdefault((path, pn), "sidecar")


def parse_dtbo_table(blob):
    hdr = struct.unpack_from(">8I", blob, 0)
    magic, total, hsize, esize, count, eoff, page, ver = hdr
    if magic != DTBO_MAGIC:
        raise ValueError("not a DTBO image (magic %#x)" % magic)
    entries = []
    for i in range(count):
        e = struct.unpack_from(">8I", blob, eoff + i * esize)
        entries.append({"dt_size": e[0], "dt_offset": e[1], "id": e[2], "rev": e[3],
                        "custom": list(e[4:8])})
    return {"magic": magic, "total_size": total, "header_size": hsize, "dt_entry_size": esize,
            "dt_entry_count": count, "dt_entries_offset": eoff, "page_size": page,
            "version": ver, "file_size": len(blob), "entries": entries}


def split_dtb_image(blob):
    out, pos = [], 0
    while pos + 8 <= len(blob):
        magic, size = struct.unpack_from(">II", blob, pos)
        if magic != FDT_MAGIC:
            break
        out.append(blob[pos:pos + size])
        pos += size
    return out


CHAINS = {}


def load_chains(fn):
    """merge-chains.json from amethyst-dt-build.py: replay merges for phrefs."""
    with open(fn) as f:
        CHAINS["_"] = json.load(f)


def _chain_tree(path):
    """Load a compiled input with its sidecar from the build's phrefs dir."""
    c = CHAINS.get("_")
    t = load(path, sidecar=False)
    if c:
        rel = os.path.relpath(path, c["out_root"])
        side = os.path.join(c["phrefs_root"], rel + ".phrefs")
        if os.path.exists(side):
            load_sidecar(t, side)
    return t


def chain_phrefs(t, fn):
    """If fn is a merge_dtbs output, replay its chain to recover positions."""
    c = CHAINS.get("_")
    if not c:
        return
    chain = c["chains"].get(os.path.basename(fn))
    if not chain:
        return
    base = _chain_tree(chain[0])
    for ov in chain[1:]:
        o = _chain_tree(ov)
        if base.is_overlay():
            # fdtoverlaymerge output keeps fixups; nothing to replay.
            return
        base = apply_overlay(base, o)
    for k, v in base.phrefs.items():
        n = t.lookup(k[0])
        bn = base.lookup(k[0])
        if n is not None and bn is not None and n.props.get(k[1]) is not None and \
                len(n.props[k[1]]) == len(bn.props.get(k[1], b"")):
            t.phrefs.setdefault(k, set(v))
            t.phref_source.setdefault(k, "chain")


def load(spec, sidecar=True):
    """Load "file", "file.img:N" (dtbo or concatenated dtb)."""
    fn, idx = spec, None
    m = re.match(r"^(.*):(\d+)$", spec)
    if m and not os.path.exists(spec):
        fn, idx = m.group(1), int(m.group(2))
    blob = open(fn, "rb").read()
    magic = struct.unpack_from(">I", blob, 0)[0]
    if magic == DTBO_MAGIC:
        tab = parse_dtbo_table(blob)
        if idx is None:
            raise ValueError("%s is a DTBO image; use %s:N" % (fn, fn))
        e = tab["entries"][idx]
        t = parse_fdt(blob[e["dt_offset"]:e["dt_offset"] + e["dt_size"]], spec)
        t.dtbo_entry = e
    else:
        if idx is not None:
            t = parse_fdt(split_dtb_image(blob)[idx], spec)
        else:
            t = parse_fdt(blob, spec)
    if sidecar and idx is None:
        chain_phrefs(t, fn)
    if sidecar:
        for cand in (spec + ".phrefs", fn + ".phrefs" if idx is None else None,
                     re.sub(r"\.dtbo?$", "", fn) + ".phrefs" if idx is None else None):
            if cand and os.path.exists(cand):
                load_sidecar(t, cand)
                break
    return t


# --------------------------------------------------------------------------
# Overlay application (libfdt fdt_overlay_apply semantics)
# --------------------------------------------------------------------------
def u32_at(b, off):
    return struct.unpack_from(">I", b, off)[0]


def put_u32(b, off, v):
    return b[:off] + struct.pack(">I", v) + b[off + 4:]


def deep_copy(n, parent=None):
    c = Node(n.name, parent)
    c.props = OrderedDict(n.props)
    for k, v in n.children.items():
        c.children[k] = deep_copy(v, c)
    return c


def copy_tree(t):
    nt = Tree(deep_copy(t.root), t.label)
    nt.phrefs = {k: set(v) for k, v in t.phrefs.items()}
    nt.phref_source = dict(t.phref_source)
    nt.header = dict(t.header)
    return nt


class OverlayError(Exception):
    pass


def apply_overlay(base, ovl):
    """Return a new Tree = base + ovl, following libfdt."""
    base = copy_tree(base)
    ov = copy_tree(ovl)
    delta = base.max_phandle()
    bmap = base.phandle_map()

    # 1. renumber overlay phandles
    for n in ov.root.walk():
        for pn in ("phandle", "linux,phandle"):
            v = n.props.get(pn)
            if v is not None and len(v) == 4:
                pv = u32_at(v, 0)
                if pv not in (0, 0xFFFFFFFF):
                    n.props[pn] = struct.pack(">I", pv + delta)
    # 2. local references
    lf = ov.root.children.get("__local_fixups__")
    local_pos = []
    if lf:
        def rec(fnode, onode, path):
            for pn, v in fnode.props.items():
                if pn not in onode.props:
                    raise OverlayError("local fixup for missing %s:%s" % (path, pn))
                for off in struct.unpack(">%dI" % (len(v) // 4), v):
                    onode.props[pn] = put_u32(onode.props[pn], off, u32_at(onode.props[pn], off) + delta)
                    local_pos.append((path, pn, off))
            for cn, c in fnode.children.items():
                oc = onode.children.get(cn)
                if oc is None:
                    raise OverlayError("local fixup for missing node %s/%s" % (path, cn))
                rec(c, oc, (path if path != "/" else "") + "/" + cn)
        rec(lf, ov.root, "/")
    # 3. external references
    syms = base.symbols()
    fx = ov.root.children.get("__fixups__")
    if fx:
        for lbl, v in fx.props.items():
            if lbl not in syms:
                raise OverlayError("unresolved symbol %s" % lbl)
            tn = base.lookup(syms[lbl])
            if tn is None:
                raise OverlayError("symbol %s -> missing %s" % (lbl, syms[lbl]))
            ph = tn.props.get("phandle") or tn.props.get("linux,phandle")
            if ph is None:
                raise OverlayError("symbol %s (%s) has no phandle" % (lbl, syms[lbl]))
            for ent in strlist(v) or []:
                path, pn, off = ent.rsplit(":", 2)
                on = ov.lookup(path)
                if on is None or pn not in on.props:
                    raise OverlayError("fixup target %s missing" % ent)
                on.props[pn] = put_u32(on.props[pn], int(off), u32_at(ph, 0))
    bmap = base.phandle_map()

    def frag_target(frag):
        fpath = "/" + frag.name
        if "target" in frag.props:
            tph = u32_at(frag.props["target"], 0)
            tgt = bmap.get(tph)
            if tgt is None:
                raise OverlayError("%s: target phandle %#x not in base" % (fpath, tph))
            return tgt
        if "target-path" in frag.props:
            tp = cstr(frag.props["target-path"])
            tgt = base.lookup(tp)
            if tgt is None:
                aliases = base.root.children.get("aliases")
                if aliases and tp in aliases.props:
                    tgt = base.lookup(cstr(aliases.props[tp]))
            if tgt is None:
                raise OverlayError("%s: target-path %s not in base" % (fpath, tp))
            return tgt
        raise OverlayError("%s: no target" % fpath)

    # 3b. overlay_prevent_phandle_overwrite: an overlay node that lands on a
    # base node which already has a phandle takes the base phandle, and every
    # local reference to the overlay's number is rewritten.
    def prevent(tnode, onode):
        tph = tnode.props.get("phandle") or tnode.props.get("linux,phandle")
        oph = onode.props.get("phandle")
        if tph is not None and oph is not None and tph != oph:
            old, new = u32_at(oph, 0), u32_at(tph, 0)
            for (path, pn, off) in local_pos:
                n = ov.lookup(path)
                if u32_at(n.props[pn], off) == old:
                    n.props[pn] = put_u32(n.props[pn], off, new)
            for pn in ("phandle", "linux,phandle"):
                if pn in onode.props:
                    onode.props[pn] = struct.pack(">I", new)
        for cn, oc in onode.children.items():
            tc = tnode.children.get(cn)
            if tc is not None:
                prevent(tc, oc)

    for frag in ov.fragments():
        prevent(frag_target(frag), frag.children["__overlay__"])

    # 4. merge fragments
    frag_targets = {}
    for frag in ov.fragments():
        fpath = "/" + frag.name
        tgt = frag_target(frag)
        frag_targets[fpath] = tgt.path()
        merge_node(base, tgt, frag.children["__overlay__"], ov, fpath + "/__overlay__")

    # 5. symbols
    osym = ov.root.children.get("__symbols__")
    if osym:
        bsym = base.root.child("__symbols__", create=True)
        for lbl, v in osym.props.items():
            p = cstr(v)
            m = re.match(r"^(/[^/]+)/__overlay__(/.*)?$", p)
            if not m or m.group(1) not in frag_targets:
                continue
            tp = frag_targets[m.group(1)]
            np = (tp if tp != "/" else "") + (m.group(2) or "")
            bsym.props[lbl] = np.encode() + b"\0"
    return base


def merge_node(base, tgt, onode, ov, opath):
    tpath = tgt.path()
    for pn, v in onode.props.items():
        tgt.props[pn] = v
        key = (tpath, pn)
        base.phrefs.pop(key, None)
        base.phref_source.pop(key, None)
        if (opath, pn) in ov.phrefs:
            base.phrefs[key] = set(ov.phrefs[(opath, pn)])
            base.phref_source[key] = ov.phref_source.get((opath, pn), "overlay")
    for cn, c in onode.children.items():
        tc = tgt.child(cn, create=True)
        merge_node(base, tc, c, ov, opath + "/" + cn)


# --------------------------------------------------------------------------
# Canonical values and diff
# --------------------------------------------------------------------------
def fmt_raw(b):
    sl = strlist(b)
    if sl is not None:
        return json.dumps(sl if len(sl) > 1 else sl[0])
    if len(b) == 0:
        return "<empty>"
    if len(b) % 4 == 0:
        return "<" + " ".join("%#x" % x for x in struct.unpack(">%dI" % (len(b) // 4), b)) + ">"
    return "[" + b.hex() + "]"


class Canon:
    """Canonical view of one tree for comparison."""

    def __init__(self, t, oracle=None):
        self.t = t
        self.ph = t.phandle_map()
        self.oracle = oracle or {}

    def positions(self, path, pn):
        p = self.t.phrefs.get((path, pn))
        if p is not None:
            return p, self.t.phref_source.get((path, pn), "?")
        p = self.oracle.get((path, pn))
        if p is not None:
            return p, "oracle"
        return None, None

    def target(self, v):
        n = self.ph.get(v)
        return n.path() if n is not None else None

    def render(self, path, pn, b, pos):
        if pn in ("phandle", "linux,phandle"):
            return "<phandle>"
        if pos and len(b) % 4 == 0:
            cells = struct.unpack(">%dI" % (len(b) // 4), b)
            out = []
            for i, c in enumerate(cells):
                if i * 4 in pos:
                    tp = self.target(c)
                    out.append("&{%s}" % tp if tp else "&?%#x" % c)
                else:
                    out.append("%#x" % c)
            return "<" + " ".join(out) + ">"
        return fmt_raw(b)


def compare_values(ca, cb, path, pn, va, vb):
    """Return (equal, how, ra, rb)."""
    if pn in ("phandle", "linux,phandle"):
        return True, "phandle", "<phandle>", "<phandle>"
    pa, sa = ca.positions(path, pn)
    pb, sb = cb.positions(path, pn)
    # Borrow positions from the side that has them (stock bases have none).
    if pa is None and pb is not None and len(va) == len(vb):
        pa, sa = pb, "borrowed"
    if pb is None and pa is not None and len(va) == len(vb):
        pb, sb = pa, "borrowed"
    if pa is not None or pb is not None:
        ra = ca.render(path, pn, va, pa or set())
        rb = cb.render(path, pn, vb, pb or set())
        return ra == rb, "exact", ra, rb
    if va == vb:
        return True, "raw", None, None
    # heuristic: same length, every differing cell resolves to the same node
    if len(va) == len(vb) and len(va) % 4 == 0 and len(va) > 0:
        A = struct.unpack(">%dI" % (len(va) // 4), va)
        B = struct.unpack(">%dI" % (len(vb) // 4), vb)
        ok = True
        for x, y in zip(A, B):
            if x != y:
                tx, ty = ca.target(x), cb.target(y)
                if tx is None or tx != ty:
                    ok = False
                    break
        if ok:
            return True, "heuristic", None, None
    return False, "raw", fmt_raw(va), fmt_raw(vb)


class Diff:
    def __init__(self, explain=None):
        self.lines = []          # (kind, text)
        self.explain = explain or []
        self.stats = {"heuristic": 0, "exact": 0, "raw": 0, "borrowed": 0}

    def add(self, text):
        self.lines.append(text)

    def classify(self):
        expl, unexpl = [], []
        for ln in self.lines:
            for e in self.explain:
                if re.search(e["match"], ln):
                    expl.append((ln, e["reason"]))
                    break
            else:
                unexpl.append(ln)
        return expl, unexpl


def diff_trees(a, b, d, oracle=None, skip_special=True, prefix=""):
    ca, cb = Canon(a, oracle), Canon(b, oracle)

    def rec(na, nb, path):
        for pn in list(na.props.keys()) + [k for k in nb.props if k not in na.props]:
            if pn not in nb.props:
                d.add("%s-prop %s : %s = %s" % (prefix, path, pn,
                      ca.render(path, pn, na.props[pn], ca.positions(path, pn)[0])))
                continue
            if pn not in na.props:
                d.add("%s+prop %s : %s = %s" % (prefix, path, pn,
                      cb.render(path, pn, nb.props[pn], cb.positions(path, pn)[0])))
                continue
            eq, how, ra, rb = compare_values(ca, cb, path, pn, na.props[pn], nb.props[pn])
            d.stats[how] = d.stats.get(how, 0) + 1
            if not eq:
                d.add("%s~prop %s : %s : %s -> %s" % (prefix, path, pn, ra, rb))
        for cn in list(na.children.keys()) + [k for k in nb.children if k not in na.children]:
            if skip_special and path == "/" and cn in SPECIAL:
                continue
            cp = (path if path != "/" else "") + "/" + cn
            if cn not in nb.children:
                d.add("%s-node %s (%d props, %d subnodes)" % (prefix, cp, len(na.children[cn].props),
                      sum(1 for _ in na.children[cn].walk()) - 1))
                continue
            if cn not in na.children:
                d.add("%s+node %s (%d props, %d subnodes)" % (prefix, cp, len(nb.children[cn].props),
                      sum(1 for _ in nb.children[cn].walk()) - 1))
                continue
            rec(na.children[cn], nb.children[cn], cp)

    rec(a.root, b.root, "/")
    # symbols: label -> path
    sa, sb = a.symbols(), b.symbols()
    for k in sorted(set(sa) | set(sb)):
        if k not in sb:
            d.add("%s-symbol %s = %s" % (prefix, k, sa[k]))
        elif k not in sa:
            d.add("%s+symbol %s = %s" % (prefix, k, sb[k]))
        elif sa[k] != sb[k]:
            d.add("%s~symbol %s : %s -> %s" % (prefix, k, sa[k], sb[k]))
    if a.header.get("memreserve") != b.header.get("memreserve"):
        d.add("%s~memreserve %s -> %s" % (prefix, a.header.get("memreserve"), b.header.get("memreserve")))


# --------------------------------------------------------------------------
# Overlay-level (fragment) comparison
# --------------------------------------------------------------------------
def fragment_key(t, frag):
    """Stable name for a fragment target: &label, or a path."""
    fpath = "/" + frag.name
    if "target-path" in frag.props:
        return "path:" + cstr(frag.props["target-path"])
    fx = t.root.children.get("__fixups__")
    if fx:
        for lbl, v in fx.props.items():
            for ent in strlist(v) or []:
                if ent == fpath + ":target:0":
                    return "&" + lbl
    # local target (fragment pointing at a node in the same overlay)
    tph = u32_at(frag.props["target"], 0)
    n = t.phandle_map().get(tph)
    return "local:" + (n.path() if n else "%#x" % tph)


def overlay_view(t):
    """Merge fragments by target; return OrderedDict key -> (Tree, path-map)."""
    out = OrderedDict()
    order = []
    for frag in t.fragments():
        k = fragment_key(t, frag)
        order.append(k)
        if k not in out:
            out[k] = Node("", None)
        rel = out[k]

        def m(dst, src, spath, dpath):
            for pn, v in src.props.items():
                dst.props[pn] = v
                if (spath, pn) in t.phrefs:
                    view_phrefs[(k, dpath, pn)] = t.phrefs[(spath, pn)]
                else:
                    view_phrefs.pop((k, dpath, pn), None)
            for cn, c in src.children.items():
                m(dst.child(cn, create=True), c, spath + "/" + cn, (dpath if dpath != "/" else "") + "/" + cn)
        view_phrefs = overlay_view.phrefs.setdefault(id(t), {})
        m(rel, frag.children["__overlay__"], "/" + frag.name + "/__overlay__", "/")
    return out, order


overlay_view.phrefs = {}


def diff_overlays(a, b, d, prefix="ovl "):
    va, oa = overlay_view(a)
    vb, ob = overlay_view(b)
    pa, pb = overlay_view.phrefs[id(a)], overlay_view.phrefs[id(b)]
    # Phandle targets inside an overlay resolve either to overlay-local nodes
    # (map phandle -> "<fragment-key><relative path>") or to external labels.
    def ovl_targets(t, view):
        ph = {}
        for frag in t.fragments():
            k = fragment_key(t, frag)
            for n in frag.children["__overlay__"].walk():
                v = n.props.get("phandle")
                if v:
                    rp = n.path().split("/__overlay__", 1)[1] or "/"
                    ph[u32_at(v, 0)] = "%s%s" % (k, rp)
        ext = {}
        fx = t.root.children.get("__fixups__")
        if fx:
            for lbl, v in fx.props.items():
                for ent in strlist(v) or []:
                    p, pn, off = ent.rsplit(":", 2)
                    ext[(p, pn, int(off))] = "&" + lbl
        return ph, ext

    pha, exta = ovl_targets(a, va)
    phb, extb = ovl_targets(b, vb)

    def render(t, k, path, pn, v, phrefs, ph):
        if pn in ("phandle", "linux,phandle"):
            return "<phandle>"
        pos = phrefs.get((k, path, pn))
        if not pos or len(v) % 4:
            return fmt_raw(v)
        cells = struct.unpack(">%dI" % (len(v) // 4), v)
        out = []
        for i, c in enumerate(cells):
            if i * 4 in pos:
                out.append("&{%s}" % ph.get(c, "EXT"))
            else:
                out.append("%#x" % c)
        return "<" + " ".join(out) + ">"

    # External references are zero in the blob; resolve them by label via fixups.
    def ext_render(t, k, path, pn, v, phrefs, ph, ext):
        r = render(t, k, path, pn, v, phrefs, ph)
        if "EXT" not in r:
            return r
        # find any fragment path whose merged prop maps here; walk fixups
        labels = []
        for (p, ppn, off), lbl in sorted(ext.items(), key=lambda x: x[0][2]):
            if ppn != pn:
                continue
            m = re.match(r"^/([^/]+)/__overlay__(/.*)?$", p)
            if not m:
                continue
            frag = t.root.children[m.group(1)]
            if fragment_key(t, frag) == k and (m.group(2) or "/") == path:
                labels.append((off, lbl))
        cells = struct.unpack(">%dI" % (len(v) // 4), v)
        pos = phrefs.get((k, path, pn), set())
        lab = dict(labels)
        out = []
        for i, c in enumerate(cells):
            if i * 4 in pos:
                out.append(lab.get(i * 4) or "&{%s}" % ph.get(c, "?%#x" % c))
            else:
                out.append("%#x" % c)
        return "<" + " ".join(out) + ">"

    for k in list(va.keys()) + [x for x in vb if x not in va]:
        if k not in vb:
            d.add("%s-fragment %s" % (prefix, k))
            continue
        if k not in va:
            d.add("%s+fragment %s" % (prefix, k))
            continue

        def rec(na, nb, path):
            for pn in list(na.props) + [x for x in nb.props if x not in na.props]:
                if pn not in nb.props:
                    d.add("%s-prop %s %s : %s" % (prefix, k, path, pn))
                elif pn not in na.props:
                    d.add("%s+prop %s %s : %s" % (prefix, k, path, pn))
                else:
                    ra = ext_render(a, k, path, pn, na.props[pn], pa, pha, exta)
                    rb = ext_render(b, k, path, pn, nb.props[pn], pb, phb, extb)
                    if ra != rb:
                        d.add("%s~prop %s %s : %s : %s -> %s" % (prefix, k, path, pn, ra, rb))
            for cn in list(na.children) + [x for x in nb.children if x not in na.children]:
                cp = (path if path != "/" else "") + "/" + cn
                if cn not in nb.children:
                    d.add("%s-node %s %s" % (prefix, k, cp))
                elif cn not in na.children:
                    d.add("%s+node %s %s" % (prefix, k, cp))
                else:
                    rec(na.children[cn], nb.children[cn], cp)
        rec(va[k], vb[k], "/")
    # root (metadata) properties
    for pn in sorted(set(a.root.props) | set(b.root.props)):
        x, y = a.root.props.get(pn), b.root.props.get(pn)
        if x != y:
            d.add("%s~root %s : %s -> %s" % (prefix, pn, fmt_raw(x) if x is not None else "-",
                                               fmt_raw(y) if y is not None else "-"))
    # symbols, by label -> (fragment key + relative path)
    def sym_view(t):
        out = {}
        for lbl, p in t.symbols().items():
            m = re.match(r"^/([^/]+)/__overlay__(/.*)?$", p)
            if m and m.group(1) in t.root.children:
                out[lbl] = fragment_key(t, t.root.children[m.group(1)]) + (m.group(2) or "")
            else:
                out[lbl] = p
        return out
    sa, sb = sym_view(a), sym_view(b)
    for lbl in sorted(set(sa) | set(sb)):
        if sa.get(lbl) != sb.get(lbl):
            d.add("%s~symbol %s : %s -> %s" % (prefix, lbl, sa.get(lbl, "-"), sb.get(lbl, "-")))
    # targets order (only matters when several fragments hit one target)
    if [x for x in oa] != [x for x in ob]:
        dup = {x for x in oa if oa.count(x) > 1} | {x for x in ob if ob.count(x) > 1}
        if any([y for y in oa if y == x] != [y for y in ob if y == x] for x in dup):
            d.add("%s~fragment-order for repeated targets %s" % (prefix, sorted(dup)))


# --------------------------------------------------------------------------
# Catalogue
# --------------------------------------------------------------------------
def u32list(b):
    return list(struct.unpack(">%dI" % (len(b) // 4), b)) if b and len(b) % 4 == 0 else None


def catalogue(t):
    r = t.root
    info = OrderedDict()
    for pn in ("model", "compatible", "qcom,msm-id", "qcom,board-id", "qcom,pmic-id", "qcom,pmic-id-size"):
        if pn in r.props:
            v = r.props[pn]
            sl = strlist(v)
            info[pn] = sl if sl and pn in ("model", "compatible") else ["%#x" % x for x in u32list(v) or []]
    info["nodes"] = sum(1 for _ in r.walk())
    info["properties"] = sum(len(n.props) for n in r.walk())
    info["phandles"] = len(t.phandle_map())
    info["symbols"] = len(t.symbols())
    info["header"] = t.header
    fr = t.fragments()
    if fr:
        info["fragments"] = len(fr)
        tk = [fragment_key(t, f) for f in fr]
        info["fragment_targets"] = tk
        fx = r.children.get("__fixups__")
        info["external_labels"] = sorted(fx.props) if fx else []
    rm = t.lookup("/reserved-memory")
    if rm:
        info["reserved_memory"] = OrderedDict(
            (c.name, {k: fmt_raw(v) for k, v in c.props.items() if k in ("reg", "size", "alignment", "alloc-ranges", "compatible", "no-map", "reusable", "status")})
            for c in rm.children.values())
    comp = {}
    for n in r.walk():
        sl = strlist(n.props.get("compatible", b""))
        if sl:
            comp[n.path()] = sl
    info["compatibles"] = comp
    st = {}
    for n in r.walk():
        if "status" in n.props:
            st[n.path()] = cstr(n.props["status"])
    info["status"] = st
    return info


# --------------------------------------------------------------------------
# CLI
# --------------------------------------------------------------------------
def load_explain(fn):
    if not fn:
        return []
    with open(fn) as f:
        return json.load(f)


def emit(d, out, title):
    expl, unexpl = d.classify()
    out.write("== %s\n" % title)
    out.write("   cells compared: %s\n" % ", ".join("%s=%d" % kv for kv in sorted(d.stats.items())))
    out.write("   differences: %d (explained %d, unexplained %d)\n" % (len(d.lines), len(expl), len(unexpl)))
    for ln in unexpl:
        out.write("   UNEXPLAINED %s\n" % ln)
    for ln, why in expl:
        out.write("   explained   %s\n                [%s]\n" % (ln, why))
    return len(unexpl)


def build_oracle(specs):
    o = {}
    for s in specs or []:
        t = load(s)
        for k, v in t.phrefs.items():
            o.setdefault(k, set()).update(v)
    return o


def cmd_info(a):
    res = OrderedDict()
    for s in a.blobs:
        fn = re.sub(r":\d+$", "", s)
        blob = open(fn if os.path.exists(fn) else s, "rb").read()
        if struct.unpack_from(">I", blob, 0)[0] == DTBO_MAGIC and not re.search(r":\d+$", s):
            tab = parse_dtbo_table(blob)
            res[s] = {"dtbo_table": tab}
            for i in range(tab["dt_entry_count"]):
                res["%s:%d" % (s, i)] = catalogue(load("%s:%d" % (s, i)))
        else:
            res[s] = catalogue(load(s))
    json.dump(res, sys.stdout, indent=1)
    sys.stdout.write("\n")


def cmd_table(a):
    json.dump(parse_dtbo_table(open(a.img, "rb").read()), sys.stdout, indent=1)
    sys.stdout.write("\n")


def cmd_diff(a):
    if a.chains:
        load_chains(a.chains)
    ta, tb = load(a.a), load(a.b)
    d = Diff(load_explain(a.explain))
    oracle = build_oracle(a.oracle)
    if ta.is_overlay() and tb.is_overlay() and not a.raw:
        diff_overlays(ta, tb, d)
    else:
        diff_trees(ta, tb, d, oracle)
    return 1 if emit(d, sys.stdout, "%s vs %s" % (a.a, a.b)) else 0


def write_dts(n, out, ind=0):
    pad = "\t" * ind
    out.write("%s%s {\n" % (pad, n.name or "/"))
    for pn, v in n.props.items():
        out.write("%s\t%s = %s;\n" % (pad, pn, fmt_raw(v)) if v else "%s\t%s;\n" % (pad, pn))
    for c in n.children.values():
        write_dts(c, out, ind + 1)
    out.write("%s};\n" % pad)


def write_fdt(t):
    """Serialise a Tree (version 17)."""
    strings, stroff = bytearray(), {}
    struct_b = bytearray()

    def soff(name):
        if name not in stroff:
            stroff[name] = len(strings)
            strings.extend(name.encode() + b"\0")
        return stroff[name]

    def rec(n):
        struct_b.extend(struct.pack(">I", FDT_BEGIN_NODE))
        nm = n.name.encode() + b"\0"
        struct_b.extend(nm + b"\0" * ((-len(nm)) % 4))
        for pn, v in n.props.items():
            struct_b.extend(struct.pack(">III", FDT_PROP, len(v), soff(pn)))
            struct_b.extend(v + b"\0" * ((-len(v)) % 4))
        for c in n.children.values():
            rec(c)
        struct_b.extend(struct.pack(">I", FDT_END_NODE))
    rec(t.root)
    struct_b.extend(struct.pack(">I", FDT_END))
    rsv = b"".join(struct.pack(">QQ", a, s) for a, s in t.header.get("memreserve", [])) + b"\0" * 16
    off_rsv = 40
    off_struct = off_rsv + len(rsv)
    off_strings = off_struct + len(struct_b)
    total = off_strings + len(strings)
    hdr = struct.pack(">10I", FDT_MAGIC, total, off_struct, off_strings, off_rsv, 17, 16,
                      t.header.get("boot_cpuid_phys", 0), len(strings), len(struct_b))
    return hdr + rsv + bytes(struct_b) + bytes(strings)


def subset_overlay(t, indices):
    """New overlay holding only the given fragment indices (by position)."""
    t = copy_tree(t)
    frs = t.fragments()
    keep = {"/" + frs[i].name for i in indices}
    for f in frs:
        if "/" + f.name not in keep:
            del t.root.children[f.name]

    def kept(p):
        return any(p == k or p.startswith(k + "/") for k in keep)
    sym = t.root.children.get("__symbols__")
    if sym:
        for k in [k for k, v in sym.props.items() if not kept(cstr(v))]:
            del sym.props[k]
    fx = t.root.children.get("__fixups__")
    if fx:
        for k in list(fx.props):
            ents = [e for e in strlist(fx.props[k]) or [] if kept(e.rsplit(":", 2)[0])]
            if ents:
                fx.props[k] = b"".join(e.encode() + b"\0" for e in ents)
            else:
                del fx.props[k]
    lf = t.root.children.get("__local_fixups__")
    if lf:
        for k in list(lf.children):
            if "/" + k not in keep:
                del lf.children[k]
    t.phrefs = {k: v for k, v in t.phrefs.items() if kept(k[0])}
    return t


def cmd_subset(a):
    from_t = load(a.blob, sidecar=False)
    idx = []
    for part in a.fragments.split(","):
        if "-" in part:
            x, y = part.split("-")
            idx.extend(range(int(x), int(y) + 1))
        else:
            idx.append(int(part))
    with open(a.output, "wb") as f:
        f.write(write_fdt(subset_overlay(from_t, idx)))


def cmd_apply(a):
    t = apply_overlay(load(a.base), load(a.overlay))
    with open(a.output, "w") if a.output != "-" else sys.stdout as f:
        f.write("/dts-v1/;\n\n")
        write_dts(t.root, f)


def cmd_parity(a):
    """--base STOCK REBUILT (repeat); --dtbo STOCK_IMG REBUILT_IMG."""
    if a.chains:
        load_chains(a.chains)
    explain = load_explain(a.explain)
    out = open(a.report, "w") if a.report else sys.stdout
    total_unexpl = 0
    summary = []
    oracle = build_oracle(a.oracle)
    pairs = []
    for sb, rb in a.base:
        ts, tr = load(sb), load(rb)
        d = Diff(explain)
        diff_trees(ts, tr, d, oracle, prefix="base ")
        if open(sb, "rb").read() != open(rb, "rb").read():
            d.add("base %s raw-bytes differ" % os.path.basename(sb))
        n = emit(d, out, "base %s vs %s" % (sb, rb))
        summary.append(("base " + os.path.basename(sb), len(d.lines), n))
        total_unexpl += n
        pairs.append((sb, rb, ts, tr))
    if a.dtbo:
        simg, rimg = a.dtbo
        st, rt = parse_dtbo_table(open(simg, "rb").read()), parse_dtbo_table(open(rimg, "rb").read())
        d = Diff(explain)
        for k in ("magic", "header_size", "dt_entry_size", "dt_entry_count", "dt_entries_offset",
                  "page_size", "version"):
            if st[k] != rt[k]:
                d.add("table ~%s %s -> %s" % (k, st[k], rt[k]))
        for i, (es, er) in enumerate(zip(st["entries"], rt["entries"])):
            for k in ("id", "rev", "custom"):
                if es[k] != er[k]:
                    d.add("table entry%d ~%s %s -> %s" % (i, k, es[k], er[k]))
            # packaging: entry layout and raw bytes (not semantic, but must be explained)
            for k in ("dt_offset", "dt_size"):
                if es[k] != er[k]:
                    d.add("table entry%d ~%s %s -> %s" % (i, k, es[k], er[k]))
            sb = open(simg, "rb").read()[es["dt_offset"]:es["dt_offset"] + es["dt_size"]]
            rb_ = open(rimg, "rb").read()[er["dt_offset"]:er["dt_offset"] + er["dt_size"]]
            if sb != rb_:
                d.add("table entry%d raw-bytes differ" % i)
        for k in ("total_size", "file_size"):
            if st[k] != rt[k]:
                d.add("table ~%s %s -> %s" % (k, st[k], rt[k]))
        n = emit(d, out, "dtbo table %s vs %s" % (simg, rimg))
        summary.append(("dtbo table", len(d.lines), n))
        total_unexpl += n
        for i in range(min(st["dt_entry_count"], rt["dt_entry_count"])):
            so, ro = load("%s:%d" % (simg, i)), load("%s:%d" % (rimg, i))
            d = Diff(explain)
            diff_overlays(so, ro, d, prefix="entry%d " % i)
            n = emit(d, out, "dtbo entry %d overlay-level" % i)
            summary.append(("dtbo entry%d overlay" % i, len(d.lines), n))
            total_unexpl += n
            msm_s = set(u32list(so.root.props.get("qcom,msm-id", b"")) or [])
            for sb, rb, ts, tr in pairs:
                bid = (u32list(ts.root.props.get("qcom,msm-id", b"")) or [None])[0]
                if bid not in msm_s and not a.all_bases:
                    continue
                d = Diff(explain)
                es = er = None
                try:
                    es = apply_overlay(ts, so)
                    er = apply_overlay(tr, ro)
                except OverlayError as e:
                    d.add("entry%d+%s apply-failed %s" % (i, os.path.basename(sb), e))
                else:
                    diff_trees(es, er, d, oracle, prefix="eff%d/%s " % (i, os.path.basename(sb)))
                n = emit(d, out, "effective: %s + entry %d vs rebuilt" % (os.path.basename(sb), i))
                summary.append(("effective %s+entry%d" % (os.path.basename(sb), i), len(d.lines), n))
                total_unexpl += n
                if a.ufdt:
                    # Same comparison with the trees libufdt (ABL) produces.
                    import subprocess
                    import tempfile
                    d = Diff(explain)
                    with tempfile.TemporaryDirectory() as td:
                        outs = []
                        for tag, base_f, img in (("s", sb, simg), ("r", rb, rimg)):
                            ov = os.path.join(td, tag + ".dtbo")
                            tb = parse_dtbo_table(open(img, "rb").read())["entries"][i]
                            with open(ov, "wb") as f:
                                f.write(open(img, "rb").read()[tb["dt_offset"]:tb["dt_offset"] + tb["dt_size"]])
                            o = os.path.join(td, tag + ".dtb")
                            r_ = subprocess.run([a.ufdt, base_f, ov, o], stdout=subprocess.DEVNULL,
                                                stderr=subprocess.PIPE)
                            if r_.returncode:
                                d.add("ufdt%d/%s apply-failed (%s)" % (i, tag, r_.stderr.decode()[:200]))
                            outs.append(o)
                        if not d.lines:
                            us, ur = load(outs[0], sidecar=False), load(outs[1], sidecar=False)
                            orc = dict(oracle)
                            for t_ in (es, er):
                                for k, v in (t_.phrefs.items() if t_ else ()):
                                    orc.setdefault(k, set(v))
                            diff_trees(us, ur, d, orc, prefix="ufdt%d/%s " % (i, os.path.basename(sb)))
                    n = emit(d, out, "effective (ufdt_apply_overlay): %s + entry %d" % (os.path.basename(sb), i))
                    summary.append(("ufdt %s+entry%d" % (os.path.basename(sb), i), len(d.lines), n))
                    total_unexpl += n
    out.write("\n== SUMMARY\n")
    for name, tot, n in summary:
        out.write("   %-40s differences=%-5d unexplained=%d\n" % (name, tot, n))
    out.write("   TOTAL unexplained: %d\n" % total_unexpl)
    if a.report:
        out.close()
        sys.stdout.write("".join("%-40s differences=%-5d unexplained=%d\n" % s for s in summary))
        sys.stdout.write("TOTAL unexplained: %d (report: %s)\n" % (total_unexpl, a.report))
    return 1 if total_unexpl else 0


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sp = ap.add_subparsers(dest="cmd", required=True)
    p = sp.add_parser("info"); p.add_argument("blobs", nargs="+"); p.set_defaults(fn=cmd_info)
    p = sp.add_parser("table"); p.add_argument("img"); p.set_defaults(fn=cmd_table)
    p = sp.add_parser("diff"); p.add_argument("a"); p.add_argument("b")
    p.add_argument("--explain"); p.add_argument("--oracle", action="append")
    p.add_argument("--raw", action="store_true", help="tree-level diff even for overlays")
    p.add_argument("--chains", help="merge-chains.json from amethyst-dt-build.py")
    p.set_defaults(fn=cmd_diff)
    p = sp.add_parser("subset", help="write an overlay holding only some fragments")
    p.add_argument("blob"); p.add_argument("--fragments", required=True)
    p.add_argument("-o", "--output", required=True); p.set_defaults(fn=cmd_subset)
    p = sp.add_parser("apply"); p.add_argument("base"); p.add_argument("overlay")
    p.add_argument("-o", "--output", default="-"); p.set_defaults(fn=cmd_apply)
    p = sp.add_parser("parity")
    p.add_argument("--base", nargs=2, action="append", default=[], metavar=("STOCK", "REBUILT"))
    p.add_argument("--dtbo", nargs=2, metavar=("STOCK_IMG", "REBUILT_IMG"))
    p.add_argument("--oracle", action="append", help="blob(s) whose .phrefs give phandle positions")
    p.add_argument("--explain"); p.add_argument("--report")
    p.add_argument("--chains", help="merge-chains.json from amethyst-dt-build.py")
    p.add_argument("--all-bases", action="store_true", help="apply every entry to every base")
    p.add_argument("--ufdt", help="ufdt_apply_overlay binary: also compare trees as libufdt (ABL) builds them")
    p.set_defaults(fn=cmd_parity)
    a = ap.parse_args()
    sys.exit(a.fn(a) or 0)


if __name__ == "__main__":
    main()
