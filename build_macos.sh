#!/bin/bash
set -e

echo "============================================"
echo " Fomezinha Print Client - Build macOS"
echo "============================================"

if ! command -v python3 &>/dev/null; then
    echo "ERRO: Python3 não encontrado."
    exit 1
fi

# Ambiente virtual
if [ ! -d ".venv" ]; then
    python3 -m venv .venv
fi
source .venv/bin/activate

pip install --upgrade pip -q
pip install -r requirements.txt -q
pip install pyinstaller -q

# Gera ícones a partir do SVG (via qlmanage do macOS)
echo "Gerando ícones..."
if [ ! -f "icon.png" ] || [ ! -f "icon.icns" ]; then
    qlmanage -t -s 1024 -o /tmp/ logo.svg 2>/dev/null || true
    python3 - << 'PYEOF'
from PIL import Image
import os, subprocess, sys

src_path = "/tmp/logo.svg.png"
if not os.path.exists(src_path):
    print("AVISO: logo.svg.png não encontrado, gerando ícone genérico.")
    img = Image.new("RGBA", (1024, 1024), (255, 107, 53, 255))
else:
    img = Image.open(src_path).convert("RGBA").resize((1024, 1024), Image.LANCZOS)

img.save("icon_1024.png")
img.resize((256, 256), Image.LANCZOS).save("icon.png")
print("icon.png OK")

iconset = "icon.iconset"
os.makedirs(iconset, exist_ok=True)
for s in [16, 32, 64, 128, 256, 512, 1024]:
    img.resize((s, s), Image.LANCZOS).save(f"{iconset}/icon_{s}x{s}.png")
    if s <= 512:
        img.resize((s*2, s*2), Image.LANCZOS).save(f"{iconset}/icon_{s}x{s}@2x.png")
PYEOF
    iconutil -c icns icon.iconset -o icon.icns
    rm -rf icon.iconset
    echo "icon.icns OK"
fi

# Build .app com PyInstaller
echo "Gerando .app..."
pyinstaller \
    --onedir \
    --windowed \
    --name "FomezinhaPrint" \
    --icon icon.icns \
    --add-data "icon.png:." \
    --add-data "icon.icns:." \
    --hidden-import pystray._darwin \
    --hidden-import PIL._tkinter_finder \
    --osx-bundle-identifier "com.fomezinha.print" \
    --noconfirm \
    --clean \
    fomezinha_print.py

if [ ! -d "dist/FomezinhaPrint.app" ]; then
    echo "ERRO: .app não foi gerado!"
    exit 1
fi
echo ".app OK"

# Gera .dmg com hdiutil (nativo macOS)
echo "Gerando .dmg..."
DMG_NAME="FomezinhaPrint.dmg"
rm -f "dist/$DMG_NAME"

# Pasta staging: .app + atalho para /Applications
STAGING=$(mktemp -d)
cp -R "dist/FomezinhaPrint.app" "$STAGING/"
ln -s /Applications "$STAGING/Applications"

# Cria DMG comprimido direto
hdiutil create \
    -volname "Fomezinha Print" \
    -srcfolder "$STAGING" \
    -ov \
    -format UDZO \
    -imagekey zlib-level=9 \
    "dist/$DMG_NAME"

rm -rf "$STAGING"

echo ""
echo "============================================"
echo " DMG gerado em: dist/$DMG_NAME"
echo "============================================"
