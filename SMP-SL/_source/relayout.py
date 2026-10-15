#!/usr/bin/env python3
"""Move the cold code (INIT, TRIG and its helpers) after the hot code (RENDER and
what it calls), so the code one block executes is contiguous for the instruction
cache. Pure text move; the instructions are unchanged.

  python relayout.py ENGINE.inc [ONSETS.inc]
"""
import re
import sys
from pathlib import Path

engine = Path(sys.argv[1])
lines = engine.read_text().splitlines(keepends=True)
if any(line.startswith("; ---- cold code") for line in lines):
    sys.exit(f"{engine} is already laid out")
start = next(i for i, line in enumerate(lines) if line.startswith("INIT:"))
end = next(i for i, line in enumerate(lines) if line.startswith("DIVQ:"))
# keep DIVQ's comment line(s) with DIVQ
while lines[end - 1].startswith(";"):
    end -= 1
cold = lines[start:end]
rest = lines[:start] + lines[end:]
# insert before the onsets include (TRANS) or the tables include
anchor = next(i for i, line in enumerate(rest)
              if re.match(r"\s+if\s+TRANS\s*$", line) and "onsets.inc" in rest[i + 1]) \
    if any("onsets.inc" in line for line in rest) else \
    next(i for i, line in enumerate(rest) if "include 'tables.inc'" in line)
header = ["; ---- cold code: INIT, TRIG and the slice bounds, after the hot code so the\n",
          "; code RENDER executes stays together in the instruction cache ----\n"]
if len(sys.argv) > 2:                    # the onsets file: ONSET_BOUNDS is cold too
    onsets = Path(sys.argv[2])
    o = onsets.read_text().splitlines(keepends=True)
    a = next(i for i, line in enumerate(o) if line.startswith("; TRIG, with R4 = TABLES"))
    b = next(i for i, line in enumerate(o) if line.startswith("; X0 = bank, Y0 = slot"))
    Path(onsets.parent / "onsets_trig.inc").write_text("".join(o[a:b]))
    onsets.write_text("".join(o[:a] + o[b:]))
    # onsets.inc (hot) first, then the cold code
    anchor += 3                          # after "if TRANS / include onsets / endif"
    cold = cold + ["        if      TRANS\n", "        include 'onsets_trig.inc'\n", "        endif\n"]
out = rest[:anchor] + header + cold + ["\n"] + rest[anchor:]
engine.write_text("".join(out))
print(f"moved {len(cold)} lines of cold code in {engine.name}")
