# Техническая документация T-Bot

## Содержание

1. [Архитектура проекта](#архитектура-проекта)
2. [Модули и их назначение](#модули-и-их-назначение)
3. [Конфигурация](#конфигурация)
4. [Подключение к API](#подключение-к-api)
5. [Торговый цикл](#торговый-цикл)
6. [Управление ордерами](#управление-ордерами)
7. [Отчётность](#отчётность)
8. [Запуск и развёртывание](#запуск-и-развёртывание)
9. [Зависимости](#зависимости)

---

## Архитектура проекта

```
t-bot/
├── config.py          # Конфигурация через переменные окружения
├── client.py          # Обёртка над tinkoff.invest SDK
├── trader.py          # Торговый движок (основной цикл)
├── portfolio.py       # Работа с позициями и операциями
├── reports.py         # Форматирование и экспорт отчётов
├── main.py            # CLI точка входа
├── strategies/
│   ├── __init__.py
│   ├── base.py        # Абстрактный базовый класс стратегий
│   ├── ma_crossover.py
│   └── rsi.py
├── docs/
│   ├── technical.md   # этот файл
│   └── strategies.md
├── setup.sh           # Подготовка среды (macOS/Linux)
├── run.sh             # Интерактивное меню (macOS/Linux)
├── setup.bat          # Подготовка среды (Windows)
├── run.bat            # Интерактивное меню (Windows)
├── requirements.txt
└── .env.example
```

### Поток данных

```
API T-Инвестиций (gRPC)
        │
        ▼
   client.py  ←─── config.py (TOKEN, MODE)
   (SDK-обёртка)
        │
   ┌────┴────┐
   │         │
trader.py  portfolio.py
   │               │
strategies/    reports.py
(сигналы)      (CSV / таблицы)
   │
   └──► client.py (place_market_order / place_stop_orders)
```

---

## Модули и их назначение

### `config.py`

Единственный источник конфигурации. Читает переменные из `.env` через `python-dotenv`.

```python
@dataclass
class Config:
    token: str          # INVEST_TOKEN
    mode: str           # "sandbox" | "production"
    account_id: str     # пусто → auto-detect
    instruments: list[str]   # FIGI инструментов
    max_lots: int        # MAX_LOTS
    check_interval: int  # CHECK_INTERVAL (секунды)
    reports_dir: Path    # REPORTS_DIR
    # параметры стратегий ...
```

`Config.is_sandbox` → `bool` — удобный флаг для переключения клиента.

---

### `client.py`

Тонкая обёртка над `tinkoff.invest.Client` / `SandboxClient`.

| Функция | Описание |
|---|---|
| `get_client(config)` | Context manager. Возвращает нужный клиент по `config.mode` |
| `resolve_account_id(client, config)` | Берёт `account_id` из конфига или auto-detect первого счёта |
| `place_market_order(...)` | Рыночная заявка BUY/SELL |
| `place_stop_orders(...)` | Take-profit + Stop-loss после покупки |
| `quotation_to_decimal(q)` | `Quotation` → `Decimal` |
| `money_value_to_decimal(mv)` | `MoneyValue` → `Decimal` |
| `decimal_to_quotation(v)` | `Decimal` → `Quotation` |

**Почему Decimal?** Использование `float` при финансовых расчётах приводит к ошибкам округления (например, `0.1 + 0.2 ≠ 0.3`). Все цены хранятся и вычисляются в `Decimal`.

**SandboxClient vs Client:**
- Методы sandbox живут в `client.sandbox.*` и `client.sandbox.post_sandbox_order`
- Методы production — в `client.orders.*`, `client.operations.*`, `client.users.*`
- `get_client` скрывает это различие для остального кода

---

### `trader.py`

Реализует основной торговый цикл.

```
warm_up_strategies()
    └─ загружает 60 дней дневных свечей
    └─ прогоняет все цены через каждую стратегию
           (инициализирует внутренние буферы)

run_trading_loop()
    └─ бесконечный цикл (sleep = CHECK_INTERVAL сек.)
        ├─ для каждого инструмента: get_last_price()
        └─ для каждой стратегии: update(price) → Signal?
               └─ если сигнал ≠ None: _execute_signal()
```

**`_execute_signal`** — выставляет рыночную заявку. В production после успешной покупки автоматически добавляет стоп-ордера (take-profit +5%, stop-loss −2%).

---

### `portfolio.py`

| Функция | Возвращает |
|---|---|
| `get_portfolio(config)` | `list[PositionSummary]` — позиции с рыночными ценами и P&L |
| `get_operations(config, days)` | `list[OperationRecord]` — история BUY/SELL за N дней |
| `get_portfolio_balance(config)` | `dict[str, Decimal]` — денежные остатки по валютам |

`PositionSummary` содержит рассчитываемые свойства:
- `market_value = quantity × current_price`
- `pnl = (current_price − avg_price) × quantity`
- `pnl_pct = pnl / (avg_price × quantity) × 100`

---

### `reports.py`

Использует библиотеку `tabulate` для форматирования таблиц в консоли.

| Функция | Описание |
|---|---|
| `print_portfolio(positions, balances)` | Таблица позиций + итоги |
| `print_operations(operations)` | Хронологическая таблица сделок |
| `print_summary_report(...)` | Реализованный и нереализованный P&L |
| `save_portfolio_csv(positions, config)` | Экспорт позиций в `reports/portfolio_YYYYMMDD_HHMMSS.csv` |
| `save_operations_csv(operations, config)` | Экспорт операций в `reports/operations_YYYYMMDD_HHMMSS.csv` |

---

### `strategies/base.py`

```python
class BaseStrategy(ABC):
    def update(self, price: Decimal, volume: int = 0) -> Optional[Signal]: ...
    def name(self) -> str: ...   # abstract property

@dataclass
class Signal:
    type: SignalType      # BUY | SELL | HOLD
    instrument_id: str
    price: Decimal
    reason: str           # человекочитаемое объяснение сигнала
```

---

## Конфигурация

Все настройки задаются в файле `.env` (скопируйте из `.env.example`).

| Переменная | По умолчанию | Описание |
|---|---|---|
| `INVEST_TOKEN` | **обязательно** | Токен T-Инвестиций |
| `TRADING_MODE` | `sandbox` | `sandbox` или `production` |
| `ACCOUNT_ID` | _(пусто)_ | ID счёта. Если пусто — берётся первый |
| `INSTRUMENTS` | `BBG004730ZJ9` | FIGI через запятую |
| `MAX_LOTS` | `1` | Макс. лотов в одной заявке |
| `CHECK_INTERVAL` | `60` | Интервал проверки сигналов (сек.) |
| `REPORTS_DIR` | `reports` | Папка для CSV-файлов |
| `RISK_HISTORY_DAYS` | `365` | Глубина истории операций для FIFO риск-менеджера |
| `MA_SHORT` | `9` | Период быстрой MA |
| `MA_LONG` | `21` | Период медленной MA |
| `RSI_PERIOD` | `14` | Период RSI |
| `RSI_OVERSOLD` | `30` | Уровень перепроданности |
| `RSI_OVERBOUGHT` | `70` | Уровень перекупленности |
| `LLM_ENABLED` | `false` | Включить автономное управление через LLM |
| `LLM_PROVIDER` | `openai` | Провайдер: `openai`, `deepseek`, `qwen`, `gigachat`, `anthropic`, `openrouter` |
| `LLM_MODEL` | _(пусто)_ | Имя модели у выбранного провайдера |
| `LLM_API_KEY` | _(пусто)_ | Универсальный API key, если не используется provider-specific переменная |
| `OPENAI_API_KEY` / `DEEPSEEK_API_KEY` / `QWEN_API_KEY` / `GIGACHAT_API_KEY` / `ANTHROPIC_API_KEY` / `OPENROUTER_API_KEY` | _(пусто)_ | Ключи конкретных провайдеров |
| `LLM_BASE_URL` | _(пусто)_ | Переопределение URL API модели |
| `LLM_TIMEOUT` | `30` | Таймаут запроса к модели, секунды |
| `LLM_DECISION_INTERVAL` | `300` | Минимальный интервал между решениями LLM |
| `LLM_UNIVERSE_LIMIT` | `40` | Сколько инструментов из T-Invest universe отправлять в shortlist |
| `LLM_MAX_TICKERS` | `20` | Сколько тикеров модель должна разобрать и сколько решений может вернуть за один запрос |
| `LLM_MAX_LOTS` | `1` | Верхний лимит лотов для LLM; дополнительно ограничивается `MAX_LOTS` |
| `LLM_SESSION_ID` | `t-bot-trading` | `session_id` для OpenRouter chat completions |
| `LLM_SHOW_PROMPTS` | `true` | Показывать на экране запросы к модели и ответы |
| `LLM_MOCK_RESPONSE` | _(пусто)_ | JSON-ответ для локального теста без внешнего LLM API |
| `AGGRESSION_LEVEL` | `3` | Начальный уровень агрессивности: `1` очень осторожно, `5` максимально агрессивно |
| `AGGRESSION_MIN_INTERVAL` | `20` | Минимальный интервал опроса биржи/LLM после поправки на агрессивность |
| `AGGRESSION_CONTROL_FILE` | `.trading_control.json` | Файл для изменения агрессивности во время сессии |

### LLM-режим

При `LLM_ENABLED=true` торговый цикл использует модель как автономный decision layer:

1. Бот получает список доступных инструментов T-Invest, фильтрует торгуемые RUB акции/ETF и формирует shortlist.
2. В промпт отправляются рыночные цены, позиции, дневной FIFO P&L, комиссии, остаток риска и торговые лимиты.
3. Модель возвращает строгий JSON с решениями `BUY`, `SELL` или `HOLD`; prompt требует разобрать максимально возможное число тикеров до `LLM_MAX_TICKERS`.
4. Бот валидирует ответ: запрещает неизвестные FIGI, `SELL` без позиции, превышение лотов и торговлю при сработавшем риск-лимите.
5. Валидные решения исполняются через тот же `place_market_order`, риск-менеджер, комиссии и stop-orders.

LLM не гарантирует прибыль. Промпт оптимизирует положительный ожидаемый результат после комиссий и обязан предпочитать `HOLD`, если уверенность недостаточна.

Для `LLM_PROVIDER=openrouter` клиент добавляет в payload поле `session_id` из `LLM_SESSION_ID` и заголовок `X-OpenRouter-Title`.

### Strategy Toolkit как emulated tools

Текущий LLM API-вызов не использует native `tool_calls`, поэтому стратегии подключены как эмулированные tools:

1. `StrategyToolkit` локально вызывает детерминированные стратегии по shortlisted тикерам.
2. `ContextBuilder` добавляет schemas, market regime, strategy outputs и quick backtest summaries в prompt context.
3. LLM остаётся центральным оркестратором: выбирает стратегию, может указать `params_override`, подтверждает/отклоняет сигнал и объясняет решение.
4. Исполнение ордеров и риск-менеджер остаются прежними.

Файлы:

- `strategies/toolkit.py` — единая точка входа для стратегических tools.
- `strategies/market_regime.py` — режим рынка.
- `strategies/trend_following.py`, `mean_reversion.py`, `breakout.py`, `stat_arb.py`, `ml_strategy.py` — чистые вычислители.
- `strategies/backtester.py` — быстрые метрики стратегий.
- `llm/tools_schema.py` — JSON schemas tools.
- `llm/context_builder.py` — добавление tool context к LLM prompt.
- `llm/decision_logger.py` — audit trail в JSONL.

### Агрессивность во время сессии

Бот поддерживает оперативное изменение агрессивности без перезапуска:

- В интерактивном терминале введите `+` и нажмите Enter, чтобы повысить уровень.
- Введите `-` и нажмите Enter, чтобы снизить уровень.
- Если бот запущен без интерактивного ввода, измените файл из `AGGRESSION_CONTROL_FILE`, например:

```json
{
  "aggression": 4
}
```

Уровень `1..5` влияет на размер заявки и интервал следующего LLM/биржевого цикла. Количество LLM-решений не уменьшается агрессивностью, чтобы рыночный обзор оставался широким; его задаёт `LLM_MAX_TICKERS`. Текущий уровень периодически выводится в логах рядом со статусом риск-менеджера.

### Человекочитаемые консольные логи

`pretty_logging.py` заменяет стандартный `logging.basicConfig` для экранного вывода:

- добавляет псевдографику, мягкие ANSI-цвета и строковый индикатор активности;
- переводит названия внутренних модулей в понятные источники: `Биржа`, `Торговля`, `Риск`, `LLM`, `T-Invest API`;
- преобразует SDK-события вроде `GetPortfolio` и `PostOrder` в человекочитаемые действия;
- оставляет сообщения без ANSI-кодов, если stdout не интерактивный.

### Как получить FIGI инструмента

```python
from tinkoff.invest import Client
with Client("ВАШ_ТОКЕН") as c:
    r = c.instruments.find_instrument(query="SBER")
    for i in r.instruments:
        print(i.ticker, i.figi, i.name)
```

---

## Подключение к API

### Аутентификация

T-Invest API использует **gRPC + Bearer Token**. Токен передаётся при создании клиента:

```python
with Client(token="...", target=INVEST_GRPC_API) as client:
    ...
```

Токены бывают двух типов:
- **Read-only** — только чтение данных и портфеля. Торговля недоступна.
- **Full-access** — полный доступ, включая выставление заявок.

Для работы торгового бота нужен **Full-access** токен.

### Sandbox

Sandbox — бесплатная изолированная среда для тестирования. Деньги и заявки в нём виртуальные.

```
TRADING_MODE=sandbox  →  SandboxClient + INVEST_GRPC_API_SANDBOX
TRADING_MODE=production →  Client + INVEST_GRPC_API
```

При первом запуске в sandbox-режиме бот автоматически открывает тестовый счёт.

### Ограничения API

| Метод | Лимит |
|---|---|
| `get_last_prices` | 300 запросов/минуту |
| `post_order` | 100 заявок/минуту |
| `get_all_candles` | 20 запросов/минуту |

При `CHECK_INTERVAL < 20` секунд высока вероятность получить `RESOURCE_EXHAUSTED`.

---

## Торговый цикл

```
startup
  ├─ resolve_account_id()
  ├─ _get_instrument_info() для каждого FIGI
  ├─ build_strategies()
  └─ warm_up_strategies()   ← 60 дней истории

loop (каждые CHECK_INTERVAL сек.)
  for figi in instruments:
    price = _get_last_price(figi)
    for strategy in strategies[figi]:
      signal = strategy.update(price)
      if signal:
        _execute_signal(signal)
  sleep(CHECK_INTERVAL)
```

### Прогрев стратегий

Без прогрева стратегия на основе MA-21 не выдаст первый сигнал пока не накопит 21 значение — это заняло бы 21 опроса (≈21 минуту при интервале 60 сек.). Прогрев на исторических данных устраняет это ожидание.

---

## Управление ордерами

### Рыночная заявка

```
place_market_order(client, account_id, figi, direction, quantity)
  → PostOrderResponse
     .executed_order_price  — цена исполнения
     .execution_report_status — статус (FILL, PARTIALLYFILL, ...)
```

### Стоп-ордера

После успешной покупки автоматически выставляются два ордера:

```
take_price = executed_price × (1 + 0.05)  →  STOP_ORDER_TYPE_TAKE_PROFIT
stop_price = executed_price × (1 − 0.02)  →  STOP_ORDER_TYPE_STOP_LOSS
```

Оба округляются до `min_price_increment` инструмента во избежание ошибки `INVALID_ARGUMENT`.

Стоп-ордера выставляются только в **production**-режиме (в sandbox API не поддерживает их полностью).

---

## Отчётность

### Консольный вывод

```
=== ПОРТФЕЛЬ ===
╭────────┬───────────┬────────┬─────────┬──────────┬──────────────┬────────┬────────╮
│ Тикер  │ Название  │ Кол-во │ Ср.цена │ Тек.цена │ Стоимость    │ P&L    │ P&L%   │
├────────┼───────────┼────────┼─────────┼──────────┼──────────────┼────────┼────────┤
│ SBER   │ Сбербанк  │      1 │ 285.00  │ 294.50   │ 294.50 RUB   │ +9.50  │ +3.33% │
╰────────┴───────────┴────────┴─────────┴──────────┴──────────────┴────────┴────────╯
```

### CSV-файлы

Сохраняются в директорию `reports/` с временной меткой в имени файла:

```
reports/
├── portfolio_20240415_103045.csv
└── operations_20240415_103045.csv
```

**portfolio CSV columns:** `ticker, name, quantity, avg_price, current_price, market_value, pnl, pnl_pct, currency`

**operations CSV columns:** `date, type, ticker, figi, quantity, price, payment, currency`

---

## Запуск и развёртывание

### Локальный запуск

```bash
# macOS / Linux
./setup.sh
./run.sh

# Windows
setup.bat
run.bat

# Прямой вызов CLI
python main.py portfolio
python main.py report --days 30
python main.py trade --dry-run
python main.py trade
```

### Аргументы CLI

```
python main.py <команда> [опции]

Команды:
  portfolio              Показать текущий портфель
  report [--days N]      Сводный отчёт + CSV (по умолчанию 30 дней)
  trade [--dry-run]      Запустить бота (--dry-run: без реальных заявок)
```

### Добавление новой стратегии

1. Создайте файл `strategies/my_strategy.py`
2. Унаследуйтесь от `BaseStrategy`
3. Реализуйте метод `update(price)` и свойство `name`
4. Добавьте импорт в `strategies/__init__.py`
5. Добавьте создание экземпляра в `trader.py::build_strategies()`

```python
# strategies/my_strategy.py
from .base import BaseStrategy, Signal, SignalType
from decimal import Decimal
from typing import Optional

class MyStrategy(BaseStrategy):
    @property
    def name(self) -> str:
        return "MyStrategy"

    def update(self, price: Decimal, volume: int = 0) -> Optional[Signal]:
        # ваша логика
        return None
```

---

## Зависимости

| Пакет | Версия | Назначение |
|---|---|---|
| `tinkoff-investments` | ≥0.2.0b118 | T-Invest Python SDK (gRPC) |
| `python-dotenv` | ≥1.0.0 | Загрузка `.env` файлов |
| `pandas` | ≥2.0.0 | Анализ данных (зарезервировано для стратегий) |
| `tabulate` | ≥0.9.0 | Форматирование таблиц в консоли |

**Python:** 3.10+
