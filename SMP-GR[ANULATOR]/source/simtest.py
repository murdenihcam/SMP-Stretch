#!/usr/bin/env python3
"""Run granular.mds in the Motorola DSP56300 simulator and check it.

The package is loaded the way the firmware loader does it: at a nonzero program
base, with its relocations applied and its imports patched (temporary memory at
X/Y:$0000, services replaced by the stand-ins in sim/stubs.asm56k).

1. Audio: every RENDER's 32 output words must equal granular_dsp_model.py, and so
   must the track state after the last block (Y+9..22 and the grain records X+0..63).
2. Cycles: the same scenarios run again with fixed-cost service stand-ins. Their
   measured cost is taken out; the documented worst case of each service is added
   back (SAMPLE_INFO 149, SAMPLE_READ 202 + 33 per frame). The machine's own cycles
   per block are fitted as BASE + sum of PCOST over its grains (per tier), the
   model the spawn budget uses; the fit and the worst block are printed.

Usage:  python simtest.py [granular|rom_granular|e12_granular] [--quick] [--cycles]   (DSP56300_TOOLS and MDS_REPO as for build.cmd)
"""
import math
import os
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
MDS_REPO = Path(os.environ.get("MDS_REPO", r"C:\MDS"))
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(MDS_REPO / "tools"))
from lib.mds_format import parse_package          # noqa: E402
import granular_dsp_model as model                # noqa: E402
import gen_tables as T                            # noqa: E402

TOOLS = Path(os.environ.get("DSP56300_TOOLS", r"C:\DSP56300Tools\clas"))
SIM = TOOLS.parent / "sim" / "sim56300.exe"
WORK = HERE / "sim"
BASE = 0x100                     # program base in internal P memory (below the stubs at $E00)
R6, R7 = 0x100, 0x200            # track memory and output buffer
REAL = {9: 0xE00, 10: 0xE40}     # service stand-ins (see stubs.asm56k)
FAST = {9: 0xEC0, 10: 0xED0}
DRIVER, RETURN = 0xEF0, 0xEF2    # jsr >routine / stop here
INFO_AT, SAMPLE_AT, INTERNAL_AT = 0x7F0, 0x4000, 0xC000
SERVICE_MAX = {9: lambda n: 149, 10: lambda n: 202 + 33 * n}
MACHINES = {"granular": -1, "rom_granular": 1, "e12_granular": 0}   # BANK_ID of each
MACHINE = next((a for a in sys.argv[1:] if a in MACHINES), "granular")
SMPL_MAX = {-1: 69, 1: 48, 0: 21}[MACHINES[MACHINE]]
LIMIT, OVERHEAD = 3951, 75


def assemble_stubs():
    (WORK / "stubs.asm").write_text((WORK / "stubs.asm56k").read_text())
    subprocess.run(f'"{TOOLS / "asm56300.exe"}" -a -b stubs.asm > stubs_asm.txt', cwd=WORK, shell=True,
                   check=True)
    lod = subprocess.run(f'"{TOOLS / "cldlod.exe"}" stubs.cld', cwd=WORK, shell=True, check=True,
                         capture_output=True, text=True).stdout
    return [line for line in lod.splitlines() if not line.startswith(("_START", "_END", "_SYMBOL"))
            and not (line[:1].isalpha() and " I " in line)]


def program_words(package, services):
    p = parse_package(Path(package).read_bytes())
    code = p["program"]
    words = [int.from_bytes(code[i:i + 3], "big") for i in range(0, len(code), 3)]
    for w in p["relocations"]:
        words[w] = (words[w] + BASE) & 0xFFFFFF
    for imp in p["imports"]:
        if imp.kind == 5:
            assert words[imp.patch_word] == 0
            words[imp.patch_word] = services[imp.symbol]
        # kinds 1-4 keep their offset: the temporary areas start at X/Y:$0000
    entries = {"INIT": p["init_word"], "TRIG": p["mutate_word"], "RENDER": p["execute_word"]}
    assert BASE + len(words) <= min(REAL.values()), "program overlaps the service stand-ins"
    return words, entries, p


# The DSP56300 instruction cache has 8 sectors of 128 words. The code one block runs
# should span at most SECTORS_MAX of them (worst program alignment), leaving room
# for other machines (SMP-ST, which runs 16 tracks, touches 235 words).
SECTORS_MAX = 5


def set_code_addresses():
    """Kept for the sim/ helper scripts; v0.4 records hold no routine addresses."""


def footprint(tag, step, params, changes, block, track=3):
    """Trace RENDER number `block` of a scenario (fast service stand-ins): returns
    (machine instructions executed, distinct program words touched, cycles)."""
    import re
    words, entries, _ = program_words(HERE / f"{MACHINE}.mds", FAST)
    s = Session()
    t = model.Track(track, MACHINES[MACHINE])
    t.set_params(**params)
    for k in range(1, 9):
        s.set_y(k, t.y[k])
    s.call(BASE + entries["INIT"], track)
    s.call(BASE + entries["TRIG"], track)
    changes = dict(changes)
    for b in range(block):
        if b in changes:
            params = {**params, **changes[b]}
            t.set_params(**params)
            for k in range(1, 9):
                s.set_y(k, t.y[k])
        s.call(BASE + entries["RENDER"], track)
    s.cmds += ["change r6 $%x" % R6, "change r7 $%x" % R7, "change m7 $1f"]
    s.cmds += ["change m%d $ffffff" % i for i in range(6)]
    s.cmds += ["change p:$%x $%x" % (DRIVER + 1, BASE + entries["RENDER"]), "change pc $%x" % DRIVER,
               "change cyc 0", "trace 8000 h"]
    pcm = test_signal(30000)
    lod = lod_block("P", BASE, words) + STUB_LOD + lod_block("X", INFO_AT, [len(pcm), step])
    s.run(lod, "footprint")
    log = (WORK / "footprint.log").read_text().splitlines()
    log = log[next(i for i, line in enumerate(log) if line.startswith("trace ")):]
    pcs, n, cyc = set(), 0, 0
    for line in log:
        m = re.search(r"cyc=\s*\{?(\d+)", line)
        if m:
            cyc = int(m.group(1))
        m = re.match(r"p:\$([0-9a-f]+) ([0-9a-f]{6})( [0-9a-f]{6})?", line)
        if m:
            a = int(m.group(1), 16)
            if a == RETURN:
                break
            if BASE <= a < BASE + len(words):
                n += 1
                pcs.add(a)
                if m.group(3):
                    pcs.add(a + 1)
    # 128-word cache sectors spanned, at the worst alignment of the program base
    sectors = max(len({(a - BASE + o) >> 7 for a in pcs}) for o in range(128))
    return n, len(pcs), sectors


def lod_block(space, addr, words):
    lines = [f"_DATA {space} {addr:04X}"]
    for i in range(0, len(words), 8):
        lines.append(" ".join(f"{w & 0xFFFFFF:06X}" for w in words[i:i + 8]))
    return lines


class Session:
    def __init__(self):
        self.cmds = ["break pc=$%x" % RETURN]
        self.calls = []

    def call(self, address, track=0, capture=False):
        c = self.cmds
        c += ["change r6 $%x" % R6, "change r7 $%x" % R7, "change m7 $1f", "change r1 $%x" % track]
        c += ["change m%d $ffffff" % i for i in range(6)]
        c += ["change p:$%x $%x" % (DRIVER + 1, address), "change pc $%x" % DRIVER, "change cyc 0", "go"]
        if capture:
            c.append("display y:$%x..$%x" % (R7, R7 + 31))
        self.calls.append(capture)

    def set_y(self, offset, value):
        self.cmds.append("change y:$%x $%x" % (R6 + offset, value & 0xFFFFFF))

    def run(self, lod_lines, tag):
        (WORK / f"{tag}.lod").write_text("\n".join(["_START TEST 0000 0000 0000 DSP56300 6.3.15", ""]
                                                   + lod_lines + ["_END 0000", ""]))
        log = WORK / f"{tag}.log"
        script = ["device dv0 56303", f"log s {log.name} -o", f"load {tag}.lod"] + self.cmds \
            + ["log off s", "quit"]
        (WORK / f"{tag}.cmd").write_text("\n".join(script) + "\n")
        subprocess.run([str(SIM), f"{tag}.cmd"], cwd=WORK, check=True, timeout=1800)
        cycles, blocks, lines = [], [], log.read_text().splitlines()
        i = 0
        for capture in self.calls:
            while not lines[i].startswith("Break #1"):
                i += 1
            cycles.append(int(lines[i].split("cyc:")[1]))
            i += 1
            if capture:
                while not lines[i].startswith("y:$%06x=" % R7):
                    i += 1
                words = []
                while len(words) < 32:
                    words += [int(t[1:], 16) for t in lines[i].split("=")[-1].split()]
                    i += 1
                blocks.append(words)
        return cycles, blocks


def read_display(lines, space, start, count):
    """Words of the last 'display space:$start..' in a log."""
    first = max(i for i, line in enumerate(lines) if line.startswith("display %s:$%x" % (space, start)))
    out = []
    for line in lines[first + 1:]:
        if not line.startswith(space + ":$"):
            break
        out += [int(v[1:], 16) for v in line.split("=")[-1].split()]
    return out[:count]


def test_signal(n, hz=441):
    """A decaying tone with a click every 1000 frames, so grain positions are visible."""
    out = []
    for i in range(n):
        v = 0.6 * math.sin(2 * math.pi * hz * i / 44100) * math.exp(-i / n)
        if i % 1000 == 0:
            v = 0.9
        out.append(round(v * 0x7FFFFF) & 0xFFFFFF)
    return out


def stub_costs():
    """Cycles from JSR to return for each fixed-cost stand-in."""
    s = Session()
    for symbol in (9, 10):
        s.call(FAST[symbol])
    cycles, _ = s.run(STUB_LOD + lod_block("X", INFO_AT, [1000, 0x10000]), "stubcost")
    return dict(zip((9, 10), cycles))


def scenario(tag, pcm, step, params, changes=(), blocks=150, track=3, fast=False):
    """INIT, TRIG and RENDER blocks in the simulator and in the model.

    Returns (status, per-call cycles, per-call service calls, per-block cost-model info)."""
    words, entries, _ = program_words(HERE / f"{MACHINE}.mds", FAST if fast else REAL)
    s = Session()
    t = model.Track(track, MACHINES[MACHINE])
    t.set_params(**params)
    for k in range(1, 9):
        s.set_y(k, t.y[k])
    s.call(BASE + entries["INIT"], track)
    s.call(BASE + entries["TRIG"], track)
    info, read = model.sample_services(pcm, step, INTERNAL)
    t.trig(info)
    services = [[], [(9, 0)]]          # per call: (service, frames) as the model saw them
    want, costinfo = [], [None, None]
    changes = dict(changes)
    for b in range(blocks):
        if b in changes:
            params = {**params, **changes[b]}
            t.set_params(**params)
            for k in range(1, 9):
                s.set_y(k, t.y[k])
        s.call(BASE + entries["RENDER"], track, capture=True)
        calls = []

        def counting_read(bank, slot, positions, n, calls=calls):
            calls.append((10, n))
            return read(bank, slot, positions, n)
        want.append(t.render(counting_read))
        services.append(calls)
        costinfo.append(getattr(t, "block", None))
    s.cmds.append("display y:$%x..$%x" % (R6 + model.STATE_Y[0], R6 + model.STATE_Y[-1]))
    s.cmds.append("display x:$%x..$%x" % (R6, R6 + 63))
    lod = lod_block("P", BASE, words) + STUB_LOD + lod_block("X", INFO_AT, [len(pcm), step]) \
        + ([] if fast else lod_block("X", SAMPLE_AT, pcm) + lod_block("X", INTERNAL_AT, INTERNAL))
    run_tag = tag + ("_fast" if fast else "")
    cycles, got = s.run(lod, run_tag)
    if fast:
        status = "-"
    else:
        bad = [i for i, (g, w) in enumerate(zip(got, want)) if g != w]
        status = "OK" if not bad and len(got) == blocks else f"MISMATCH in blocks {bad[:8]}"
        lines = (WORK / f"{run_tag}.log").read_text().splitlines()
        ys = read_display(lines, "y", R6 + model.STATE_Y[0], len(model.STATE_Y))
        wrong = [k for k, v in zip(model.STATE_Y, ys) if v != t.y[k] & 0xFFFFFF]
        xs = read_display(lines, "x", R6, 64)
        wrong_x = [k for k, v in enumerate(xs) if v != t.x[k] & 0xFFFFFF]
        if wrong or len(ys) != len(model.STATE_Y):
            status += f", Y STATE DIFFERS at Y+{wrong[:6]}"
        if wrong_x or len(xs) != 64:
            status += f", X STATE DIFFERS at X+{wrong_x[:6]}"
    return status, cycles, services, costinfo, t


def solve(rows, rhs):
    """Least squares for a few unknowns (normal equations, Gaussian elimination)."""
    n = len(rows[0])
    a = [[sum(r[i] * r[j] for r in rows) for j in range(n)] + [sum(r[i] * y for r, y in zip(rows, rhs))]
         for i in range(n)]
    for i in range(n):
        p = max(range(i, n), key=lambda k: abs(a[k][i]))
        a[i], a[p] = a[p], a[i]
        if abs(a[i][i]) < 1e-9:
            continue
        for k in range(n):
            if k != i:
                f = a[k][i] / a[i][i]
                a[k] = [u - f * v for u, v in zip(a[k], a[i])]
    return [a[i][n] / a[i][i] if abs(a[i][i]) > 1e-9 else 0.0 for i in range(n)]


BASE_P = dict(ptch=64, smpl=5, dec=127, dens=64, seek=0, scan=64, gran=40, spry=0)
RUNS = [
    # tag, step, params, changes
    ("default", 0x010000, {}, ()),
    ("full_pair", 0x010000, dict(dens=80, gran=30, spry=20), ()),
    ("half_cloud", 0x00B000, dict(dens=100, gran=25, spry=40), ()),
    ("quarter_cloud", 0x010000, dict(dens=127, gran=30, spry=40), ()),
    ("tiny_dense", 0x010000, dict(dens=127, gran=0, spry=60, scan=90), ()),
    ("reverse_spray", 0x00B000, dict(dens=110, gran=35, spry=127), ()),
    ("scan_fwd", 0x010000, dict(dens=90, gran=20, scan=127, seek=100), ()),
    ("scan_rev", 0x00B000, dict(dens=90, gran=20, scan=0, seek=10), ()),
    ("pitch_up", 0x010000, dict(dens=110, gran=50, ptch=127, spry=30), ()),
    ("pitch_down", 0x00B000, dict(dens=127, gran=20, ptch=0, spry=90), ()),
    ("decay", 0x010000, dict(dens=100, gran=20, dec=40), ()),
    ("decay_short", 0x010000, dict(dec=0), ()),
    ("long_grains", 0x010000, dict(dens=127, gran=127, spry=70), ()),
    ("internal", 0x010000, dict(smpl=60, dens=100, gran=25, spry=50), ()),
    ("live_changes", 0x010000, dict(dens=60, gran=30),
     ((20, dict(dens=127, spry=100)), (50, dict(gran=5, ptch=90)), (80, dict(dens=20, scan=20)),
      (110, dict(dens=127, gran=60, ptch=30)))),
    ("modulated", 0x00B000, dict(dens=100.4, gran=33.7, spry=64.5, scan=70.2, ptch=63.3, seek=40.6), ()),
    ("full_busy", 0x010000, dict(dens=84, gran=0, spry=127), ()),
    ("half_busy", 0x010000, dict(dens=106, gran=0, spry=127, ptch=90), ()),
    ("mixed_tiers", 0x010000, dict(dens=84, gran=30, spry=100),
     ((12, dict(dens=106)), (30, dict(dens=127)), (55, dict(dens=84)), (90, dict(dens=127, gran=5)))),
]


if __name__ == "__main__":
    quick = "--quick" in sys.argv
    WORK.mkdir(exist_ok=True)
    STUB_LOD = assemble_stubs()
    STUB = stub_costs()
    print("stand-in cost, JSR to return:", STUB)
    pcm = test_signal(30000)
    INTERNAL = test_signal(30000, hz=660)   # bank 0 (internal) plays a different tone
    runs = [(tag, step, {**BASE_P, **p, "smpl": min(SMPL_MAX, p.get("smpl", BASE_P["smpl"]))}, ch)
            for tag, step, p, ch in RUNS]
    if quick:
        runs = runs[:4]
    all_ok = True
    print("\n1. audio and state, simulator against the model")
    for tag, step, params, changes in runs:
        status, *_ = scenario(tag, pcm, step, params, changes)
        all_ok &= status == "OK"
        print(f"   {tag:15s} {status}")

    print("\n2. cycles, own code + documented service worst case")
    samples, worst_trig, worst = [], 0, (0, "")
    for tag, step, params, changes in runs:
        _, cycles, services, costinfo, _ = scenario(tag, pcm, step, params, changes, fast=True)
        trig = cycles[0] + cycles[1] + 149 - STUB[9]
        for i in range(2, len(cycles)):
            reads = sum(SERVICE_MAX[sym](n) for sym, n in services[i])
            own = cycles[i] - sum(STUB[sym] for sym, _ in services[i])
            total = own + reads
            if i == 2:
                worst_trig = max(worst_trig, trig + total)
            if total > worst[0]:
                worst = (total, f"{tag} block {i - 2}", (tag, step, params, changes, i - 2))
            info = costinfo[i]
            if info is not None and services[i]:
                mask, proc, counts, ev = info
                buffers = int(mask & 3 != 0) + int(mask >> 2 & 3 != 0)
                samples.append((own, counts, proc, reads, T.RCB[mask & 3] + T.RCB[mask >> 2 & 3], tag, i - 2,
                                [ev["attempt"], ev["ok"], ev["fallback"], ev["frees"]], buffers))
    # own cycles = base + spawn attempt/success/fallback + frees + buffers + grains per tier
    rows = [[1] + s[7] + [s[8]] + s[1] for s in samples]
    fit = solve(rows, [s[0] for s in samples])
    print("   fit: base %.0f, spawn attempt %+.0f, start %+.0f, fallback %+.0f, per free %+.0f, per buffer"
          " %+.0f; per grain full %.0f, half %.0f" % tuple(fit))
    # cost model in the package: BASE + RCB(mask) (reads + buffers) + sum PCOST; check every block
    over = [(s[0] + s[3]) - (T.BASE_CYCLES + s[4] + s[2]) for s in samples]
    k = max(range(len(over)), key=lambda j: over[j])
    print("   cost model in tables (BASE %d, BUF %d, PCOST %s): worst excess %+d (%s block %d)"
          % (T.BASE_CYCLES, T.BUF_CYCLES, T.PCOST[1:], over[k], samples[k][5], samples[k][6]))
    # suggestion: PCOST = grain cost + a free (any grain may end in any block), rounded up;
    # BUF from the fit; BASE = the worst remaining own cycles over all blocks, plus a margin
    sug = [math.ceil(c + max(0.0, fit[4]) + 3) for c in fit[6:]]
    sug_buf = math.ceil(fit[5] + 3)
    sug_base = max(s[0] - sum(n * c for n, c in zip(s[1], sug)) - s[8] * sug_buf for s in samples)
    print("   suggested: PCOST %s, BUF_CYCLES %d, BASE_CYCLES %d -> VBUDGET %d"
          % (sug, sug_buf, sug_base + 20, LIMIT - OVERHEAD - sug_base - 20))
    print("   reads modelled vs documented: %s" % ("same" if all(s[3] == s[4] - s[8] * T.BUF_CYCLES for s in samples) else "DIFFER"))
    print(f"   worst block {worst[0]} ({worst[1]}); INIT + TRIG + first RENDER {worst_trig}")
    budget = max(worst[0], worst_trig)
    print(f"   + {OVERHEAD} firmware overhead = {budget + OVERHEAD}  (limit {LIMIT})")
    all_ok &= budget + OVERHEAD <= LIMIT

    # The hardware runs the program through the instruction cache: the code one
    # block executes must stay small (SMP-ST, which runs 16 tracks, touches 235 words).
    print("\n3. code footprint of the worst block (instruction cache)")
    for name, spec in (("worst block", worst[2]),
                       ("tiny_dense block 40", next((r[0], r[1], {**BASE_P, **r[2]}, r[3], 40) for r in RUNS
                                                    if r[0] == "tiny_dense"))):
        n, words, sectors = footprint(*spec)
        ok = sectors <= SECTORS_MAX
        all_ok &= ok
        print(f"   {name:22s} ({spec[0]} block {spec[4]}): {n} instructions, {words} distinct program"
              f" words, {sectors} cache sectors{'' if ok else '  OVER ' + str(SECTORS_MAX)}")
    sys.exit(0 if all_ok else 1)
