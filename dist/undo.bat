@echo off
setlocal EnableDelayedExpansion
title AULA F75 - откат
chcp 866 >nul
set "APP="
for %%P in ("C:\Program Files (x86)\AULA\F75" "C:\Program Files\AULA\F75" "C:\Program Files (x86)\AULA\F75 Pro" "C:\Program Files (x86)\AULA\F87") do if exist %%P\Text\ set "APP=%%~P"
if not defined APP ( echo Не нашёл папку AULA\...\Text. & pause & exit /b 1 )
for /d %%D in ("!APP!\Text\*") do if exist "%%D\text.xml.bak" (
  move /y "%%D\text.xml.bak" "%%D\text.xml" >nul && echo   возвращено: Text\%%~nxD
)
if exist "!APP!\Text\text.xml.bak" move /y "!APP!\Text\text.xml.bak" "!APP!\Text\text.xml" >nul && echo   возвращено: Text\text.xml
echo.
echo Откат готов. Перезапусти программу.
pause
