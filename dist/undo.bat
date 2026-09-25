@echo off
setlocal EnableDelayedExpansion
title AULA F75 - откат
chcp 866 >nul
set "APP="
if exist "C:\Program Files (x86)\AULA\F75\Text\" set "APP=C:\Program Files (x86)\AULA\F75"
if not defined APP if exist "C:\Program Files (x86)\AULA\F75 Pro\Text\" set "APP=C:\Program Files (x86)\AULA\F75 Pro"
if not defined APP if exist "C:\Program Files (x86)\AULA\F75 Max\Text\" set "APP=C:\Program Files (x86)\AULA\F75 Max"
if not defined APP if exist "C:\Program Files (x86)\AULA\F87\Text\" set "APP=C:\Program Files (x86)\AULA\F87"
if not defined APP if exist "C:\Program Files (x86)\AULA\F99\Text\" set "APP=C:\Program Files (x86)\AULA\F99"
if not defined APP if exist "C:\Program Files\AULA\F75\Text\" set "APP=C:\Program Files\AULA\F75"
if not defined APP if exist "D:\Program Files (x86)\AULA\F75\Text\" set "APP=D:\Program Files (x86)\AULA\F75"
if not defined APP ( echo Не нашёл папку AULA\...\Text. & pause & exit /b 1 )

echo  Откатываю: !APP!
set /a M=0
for /d %%D in ("!APP!\Text\*") do call :back "%%D"
call :back "!APP!\Text"

echo.
if !M! equ 0 ( echo  Резервных копий text.xml.bak не нашёл - значит установка здесь не делалась. ) else ( echo  Возвращено папок: !M! )
echo  Перезапусти программу, чтобы она прочитала оригинал.
pause
exit /b 0

:back
if exist "%~1\text.xml.bak" (
  move /y "%~1\text.xml.bak" "%~1\text.xml" >nul
  if errorlevel 1 (echo   [ОШИБКА] %~nxD & goto :eof)
  set /a M+=1
  echo   возвращено: Text\%~nxD
)
goto :eof
