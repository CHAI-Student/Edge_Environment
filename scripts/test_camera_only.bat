@echo off
REM Camera-Only Testing Script for Windows
REM 로드셀 없이 카메라만으로 상품 판단 테스트

echo ============================================================
echo   CHAI Smart Vending - Camera-Only Test
echo ============================================================
echo.

set ZONE=%1
if "%ZONE%"=="" set ZONE=0

echo Testing Zone %ZONE% with camera only...
echo.

REM Node.js 서버를 통한 테스트
echo [1] Testing via Node.js server (localhost:8889)
curl -s -X POST http://localhost:8889/api/camera/test/snapshot-and-judge ^
    -H "Content-Type: application/json" ^
    -d "{\"zone_id\": %ZONE%, \"include_top\": true}" | python -m json.tool

echo.
echo ============================================================
echo.
echo Usage:
echo   test_camera_only.bat [zone_id]
echo   test_camera_only.bat 0    (Zone 0 test)
echo   test_camera_only.bat 1    (Zone 1 test)
echo.
echo Or use Python script for more options:
echo   python test_camera_only.py --help
echo.

pause
