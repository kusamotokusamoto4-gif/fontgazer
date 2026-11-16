@echo off
chcp 65001 >nul
cd /d "%~dp0"
title Font Library

set "PY="
where py >nul 2>nul
if not errorlevel 1 set "PY=py -3"
if not defined PY (
  where python >nul 2>nul
  if not errorlevel 1 set "PY=python"
)
if not defined PY (
  echo Python が見つかりません。https://www.python.org/ からインストールしてください。
  echo インストール時に "Add python.exe to PATH" にチェックを入れてください。
  pause
  exit /b 1
)

:menu
cls
echo ==========================================
echo   テロップ用フォント ライブラリ
echo ==========================================
echo   1. 日本語対応フォントを収集（続きから再開OK）
echo   2. 1 に加えて、欧文のみ人気上位100も収集
echo   3. プレビューを開く（日本語テロップで確認）
echo   4. GitHub に保存（commit と push）
echo   5. 装飾系（縁取り・影・カラー）を追加収集
echo   6. 他サイトのフォントを取り込む（queue.json と inbox）
echo   0. 終了
echo ------------------------------------------
set /p CHOICE=番号を入力: 

if "%CHOICE%"=="1" goto fetch
if "%CHOICE%"=="2" goto fetchlatin
if "%CHOICE%"=="3" goto preview
if "%CHOICE%"=="4" goto gitpush
if "%CHOICE%"=="5" goto deco
if "%CHOICE%"=="6" goto manual
if "%CHOICE%"=="0" exit /b 0
goto menu

:fetch
%PY% fetch_fonts.py
pause
goto menu

:fetchlatin
%PY% fetch_fonts.py --latin 100
pause
goto menu

:deco
%PY% fetch_fonts.py --display 150 --color
pause
goto menu

:manual
%PY% add_manual.py
pause
goto menu

:preview
%PY% fetch_fonts.py --preview-only
start "" "%~dp0preview.html"
goto menu

:gitpush
where git >nul 2>nul
if errorlevel 1 (
  echo Git が見つかりません。https://git-scm.com/ からインストールしてください。
  pause
  goto menu
)
git add -A
git commit -m "Update fonts %date% %time%"
git push
pause
goto menu
