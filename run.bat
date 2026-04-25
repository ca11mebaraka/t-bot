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
echo   7. Выход
echo.
set /p CHOICE=Ваш выбор (1-7):

if "%CHOICE%"=="1" goto PORTFOLIO
if "%CHOICE%"=="2" goto REPORT30
if "%CHOICE%"=="3" goto REPORT90
if "%CHOICE%"=="4" goto SANDBOX
if "%CHOICE%"=="5" goto PRODUCTION
if "%CHOICE%"=="6" goto DRYRUN
if "%CHOICE%"=="7" goto EXIT
echo Неверный ввод, попробуйте снова.
timeout /t 1 >nul
goto MENU

:PORTFOLIO
cls
echo --- Загрузка портфеля ---
python main.py portfolio
echo.
pause
goto MENU

:REPORT30
cls
echo --- Отчёт за 30 дней ---
python main.py report --days 30
echo.
pause
goto MENU

:REPORT90
cls
echo --- Отчёт за 90 дней ---
python main.py report --days 90
echo.
pause
goto MENU

:SANDBOX
cls
echo --- Запуск в Sandbox (тест) ---
echo Для остановки нажмите Ctrl+C
echo.
set TRADING_MODE=sandbox
python main.py trade
echo.
pause
goto MENU

:PRODUCTION
cls
echo.
echo [!] ВНИМАНИЕ: Режим Production выполняет РЕАЛЬНЫЕ сделки с реальными деньгами!
echo.
set /p CONFIRM=Введите YES для подтверждения:
if /i not "%CONFIRM%"=="YES" (
    echo Отменено.
    timeout /t 2 >nul
    goto MENU
)
echo --- Запуск в Production ---
echo Для остановки нажмите Ctrl+C
echo.
set TRADING_MODE=production
python main.py trade
echo.
pause
goto MENU

:DRYRUN
cls
echo --- Dry-run: сигналы без сделок ---
echo Для остановки нажмите Ctrl+C
echo.
python main.py trade --dry-run
echo.
pause
goto MENU

:EXIT
echo Выход...
endlocal
exit /b 0
