#!/usr/bin/env python3
"""Write rom_granular.json (SMP-GM) and e12_granular.json (SMP-G2) from granular.json (SMP-GR)."""
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
base = json.loads((HERE / "granular.json").read_text())
VERSION = "0.5"
TAIL = ("up to 3 grains with smoothstep fades; DENS grains at once (full rate up to 1, then half rate, "
        "within the cycle budget), GRAN grain length, SEEK start, SCAN playhead speed (64 = still), SPRY random "
        "position and reverse chance, PTCH +-32 semitones, DEC decay (127 = none)")
# the combined machine keeps its installed id
next(p for p in base["params"] if p["name"] == "DEC")["default"] = 64   # mid knob, about 1 s
base["program"].update(x_workset_words=32, y_workset_words=56, relocations=["TABLE_BASE", "TABLE_BASE2"],
                       imports=[{"symbol": s, "abi_symbol": n} for s, n in   # in program order
                                (("POS_ADDR", 8), ("READ_SAMPLES", 10), ("PCM_ADDR", 7), ("TRIG_INFO", 9))])
base.update(display_name="ROM+E12 GRANULAR", machine_version=VERSION,
            description="Granular player for UW ROM (SMPL 1..48) and internal E1..E21 samples: " + TAIL)
(HERE / "granular.json").write_text(json.dumps(base, indent=2) + "\n")
print("wrote granular.json")
TAIL += "; same engine as SMP-GR"
VARIANTS = {
    "rom_granular": dict(id="org.example.rom-only-granular", display_name="ROM GRANULAR", short_label="GM",
                         smpl_max=48, description="Granular player for the UW ROM samples (SMPL 1..48): " + TAIL),
    "e12_granular": dict(id="org.example.e12-granular", display_name="E12 GRANULAR", short_label="G2",
                         smpl_max=21, description="Granular player for the internal E12 samples (SMPL 1..21): "
                         + TAIL),
}
for name, v in VARIANTS.items():
    doc = json.loads(json.dumps(base))
    doc.update(id=v["id"], display_name=v["display_name"], short_label=v["short_label"],
               description=v["description"])
    smpl = next(p for p in doc["params"] if p["name"] == "SMPL")
    smpl["max"] = v["smpl_max"]
    smpl.pop("value_text", None)
    (HERE / f"{name}.json").write_text(json.dumps(doc, indent=2) + "\n")
    print("wrote", name + ".json")
