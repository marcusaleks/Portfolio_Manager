@echo off
echo Enviando para GitHub...
"C:\Program Files\Git\cmd\git.exe" push -u origin main
if %errorlevel% neq 0 (
    echo.
    echo Falha ao enviar! Verifique se voce esta autenticado.
    echo Tente rodar: git credential-manager configure
    echo Ou faca login no navegador quando solicitado.
) else (
    echo.
    echo Sucesso! Codigo enviado para https://github.com/marcusaleks/Portfolio_Manager
)
pause
