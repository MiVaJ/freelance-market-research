@echo off
chcp 65001 >nul
setlocal

echo ==========================================
echo  Kwork Parser: Автоматическая установка
echo ==========================================
echo.

:: 1. Проверяем, есть ли Python
where py >nul 2>&1
if %errorlevel% neq 0 (
    echo [ОШИБКА] Python не найден.
    echo Установите Python 3.11+ с https://www.python.org/downloads/
    echo При установке отметьте "Add Python to PATH".
    pause
    exit /b 1
)

:: 2. Создаём виртуальное окружение (если его нет)
if not exist ".venv\Scripts\python.exe" (
    echo [1/3] Создаю виртуальное окружение...
    py -3 -m venv .venv
)

:: 3. Устанавливаем зависимости из ЛОКАЛЬНОЙ папки wheels
echo [2/3] Устанавливаю библиотеки...
call ".venv\Scripts\activate.bat"
pip install --no-index --find-links=wheels -r requirements.txt

:: 4. Устанавливаем браузер Playwright (если нужно)
echo [3/3] Проверяю браузеры Playwright...
playwright install chromium

:: 5. Запускаем основной скрипт
echo.
echo Запуск парсера...
python kwork_collector.py

pause