@echo off
chcp 65001 >nul
setlocal
cd /d "%~dp0"

title Freeworker Parser

echo ==========================================
echo  Freeworker Parser: Сбор данных
echo ==========================================
echo.

where py >nul 2>&1
if %errorlevel% neq 0 (
    echo [ОШИБКА] Python не найден.
    echo Установите Python 3.11 или новее с https://www.python.org/downloads/
    echo При установке отметьте "Add Python to PATH".
    pause
    exit /b 1
)

if not exist ".venv\Scripts\python.exe" (
    echo [1/4] Создаю виртуальное окружение...
    py -3 -m venv .venv
    if errorlevel 1 goto error
)

call ".venv\Scripts\activate.bat"

echo [2/4] Устанавливаю зависимости...
python -m pip install --upgrade pip >nul 2>&1
pip install -r requirements.txt
if errorlevel 1 goto error

echo [3/4] Устанавливаю браузер Chromium...
playwright install chromium
if errorlevel 1 goto error

echo [4/4] Запускаю парсер...
echo.
python freeworker_collector.py
if errorlevel 1 goto error

echo.
echo Сбор завершён успешно.
pause
exit /b 0

:error
echo.
echo [ОШИБКА] Что-то пошло не так. Проверьте сообщения выше.
pause
exit /b 1