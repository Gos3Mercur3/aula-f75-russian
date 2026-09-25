@echo off
rem publish.bat - entry point for Windows. Same as tools/publish.ps1, but one double-click.
rem The token is never written to disk: it is asked once at run time.
title AULA F75 - publish to GitHub
setlocal
cd /d "%~dp0"
if not exist "tools\publish.ps1" (
  echo ERROR: tools\publish.ps1 not found next to this file.
  echo Unpack the WHOLE folder, do not drag out a single file.
  pause
  exit /b 1
)
powershell -NoProfile -ExecutionPolicy Bypass -File "tools\publish.ps1" %*
if errorlevel 1 (
  echo.
  echo Something went wrong. Screenshot this window and send it.
  pause
)
