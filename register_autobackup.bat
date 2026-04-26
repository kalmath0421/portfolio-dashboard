@echo off
REM Windows 작업 스케줄러에 매일 자동 백업 작업 등록
chcp 65001 >nul
title 자동 백업 등록
cd /d "%~dp0"

if not exist "backup_silent.bat" (
    echo [ERROR] backup_silent.bat 가 없습니다.
    pause
    exit /b 1
)

REM 매일 23:30 에 실행 (PC 켜져 있는 시간이면 그때, 꺼져 있으면 다음 부팅 시)
schtasks /create /tn "PortfolioDashboardBackup" ^
    /tr "\"%~dp0backup_silent.bat\"" ^
    /sc DAILY /st 23:30 /f /rl LIMITED

if errorlevel 1 (
    echo.
    echo [ERROR] 작업 등록 실패. 명령 프롬프트를 관리자 권한으로 실행해 주세요.
    pause
    exit /b 1
)

echo.
echo [OK] 매일 23:30 자동 백업이 등록되었습니다.
echo      Windows 작업 스케줄러에서 "PortfolioDashboardBackup" 으로 확인 가능.
echo.
echo 해제하려면 unregister_autobackup.bat 실행.
echo.
pause
