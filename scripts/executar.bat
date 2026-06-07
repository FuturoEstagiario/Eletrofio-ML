@echo off
REM EletroFrio ML - Script de execucao para Windows
REM Garante backend nao-interativo e encoding UTF-8

set MPLBACKEND=Agg
set PYTHONIOENCODING=utf-8

echo.
echo  Iniciando pipeline EletroFrio ML...
echo.

python main.py %*
