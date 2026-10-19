@echo off
setlocal
cd /d "%~dp0"
"%SystemRoot%\System32\chcp.com" 65001 >nul
echo Setting up the WeCom transcript exporter...
if exist "runtime\python.exe" (
  "runtime\python.exe" -m venv .venv
) else (
  py -3.13 -m venv .venv
)
if errorlevel 1 goto failed
".venv\Scripts\python.exe" -m pip install --disable-pip-version-check --requirement requirements-lock.txt
if errorlevel 1 goto failed
echo.
echo Setup complete. Double-click Start-Export.cmd to export a recording.
pause
exit /b 0
:failed
echo.
echo Setup failed. Install 64-bit Python 3.13 with its Windows launcher,
echo check your network connection, and run Setup.cmd again.
pause
exit /b 1
