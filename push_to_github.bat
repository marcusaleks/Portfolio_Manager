@echo off
set /p REPO_URL="Digite a URL do seu repositorio GitHub (ex: https://github.com/usuario/portfolio.git): "
if "%REPO_URL%"=="" goto error

echo Configurando remoto...
"C:\Program Files\Git\cmd\git.exe" branch -M main
"C:\Program Files\Git\cmd\git.exe" remote add origin %REPO_URL%

echo Enviando arquivos...
"C:\Program Files\Git\cmd\git.exe" push -u origin main

echo.
echo Sucesso! Agora crie a Release no GitHub e anexe os arquivos.
pause
goto end

:error
echo URL invalida. Tente novamente.
pause

:end
