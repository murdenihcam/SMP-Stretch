#!/usr/bin/env python3
"""Run the packaged machine in the Motorola DSP56300 simulator and check it.

The .mds package is loaded the way the firmware loader does it: at a nonzero
program base, with its relocations applied and its imports patched (temporary
memory at X/Y:$0000, services replaced by the stand-ins in sim/stubs.asm56k).

1. Audio: every RENDER's 32 output words must equal slicer_model.py, and
   so must the track's state words after the last block (Y+9..50: bank, slot,
   positions, envelope and the rest).
2. Cycles: the same scenarios run again with fixed-cost service stand-ins. Their
   measured cost is taken out and the documented worst case of each service is
   added back (SAMPLE_INFO 149, SAMPLE_READ 202 + 33 per frame).
   The reference machines sine.mds and userwave_hit.mds are measured the same
   way, to compare with the cycle counts declared in their packages.

Usage:  python simtest.py [machine]  (rom_e12_slicer or rom_e12_slicer_st;
                                      DSP56300_TOOLS and MDS_REPO as for build.cmd)
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
import slicer_model as model                      # noqa: E402

TOOLS = Path(os.environ.get("DSP56300_TOOLS", r"C:\DSP56300Tools\clas"))
SIM = TOOLS.parent / "sim" / "sim56300.exe"
WORK = HERE / "sim"
BASE = 0x400                     # program base in internal P memory
R6, R7 = 0x100, 0x200            # track memory and output buffer
REAL = {9: 0xE00, 10: 0xE40}     # service stand-ins (see stubs.asm56k)
FAST = {9: 0xEC0, 10: 0xED0}
DRIVER, RETURN = 0xEF0, 0xEF2    # jsr >routine / stop here
INFO_AT, SAMPLE_AT, INTERNAL_AT = 0x7F0, 0x4000, 0xC000
SERVICE_MAX = {9: lambda n: 149, 10: lambda n: 202 + 33 * n}
MACHINES = {"rom_e12_slicer": -1, "rom_slicer": 1, "e12_slicer": 0}   # BANK_ID of each
MACHINE = sys.argv[1] if len(sys.argv) > 1 and sys.argv[1] in MACHINES else "rom_e12_slicer"
STATE = range(9, 53)             # Y words compared after the last block


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
    return words, entries, p


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
        subprocess.run([str(SIM), f"{tag}.cmd"], cwd=WORK, check=True, timeout=900)
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


def test_signal(n, hz=441):
    """A decaying tone with a click every 1000 frames, so splices are visible."""
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


def scenario(tag, pcm, step, params, changes=(), blocks=200, track=3, fast=False):
    """INIT, TRIG and RENDER blocks in the simulator and in the model.

    Returns (status, per-call cycles, per-call service worst case, model output)."""
    words, entries, _ = program_words(HERE / f"{MACHINE}.mds", FAST if fast else REAL)
    s = Session()
    t = model.Track(track, bank_id=MACHINES[MACHINE])
    t.set_params(**params)
    for k in range(1, 9):
        s.set_y(k, t.y[k])
    s.call(BASE + entries["INIT"], track)
    s.call(BASE + entries["TRIG"], track)
    info, read = model.sample_services(pcm, step, INTERNAL)
    t.trig(info)
    services = [[], [(9, 0)]]          # per call: (service, frames) as the model saw them
    want = []
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
    s.cmds.append("display y:$%x..$%x" % (R6 + STATE[0], R6 + STATE[-1]))
    lod = lod_block("P", BASE, words) + STUB_LOD + lod_block("X", INFO_AT, [len(pcm), step]) \
        + ([] if fast else lod_block("X", SAMPLE_AT, pcm) + lod_block("X", INTERNAL_AT, INTERNAL))
    run_tag = tag + ("_fast" if fast else "")
    cycles, got = s.run(lod, run_tag)
    if fast:
        status = "-"
    else:
        bad = [i for i, (g, w) in enumerate(zip(got, want)) if g != w]
        status = "OK" if not bad and len(got) == blocks else f"MISMATCH in blocks {bad[:8]}"
        # the track state after the last block, word for word
        lines = (WORK / f"{run_tag}.log").read_text().splitlines()
        start = max(i for i, line in enumerate(lines) if line.startswith("display y:$%x" % (R6 + STATE[0])))
        state = []
        for line in lines[start + 1:]:
            if not line.startswith("y:$"):
                break
            state += [int(v[1:], 16) for v in line.split("=")[-1].split()]
        wrong = [k for k, v in zip(STATE, state) if v != t.y[k] & 0xFFFFFF]
        if wrong or len(state) != len(STATE):
            status += f", STATE DIFFERS at Y+{wrong[:6]}"
    return status, cycles, services, want


def reference_cycles(package, params, blocks=4):
    """TRIG + worst RENDER of a reference machine, with documented service costs."""
    words, entries, p = program_words(package, FAST)
    s = Session()
    for k, v in params.items():
        s.set_y(k, v)
    s.call(BASE + entries["INIT"])
    s.call(BASE + entries["TRIG"])
    for _ in range(blocks):
        s.call(BASE + entries["RENDER"])
    lod = lod_block("P", BASE, words) + STUB_LOD + lod_block("X", INFO_AT, [20000, 0x10000])
    cycles, _ = s.run(lod, Path(package).stem)
    imported = {imp.symbol for imp in p["imports"]}
    trig = cycles[1] + (149 - STUB[9] if 9 in imported else 0)
    render = max(cycles[2:]) + (1258 - STUB[10] if 10 in imported else 0)
    return trig, render, p["max_track_cycles"]


if __name__ == "__main__":
    WORK.mkdir(exist_ok=True)
    STUB_LOD = assemble_stubs()
    STUB = stub_costs()
    print("stand-in cost, JSR to return:", STUB)
    pcm = test_signal(12000)
    INTERNAL = test_signal(12000, hz=660)  # what bank 0 (internal) plays, to tell the banks apart
    print("machine:", MACHINE)
    full, uw = 0x010000, 0x00B000         # 44.1 kHz and a slower (UW-like) native rate
    base = dict(ptch=64, smpl=5, dec=127, time=0, play=0, mode=0, slic=8, slno=3)
    runs = [
        ("equa_fwd", full, base, ()),
        ("equa_rev", full, {**base, "play": 1}, ()),
        ("exp_bi", full, {**base, "play": 2, "mode": 1, "slno": 5, "ptch": 76}, ()),
        ("log_last", uw, {**base, "mode": 2, "slic": 16, "slno": 16, "ptch": 80, "play": 2}, ()),
        ("sed1", full, {**base, "mode": 3, "slic": 5, "slno": 2}, ()),
        ("sed2_rev", uw, {**base, "mode": 4, "slic": 12, "slno": 7, "play": 1, "ptch": 50}, ()),
        ("sed3_time", full, {**base, "mode": 5, "slic": 3, "slno": 3, "time": 42, "play": 2}, ()),
        ("sed4_last", full, {**base, "mode": 6, "slic": 64, "slno": 64, "ptch": 100}, ()),
        ("time_half", full, {**base, "slic": 2, "slno": 1, "time": 42, "ptch": 70}, ()),
        ("time_frozen", uw, {**base, "slic": 4, "time": 127, "ptch": 88, "play": 1}, ()),
        ("live_changes", full, {**base, "slic": 3, "slno": 2, "dec": 110},
         ((10, {"ptch": 52, "time": 30}), (25, {"play": 2, "time": 0}), (40, {"ptch": 90, "play": 1}),
          (70, {"time": 100, "play": 0, "ptch": 64}), (100, {"slno": 1, "mode": 4}))),
        ("pitch_extremes", full, {**base, "ptch": 127, "time": 30, "play": 2},
         ((20, {"ptch": 0}), (45, {"ptch": 101}), (70, {"ptch": 13}))),
        ("decay_short", full, {**base, "dec": 0}, ()),
        ("decay_mid", uw, {**base, "dec": 40, "time": 20, "play": 2}, ()),
        ("tiny_slice", full, {**base, "mode": 1, "slic": 64, "slno": 1, "ptch": 127, "play": 2}, ()),
        ("tiny_slow", full, {**base, "mode": 1, "slic": 64, "slno": 2, "ptch": 110, "time": 64}, ()),
        ("modulo", full, {**base, "slic": 5, "slno": 13, "play": 2}, ()),
        ("whole", uw, {**base, "slic": 1, "slno": 9, "ptch": 100}, ()),
        # DEC 0: play once, fade out over the last 4 blocks, stop
        ("once_fwd", full, {**base, "dec": 0}, ()),
        ("once_rev_pitch", uw, {**base, "dec": 0, "play": 1, "ptch": 90, "mode": 2, "slno": 2}, ()),
        ("once_time", full, {**base, "dec": 0, "time": 42, "slic": 16, "slno": 9}, ()),
        ("once_tiny", full, {**base, "dec": 0, "mode": 1, "slic": 64, "slno": 1, "ptch": 127}, ()),
        ("once_then_loop", full, {**base, "dec": 0, "slic": 4}, ((20, {"dec": 100}),)),
        ("loop_then_once", full, {**base, "dec": 127, "slic": 16, "play": 2}, ((60, {"dec": 0}),)),
    ]
    if MACHINES[MACHINE] < 0:              # the combined list: last UW slot, first and last internal
        runs += [
            ("last_uw_slot", full, {**base, "smpl": 48, "time": 42}, ()),
            ("first_internal", full, {**base, "smpl": 49, "time": 42, "play": 1}, ()),
            ("last_internal", full, {**base, "smpl": 69, "mode": 2, "slno": 8, "time": 70}, ()),
            ("internal_retune", full, {**base, "smpl": 60, "ptch": 90, "time": 96},
             ((30, {"smpl": 10}),)),      # SMPL is latched at TRIG: no change mid-note
        ]
    else:                                  # a single bank: its last slot, and a retune
        last = 48 if MACHINES[MACHINE] else 21
        runs += [
            ("last_slot", full, {**base, "smpl": last, "time": 42, "play": 1}, ()),
            ("retune", full, {**base, "smpl": last - 3, "ptch": 90, "time": 96}, ((30, {"smpl": 2}),)),
        ]
    all_ok = True
    print("\n1. audio, simulator against the model")
    for tag, step, params, changes in runs:
        status, *_ = scenario(tag, pcm, step, params, changes)
        all_ok &= status == "OK"
        print(f"   {tag:17s} {status}")

    print("\n2. cycles, own code + documented service worst case")
    # The block a track is triggered in is never a crossfade block: TRIG sets at
    # least 300 samples to the first splice. So the worst block is either
    # INIT + TRIG + the first RENDER, or the worst RENDER on its own.
    worst = {"INIT": 0, "TRIG": 0, "first RENDER": 0, "RENDER": 0, "RENDER crossfade": 0}
    for tag, step, params, changes in runs:
        _, cycles, services, _ = scenario(tag, pcm, step, params, changes, fast=True)
        for i, (c, calls) in enumerate(zip(cycles, services)):
            total = c + sum(SERVICE_MAX[sym](n) - STUB[sym] for sym, n in calls)
            name = (("INIT", "TRIG", "first RENDER")[i] if i < 3
                    else ("RENDER crossfade" if len(calls) == 2 else "RENDER"))
            worst[name] = max(worst[name], total)
    for name, c in worst.items():
        print(f"   {name:17s} {c:5d}")
    trig_block = worst["INIT"] + worst["TRIG"] + worst["first RENDER"]
    budget = max(trig_block, worst["RENDER"], worst["RENDER crossfade"])
    print(f"   INIT + TRIG + first RENDER = {trig_block}; worst block = {budget}  (limit 3951)")

    # userwave_hit uses the same services, so it calibrates the firmware overhead
    # that its declared figure carries on top of this measurement. (sine.mds is
    # not comparable here: its sine table reads land in slow simulator memory.)
    print("\n3. reference machine, measured the same way")
    package = MDS_REPO / "machines" / "examples" / "sample_playback" / "userwave_hit.mds"
    trig, render, declared = reference_cycles(package, {1: 0, 2: 0, 3: 0x6E0000, 4: 0x600000})
    overhead = declared - (trig + render)
    print(f"   {package.name}: TRIG {trig} + RENDER {render} = {trig + render}, declared {declared}"
          f" -> overhead {overhead}")
    print(f"\n   suggested max_track_cycles: {budget} + {overhead} = {budget + overhead},"
          f" rounded up to {-(-(budget + overhead) // 50) * 50}")
    sys.exit(0 if all_ok else 1)
