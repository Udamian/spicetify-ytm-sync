@echo off
rem Double-click to remove YTM Sync. Your YouTube Music session and data are kept.
rem To delete those too, run:  ytm-sync.exe uninstall --purge
cd /d "%~dp0"
ytm-sync.exe uninstall
echo.
pause
