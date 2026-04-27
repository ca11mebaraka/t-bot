# Логика работы T-Invest Bot

Документ описывает, как бот работает в каждом режиме запуска, как проходит торговое решение, где включается риск-менеджер, как считаются комиссии и FIFO P&L, а также какие есть сильные стороны, ограничения и направления развития.

## Общая Архитектура

```mermaid
flowchart TD
    A[run.sh / run.bat / CLI] --> B[main.py]
    B --> C[Config из .env]
    C --> D{Команда}

    D -->|portfolio| P[Портфель]
    D -->|report| R[Отчёты + CSV]
    D -->|risk-status| RS[Риск из истории операций]
    D -->|trade| T[Один торговый цикл до остановки/ошибки]
    D -->|auto| AU[Автомат с перезапуском]

    T --> LOOP[run_trading_loop]
    AU --> LOOP

    LOOP --> API[T-Invest API]
    LOOP --> RISK[DailyRiskManager]
    LOOP --> AGG[AggressionController]
    LOOP --> MODE{LLM_ENABLED}

    MODE -->|false| RB[MA/RSI стратегии]
    MODE -->|true| LLM[LLMTradingController]

    RB --> EXEC[_execute_signal]
    LLM --> EXEC
    EXEC --> ORDERS[Market order + комиссии + stop orders]
    ORDERS --> RISK
```

Главная идея: бот разделяет генерацию торгового сигнала, локальную валидацию, исполнение заявки и риск-учёт. Даже когда решение принимает LLM, ордер всё равно проходит через локальные ограничения.

## Режимы Запуска

### `portfolio`

Показывает текущие позиции и денежные остатки.

Flow:

```mermaid
sequenceDiagram
    participant U as Пользователь
    participant M as main.py
    participant P as portfolio.py
    participant API as T-Invest API

    U->>M: python main.py portfolio
    M->>P: get_portfolio()
    P->>API: GetPortfolio
    P->>API: GetPositions
    API-->>P: позиции, цены, деньги
    P-->>M: PositionSummary + balances
    M-->>U: таблица портфеля
```

Особенности:

- Использует `TRADING_MODE` и `ACCOUNT_ID`.
- Ничего не покупает и не продаёт.
- Совместим с новой формой SDK: средняя цена берётся из `average_position_price_fifo` / `average_position_price`, если старого поля нет.

### `report`

Формирует отчёт по портфелю и операциям за период.

Flow:

```mermaid
flowchart LR
    A[report --days N] --> B[get_portfolio]
    A --> C[get_operations]
    B --> D[print_portfolio]
    C --> E[print_operations]
    B --> F[save_portfolio_csv]
    C --> G[save_operations_csv]
```

Плюсы:

- Быстро показывает состояние счёта и историю.
- Сохраняет CSV в `reports/`.

Минусы:

- Это отчётный режим, а не аналитический backtest.
- Метрики ограничены тем, что отдаёт API операций.

### `risk-status`

Показывает дневной риск, комиссии и FIFO P&L на основе истории операций.

Flow:

```mermaid
flowchart TD
    A[risk-status] --> B[DailyRiskManager]
    B --> C[hydrate_risk_from_operations]
    C --> D[GetOperations за RISK_HISTORY_DAYS]
    D --> E[seed_buy / seed_sell для прошлых дней]
    D --> F[record_buy / record_sell для сегодня]
    D --> G[record_commission для broker fee]
    F --> H[daily_summary]
    G --> H
```

Особенности:

- Исторические сделки восстанавливают FIFO-базис.
- Сегодняшние сделки попадают в дневной итог.
- Отдельные broker fee операции учитываются в общей комиссии и отображаются в строках сделок.

## Торговые Режимы

### `trade`

Обычный торговый запуск. Работает до `Ctrl+C` или необработанной ошибки.

```mermaid
flowchart TD
    A[trade] --> B[Config]
    B --> C{--dry-run?}
    C -->|да| D[Подмена place_market_order на fake order]
    C -->|нет| E[Реальные заявки разрешены режимом]
    D --> F[run_trading_loop]
    E --> F
```

Если указан `--dry-run`, бот генерирует сигналы и проходит большую часть логики, но вместо реальной заявки использует заглушку.

### `auto`

Полный автомат с перезапуском после ошибок.

```mermaid
flowchart TD
    A[auto] --> B{MAX_DAILY_LOSS задан?}
    B -->|нет| X[Запуск отклоняется]
    B -->|да| C[run_auto_loop]
    C --> D[run_trading_loop]
    D -->|ошибка| E[Лог ошибки]
    E --> F[сон AUTO_RESTART_DELAY]
    F --> D
    D -->|Ctrl+C| G[Печать daily_summary]
```

Отличия от `trade`:

- Требует `MAX_DAILY_LOSS`.
- При исключении ждёт `AUTO_RESTART_DELAY` и запускает цикл заново.
- При достижении дневного лимита не завершает процесс, а ждёт новый день.

Плюсы:

- Устойчивее к временным сетевым/API ошибкам.
- Удобен для долгой сессии без ручного перезапуска.

Минусы:

- Требует более аккуратных лимитов.
- Ошибочная конфигурация может многократно воспроизводиться после перезапуска.

## Sandbox И Production

Режим выбирается через `TRADING_MODE`.

```mermaid
flowchart LR
    A[TRADING_MODE] --> B{sandbox?}
    B -->|да| C[SandboxClient]
    B -->|нет| D[Production Client]
    C --> E[post_sandbox_order]
    D --> F[post_order]
```

Sandbox:

- Виртуальные деньги и заявки.
- Подходит для проверки логики запуска, LLM-ответов и риск-менеджера.

Production:

- Реальные сделки.
- Требует full-access token.
- В `run.sh` и `run.bat` есть подтверждение `YES` перед production-пунктами.

## Rule-Based Режим

Работает, когда `LLM_ENABLED=false`.

```mermaid
flowchart TD
    A[run_trading_loop] --> B[build_strategies]
    B --> C[MA Crossover]
    B --> D[RSI]
    C --> E[warm_up_strategies]
    D --> E
    E --> F[Цикл по INSTRUMENTS]
    F --> G[GetLastPrices]
    G --> H[strategy.update price]
    H --> I{Есть сигнал?}
    I -->|нет| F
    I -->|BUY/SELL| J[_execute_signal]
```

### MA Crossover

- `BUY`: быстрая MA пересекает медленную снизу вверх.
- `SELL`: быстрая MA пересекает медленную сверху вниз.

### RSI

- `BUY`: RSI выходит из перепроданности.
- `SELL`: RSI выходит из перекупленности.

Плюсы:

- Простая и предсказуемая логика.
- Легко отлаживать.
- Не зависит от LLM API и стоимости токенов.

Минусы:

- Не понимает контекст портфеля так глубоко, как LLM.
- Rule-based SELL может возникнуть по индикатору без предварительной интеллектуальной оценки альтернатив.
- Слабее адаптируется к режиму рынка.

## LLM Режим

Работает, когда `LLM_ENABLED=true`.

```mermaid
flowchart TD
    A[run_trading_loop] --> B[LLMTradingController.make_decisions]
    B --> C[_load_positions]
    B --> D[_scan_market]
    D --> E[Ротационный shortlist акций/ETF]
    C --> F[_build_context]
    E --> F
    F --> G[ContextBuilder.enrich_context]
    G --> H[StrategyToolkit emulated tools]
    H --> I[LLM prompt]
    I --> J[LLM JSON decisions]
    J --> K[_parse_decisions]
    K --> L[_validate_decisions]
    L --> M[_execute_signal]
```

Что получает модель:

- market candidates;
- текущие позиции;
- дневной FIFO P&L;
- комиссии;
- остаток дневного риска;
- уровень агрессивности;
- результаты стратегий из `StrategyToolkit`;
- quick backtests;
- инструкции по формату JSON.

Что модель возвращает:

```json
{
  "decisions": [
    {
      "figi": "...",
      "ticker": "...",
      "action": "BUY|SELL|HOLD",
      "lots": 1,
      "confidence": 0.75,
      "strategy_mode": "balanced",
      "strategy_used": "trend_following",
      "params_override": {},
      "reasoning": "audit trail",
      "reason": "...",
      "risk_notes": "..."
    }
  ]
}
```

### Валидация LLM-Решений

```mermaid
flowchart TD
    A[LLM decision] --> B{HOLD?}
    B -->|да| H[Логируем HOLD, сделки нет]
    B -->|нет| C{FIGI есть в candidates?}
    C -->|нет| X[Отклонить]
    C -->|да| D{BUY или SELL?}
    D -->|BUY| E{buy_available?}
    E -->|нет| X
    E -->|да| I[Ограничить lots]
    D -->|SELL| F{Есть позиция?}
    F -->|нет| X
    F -->|да| G{sell_available?}
    G -->|нет| X
    G -->|да| J[Урезать lots до позиции]
    I --> K[_execute_signal]
    J --> K
```

Плюсы:

- Модель видит шире одного индикатора.
- Может выбирать стратегию и объяснять режим: `capital_preservation`, `balanced`, `opportunity_seeking`.
- Может вернуть несколько `HOLD`, чтобы показать анализ альтернатив.
- Локальная валидация запрещает продажу без позиции и превышение лотов.

Минусы:

- Зависит от LLM API, ключей, задержек и стоимости.
- Нужен строгий контроль prompt/schema.
- Модель может быть консервативной и часто возвращать `HOLD`.
- Результат не гарантирует прибыль.

## Strategy Toolkit

Strategy Toolkit не торгует сам. Он считает детерминированные результаты для LLM.

```mermaid
flowchart LR
    A[ContextBuilder] --> B[StrategyToolkit]
    B --> C[get_market_regime]
    B --> D[run_strategy]
    B --> E[run_strategy_pair]
    B --> F[backtest_strategy]
    C --> G[LLM context]
    D --> G
    E --> G
    F --> G
```

Доступные стратегии:

- `trend_following`;
- `mean_reversion`;
- `breakout`;
- `stat_arb`;
- `ml`.

Смысл слоя: дать LLM структурированные факты, но оставить финальное решение за моделью и локальной валидацией.

## Исполнение Сделки

```mermaid
sequenceDiagram
    participant S as Signal
    participant T as trader._execute_signal
    participant R as DailyRiskManager
    participant API as T-Invest API

    S->>T: BUY или SELL
    T->>R: can_trade()
    R-->>T: allowed / halted
    T->>API: post_order / post_sandbox_order
    API-->>T: execution price, lots, commission
    T->>API: get_order_commission если комиссия 0
    T->>R: record_buy / record_sell
    T->>API: stop orders только после BUY в production
```

Для `SELL`:

- заявка выставляется как market sell;
- после исполнения `record_sell()` считает FIFO P&L;
- комиссия уменьшает чистый результат;
- стоп-ордера после продажи не создаются.

Для `BUY`:

- заявка выставляется как market buy;
- позиция добавляется в FIFO-книгу;
- в production после покупки выставляются take-profit и stop-loss.

## Риск-Менеджер И FIFO

```mermaid
flowchart TD
    A[Старт с risk] --> B[hydrate_risk_from_operations]
    B --> C[Прошлые BUY -> seed_buy]
    B --> D[Прошлые SELL -> seed_sell]
    B --> E[Сегодня BUY/SELL -> record_*]
    B --> F[Сегодня BROKER_FEE -> record_commission]
    E --> G[FIFO book]
    F --> H[total_commissions]
    G --> I[realized_pnl]
    H --> J[net_result = realized_pnl - commissions]
    I --> J
    J --> K{net_result <= -MAX_DAILY_LOSS?}
    K -->|да| L[halt trading]
    K -->|нет| M[continue]
```

FIFO закрытие:

1. Берётся самая ранняя открытая покупка по FIGI.
2. Считается `(sell_price - buy_price) * shares`.
3. Если продажа закрыла только часть покупки, остаток остаётся в книге.
4. Если базис неизвестен, P&L считается консервативно как `0`.

Комиссии:

- комиссия из ответа заявки учитывается сразу;
- если ответ заявки вернул `0`, бот ищет broker fee через операции;
- отдельные broker fee операции также добавляются в дневной итог;
- для читаемого отчёта broker fee привязывается к последней сделке без комиссии.

## Агрессивность

Управляется через `AGGRESSION_LEVEL` и во время сессии:

- `+` повышает уровень;
- `-` снижает уровень;
- `.trading_control.json` позволяет менять уровень без интерактивного ввода.

```mermaid
flowchart LR
    A[AGGRESSION_LEVEL 1..5] --> B[lot_multiplier]
    A --> C[interval_multiplier]
    B --> D[max_lots]
    C --> E[llm_interval / check_interval]
```

Важно: агрессивность больше не уменьшает ширину LLM-анализа. Количество тикеров задаётся `LLM_MAX_TICKERS`, чтобы модель видела рынок широко даже в осторожном режиме.

## Сравнение Режимов

| Режим | Что делает | Плюсы | Минусы | Когда использовать |
|---|---|---|---|---|
| `portfolio` | Показывает портфель | Безопасно, быстро | Нет торговли | Проверка счёта |
| `report` | Отчёты и CSV | Удобно для анализа | Не прогнозирует | Разбор истории |
| `risk-status` | FIFO P&L и комиссии | Проверяет дневной риск | Зависит от полноты операций API | Перед/после торгов |
| `trade --dry-run` | Сигналы без реальных сделок | Безопасная проверка логики | Нет реального исполнения | Перед production |
| `trade sandbox` | Торговля в sandbox | Проверка end-to-end | Sandbox отличается от рынка | Тестирование |
| `trade production` | Реальные сделки | Полный режим | Реальный риск денег | Только после dry-run/sandbox |
| `auto sandbox` | Sandbox с перезапуском | Тест устойчивости | Не реален по ликвидности | Долгий тест |
| `auto production` | Реальный автомат | Максимальная автономность | Максимальный риск | Только с лимитами и мониторингом |
| Rule-based | MA/RSI | Просто и прозрачно | Мало контекста | Базовая стратегия |
| LLM | Модель + tools + валидация | Широкий анализ, объяснения | LLM latency/cost/risk | Адаптивная торговля |

## Сильные Стороны Текущей Архитектуры

- Чёткое разделение: signal generation, validation, execution, risk accounting.
- LLM не исполняет заявки напрямую.
- Есть dry-run и sandbox.
- Есть дневной risk limit.
- FIFO-базис восстанавливается из истории операций.
- OpenRouter/DeepSeek/OpenAI/Qwen/GigaChat/Anthropic можно переключать конфигом.
- Strategy Toolkit даёт LLM структурированные данные, а не только сырой текст.
- Решения LLM пишутся в JSONL audit trail.

## Ограничения И Риски

- Market order может исполниться хуже ожидаемой цены.
- Rule-based режим не проверяет наличие позиции перед SELL так строго, как LLM-валидация.
- FIFO зависит от глубины `RISK_HISTORY_DAYS`; если история короче жизненного цикла позиции, базис может быть неполным.
- LLM может ошибиться в reasoning, даже если JSON валиден.
- API T-Invest может временно отдавать `UNAVAILABLE` или rate limit.
- Sandbox не полностью отражает реальные спреды, ликвидность и проскальзывание.
- ML-стратегия в текущем виде является вспомогательным сигналом, а не полноценной production ML-системой.

## Предложения По Развитию

### Безопасность Торговли

- Добавить локальную проверку позиции перед rule-based `SELL`, как в LLM-режиме.
- Добавить per-instrument лимиты: максимум позиции, максимум дневных сделок, cooldown после сделки.
- Добавить запрет торговли при широком spread или низкой ликвидности.
- Добавить ограничение max slippage для market order или перейти на limit order с timeout.

### Риск И P&L

- Хранить собственный persistent trade ledger в SQLite.
- Разделить комиссии по order_id, если API позволяет надёжно связать broker fee и сделку.
- Добавить unrealized P&L в risk status и LLM context.
- Добавить дневной лимит не только по убытку, но и по числу сделок/комиссиям.

### LLM-Оркестрация

- Добавить scorecard: почему тикер выбран/отклонён по фиксированным критериям.
- Сохранять полный prompt/response hash для аудита без утечки секретов.
- Добавить self-check: модель сначала формирует анализ, затем отдельный JSON decision.
- Поддержать native tool calls для провайдеров, где это стабильно.

### Стратегии

- Добавить стратегию по стакану/спреду, если API и лимиты позволяют.
- Добавить volatility targeting: размер позиции зависит от ATR/волатильности.
- Добавить portfolio-level allocation: не только сигнал по тикеру, но и балансировка портфеля.
- Добавить walk-forward backtesting и сравнение стратегий на одинаковом периоде.

### Эксплуатация

- Добавить health-check endpoint или Telegram уведомления.
- Добавить отдельный файл логов для сделок и ошибок.
- Добавить Windows smoke-test для `.bat` файлов через CI.
- Добавить GitHub Actions: lint, tests, compile, release validation.

## Рекомендуемый Рабочий Процесс

```mermaid
flowchart TD
    A[Настроить .env] --> B[portfolio]
    B --> C[risk-status]
    C --> D[trade --dry-run]
    D --> E{Логи и LLM ответы понятны?}
    E -->|нет| F[Поправить настройки]
    F --> D
    E -->|да| G[Sandbox]
    G --> H{Поведение стабильно?}
    H -->|нет| F
    H -->|да| I[Production с малым MAX_LOTS]
    I --> J[Мониторинг risk-status и daily_summary]
```

Для production рекомендуется начинать с:

- `MAX_LOTS=1`;
- небольшого `MAX_DAILY_LOSS`;
- `LLM_MAX_TICKERS=20`;
- `LLM_DECISION_INTERVAL` не ниже разумного лимита API/LLM;
- обязательного dry-run перед реальной сессией.
