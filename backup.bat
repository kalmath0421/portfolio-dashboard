@echo off
REM 수동 백업 — 더블클릭으로 즉시 실행
chcp 65001 >nul
title 포트폴리오 백업
cd /d "%~dp0"

if not exist ".venv\Scripts\activate.bat" (
    echo [ERROR] 가상환경이 없습니다. 먼저 run.bat 으로 설치하세요.
    pause
    exit /b 1
)

call .venv\Scripts\activate.bat
python -m src.backup
echo.
pause
