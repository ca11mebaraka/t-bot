#!/usr/bin/env bash
set -euo pipefail

# Цвета для вывода
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

info()    { echo -e "${BLUE}[INFO]${NC} $*"; }
ok()      { echo -e "${GREEN}[OK]${NC} $*"; }
warn()    { echo -e "${YELLOW}[WARN]${NC} $*"; }
err()     { echo -e "${RED}[ОШИБКА]${NC} $*" >&2; exit 1; }

echo "============================================"
echo "  T-Invest Bot — Подготовка среды (macOS/Linux)"
echo "============================================"
echo

# ── Определение ОС ──────────────────────────────────────────────────────────
OS="$(uname -s)"
case "$OS" in
  Darwin)
    info "Обнаружена macOS"
    # Проверка Homebrew
    if ! command -v brew &>/dev/null; then
      warn "Homebrew не найден. Устанавливаем..."
      /bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"
      # Добавляем brew в PATH для Apple Silicon
      if [[ -f /opt/homebrew/bin/brew ]]; then
        eval "$(/opt/homebrew/bin/brew shellenv)"
      fi
    fi
    ;;
  Linux)
    info "Обнаружена Linux"
    ;;
  *)
    err "Неизвестная ОС: $OS"
    ;;
esac

# ── Проверка Python ──────────────────────────────────────────────────────────
PYTHON=""
for cmd in python3.12 python3.11 python3.10 python3 python; do
  if command -v "$cmd" &>/dev/null; then
    ver=$("$cmd" -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")')
    major=${ver%%.*}
    minor=${ver##*.}
    if [[ "$major" -ge 3 && "$minor" -ge 10 ]]; then
      PYTHON="$cmd"
      ok "Python $ver найден: $(command -v "$cmd")"
      break
    fi
  fi
done

if [[ -z "$PYTHON" ]]; then
  if [[ "$OS" == "Darwin" ]]; then
    info "Устанавливаем Python через Homebrew..."
    brew install python@3.12
    PYTHON="python3.12"
  else
    err "Python 3.10+ не найден. Установите: sudo apt install python3.12 python3.12-venv"
  fi
fi

# ── Виртуальное окружение ────────────────────────────────────────────────────
VENV_DIR=".venv"
if [[ -d "$VENV_DIR" ]]; then
  info "Виртуальное окружение уже существует — пропускаем."
else
  info "Создание виртуального окружения $VENV_DIR ..."
  "$PYTHON" -m venv "$VENV_DIR"
  ok "Виртуальное окружение создано."
fi

# Активация
# shellcheck source=/dev/null
source "$VENV_DIR/bin/activate"

# ── Зависимости ──────────────────────────────────────────────────────────────
info "Обновление pip..."
pip install --upgrade pip --quiet

info "Установка зависимостей из requirements.txt ..."
pip install -r requirements.txt
ok "Зависимости установлены."

# ── Файл конфигурации ────────────────────────────────────────────────────────
if [[ ! -f ".env" ]]; then
  if [[ -f ".env.example" ]]; then
    cp .env.example .env
    ok "Файл .env создан из .env.example"
  else
    warn ".env.example не найден."
  fi
else
  info "Файл .env уже существует."
fi

# ── Директория отчётов ───────────────────────────────────────────────────────
mkdir -p reports

# ── Права на run.sh ──────────────────────────────────────────────────────────
if [[ -f "run.sh" ]]; then
  chmod +x run.sh
fi

echo
echo "============================================"
echo "  Установка завершена успешно!"
echo "============================================"
echo
echo "Следующие шаги:"
echo "  1. Откройте .env в редакторе:"
echo "       nano .env   или   open .env  (macOS)"
echo "  2. Замените 'your_token_here' на токен T-Инвестиций"
echo "     (Приложение T-Банк → Профиль → Настройки → Токены API)"
echo "  3. Запустите бота:"
echo "       ./run.sh"
echo
