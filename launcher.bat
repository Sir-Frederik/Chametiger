@echo off
cd /d "%~dp0"

echo Avvio ChamerTiger...

:: Avvia app.py in background (tray)
start "" pythonw.exe app.py

:: Piccola pausa per dare tempo al tray di partire
timeout /t 2 /nobreak >nul

:: Avvia la GUI
python.exe gui.py

pause
