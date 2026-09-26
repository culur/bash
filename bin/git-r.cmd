@echo off
setlocal

rem Prioritize Git for Windows bash/sh over WSL bash
if exist "%ProgramFiles%\Git\bin\bash.exe" (
  "%ProgramFiles%\Git\bin\bash.exe" "%~dp0..\src\git\git-r.sh" %*
  exit /b %ERRORLEVEL%
)

if exist "%LOCALAPPDATA%\Programs\Git\bin\bash.exe" (
  "%LOCALAPPDATA%\Programs\Git\bin\bash.exe" "%~dp0..\src\git\git-r.sh" %*
  exit /b %ERRORLEVEL%
)

where sh >nul 2>nul
if %ERRORLEVEL% equ 0 (
  sh "%~dp0..\src\git\git-r.sh" %*
  exit /b %ERRORLEVEL%
)

where bash >nul 2>nul
if %ERRORLEVEL% equ 0 (
  bash "%~dp0..\src\git\git-r.sh" %*
  exit /b %ERRORLEVEL%
)

echo Error: Git Bash or sh not found. On Windows, install Git with Scoop first: scoop install git >&2
echo If Scoop is unavailable, use WinGet: winget install Git.Git >&2
exit /b 1
