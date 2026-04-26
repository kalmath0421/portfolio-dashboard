@echo off
REM 백그라운드로 돌고 있는 Streamlit 서버 종료
title 포트폴리오 대시보드 종료

echo [INFO] 실행 중인 Streamlit 프로세스를 찾습니다...
taskkill /F /FI "WINDOWTITLE eq 포트폴리오 대시보드*" /T >nul 2>&1
taskkill /F /IM streamlit.exe /T >nul 2>&1

REM Streamlit이 streamlit.exe 가 아니라 python.exe 로 떠 있는 경우, 8501 포트 점유 프로세스 종료
for /f "tokens=5" %%a in ('netstat -ano ^| findstr ":8501" ^| findstr "LISTENING"') do (
    echo [INFO] 포트 8501 점유 프로세스 종료: PID %%a
    taskkill /F /PID %%a /T >nul 2>&1
)

echo [INFO] 종료 완료.
timeout /t 2 >nul
