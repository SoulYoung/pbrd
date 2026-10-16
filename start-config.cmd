@echo off
setlocal
cd /d "%~dp0"
where py >nul 2>nul
if not errorlevel 1 (
  py -3 -B ui\local_server.py %*
  if not errorlevel 1 goto :eof
  echo Python launcher failed. Check the error above.
  pause
  exit /b 1
)
where python >nul 2>nul
if not errorlevel 1 (
  python -B ui\local_server.py %*
  if not errorlevel 1 goto :eof
  pause
  exit /b 1
)
echo Python 3.8 or later is required.
echo Install Python 3 and run this script again.
pause
exit /b 1
