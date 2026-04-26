@echo off
chcp 65001 >nul
title 자동 백업 해제
schtasks /delete /tn "PortfolioDashboardBackup" /f
if errorlevel 1 (
    echo [INFO] 등록된 작업이 없거나 이미 해제됨.
) else (
    echo [OK] 자동 백업 등록이 해제되었습니다.
)
pause
