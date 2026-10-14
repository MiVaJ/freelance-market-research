@echo off
chcp 65001 >nul
setlocal
cd /d "%~dp0"

title Kwork Analysis

echo ==========================================
echo  Kwork Parser: Анализ данных
echo ==========================================
echo.

if not exist ".venv\Scripts\python.exe" (
    echo [ОШИБКА] Виртуальное окружение не найдено.
    echo Сначала запустите run_parser.cmd.
    pause
    exit /b 1
)

call ".venv\Scripts\activate.bat"

echo Запускаю анализ...
echo.
python kwork_analyze.py
if errorlevel 1 (
    echo.
    echo [ОШИБКА] Анализ завершился с ошибкой.
    pause
    exit /b 1
)

echo.
echo Анализ завершён успешно.
echo Отчёты сохранены в папке output/.
pause
exit /b 0