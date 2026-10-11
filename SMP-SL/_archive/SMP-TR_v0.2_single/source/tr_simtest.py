#!/usr/bin/env python3
"""Simulator test of the transient slicer draft (SMP-TR) against tr_model.py.

Like simtest.py (which it reuses): every RENDER's output must match the model,
and so must the Y state (Y+9..63) and the onset list in X (X+0..60) after the
last block. Scenarios can re-trigger (so the second TRIG uses the onsets the
first blocks found) and change parameters. Then the cycle budget, with the
documented service maxima, including the analysis reads and SAMPLE_INFO calls.

Usage:  python tr_simtest.py   (DSP56300_TOOLS and MDS_REPO as for build.cmd)
"""
import math
import random
import sys

import simtest as S
import slicer_model as sm
import tr_model as tm

S.WORK.mkdir(exist_ok=True)
NAME = "rom_e12_trslicer"
SR = 44100
XSTATE = range(0, 61)


def drums(seconds, seed=1):
    n = int(seconds * SR)
    x = [0.0] * n
    rnd = random.Random(seed)
    step = SR // 8
    for s in range(int(seconds * 8)):
        t0 = s * step
        if s % 8 in (0, 3):
            for i in range(min(n - t0, int(0.3 * SR))):
                f = 50 + 120 * math.exp(-i / 900)
                x[t0 + i] += 0.9 * math.sin(2 * math.pi * f * i / SR) * math.exp(-i / 7000)
        if s % 8 == 4:
            for i in range(min(n - t0, int(0.2 * SR))):
                x[t0 + i] += 0.5 * rnd.uniform(-1, 1) * math.exp(-i / 3000)
        if s % 2 == 1:
            for i in range(min(n - t0, int(0.05 * SR))):
                x[t0 + i] += 0.25 * rnd.uniform(-1, 1) * math.exp(-i / 500)
    peak = max(abs(v) for v in x)
    return [round(v / peak * 0.8 * 0x7FFFFF) & 0xFFFFFF for v in x]


def dense_hits(n, seed=7):
    """Clicks of random level every ~1300 frames: more onsets than the list keeps."""
    rnd = random.Random(seed)
    x = [0.0] * n
    t = 2000
    while t < n:
        a = rnd.uniform(0.2, 1.0)
        for i in range(min(n - t, 900)):
            x[t + i] += a * rnd.uniform(-1, 1) * math.exp(-i / 150)
        t += rnd.randint(1200, 1500)
    peak = max(abs(v) for v in x)
    words = [round(v / peak * 0.9 * 0x7FFFFF) & 0xFFFFFF for v in x]
    words[5000] = 0x800000                       # a full-scale negative sample (abs limits)
    return words


def full_list(t, length):
    """Preset a full onset list of the current SMPL setting (analysis from the start again)."""
    rnd = random.Random(3)
    qs = [rnd.randint(2000, 26000) for _ in range(tm.MAX_ON)]
    order = sorted(range(tm.MAX_ON), key=lambda i: (qs[i], i))
    for rank, i in enumerate(order):
        t.x[2 * i], t.x[2 * i + 1] = 700 * (i + 1), (qs[i] << 8) | rank
    y = t.y
    y[tm.A_KEY], y[tm.A_LEN], y[tm.A_STRIDE] = y[sm.P_SMPL], length, 16
    y[tm.A_POS] = y[tm.A_ENV] = y[tm.A_DONE] = 0
    y[tm.A_CNT], y[tm.A_PPOS] = tm.MAX_ON, tm.NONE


SECTORS_MAX = 5                  # instruction cache: 8 sectors of 128 words (see the workflow notes)


def block_kinds(pcm, internal, step, params, events, blocks, preset=None):
    """Model only: the kind of every RENDER (crossfade / analysis step / plain)."""
    t = tm.TrTrack(3, bank_id=-1)
    t.set_params(**params)
    if preset:
        preset(t, len(pcm))
    info, read = sm.sample_services(pcm, step, internal)
    t.trig(info)
    kinds, events = [], dict(events)
    for b in range(blocks):
        ev = dict(events.get(b, {}))
        retrig = ev.pop("trig", False)
        if ev:
            params = {**params, **ev}
            t.set_params(**params)
        if retrig:
            t.trig(info)
        fade = t.y[sm.S_FADE]
        t.render(read, info)
        kinds.append("crossfade" if fade else (t.step or "voice only"))
    return kinds


def footprint(run, block):
    """Trace RENDER number `block` of a run (real service stand-ins): returns
    (instructions executed, distinct program words, 128-word cache sectors at the
    worst alignment of the program base). Service code is not counted."""
    import re
    tag, pcm, internal, step, params, events, blocks, *preset = run
    scenario(tag, pcm, internal, step, params, events, block + 1, preset=preset[0] if preset else None,
             trace=block)
    log = (S.WORK / f"{tag}_trace.log").read_text().splitlines()
    log = log[next(i for i, line in enumerate(log) if line.startswith("trace ")):]
    words, _, _ = S.program_words(S.HERE / f"{NAME}.mds", S.REAL)
    pcs, n = set(), 0
    for line in log:
        m = re.match(r"p:\$([0-9a-f]+) ([0-9a-f]{6})( [0-9a-f]{6})?", line)
        if m:
            a = int(m.group(1), 16)
            if a == S.RETURN:
                break
            if S.BASE <= a < S.BASE + len(words):
                n += 1
                pcs.add(a)
                if m.group(3):
                    pcs.add(a + 1)
    sectors = max(len({(a - S.BASE + o) >> 7 for a in pcs}) for o in range(128))
    return n, len(pcs), sectors


def scenario(tag, pcm, internal, step, params, events=(), blocks=200, track=3, fast=False, preset=None,
             trace=None):
    """events: {block: dict of parameter changes, "trig": True to TRIG before that block}.
    preset(track, length) changes the model's state after INIT; the simulator gets the same.
    trace: trace that RENDER instruction by instruction and stop there (see footprint)."""
    words, entries, _ = S.program_words(S.HERE / f"{NAME}.mds", S.FAST if fast else S.REAL)
    s = S.Session()
    t = tm.TrTrack(track, bank_id=-1)
    t.set_params(**params)
    for k in range(1, 9):
        s.set_y(k, t.y[k])
    info, read = sm.sample_services(pcm, step, internal)
    services = []
    if preset:
        s.call(S.BASE + entries["INIT"], track)
        services.append([])
        preset(t, len(pcm))
        for k in range(53, 64):
            s.set_y(k, t.y[k])
        for k in range(60):
            s.cmds.append("change x:$%x $%x" % (S.R6 + k, t.x[k]))

    def counted(calls):
        def c_info(bank, slot):
            calls.append((9, 0))
            return info(bank, slot)

        def c_read(bank, slot, positions, n):
            calls.append((10, n))
            return read(bank, slot, positions, n)
        return c_info, c_read

    if not preset:
        s.call(S.BASE + entries["INIT"], track)
        services.append([])
    calls = []
    s.call(S.BASE + entries["TRIG"], track)
    t.trig(counted(calls)[0])
    services.append(calls)
    want, kinds = [], ["INIT", "TRIG"]
    events = dict(events)
    for b in range(blocks):
        ev = dict(events.get(b, {}))
        retrig = ev.pop("trig", False)
        if ev:
            params = {**params, **ev}
            t.set_params(**params)
            for k in range(1, 9):
                s.set_y(k, t.y[k])
        if retrig:
            calls = []
            s.call(S.BASE + entries["TRIG"], track)
            t.trig(counted(calls)[0])
            services.append(calls)
            kinds.append("TRIG")
        calls = []
        if b == trace:
            s.cmds += ["change r6 $%x" % S.R6, "change r7 $%x" % S.R7, "change m7 $1f"]
            s.cmds += ["change m%d $ffffff" % i for i in range(6)]
            s.cmds += ["change p:$%x $%x" % (S.DRIVER + 1, S.BASE + entries["RENDER"]),
                       "change pc $%x" % S.DRIVER, "trace 9000 h"]
            lod = S.lod_block("P", S.BASE, words) + S.STUB_LOD + S.lod_block("X", S.INFO_AT, [len(pcm), step]) \
                + S.lod_block("X", S.SAMPLE_AT, pcm) + ([] if internal is None else S.lod_block("X", S.INTERNAL_AT, internal))
            S.Session.run(s, lod, f"{tag}_trace")
            return None
        s.call(S.BASE + entries["RENDER"], track, capture=True)
        ci, cr = counted(calls)
        want.append(t.render(cr, ci))
        services.append(calls)
        kinds.append("RENDER")
    s.cmds.append("display y:$%x..$%x" % (S.R6 + 9, S.R6 + 63))
    s.cmds.append("display x:$%x..$%x" % (S.R6, S.R6 + XSTATE[-1]))
    lod = S.lod_block("P", S.BASE, words) + S.STUB_LOD + S.lod_block("X", S.INFO_AT, [len(pcm), step])
    if not fast:
        lod += S.lod_block("X", S.SAMPLE_AT, pcm)
        if internal is not None:
            lod += S.lod_block("X", S.INTERNAL_AT, internal)
    run_tag = tag + ("_fast" if fast else "")
    cycles, got = s.run(lod, run_tag)
    status = "-"
    if not fast:
        bad = [i for i, (g, w) in enumerate(zip(got, want)) if g != w]
        status = "OK" if not bad and len(got) == blocks else f"MISMATCH in blocks {bad[:8]}"
        lines = (S.WORK / f"{run_tag}.log").read_text().splitlines()
        for space, rng, ref in (("y", range(9, 64), t.y), ("x", XSTATE, t.x)):
            start = max(i for i, line in enumerate(lines) if line.startswith("display %s:$%x" % (space, S.R6 + rng[0])))
            vals = []
            for line in lines[start + 1:]:
                if not line.startswith(space + ":$"):
                    break
                vals += [int(v[1:], 16) for v in line.split("=")[-1].split()]
            wrong = [k for k, v in zip(rng, vals) if v != ref[k] & 0xFFFFFF]
            if wrong or len(vals) != len(rng):
                status += f", {space.upper()} DIFFERS at +{wrong[:6]}"
    return status, cycles, services, kinds, t


if __name__ == "__main__":
    S.STUB_LOD = S.assemble_stubs()
    S.STUB = S.stub_costs()
    print("stand-in cost, JSR to return:", S.STUB)
    loop = drums(0.55)                           # 24255 frames: X:$4000.. stays below $C000
    internal = S.test_signal(12000, hz=660)
    dense = dense_hits(46000)                    # longer: no internal sample loaded with it
    base = dict(ptch=64, smpl=5, dec=127, time=0, play=0, thrs=27, slic=32, slno=1)
    full, uw = 0x010000, 0x00B000
    runs = [
        # analysis during silence after a TRIG of an unanalysed sample (equal slices), then onsets
        ("idle_then_onsets", loop, internal, full, {**base, "dec": 0, "slic": 4, "slno": 2},
         {150: {"trig": True, "slno": 3}, 170: {"trig": True, "slno": 6, "thrs": 60}}, 260),
        ("playing_while_analysing", loop, internal, full, {**base, "slic": 8, "slno": 1, "time": 30},
         {120: {"trig": True, "slno": 2, "play": 2}}, 220),
        ("bigger_threshold", loop, internal, uw, {**base, "slic": 3, "dec": 0},
         {100: {"trig": True, "thrs": 127, "slno": 2}, 140: {"trig": True, "thrs": 0, "slic": 2, "slno": 2}}, 200),
        ("smpl_change", loop, internal, full, {**base, "dec": 0},
         {40: {"smpl": 49}, 120: {"trig": True, "slno": 4}, 160: {"smpl": 5, "trig": True}}, 220),
        ("dense", dense, None, full, {**base, "dec": 0, "slic": 32},
         {180: {"trig": True, "slno": 17}, 200: {"trig": True, "slno": 31, "slic": 10}}, 260),
        ("preset_full_list", dense, None, full, {**base, "dec": 0, "slic": 20, "slno": 7, "thrs": 30},
         {150: {"trig": True, "slno": 25, "slic": 32, "thrs": 0}}, 190, full_list),
    ]
    all_ok = True
    print("\n1. audio and state, simulator against the model")
    for tag, pcm, internal_pcm, step, params, events, blocks, *preset in runs:
        status, _, _, _, t = scenario(tag, pcm, internal_pcm, step, params, events, blocks,
                                      preset=preset[0] if preset else None)
        all_ok &= status == "OK"
        print(f"   {tag:24s} {status}   ({t.y[tm.A_CNT]} onsets listed, done {t.y[tm.A_DONE]})")

    print("\n2. cycles, own code + documented service worst case")
    worst = {}
    for tag, pcm, internal_pcm, step, params, events, blocks, *preset in runs:
        _, cycles, services, kinds, _ = scenario(tag, pcm, internal_pcm, step, params, events, blocks,
                                                 fast=True, preset=preset[0] if preset else None)
        prev = None
        for c, calls, kind in zip(cycles, services, kinds):
            total = c + sum(S.SERVICE_MAX[sym](n) - S.STUB[sym] for sym, n in calls)
            name = kind if kind != "RENDER" else "RENDER (%d reads%s)" % (
                sum(1 for sym, _ in calls if sym == 10), ", info" if any(sym == 9 for sym, _ in calls) else "")
            if kind == "RENDER" and prev == "TRIG":
                name = "RENDER after TRIG"
            worst[name] = max(worst.get(name, 0), total)
            prev = kind
    for name, c in sorted(worst.items()):
        print(f"   {name:24s} {c:5d}")
    trig_block = worst.get("INIT", 0) + worst["TRIG"] + worst["RENDER after TRIG"]
    budget = max([trig_block] + [c for n, c in worst.items() if n.startswith("RENDER (")])
    print(f"   INIT + TRIG + RENDER after TRIG = {trig_block}; worst block = {budget}; with 75 overhead"
          f" {budget + 75} (limit 3951)")

    print("\n3. code footprint per kind of block (instruction cache: at most %d sectors)" % SECTORS_MAX)
    for run in runs:
        tag, pcm, internal_pcm, step, params, events, blocks, *preset = run
        kinds = block_kinds(pcm, internal_pcm, step, params, events, blocks, preset[0] if preset else None)
        for kind in ("crossfade", "hop", "refine", "commit", "restart", "voice only"):
            if kind in kinds and not run[0].startswith(("bigger", "smpl", "dense")):
                b = kinds.index(kind)
                n, words, sectors = footprint(run, b)
                ok = sectors <= SECTORS_MAX
                all_ok &= ok
                print(f"   {tag:24s} block {b:3d} {kind:10s}: {n:4d} instructions, {words:3d} words,"
                      f" {sectors} sectors{'' if ok else '  OVER'}")
    sys.exit(0 if all_ok else 1)
