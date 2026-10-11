#!/usr/bin/env python3
"""Write rom_e12_slicer.json (SMP-SL) with Python, which avoids PowerShell's BOM."""
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
VERSION = "0.2"
E = [{"value": 49 + i, "text": "E%d" % (i + 1)} for i in range(21)]
PARAMS = [
    {"name": "PTCH", "default": 64, "transform": "raw14", "control": "bipolar"},
    {"name": "SMPL", "default": 1, "min": 1, "max": 69, "transform": "index", "value_text": E},
    {"name": "DEC", "default": 0, "transform": "raw14", "control": "continuous"},
    {"name": "TIME", "default": 0, "transform": "raw14", "control": "continuous"},
    {"name": "MODE", "default": 0, "min": 0, "max": 6, "transform": "index",
     "value_text": [{"value": v, "text": t}
                    for v, t in enumerate(["EQUA", "EXP", "LOG", "SED1", "SED2", "SED3", "SED4"])]},
    {"name": "PLAY", "default": 0, "min": 0, "max": 2, "transform": "index",
     "value_text": [{"value": v, "text": t} for v, t in enumerate(["FWD", "REV", "BI"])]},
    {"name": "SLIC", "default": 8, "min": 1, "max": 64, "transform": "index"},
    {"name": "SLNO", "default": 1, "min": 1, "max": 64, "transform": "index"},
]
DESC = ("UW ROM and internal (E12) sample slicer: SMPL 1..48 UW ROM, E1..E21 internal; MODE cuts the sample "
        "into SLIC slices (EQUA equal, EXP longer along, LOG shorter along, SED1-4 Perlin-noise seeds), SLNO "
        "picks the slice; DEC 0 plays it once, 1..126 decay while PLAY FWD/REV/BI loops it, 127 loops forever; "
        "TIME slows the playhead with SMP-ST's splice stretch (grain 64) at unchanged pitch; "
        "PTCH +-32 semitones")

if __name__ == "__main__":
    m = {"id": "org.example.rom-e12-slicer", "display_name": "ROM+E12 SLICER", "category": "SMP",
         "short_label": "SL", "machine_version": VERSION, "params": PARAMS,
         "program": {"y_workset_words": 52, "relocations": ["TABLE_BASE"],
                     "imports": [{"symbol": "TRIG_INFO", "abi_symbol": 9},
                                 {"symbol": "PCM_A", "abi_symbol": 7},
                                 {"symbol": "PCM_B", "abi_symbol": 7},
                                 {"symbol": "POSITIONS", "abi_symbol": 8},
                                 {"symbol": "READ_SAMPLES", "abi_symbol": 10}]},
         "max_track_cycles": 3500, "description": DESC}
    (HERE / "rom_e12_slicer.json").write_text(json.dumps(m, indent=2) + "\n", newline="\n")
    print("wrote rom_e12_slicer.json")
