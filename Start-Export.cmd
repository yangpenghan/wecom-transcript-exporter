@echo off
setlocal
cd /d "%~dp0"
"%SystemRoot%\System32\chcp.com" 65001 >nul
if not exist ".venv\Scripts\python.exe" (
  echo Run Setup.cmd once before exporting.
  pause
  exit /b 1
)
echo WeCom background transcript export
echo Select a cached recording by number. You can keep using your computer.
echo.
".venv\Scripts\python.exe" native_export.py %*
set "exportExit=%ERRORLEVEL%"
echo.
if "%exportExit%"=="0" (echo Finished. Exports are saved under exports\native\ unless --output was supplied.) else (echo Export failed. Read the error above.)
pause
exit /b %exportExit%
