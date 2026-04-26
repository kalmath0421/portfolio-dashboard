@echo off
REM 자동 백업용 — 작업 스케줄러에서 호출. 출력 없이 조용히 종료.
cd /d "%~dp0"
call .venv\Scripts\activate.bat 2>nul
python -m src.backup --silent
