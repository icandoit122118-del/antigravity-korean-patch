@echo off
chcp 65001 >nul
echo [Antigravity 한글 패치] 데스크톱 앱 UI 한글 패치를 적용합니다...
python -X utf8 "%~dp0patcher.py"
if %ERRORLEVEL% EQU 0 (
    echo [완료] Antigravity 한글 패치가 성공적으로 적용되었습니다.
) else (
    echo [오류] 패치 적용 중 문제가 발생했습니다.
)
pause
