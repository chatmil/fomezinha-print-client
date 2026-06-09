"""Gera icon.png, icon.ico e icon.iconset a partir do favicon.svg."""
import re
import base64
import io
import os
import sys
from PIL import Image

svg = open("favicon.svg", "r", encoding="utf-8").read()
match = re.search(r'xlink:href="data:image/png;base64,([^"]+)"', svg)

if match:
    data = base64.b64decode(match.group(1).strip())
    img = Image.open(io.BytesIO(data)).convert("RGBA").resize((1024, 1024), Image.LANCZOS)
    print("PNG extraído do SVG.")
else:
    print("AVISO: PNG não encontrado no SVG, usando cor sólida.")
    img = Image.new("RGBA", (1024, 1024), (255, 107, 53, 255))

img.resize((256, 256), Image.LANCZOS).save("icon.png")
print("icon.png OK")

img.save("icon.ico", format="ICO",
         sizes=[(256, 256), (128, 128), (64, 64), (48, 48), (32, 32), (16, 16)])
print("icon.ico OK")

# iconset para macOS (só gerado se não for Windows)
if sys.platform != "win32":
    iconset = "icon.iconset"
    os.makedirs(iconset, exist_ok=True)
    for s in [16, 32, 64, 128, 256, 512, 1024]:
        img.resize((s, s), Image.LANCZOS).save(f"{iconset}/icon_{s}x{s}.png")
        if s <= 512:
            img.resize((s * 2, s * 2), Image.LANCZOS).save(f"{iconset}/icon_{s}x{s}@2x.png")
    print("iconset OK")
