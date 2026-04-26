@echo off
setlocal EnableDelayedExpansion
chcp 65001 >nul
title T-Bot

:: Проверка виртуального окружения
if not exist ".venv\Scripts\activate.bat" (
    echo [ОШИБКА] Виртуальное окружение не найдено.
    echo Сначала запустите setup.bat
    pause
    exit /b 1
)

:: Проверка .env
if not exist ".env" (
    echo [ОШИБКА] Файл .env не найден.
    echo Сначала запустите setup.bat и заполните .env
    pause
    exit /b 1
)

call .venv\Scripts\activate.bat

findstr /c:"your_token_here" ".env" >nul 2>&1
if not errorlevel 1 (
    echo [ПРЕДУПРЕЖДЕНИЕ] В .env стоит токен-заглушка.
    echo Откройте .env и вставьте реальный токен T-Инвестиций.
    echo.
)

findstr /b /c:"LLM_ENABLED=true" ".env" >nul 2>&1
if not errorlevel 1 (
    echo [ПРЕДУПРЕЖДЕНИЕ] В .env включён LLM_ENABLED=true.
    echo Обычные пункты меню тоже будут использовать LLM-режим.
    echo Для rule-based MA/RSI режима поставьте LLM_ENABLED=false или используйте пункты 10-14.
    echo.
    pause
)

:MENU
cls
echo ============================================
echo         T-Invest Bot — Главное меню
echo ============================================
echo.
echo   1. Показать портфель
echo   2. Сводный отчёт (30 дней) + экспорт CSV
echo   3. Сводный отчёт (90 дней) + экспорт CSV
echo   4. Запустить бота (Sandbox — тестовый режим)
echo   5. Запустить бота (Production — реальные сделки)
echo   6. Dry-run: только сигналы, без сделок
echo   7. Полный автомат Sandbox (авто-перезапуск + дневной лимит)
echo   8. Полный автомат Production (авто-перезапуск + дневной лимит)
echo   9. Статус риск-менеджера за сегодня
echo.
echo   10. LLM dry-run: решения модели без сделок
echo   11. LLM Sandbox
echo   12. LLM Production — реальные сделки
echo   13. LLM Auto Sandbox
echo   14. LLM Auto Production — реальные сделки
echo   0. Выход
echo.
set /p CHOICE=Ваш выбор (0-14):

if "%CHOICE%"=="1" goto PORTFOLIO
if "%CHOICE%"=="2" goto REPORT30
if "%CHOICE%"=="3" goto REPORT90
if "%CHOICE%"=="4" goto SANDBOX
if "%CHOICE%"=="5" goto PRODUCTION
if "%CHOICE%"=="6" goto DRYRUN
if "%CHOICE%"=="7" goto AUTO_SANDBOX
if "%CHOICE%"=="8" goto AUTO_PRODUCTION
if "%CHOICE%"=="9" goto RISK_STATUS
if "%CHOICE%"=="10" goto LLM_DRYRUN
if "%CHOICE%"=="11" goto LLM_SANDBOX
if "%CHOICE%"=="12" goto LLM_PRODUCTION
if "%CHOICE%"=="13" goto LLM_AUTO_SANDBOX
if "%CHOICE%"=="14" goto LLM_AUTO_PRODUCTION
if "%CHOICE%"=="0" goto EXIT
echo Неверный ввод, попробуйте снова.
timeout /t 1 >nul
goto MENU

:PORTFOLIO
cls
echo --- Загрузка портфеля ---
python main.py portfolio
call :PauseAndMenu

:REPORT30
cls
echo --- Отчёт за 30 дней ---
python main.py report --days 30
call :PauseAndMenu

:REPORT90
cls
echo --- Отчёт за 90 дней ---
python main.py report --days 90
call :PauseAndMenu

:SANDBOX
cls
echo --- Запуск в Sandbox (тест) ---
echo Для остановки нажмите Ctrl+C
echo.
set "TRADING_MODE=sandbox"
python main.py trade
set "TRADING_MODE="
call :PauseAndMenu

:PRODUCTION
cls
call :ConfirmProduction
if errorlevel 1 goto MENU
echo --- Запуск в Production ---
echo Для остановки нажмите Ctrl+C
echo.
set "TRADING_MODE=production"
python main.py trade
set "TRADING_MODE="
call :PauseAndMenu

:DRYRUN
cls
echo --- Dry-run: сигналы без сделок ---
echo Для остановки нажмите Ctrl+C
echo.
python main.py trade --dry-run
call :PauseAndMenu

:AUTO_SANDBOX
cls
echo --- Полный автомат: Sandbox ---
echo Авто-перезапуск при ошибках. Дневной лимит из MAX_DAILY_LOSS.
echo Для остановки нажмите Ctrl+C
echo.
set "TRADING_MODE=sandbox"
python main.py auto
set "TRADING_MODE="
call :PauseAndMenu

:AUTO_PRODUCTION
cls
call :ConfirmProduction
if errorlevel 1 goto MENU
echo --- Полный автомат: Production ---
echo Авто-перезапуск при ошибках. Дневной лимит из MAX_DAILY_LOSS.
echo Для остановки нажмите Ctrl+C
echo.
set "TRADING_MODE=production"
python main.py auto
set "TRADING_MODE="
call :PauseAndMenu

:RISK_STATUS
cls
echo --- Статус риск-менеджера за сегодня ---
python main.py risk-status
call :PauseAndMenu

:LLM_DRYRUN
cls
echo --- LLM dry-run: решения модели без сделок ---
call :ShowLlmHint
echo Для остановки нажмите Ctrl+C
echo.
set "LLM_ENABLED=true"
python main.py trade --dry-run
set "LLM_ENABLED="
call :PauseAndMenu

:LLM_SANDBOX
cls
echo --- LLM Sandbox ---
call :ShowLlmHint
echo Для остановки нажмите Ctrl+C
echo.
set "TRADING_MODE=sandbox"
set "LLM_ENABLED=true"
python main.py trade
set "LLM_ENABLED="
set "TRADING_MODE="
call :PauseAndMenu

:LLM_PRODUCTION
cls
call :ConfirmProduction
if errorlevel 1 goto MENU
echo --- LLM Production ---
call :ShowLlmHint
echo Для остановки нажмите Ctrl+C
echo.
set "TRADING_MODE=production"
set "LLM_ENABLED=true"
python main.py trade
set "LLM_ENABLED="
set "TRADING_MODE="
call :PauseAndMenu

:LLM_AUTO_SANDBOX
cls
echo --- LLM Auto Sandbox ---
call :ShowLlmHint
echo Для остановки нажмите Ctrl+C
echo.
set "TRADING_MODE=sandbox"
set "LLM_ENABLED=true"
python main.py auto
set "LLM_ENABLED="
set "TRADING_MODE="
call :PauseAndMenu

:LLM_AUTO_PRODUCTION
cls
call :ConfirmProduction
if errorlevel 1 goto MENU
echo --- LLM Auto Production ---
call :ShowLlmHint
echo Для остановки нажмите Ctrl+C
echo.
set "TRADING_MODE=production"
set "LLM_ENABLED=true"
python main.py auto
set "LLM_ENABLED="
set "TRADING_MODE="
call :PauseAndMenu

:EXIT
echo Выход...
endlocal
exit /b 0

:ConfirmProduction
echo.
echo [!] ВНИМАНИЕ: Production выполняет РЕАЛЬНЫЕ сделки с реальными деньгами!
echo.
set /p CONFIRM=Введите YES для подтверждения:
if /i "%CONFIRM%"=="YES" exit /b 0
echo Отменено.
timeout /t 2 >nul
exit /b 1

:ShowLlmHint
echo LLM-настройки читаются из .env:
echo   LLM_PROVIDER, LLM_MODEL, *_API_KEY, LLM_MAX_LOTS, LLM_DECISION_INTERVAL
echo   LLM_MAX_TICKERS задаёт ширину анализа, LLM_SESSION_ID используется для OpenRouter.
echo Запросы и ответы модели показываются при LLM_SHOW_PROMPTS=true.
echo Агрессивность во время сессии: + Enter / - Enter или файл AGGRESSION_CONTROL_FILE.
echo.
exit /b 0

:PauseAndMenu
echo.
pause
goto MENU
