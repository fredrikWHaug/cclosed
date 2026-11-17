#!/bin/sh
# Re-export the KiCad 3D view as site/form-factor.glb after the PCB changes,
# then write site/parts.json (each part's position in the model) so page markers follow the parts
cd "$(dirname "$0")"
PCB=../form-factor/form-factor.kicad_pcb
/Applications/KiCad/KiCad.app/Contents/MacOS/kicad-cli pcb export glb \
  --subst-models --include-tracks --include-pads --include-zones --include-silkscreen --include-soldermask \
  -o form-factor.glb "$PCB"
python3 - "$PCB" <<'EOF'
# Positions come from the board file, not the model: parts without a 3D body (U1, U2) are missing from the model.
# The model uses metres with KiCad's x as x, KiCad's y as z, and y up from the board's top surface.
import json, re, struct, sys
glb = open("form-factor.glb", "rb").read()
n = struct.unpack("<I", glb[12:16])[0]
nodes = json.loads(glb[20:20 + n])["nodes"]
top = max((nd["translation"][1] for nd in nodes if "translation" in nd), default=0.0016)
pcb = open(sys.argv[1]).read()
parts = {}
for m in re.finditer(r'\(footprint "[^"]+"\s*\(layer "([^"]+)"\)\s*\(uuid "[^"]+"\)\s*\(at ([-\d.]+) ([-\d.]+)', pcb):
    ref = re.search(r'\(property "Reference" "([^"]+)"', pcb[m.end():])
    y = top if m.group(1) == "F.Cu" else 0.0
    parts[ref.group(1)] = [float(m.group(2)) / 1000, y, float(m.group(3)) / 1000]
json.dump(parts, open("parts.json", "w"), indent=1)
print(f"parts.json: {len(parts)} parts")
EOF
