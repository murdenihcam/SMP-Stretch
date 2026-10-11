#!/usr/bin/env python3
"""Cycle profile of one RENDER, by label: python sim\\profile.py [block]

Runs the 'slow_flux' settings with fixed-cost service stand-ins, traces the
given RENDER call (default: the first crossfade block) instruction by
instruction, and adds up cycles per code label of rom_stretch.lst.
"""
import re
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(HERE))
import simtest as S                                # noqa: E402
import rom_stretch_model as model                  # noqa: E402

S.WORK.mkdir(exist_ok=True)
S.STUB_LOD = S.assemble_stubs()
words, entries, _ = S.program_words(HERE / "rom_stretch.mds", S.FAST)
params = dict(ptch=70, smpl=5, dec=127, time=20, strt=0, end=127, gran=30, flux=127)
t = model.Track(3)
t.set_params(**params)
pcm = S.test_signal(12000)
info, read = model.sample_services(pcm, 0xB000)
t.trig(info)
target = None
for b in range(200):
    t.render(read)
    if t.y[model.S_FADE] == 2:               # this block was crossfade step 1, i.e. the splice block
        target = b
        break
target = int(sys.argv[1]) if len(sys.argv) > 1 else target
s = S.Session()
m = model.Track(3)
m.set_params(**params)
for k in range(1, 9):
    s.set_y(k, m.y[k])
s.call(S.BASE + entries["INIT"], 3)
s.call(S.BASE + entries["TRIG"], 3)
for _ in range(target):
    s.call(S.BASE + entries["RENDER"], 3)
# the traced call
s.cmds += ["change r6 $%x" % S.R6, "change r7 $%x" % S.R7, "change m7 $1f",
           "change p:$%x $%x" % (S.DRIVER + 1, S.BASE + entries["RENDER"]), "change pc $%x" % S.DRIVER,
           "change cyc 0", "trace 3000 h"]
lod = S.lod_block("P", S.BASE, words) + S.STUB_LOD + S.lod_block("X", S.INFO_AT, [len(pcm), 0xB000])
S.Session.run(s, lod, "profile")
log = (S.WORK / "profile.log").read_text().splitlines()
log = log[next(i for i, line in enumerate(log) if line.startswith("trace ")):]

# label of each program address, from the listing
labels, current = {}, "?"
for line in (HERE / "rom_stretch.lst").read_text().splitlines():
    m1 = re.match(r"\s*\d+\s+([A-Z_][A-Z0-9_]*):(?![0-9A-F]{6})", line)
    if m1:
        current = m1.group(1)
    m2 = re.match(r"\s*\d+\s+P:([0-9A-F]{6})", line)
    if m2:
        labels[int(m2.group(1), 16)] = current
per, last_cyc, last_pc = {}, 0, None
for line in log:
    m3 = re.search(r"cyc=\s*\{?(\d+)", line)
    if m3:
        cyc = int(m3.group(1))
    m4 = re.match(r"p:\$([0-9a-f]{6}) ", line)
    if m4 and m3 is None:
        pass
    m5 = re.search(r"pc=\{?\$([0-9a-f]{6})", line)
    if m5:
        pc = int(m5.group(1), 16)
    if line.startswith(" cnt1"):
        if last_pc is not None:
            name = labels.get(last_pc - S.BASE, "service/driver")
            per[name] = per.get(name, 0) + cyc - last_cyc
        last_cyc, last_pc = cyc, pc
        if pc == S.RETURN:
            break
total = sum(per.values())
print(f"block {target}: {total} cycles")
for name, c in sorted(per.items(), key=lambda kv: -kv[1]):
    print(f"   {name:16s} {c:5d}")
