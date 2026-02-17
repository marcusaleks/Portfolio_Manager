@echo off
echo ============================================
echo   Portfólio V.1.0 - Build Script
echo ============================================
echo.

echo [1/3] Instalando dependências de build...
pip install pyinstaller

echo.
echo [2/3] Gerando executável com PyInstaller...
pyinstaller portfolio.spec --noconfirm

echo.
echo [3/3] Build concluído!
echo.
echo O executável está em: dist\Portfolio.exe
echo.
echo Para criar o instalador:
echo   1. Instale o Inno Setup: https://jrsoftware.org/isdl.php
echo   2. Abra installer.iss no Inno Setup
echo   3. Compile (Ctrl+F9)
echo   4. O instalador será gerado em Output\PortfolioSetup_v1.0.0.exe
echo.
pause
