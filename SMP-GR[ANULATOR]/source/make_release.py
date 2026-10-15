#!/usr/bin/env python3
"""Assemble a release folder: one subfolder per machine plus the shared source.

python make_release.py release_v0.3
  SMP-GR_allbanks/, SMP-GM_rom/, SMP-G2_e12/: .syx .mds .json .asm56k .pbm, the
      32x24 logo and a web logo (6x, black on #CD2824)
  source/: the shared engine, generated includes and tools. To rebuild, work in
      the build folder (C:\\work\\granular) with the original file names (BUILD_NAME).
"""
import shutil
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
MACHINES = [  # release name, build name, logo
    ("SMP-GR_allbanks", "granular", "logo_gr_all.png"),
    ("SMP-GM_rom", "rom_granular", "logo_gm_rom.png"),
    ("SMP-G2_e12", "e12_granular", "logo_g2_e12.png"),
]
SOURCE = ["granular_engine.inc", "tables.inc", "gen_tables.py",
          "make_variants.py", "make_release.py", "png_sprite.py", "granular_dsp_model.py", "simtest.py",
          "build.cmd"]

out = HERE / sys.argv[1]
if out.exists():
    shutil.rmtree(out)
for rel, build, logo in MACHINES:
    d = out / rel
    d.mkdir(parents=True)
    for ext in ("syx", "mds", "json", "asm56k", "pbm"):
        shutil.copy2(HERE / f"{build}.{ext}", d / f"{rel}.{ext}")
    shutil.copy2(HERE / logo, d / f"{rel}_logo.png")
    subprocess.run([sys.executable, str(HERE / "png_sprite.py"), str(HERE / logo), "--web",
                    str(d / f"{rel}_web.png")], check=True, capture_output=True)
    print(rel, sorted(p.name for p in d.iterdir()))
src = out / "source"
src.mkdir()
for name in SOURCE:
    shutil.copy2(HERE / name, src / name)
(out / "README.txt").write_text(
    "SMP-GR granular machines, " + out.name.replace("release_", "") + "\n\n"
    "SMP-GR_allbanks  ROM+E12 GRANULAR  UW ROM 1..48 then E1..E21   (build name: granular)\n"
    "SMP-GM_rom       ROM GRANULAR      UW ROM 1..48                (build name: rom_granular)\n"
    "SMP-G2_e12       E12 GRANULAR      internal E12 1..21          (build name: e12_granular)\n\n"
    "Each folder: .syx to send to the Machinedrum, .mds package, .json definition, .asm56k wrapper,\n"
    ".pbm sprite, the 32x24 logo and a web logo (black on #CD2824).\n"
    "source/: shared engine (granular_engine.inc), generated includes and the Python tools.\n"
    "The builds were made in C:\\work\\granular under the build names above.\n")
print("wrote", out)
