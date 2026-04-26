STRATEGY_TOOLS = [
    {
        "name": "list_strategies",
        "description": (
            "Возвращает список доступных торговых стратегий с описанием каждой "
            "и рекомендуемыми рыночными условиями для их применения."
        ),
        "input_schema": {"type": "object", "properties": {}, "required": []},
    },
    {
        "name": "get_market_regime",
        "description": (
            "Определяет текущий рыночный режим для тикера: trending_up, trending_down, "
            "ranging, high_volatility, low_volatility."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "ticker": {"type": "string", "description": "Тикер инструмента, например SBER"},
                "interval": {"type": "string", "enum": ["1_MIN", "5_MIN", "1_HOUR", "1_DAY"], "default": "1_HOUR"},
            },
            "required": ["ticker"],
        },
    },
    {
        "name": "run_strategy",
        "description": (
            "Запускает торговую стратегию и возвращает сигнал с индикаторами. "
            "LLM может передавать params для переопределения дефолтных параметров."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "strategy_name": {"type": "string", "enum": ["trend_following", "mean_reversion", "breakout", "ml"]},
                "ticker": {"type": "string"},
                "params": {"type": "object", "additionalProperties": True},
                "interval": {"type": "string", "enum": ["1_MIN", "5_MIN", "1_HOUR", "1_DAY"], "default": "1_HOUR"},
            },
            "required": ["strategy_name", "ticker", "params"],
        },
    },
    {
        "name": "run_strategy_pair",
        "description": "Запускает статистический арбитраж для пары коррелированных инструментов.",
        "input_schema": {
            "type": "object",
            "properties": {
                "ticker_a": {"type": "string"},
                "ticker_b": {"type": "string"},
                "params": {"type": "object", "additionalProperties": True},
                "interval": {"type": "string", "enum": ["1_MIN", "5_MIN", "1_HOUR", "1_DAY"], "default": "1_HOUR"},
            },
            "required": ["ticker_a", "ticker_b", "params"],
        },
    },
    {
        "name": "backtest_strategy",
        "description": (
            "Запускает быстрый бэктест стратегии с заданными параметрами на исторических данных. "
            "Используй перед нестандартными params."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "strategy_name": {"type": "string", "enum": ["trend_following", "mean_reversion", "breakout", "stat_arb", "ml"]},
                "ticker": {"type": "string"},
                "params": {"type": "object", "additionalProperties": True},
                "bars": {"type": "integer", "default": 500},
                "interval": {"type": "string", "enum": ["1_HOUR", "1_DAY"], "default": "1_DAY"},
            },
            "required": ["strategy_name", "ticker", "params"],
        },
    },
]
