@echo off
chcp 65001 >nul
cd /d "%~dp0"
title Import Fonts

if not exist "venv\Scripts\python.exe" (
  echo 先に START.bat を一度実行して、準備を終わらせてください。
  pause
  exit /b 1
)

echo フォント保管庫(fontgazer)のフォントを、このアプリに登録します。
echo フォルダの場所は、初回だけ聞かれます（2回目以降は自動）。
echo.
venv\Scripts\python.exe -m backend.vault_import %*
echo.
pause
