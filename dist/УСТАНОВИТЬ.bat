@echo off
setlocal EnableDelayedExpansion
chcp 866 >nul
title AULA F75 - установка русского
echo.
echo  ============================================
echo   РУСИФИКАЦИЯ AULA F75  -  OemDrv / BYCOMBO4
echo   Ставит text_ru.xml во все папки языка.
echo  ============================================
echo.

rem ---- файл перевода должен лежать рядом с батником ----
set "SRC=%~dp0text_ru.xml"
if not exist "%SRC%" set "SRC=%~dp0AULA_F75_RU\text_ru.xml"
if not exist "%SRC%" goto :nosrc
rem ---- ищем папку программы (порядок = приоритет) ----
set "APP="
if exist "C:\Program Files (x86)\AULA\F75\Text\" set "APP=C:\Program Files (x86)\AULA\F75"
if not defined APP if exist "C:\Program Files (x86)\AULA\F75 Pro\Text\" set "APP=C:\Program Files (x86)\AULA\F75 Pro"
if not defined APP if exist "C:\Program Files (x86)\AULA\F75 Max\Text\" set "APP=C:\Program Files (x86)\AULA\F75 Max"
if not defined APP if exist "C:\Program Files (x86)\AULA\F87\Text\" set "APP=C:\Program Files (x86)\AULA\F87"
if not defined APP if exist "C:\Program Files (x86)\AULA\F99\Text\" set "APP=C:\Program Files (x86)\AULA\F99"
if not defined APP if exist "C:\Program Files\AULA\F75\Text\" set "APP=C:\Program Files\AULA\F75"
if not defined APP if exist "D:\Program Files (x86)\AULA\F75\Text\" set "APP=D:\Program Files (x86)\AULA\F75"
if not defined APP goto :noapp

echo  Папка программы: !APP!
echo  Файл перевода  : %SRC%
echo.

net session >nul 2>&1
if errorlevel 1 echo  Прав админа нет - пробую писать как есть.
if errorlevel 1 echo  Если размеры в конце не изменятся - повтори запуск правой кнопкой "Запуск от имени администратора".
echo.

set /a N=0
for /d %%D in ("!APP!\Text\*") do call :one "%%D"
if !N! equ 0 (
  echo  В подпапках языка text.xml не нашёлся - пишу Text\text.xml
  call :one "!APP!\Text"
)
goto :report

:one
if not exist "%~1\text.xml" (
  echo   [skip] Text\%~nxD - нет text.xml
  goto :eof
)
if not exist "%~1\text.xml.bak" copy /y "%~1\text.xml" "%~1\text.xml.bak" >nul
copy /y "%SRC%" "%~1\text.xml" >nul
if errorlevel 1 (echo   [ОШИБКА] Text\%~nxD & goto :eof)
set /a N+=1
echo   [OK] Text\%~nxD\text.xml
goto :eof

:report
echo.
echo  Проверка. Все файлы должны быть одного размера:
for %%A in ("!APP!\Text\*\text.xml") do call :show "%%A"
echo.
echo  Обновлено папок языка: !N!
echo  Оригинал цел - рядом лежит text.xml.bak, удалять его не нужно.
echo  Откат в любой момент: undo.bat
echo.
set /p Q=Запустить программу сейчас? Y/n: 
if /i not "%Q%"=="n" if exist "!APP!\OemDrv.exe" start "" "!APP!\OemDrv.exe"
echo  Готово. Перезапусти программу, если она была открыта.
pause
exit /b 0

:show
for %%B in ("%~1") do echo    Text\%%~nxB\text.xml  %%~zB байт
goto :eof

:nosrc
echo  НЕ НАШЕЛ text_ru.xml рядом с батником.
echo  Распакуй архив ЦЕЛИКОМ, не вытаскивай отдельно один батник.
echo.
pause
exit /b 1

:noapp
echo  Не нашёл папку программы вида ...\AULA\F75\Text
echo  Открой этот файл Блокнотом и впиши свой путь в строку с if exist - или напиши мне.
echo.
pause
exit /b 1
