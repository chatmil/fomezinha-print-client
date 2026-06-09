@echo off
echo ============================================
echo  Fomezinha Print Client - Build Windows
echo ============================================

:: Verifica Python
python --version >nul 2>&1
if errorlevel 1 (
    echo ERRO: Python nao encontrado. Instale Python 3.11+ em python.org
    pause
    exit /b 1
)

:: Cria/ativa ambiente virtual
if not exist ".venv" (
    echo Criando ambiente virtual...
    python -m venv .venv
)
call .venv\Scripts\activate.bat

:: Instala dependencias
echo Instalando dependencias...
pip install --upgrade pip
pip install -r requirements.txt
pip install pyinstaller

:: Gera icon.ico a partir do logo.svg se nao existir
if not exist "icon.ico" (
    python -c "
from PIL import Image
import subprocess, os, sys
svg = 'logo.svg'
png_out = 'icon_1024.png'
try:
    from cairosvg import svg2png
    svg2png(url=svg, write_to=png_out, output_width=1024, output_height=1024)
except Exception:
    pass
if not os.path.exists(png_out):
    img = Image.new('RGBA', (1024,1024), (255,107,53,255))
else:
    img = Image.open(png_out).convert('RGBA').resize((1024,1024), Image.LANCZOS)
img.resize((256,256), Image.LANCZOS).save('icon.png')
img.save('icon.ico', format='ICO', sizes=[(256,256),(128,128),(64,64),(48,48),(32,32),(16,16)])
print('Icones criados.')
"
)

:: Build com PyInstaller
echo Gerando executavel...
pyinstaller ^
    --onefile ^
    --windowed ^
    --name "FomezinhaPrint" ^
    --icon icon.ico ^
    --add-data "icon.ico;." ^
    --add-data "icon.png;." ^
    --hidden-import pystray._win32 ^
    --hidden-import PIL._tkinter_finder ^
    --clean ^
    fomezinha_print.py

if errorlevel 1 (
    echo ERRO ao gerar executavel!
    pause
    exit /b 1
)

echo.
echo ============================================
echo  Executavel gerado em: dist\FomezinhaPrint.exe
echo ============================================
pause
