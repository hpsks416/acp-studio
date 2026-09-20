@echo off
setlocal
cd /d "%~dp0"

rem Load local-only credentials (gitignored). Copy secrets.cmd.example to secrets.cmd and fill in real values.
if exist "%~dp0secrets.cmd" call "%~dp0secrets.cmd"

set "PY="
where python >nul 2>nul && set "PY=python"
if not defined PY (
  where py >nul 2>nul && set "PY=py -3"
)
if not defined PY (
  echo [acp-studio] Python 3.9+ not found. Install Python and retry.
  pause
  exit /b 1
)

echo [acp-studio] starting http://127.0.0.1:8790/
%PY% server.py