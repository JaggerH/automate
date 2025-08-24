@echo off
chcp 65001 > nul
title Automate Daemon Mode

echo Starting Automate Daemon Mode...
echo ================================
echo This will continuously monitor target processes
echo and automatically inject when processes are detected.
echo.
echo To stop, press Ctrl+C
echo ================================
echo.

python main.py --daemon

pause