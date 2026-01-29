@echo off
REM 서비스 시작 스크립트
REM Windows PowerShell 또는 CMD에서 실행

echo ============================================
echo Edge Environment 서비스 시작
echo ============================================

REM 기존 PM2 프로세스 정리
echo.
echo [1/3] 기존 PM2 프로세스 정리...
pm2 delete all 2>nul

REM 정합성 검증
echo.
echo [2/3] 서비스 정합성 검증...
python verify_services.py
if %ERRORLEVEL% NEQ 0 (
    echo.
    echo [ERROR] 서비스 정합성 검증 실패!
    echo 위의 에러를 확인하고 수정 후 다시 시도하세요.
    pause
    exit /b 1
)

REM PM2로 서비스 시작
echo.
echo [3/3] PM2로 전체 서비스 시작...
pm2 start ecosystem.config.js

echo.
echo ============================================
echo 서비스 시작 완료!
echo ============================================
echo.
echo 상태 확인: pm2 status
echo 로그 확인: pm2 logs
echo 전체 중지: pm2 stop all
echo.

pause
