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

# ── Обновление .env для новых LLM-настроек ───────────────────────────────────
ensure_env_key() {
  local key="$1"
  local value="$2"
  if [[ -f ".env" ]] && ! grep -q "^${key}=" .env 2>/dev/null; then
    printf "%s=%s\n" "$key" "$value" >> .env
  fi
}

if [[ -f ".env" ]]; then
  ensure_env_key "RISK_HISTORY_DAYS" "365"
  ensure_env_key "LLM_ENABLED" "false"
  ensure_env_key "LLM_PROVIDER" "openai"
  ensure_env_key "LLM_MODEL" ""
  ensure_env_key "LLM_API_KEY" ""
  ensure_env_key "OPENAI_API_KEY" ""
  ensure_env_key "DEEPSEEK_API_KEY" ""
  ensure_env_key "QWEN_API_KEY" ""
  ensure_env_key "GIGACHAT_API_KEY" ""
  ensure_env_key "ANTHROPIC_API_KEY" ""
  ensure_env_key "OPENROUTER_API_KEY" ""
  ensure_env_key "LLM_BASE_URL" ""
  ensure_env_key "LLM_TIMEOUT" "30"
  ensure_env_key "LLM_DECISION_INTERVAL" "300"
  ensure_env_key "LLM_UNIVERSE_LIMIT" "40"
  ensure_env_key "LLM_MAX_TICKERS" "8"
  ensure_env_key "LLM_MAX_LOTS" "1"
  ensure_env_key "LLM_SHOW_PROMPTS" "true"
  ensure_env_key "LLM_MOCK_RESPONSE" ""
  ensure_env_key "AGGRESSION_LEVEL" "3"
  ensure_env_key "AGGRESSION_MIN_INTERVAL" "20"
  ensure_env_key "AGGRESSION_CONTROL_FILE" ".trading_control.json"
  ok "LLM-настройки в .env проверены."
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
echo "  4. Для LLM-режима заполните в .env:"
echo "       LLM_PROVIDER, LLM_MODEL и API key выбранного провайдера"
echo "     Затем используйте пункты 10-14 в ./run.sh"
echo "  5. Во время сессии меняйте агрессивность:"
echo "       + Enter / - Enter  или  AGGRESSION_CONTROL_FILE"
echo
