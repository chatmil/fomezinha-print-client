@echo off
echo ============================================
echo  Fomezinha Print - Instalador
echo ============================================
echo.

:: Verifica se Python esta instalado
python --version >nul 2>&1
if errorlevel 1 (
    echo Python nao encontrado!
    echo.
    echo Abrindo pagina de download do Python...
    start https://www.python.org/downloads/
    echo.
    echo 1. Baixe e instale o Python 3.11 ou superior
    echo 2. IMPORTANTE: marque "Add Python to PATH" durante a instalacao
    echo 3. Apos instalar, execute este arquivo novamente
    pause
    exit /b 1
)

echo Python encontrado!
echo.

:: Instala dependencias
echo Instalando dependencias...
pip install requests pystray Pillow python-escpos pywin32 --quiet

if errorlevel 1 (
    echo Erro ao instalar dependencias.
    echo Tente executar como Administrador.
    pause
    exit /b 1
)

echo.
echo Dependencias instaladas com sucesso!
echo.

:: Cria atalho na area de trabalho
echo Criando atalho...
set SCRIPT_DIR=%~dp0
set SHORTCUT=%USERPROFILE%\Desktop\Fomezinha Print.lnk

powershell -Command "$WS = New-Object -ComObject WScript.Shell; $S = $WS.CreateShortcut('%SHORTCUT%'); $S.TargetPath = 'pythonw.exe'; $S.Arguments = '\"%SCRIPT_DIR%fomezinha_print.py\"'; $S.WorkingDirectory = '%SCRIPT_DIR%'; $S.IconLocation = '%SCRIPT_DIR%icon.ico, 0'; $S.Save()" 2>nul

:: Cria atalho na inicializacao do Windows (opcional)
set STARTUP=%APPDATA%\Microsoft\Windows\Start Menu\Programs\Startup
choice /C SN /M "Iniciar automaticamente com o Windows?"
if errorlevel 2 goto no_startup

set STARTUP_SHORTCUT=%STARTUP%\Fomezinha Print.lnk
powershell -Command "$WS = New-Object -ComObject WScript.Shell; $S = $WS.CreateShortcut('%STARTUP_SHORTCUT%'); $S.TargetPath = 'pythonw.exe'; $S.Arguments = '\"%SCRIPT_DIR%fomezinha_print.py\"'; $S.WorkingDirectory = '%SCRIPT_DIR%'; $S.Save()" 2>nul
echo Adicionado a inicializacao do Windows!

:no_startup
echo.
echo ============================================
echo  Instalacao concluida!
echo.
echo  - Atalho criado na area de trabalho
echo  - Execute "Fomezinha Print" para abrir
echo ============================================
echo.
pause

:: Inicia o programa
start pythonw.exe "%SCRIPT_DIR%fomezinha_print.py"
