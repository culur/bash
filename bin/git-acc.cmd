@echo off
setlocal

where uv >nul 2>nul
if %ERRORLEVEL% equ 0 (
  uv run "%~dp0..\src\git\git-acc.py" %*
  exit /b %ERRORLEVEL%
)

where python >nul 2>nul
if %ERRORLEVEL% equ 0 (
  python "%~dp0..\src\git\git-acc.py" %*
  exit /b %ERRORLEVEL%
)

echo Error: Neither uv nor python was found on your system. >&2
exit /b 1
