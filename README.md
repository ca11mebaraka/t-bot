# T-Invest Bot

Автоматический торговый бот для T-Invest с rule-based стратегиями, риск-менеджером, отчётами и опциональным управлением через LLM.

Текущая версия: `1.1.0`.

## Возможности

- Подключение к T-Invest Sandbox и Production API.
- Стратегии MA Crossover и RSI.
- LLM Trading Control: модель выбирает тикеры, стратегию, параметры, `BUY`/`SELL`/`HOLD` и размер заявки.
- Поддержка OpenAI, DeepSeek, Qwen, GigaChat, Anthropic и OpenRouter.
- OpenRouter `session_id` для стабильной сессии запросов.
- Strategy Toolkit для LLM: market regime, deterministic strategies, pair trading и quick backtests.
- FIFO риск-менеджер с дневным лимитом убытка и учётом комиссий.
- Восстановление дневного риска и FIFO-базиса из истории операций.
- Оперативное изменение агрессивности во время сессии.
- Человекочитаемые цветные консольные логи с псевдографикой.
- Отчёты по портфелю и операциям с CSV-экспортом.

## Быстрый старт

```bash
./setup.sh
./run.sh
```

`setup.sh` создаёт `.venv`, ставит зависимости и создаёт `.env` из `.env.example`, если файла ещё нет.

## Основные настройки

Заполните `.env`:

```env
INVEST_TOKEN=...
TRADING_MODE=sandbox
ACCOUNT_ID=
MAX_DAILY_LOSS=1000
MAX_LOTS=1
CHECK_INTERVAL=60
```

Для Production используйте:

```env
TRADING_MODE=production
ACCOUNT_ID=...
```

Production выполняет реальные сделки.

## LLM-режим

Минимальный пример:

```env
LLM_ENABLED=true
LLM_PROVIDER=openai
LLM_MODEL=gpt-4o-mini
OPENAI_API_KEY=...
LLM_UNIVERSE_LIMIT=20
LLM_MAX_TICKERS=20
LLM_MAX_LOTS=1
LLM_DECISION_INTERVAL=20
LLM_SESSION_ID=t-bot-trading
LLM_SHOW_PROMPTS=true
```

Провайдеры:

- `openai`
- `deepseek`
- `qwen`
- `gigachat`
- `anthropic`
- `openrouter`

LLM получает рыночный shortlist, позиции, дневной FIFO P&L, комиссии, остаток риска и текущую агрессивность. Ответ модели валидируется локально: бот не продаёт без позиции, не превышает лимиты и не торгует при остановке risk-manager.

Для `LLM_PROVIDER=openrouter` бот добавляет `session_id` в JSON-запрос. Значение берётся из `LLM_SESSION_ID`.

### Strategy Toolkit для LLM

LLM-оркестратор получает результаты детерминированных стратегий как emulated tools в prompt context:

- `list_strategies`
- `get_market_regime`
- `run_strategy`
- `run_strategy_pair`
- `backtest_strategy`

Стратегии не принимают финальных торговых решений. Они считают сигнал, confidence и индикаторы; LLM выбирает стратегию, корректирует параметры и объясняет решение в audit trail.

Доступные стратегии:

- `trend_following`
- `mean_reversion`
- `breakout`
- `stat_arb`
- `ml`

Параметры по умолчанию находятся в `config/strategies.yaml`.
Решения LLM пишутся в `logs/decisions/decisions_YYYY-MM-DD.jsonl`.
Индикаторы реализованы локально в `strategies/indicators.py`; `pandas-ta` не является обязательной зависимостью, потому что на Python 3.14 его транзитивная зависимость `numba` пока не устанавливается.

## Меню запуска

`./run.sh`:

```text
1  Показать портфель
2  Отчёт за 30 дней
3  Отчёт за 90 дней
4  Sandbox trade
5  Production trade
6  Dry-run
7  Auto Sandbox
8  Auto Production
9  Risk status
10 LLM dry-run
11 LLM Sandbox
12 LLM Production
13 LLM Auto Sandbox
14 LLM Auto Production
```

## Агрессивность

Начальные настройки:

```env
AGGRESSION_LEVEL=3
AGGRESSION_MIN_INTERVAL=20
AGGRESSION_CONTROL_FILE=.trading_control.json
```

Во время сессии:

```text
+ Enter  повысить агрессивность
- Enter  снизить агрессивность
```

Или измените файл:

```json
{
  "aggression": 4
}
```

Уровень `1..5` влияет на размер заявки и интервал следующего цикла. Количество тикеров в LLM-анализе задаётся `LLM_MAX_TICKERS`, чтобы обзор рынка оставался широким даже на осторожной агрессивности.

## Консольные логи

Экранные сообщения форматируются для человека:

- понятные источники: `Биржа`, `Торговля`, `Риск`, `LLM`, `T-Invest API`;
- мягкие цвета и псевдографика в интерактивном терминале;
- технические события SDK вроде `GetPortfolio` переводятся в действия вроде `загружаем портфель через T-Invest API`;
- временные сетевые сбои T-Invest логируются коротко, после retry.

## CLI

```bash
.venv/bin/python main.py portfolio
.venv/bin/python main.py report --days 30
.venv/bin/python main.py risk-status
.venv/bin/python main.py trade --dry-run
.venv/bin/python main.py trade
.venv/bin/python main.py auto
```

## Безопасность

- Не коммитьте `.env`, токены и реальные ключи LLM.
- Сначала проверяйте LLM-режим в `--dry-run` или `sandbox`.
- Для Production нужен full-access токен T-Invest.
- LLM не гарантирует прибыль; все решения ограничиваются риск-менеджером и локальной валидацией.
