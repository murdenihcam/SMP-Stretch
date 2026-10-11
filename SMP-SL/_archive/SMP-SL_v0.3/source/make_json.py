#!/usr/bin/env python3
"""Write the machine JSONs with Python, which avoids PowerShell's BOM:
rom_e12_slicer (SMP-SL, both banks), rom_slicer (SMP-SM, UW ROM), e12_slicer (SMP-SN, internal)."""
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
VERSION = "0.3"


def smpl(lo_text, count, first_value):
    """SMPL control: count settings from 1; E labels from first_value on (None: no labels)."""
    p = {"name": "SMPL", "default": 1, "min": 1, "max": count, "transform": "index"}
    if first_value is not None:
        p["value_text"] = [{"value": first_value + i, "text": "E%d" % (i + 1)} for i in range(21)]
    return p


def params(smpl_param):
    return [
        {"name": "PTCH", "default": 64, "transform": "raw14", "control": "bipolar"},
        smpl_param,
        {"name": "DEC", "default": 0, "transform": "raw14", "control": "continuous"},
        {"name": "TIME", "default": 0, "transform": "raw14", "control": "continuous"},
        {"name": "PLAY", "default": 0, "min": 0, "max": 2, "transform": "index",
         "value_text": [{"value": v, "text": t} for v, t in enumerate(["FWD", "REV", "BI"])]},
        {"name": "MODE", "default": 0, "min": 0, "max": 6, "transform": "index",
         "value_text": [{"value": v, "text": t}
                        for v, t in enumerate(["EQUA", "EXP", "LOG", "SED1", "SED2", "SED3", "SED4"])]},
        {"name": "SLIC", "default": 8, "min": 1, "max": 64, "transform": "index"},
        {"name": "SLNO", "default": 1, "min": 1, "max": 64, "transform": "index"},
    ]


COMMON = ("MODE cuts the sample into SLIC slices (EQUA equal, EXP longer along, LOG shorter along, SED1-4 "
          "Perlin-noise seeds), SLNO picks the slice; DEC 0 plays it once, 1..126 decay while PLAY FWD/REV/BI "
          "loops it, 127 loops forever; TIME slows the playhead with SMP-ST's splice stretch (grain 64) at "
          "unchanged pitch; PTCH +-32 semitones")
VARIANTS = {
    "rom_e12_slicer": ("org.example.rom-e12-slicer", "ROM+E12 SLICER", "SL", smpl("E", 69, 49),
                       "UW ROM and internal (E12) sample slicer: SMPL 1..48 UW ROM, E1..E21 internal; "),
    "rom_slicer": ("org.example.rom-slicer", "ROM SLICER", "SM", smpl("", 48, None),
                   "UW ROM sample slicer: SMPL 1..48 UW ROM slots; "),
    "e12_slicer": ("org.example.e12-slicer", "E12 SLICER", "SN", smpl("E", 21, 1),
                   "Internal (E12) sample slicer: SMPL E1..E21; "),
}

if __name__ == "__main__":
    for name, (mid, display, code, smpl_param, desc) in VARIANTS.items():
        m = {"id": mid, "display_name": display, "category": "SMP", "short_label": code,
             "machine_version": VERSION, "params": params(smpl_param),
             "program": {"y_workset_words": 53, "relocations": ["TABLE_BASE"],
                         "imports": [{"symbol": "TRIG_INFO", "abi_symbol": 9},
                                     {"symbol": "PCM_A", "abi_symbol": 7},
                                     {"symbol": "PCM_B", "abi_symbol": 7},
                                     {"symbol": "POSITIONS", "abi_symbol": 8},
                                     {"symbol": "READ_SAMPLES", "abi_symbol": 10}]},
             "max_track_cycles": 3500, "description": desc + COMMON}
        (HERE / f"{name}.json").write_text(json.dumps(m, indent=2) + "\n", newline="\n")
        print("wrote", name + ".json")
