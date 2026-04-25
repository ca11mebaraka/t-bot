@echo off
setlocal EnableDelayedExpansion
chcp 65001 >nul
title T-Bot Setup

echo ============================================
echo   T-Invest Bot — Подготовка среды (Windows)
echo ============================================
echo.

:: Проверка Python
python --version >nul 2>&1
if errorlevel 1 (
    echo [ОШИБКА] Python не найден.
    echo Установите Python 3.10+ с https://python.org/downloads/
    echo Убедитесь, что при установке отмечена опция "Add Python to PATH"
    pause
    exit /b 1
)

for /f "tokens=2 delims= " %%v in ('python --version 2^>^&1') do set PY_VER=%%v
echo [OK] Python %PY_VER% найден

:: Проверка версии (минимум 3.10)
for /f "tokens=1,2 delims=." %%a in ("%PY_VER%") do (
    set PY_MAJOR=%%a
    set PY_MINOR=%%b
)
if %PY_MAJOR% LSS 3 (
    echo [ОШИБКА] Требуется Python 3.10 или новее.
    pause
    exit /b 1
)
if %PY_MAJOR% EQU 3 if %PY_MINOR% LSS 10 (
    echo [ОШИБКА] Требуется Python 3.10 или новее. Установлена версия %PY_VER%
    pause
    exit /b 1
)

:: Создание виртуального окружения
if exist ".venv" (
    echo [INFO] Виртуальное окружение уже существует, пропускаем создание.
) else (
    echo [INFO] Создание виртуального окружения .venv ...
    python -m venv .venv
    if errorlevel 1 (
        echo [ОШИБКА] Не удалось создать виртуальное окружение.
        pause
        exit /b 1
    )
    echo [OK] Виртуальное окружение создано.
)

:: Активация и установка зависимостей
echo [INFO] Установка зависимостей...
call .venv\Scripts\activate.bat
python -m pip install --upgrade pip --quiet
pip install -r requirements.txt
if errorlevel 1 (
    echo [ОШИБКА] Не удалось установить зависимости.
    pause
    exit /b 1
)
echo [OK] Зависимости установлены.

:: Создание .env если не существует
if not exist ".env" (
    if exist ".env.example" (
        copy ".env.example" ".env" >nul
        echo [OK] Файл .env создан из .env.example
    ) else (
        echo [ПРЕДУПРЕЖДЕНИЕ] Файл .env.example не найден.
    )
) else (
    echo [INFO] Файл .env уже существует.
)

:: Создание директории отчётов
if not exist "reports" mkdir reports

echo.
echo ============================================
echo   Установка завершена успешно!
echo ============================================
echo.
echo Следующие шаги:
echo   1. Откройте файл .env в текстовом редакторе
echo   2. Замените "your_token_here" на ваш токен T-Инвестиций
echo      (Приложение T-Банк → Профиль → Настройки → Токены API)
echo   3. Укажите FIGI инструментов в INSTRUMENTS (необязательно)
echo   4. Запустите run.bat для старта бота
echo.
pause
