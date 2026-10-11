#!/usr/bin/env python3
"""Write the machine JSONs (avoids PowerShell's BOM): rom_e12_slicer (SMP-SL) and
rom_e12_slicer_st (SMP-SX, TIME as SMP-ST: playhead speed ignores PTCH)."""
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
VERSION = "0.1"
E = [{"value": 49 + i, "text": "E%d" % (i + 1)} for i in range(21)]
PARAMS = [
    {"name": "PTCH", "default": 64, "transform": "raw14", "control": "bipolar"},
    {"name": "SMPL", "default": 1, "min": 1, "max": 69, "transform": "index", "value_text": E},
    {"name": "DEC", "default": 127, "transform": "raw14", "control": "continuous"},
    {"name": "TIME", "default": 0, "transform": "raw14", "control": "continuous"},
    {"name": "PLAY", "default": 0, "min": 0, "max": 2, "transform": "index",
     "value_text": [{"value": v, "text": t} for v, t in enumerate(["FWD", "REV", "BI"])]},
    {"name": "MODE", "default": 0, "min": 0, "max": 6, "transform": "index",
     "value_text": [{"value": v, "text": t}
                    for v, t in enumerate(["EQUA", "EXP", "LOG", "SED1", "SED2", "SED3", "SED4"])]},
    {"name": "SLIC", "default": 8, "min": 1, "max": 64, "transform": "index"},
    {"name": "SLNO", "default": 1, "min": 1, "max": 64, "transform": "index"},
]
DESC = ("UW ROM and internal (E12) sample slicer: SMPL 1..48 UW ROM, E1..E21 internal; MODE cuts the sample "
        "into SLIC slices (EQUA equal, EXP longer along, LOG shorter along, SED1-4 Perlin-noise seeds), SLNO "
        "picks the slice; PLAY FWD/REV/BI loops it while DEC lasts (127 = forever); TIME slows the playhead "
        "with SMP-ST's splice stretch (grain 64); PTCH +-32 semitones")
VARIANTS = {
    "rom_e12_slicer": ("org.example.rom-e12-slicer", "ROM+E12 SLICER", "SL", ""),
    "rom_e12_slicer_st": ("org.example.rom-e12-slicer-st", "SLICER ST-TIME", "SX",
                          " (test variant: with TIME above 0 the playhead speed ignores PTCH, as SMP-ST)"),
}

if __name__ == "__main__":
    for name, (mid, display, code, extra) in VARIANTS.items():
        m = {"id": mid, "display_name": display, "category": "SMP", "short_label": code,
             "machine_version": VERSION, "params": PARAMS,
             "program": {"y_workset_words": 51, "relocations": ["TABLE_BASE"],
                         "imports": [{"symbol": "TRIG_INFO", "abi_symbol": 9},
                                     {"symbol": "PCM_A", "abi_symbol": 7},
                                     {"symbol": "PCM_B", "abi_symbol": 7},
                                     {"symbol": "POSITIONS", "abi_symbol": 8},
                                     {"symbol": "READ_SAMPLES", "abi_symbol": 10}]},
             "max_track_cycles": 3500, "description": DESC + extra}
        (HERE / f"{name}.json").write_text(json.dumps(m, indent=2) + "\n", newline="\n")
        print("wrote", name + ".json")
