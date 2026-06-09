#!/bin/bash
set -e

echo "============================================"
echo " Fomezinha Print Client - Build Linux"
echo "============================================"

# Verifica Python
if ! command -v python3 &>/dev/null; then
    echo "ERRO: Python3 não encontrado."
    exit 1
fi

# Ambiente virtual
if [ ! -d ".venv" ]; then
    python3 -m venv .venv
fi
source .venv/bin/activate

pip install --upgrade pip
pip install -r requirements.txt
pip install pyinstaller

# Gera ícone PNG
python3 -c "
from PIL import Image, ImageDraw
img = Image.new('RGB', (256, 256), (255, 102, 0))
d = ImageDraw.Draw(img)
d.rectangle([30, 80, 226, 176], fill='white')
d.rectangle([55, 30, 200, 90], fill='white')
d.rectangle([75, 140, 180, 220], fill='white')
d.rectangle([95, 160, 160, 205], fill=(255, 102, 0))
img.save('icon.png')
print('Ícone criado.')
"

pyinstaller \
    --onefile \
    --windowed \
    --name "fomezinha-print" \
    --add-data "icon.png:." \
    --hidden-import pystray._xorg \
    --clean \
    fomezinha_print.py

echo ""
echo "============================================"
echo " Executável gerado em: dist/fomezinha-print"
echo "============================================"
