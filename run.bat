@echo off
REM Windows 11 일반 실행 — 콘솔 창이 함께 뜸 (창을 닫으면 서버 종료)
title 포트폴리오 대시보드
cd /d "%~dp0"

if not exist ".venv\Scripts\activate.bat" (
    echo [INFO] 가상환경이 없습니다. 처음 한 번만 설치합니다 (수 분 소요)...
    py -3.11 -m venv .venv
    if errorlevel 1 (
        echo [ERROR] Python 3.11+ 가 설치되어 있는지 확인하세요.
        pause
        exit /b 1
    )
    call .venv\Scripts\activate.bat
    python -m pip install --upgrade pip --quiet
    pip install -e . --quiet
    echo [INFO] 설치 완료.
) else (
    call .venv\Scripts\activate.bat
)

echo [INFO] 대시보드 시작 — 잠시 후 브라우저가 자동으로 열립니다.
echo        (이 창을 닫으면 서버가 종료됩니다)
echo.
streamlit run app.py
