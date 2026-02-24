@echo off
echo Configurando identidade do Git...
echo.
set /p NAME="Digite seu Nome (ex: Marcus Aleks): "
set /p EMAIL="Digite seu E-mail (ex: marcus@email.com): "

if "%NAME%"=="" goto error
if "%EMAIL%"=="" goto error

echo.
echo Configurando...
"C:\Program Files\Git\cmd\git.exe" config --global user.name "%NAME%"
"C:\Program Files\Git\cmd\git.exe" config --global user.email "%EMAIL%"

echo.
echo Sucesso! Configuracao aplicada.
pause
goto end

:error
echo Nome ou E-mail invalidos.
pause

:end
