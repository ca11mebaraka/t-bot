#!/usr/bin/env bash
set -euo pipefail

# Цвета
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
BOLD='\033[1m'
NC='\033[0m'

err() { echo -e "${RED}[ОШИБКА]${NC} $*" >&2; exit 1; }

# ── Проверки перед запуском ───────────────────────────────────────────────────
[[ -d ".venv" ]]  || err "Виртуальное окружение не найдено. Запустите: ./setup.sh"
[[ -f ".env" ]]   || err "Файл .env не найден. Запустите: ./setup.sh"

# shellcheck source=/dev/null
source .venv/bin/activate

# Проверка токена
if grep -q "your_token_here" .env 2>/dev/null; then
  echo -e "${YELLOW}[ПРЕДУПРЕЖДЕНИЕ]${NC} В .env стоит токен-заглушка."
  echo "Откройте .env и вставьте реальный токен T-Инвестиций."
  echo
fi

# ── Меню ─────────────────────────────────────────────────────────────────────
show_menu() {
  clear
  echo -e "${BOLD}============================================${NC}"
  echo -e "${BOLD}        T-Invest Bot — Главное меню${NC}"
  echo -e "${BOLD}============================================${NC}"
  echo
  echo -e "  ${CYAN}1${NC}. Показать портфель"
  echo -e "  ${CYAN}2${NC}. Сводный отчёт (30 дней) + экспорт CSV"
  echo -e "  ${CYAN}3${NC}. Сводный отчёт (90 дней) + экспорт CSV"
  echo -e "  ${CYAN}4${NC}. Запустить бота (Sandbox — тестовый режим)"
  echo -e "  ${CYAN}5${NC}. Запустить бота (Production — реальные сделки)"
  echo -e "  ${CYAN}6${NC}. Dry-run: только сигналы, без сделок"
  echo -e "  ${CYAN}7${NC}. Полный автомат Sandbox (авто-перезапуск + дневной лимит)"
  echo -e "  ${CYAN}8${NC}. Полный автомат Production (авто-перезапуск + дневной лимит)"
  echo -e "  ${CYAN}9${NC}. Статус риск-менеджера за сегодня"
  echo -e "  ${CYAN}0${NC}. Выход"
  echo
}

run_with_pause() {
  "$@" || true
  echo
  read -rp "Нажмите Enter для возврата в меню..."
}

while true; do
  show_menu
  read -rp "Ваш выбор (0-9): " CHOICE
  case "$CHOICE" in
    1)
      clear
      echo "--- Загрузка портфеля ---"
      run_with_pause python main.py portfolio
      ;;
    2)
      clear
      echo "--- Отчёт за 30 дней ---"
      run_with_pause python main.py report --days 30
      ;;
    3)
      clear
      echo "--- Отчёт за 90 дней ---"
      run_with_pause python main.py report --days 90
      ;;
    4)
      clear
      echo "--- Запуск в Sandbox (тест) ---"
      echo "Для остановки нажмите Ctrl+C"
      echo
      TRADING_MODE=sandbox python main.py trade || true
      read -rp "Нажмите Enter для возврата в меню..."
      ;;
    5)
      clear
      echo -e "${RED}${BOLD}"
      echo "  [!] ВНИМАНИЕ: Production выполняет РЕАЛЬНЫЕ сделки!"
      echo -e "${NC}"
      read -rp "Введите YES для подтверждения: " CONFIRM
      if [[ "$CONFIRM" == "YES" ]]; then
        echo "--- Запуск в Production ---"
        echo "Для остановки нажмите Ctrl+C"
        echo
        TRADING_MODE=production python main.py trade || true
      else
        echo "Отменено."
        sleep 1
      fi
      read -rp "Нажмите Enter для возврата в меню..."
      ;;
    6)
      clear
      echo "--- Dry-run: сигналы без сделок ---"
      echo "Для остановки нажмите Ctrl+C"
      echo
      python main.py trade --dry-run || true
      read -rp "Нажмите Enter для возврата в меню..."
      ;;
    7)
      clear
      echo "--- Полный автомат: Sandbox ---"
      echo "Для остановки нажмите Ctrl+C"
      echo
      TRADING_MODE=sandbox python main.py auto || true
      read -rp "Нажмите Enter для возврата в меню..."
      ;;
    8)
      clear
      echo -e "${RED}${BOLD}"
      echo "  [!] ВНИМАНИЕ: Production выполняет РЕАЛЬНЫЕ сделки!"
      echo -e "${NC}"
      read -rp "Введите YES для подтверждения: " CONFIRM
      if [[ "$CONFIRM" == "YES" ]]; then
        echo "--- Полный автомат: Production ---"
        echo "Для остановки нажмите Ctrl+C"
        echo
        TRADING_MODE=production python main.py auto || true
      else
        echo "Отменено."
        sleep 1
      fi
      read -rp "Нажмите Enter для возврата в меню..."
      ;;
    9)
      clear
      echo "--- Статус риск-менеджера за сегодня ---"
      run_with_pause python main.py risk-status
      ;;
    0)
      echo "Выход."
      break
      ;;
    *)
      echo "Неверный ввод."
      sleep 1
      ;;
  esac
done
