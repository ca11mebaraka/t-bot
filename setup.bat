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

:: Обновление .env для новых настроек, если файл уже был создан раньше
if exist ".env" (
    call :EnsureEnvKey "RISK_HISTORY_DAYS" "365"
    call :EnsureEnvKey "LLM_ENABLED" "false"
    call :EnsureEnvKey "LLM_PROVIDER" "openai"
    call :EnsureEnvKey "LLM_MODEL" ""
    call :EnsureEnvKey "LLM_API_KEY" ""
    call :EnsureEnvKey "OPENAI_API_KEY" ""
    call :EnsureEnvKey "DEEPSEEK_API_KEY" ""
    call :EnsureEnvKey "QWEN_API_KEY" ""
    call :EnsureEnvKey "GIGACHAT_API_KEY" ""
    call :EnsureEnvKey "ANTHROPIC_API_KEY" ""
    call :EnsureEnvKey "OPENROUTER_API_KEY" ""
    call :EnsureEnvKey "LLM_BASE_URL" ""
    call :EnsureEnvKey "LLM_TIMEOUT" "30"
    call :EnsureEnvKey "LLM_DECISION_INTERVAL" "300"
    call :EnsureEnvKey "LLM_UNIVERSE_LIMIT" "40"
    call :EnsureEnvKey "LLM_MAX_TICKERS" "20"
    call :EnsureEnvKey "LLM_MAX_LOTS" "1"
    call :EnsureEnvKey "LLM_SESSION_ID" "t-bot-trading"
    call :EnsureEnvKey "LLM_SHOW_PROMPTS" "true"
    call :EnsureEnvKey "LLM_MOCK_RESPONSE" ""
    call :EnsureEnvKey "AGGRESSION_LEVEL" "3"
    call :EnsureEnvKey "AGGRESSION_MIN_INTERVAL" "20"
    call :EnsureEnvKey "AGGRESSION_CONTROL_FILE" ".trading_control.json"
    echo [OK] Настройки .env проверены.
)

:: Создание директории отчётов
if not exist "reports" mkdir reports
if not exist "logs" mkdir logs

echo.
echo ============================================
echo   Установка завершена успешно!
echo ============================================
echo.
echo Следующие шаги:
echo   1. Откройте файл .env в текстовом редакторе
echo   2. Замените "your_token_here" на ваш токен T-Инвестиций
echo      (Приложение T-Банк → Профиль → Настройки → Токены API)
echo   3. Для LLM-режима заполните LLM_PROVIDER, LLM_MODEL и API key
echo   4. Запустите run.bat для старта бота
echo   5. Во время сессии меняйте агрессивность: + Enter / - Enter
echo.
pause
exit /b 0

:EnsureEnvKey
set "ENV_KEY=%~1"
set "ENV_VALUE=%~2"
findstr /b /c:"%ENV_KEY%=" ".env" >nul 2>&1
if errorlevel 1 (
    >>".env" echo %ENV_KEY%=%ENV_VALUE%
)
exit /b 0
