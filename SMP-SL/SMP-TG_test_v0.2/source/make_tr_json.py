#!/usr/bin/env python3
"""Write the SMP-TR family's JSONs (Python, so no BOM): rom_e12_trslicer (SMP-TR, both
banks), rom_trslicer (SMP-TM, UW ROM), e12_trslicer (SMP-TN, internal E12)."""
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
VERSION = "0.2"
E_LABELS = lambda first: [{"value": first + i, "text": "E%d" % (i + 1)} for i in range(21)]  # noqa: E731


def params(smpl):
    return [
        {"name": "PTCH", "default": 64, "transform": "raw14", "control": "bipolar"},
        smpl,
        {"name": "DEC", "default": 0, "transform": "raw14", "control": "continuous"},
        {"name": "TIME", "default": 0, "transform": "raw14", "control": "continuous"},
        {"name": "PLAY", "default": 0, "min": 0, "max": 2, "transform": "index",
         "value_text": [{"value": v, "text": t} for v, t in enumerate(["FWD", "REV", "BI"])]},
        {"name": "THRS", "default": 27, "transform": "raw14", "control": "continuous"},
        {"name": "SLIC", "default": 32, "min": 1, "max": 32, "transform": "index"},
        {"name": "SLNO", "default": 1, "min": 1, "max": 32, "transform": "index"},
    ]


IMPORTS = [("PCM_A", 7), ("PCM_B", 7), ("POSITIONS", 8), ("READ_SAMPLES", 10), ("ANA_INFO", 9),
           ("ANA_POS", 8), ("ANA_READ", 10), ("ANA_PCM", 7), ("REF_POS", 8), ("REF_READ", 10),
           ("REF_PCM", 7), ("TRIG_INFO", 9), ("OB_TMP", 8)]          # in program order
COMMON = ("sample slicer with slices at detected transients. The selected sample is analysed in the "
          "background (well under a second while the track is quiet); THRS sets how strong a transient must "
          "be (energy rise x1.25 at 0 to x4 at 127), SLIC the most slices, up to 32 (the strongest "
          "transients), SLNO the slice; until the analysis has the sample, SLIC equal slices. PTCH, DEC, "
          "TIME, PLAY as SMP-SL.")
VARIANTS = {
    "rom_e12_trslicer": ("org.example.rom-e12-trslicer", "TRANSIENT SLICER", "TR",
                         {"name": "SMPL", "default": 1, "min": 1, "max": 69, "transform": "index",
                          "value_text": E_LABELS(49)},
                         "UW ROM (SMPL 1..48) and internal E12 (E1..E21) "),
    "rom_trslicer": ("org.example.rom-trslicer", "ROM TRANS SLICER", "TM",
                     {"name": "SMPL", "default": 1, "min": 1, "max": 48, "transform": "index"},
                     "UW ROM (SMPL 1..48) "),
    "e12_trslicer": ("org.example.e12-trslicer", "E12 TRANS SLICER", "TN",
                     {"name": "SMPL", "default": 1, "min": 1, "max": 21, "transform": "index",
                      "value_text": E_LABELS(1)},
                     "Internal E12 (E1..E21) "),
    "rom_e12_trslicer_tg": ("org.example.rom-e12-trslicer-tg", "TRANS SLICER TG", "TG",
                            {"name": "SMPL", "default": 1, "min": 1, "max": 69, "transform": "index",
                             "value_text": E_LABELS(49)},
                            "Test variant of SMP-TR in which TIME above half way also shortens the "
                            "grains (SMP-ST GRAN 64 down to about GRAN 46, 909 samples, at full TIME). UW ROM (SMPL 1..48) "
                            "and internal E12 (E1..E21) "),
}
VERSIONS = {"rom_e12_trslicer_tg": "0.2"}

if __name__ == "__main__":
    for name, (mid, display, code, smpl, desc) in VARIANTS.items():
        m = {"id": mid, "display_name": display, "category": "SMP", "short_label": code,
             "machine_version": VERSIONS.get(name, VERSION), "params": params(smpl),
             "program": {"x_workset_words": 64, "y_workset_words": 64, "relocations": ["TABLE_BASE"],
                         "imports": [{"symbol": s, "abi_symbol": a} for s, a in IMPORTS]},
             "max_track_cycles": 3900, "description": desc + COMMON}
        (HERE / f"{name}.json").write_text(json.dumps(m, indent=2) + "\n", newline="\n")
        print("wrote", name + ".json")
