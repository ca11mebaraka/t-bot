# Release Notes

## 1.1.0 - 2026-04-26

### Added

- LLM Trading Control with autonomous `BUY` / `SELL` / `HOLD` decisions.
- Strategy Toolkit emulated tools for LLM orchestration: regime detection, deterministic strategies, pair trading, and quick backtests.
- New deterministic strategies: trend following, mean reversion, breakout momentum, stat arb, and ML strategy.
- Strategy defaults in `config/strategies.yaml`.
- LLM decision audit trail in `logs/decisions/*.jsonl`.
- Unit tests for strategy outputs, market regime, toolkit, and backtester.
- Provider support for OpenAI, DeepSeek, Qwen, GigaChat, Anthropic and OpenRouter.
- OpenRouter `session_id` support via `LLM_SESSION_ID`.
- Market scanner that builds a T-Invest shortlist of tradable RUB shares and ETFs.
- Prompt context with market candidates, portfolio positions, FIFO P&L, commissions, daily risk and aggression level.
- Human-readable `LLM REQUEST` and `LLM RESPONSE` console output.
- Human-friendly colored console logging with pseudo-graphic frames and translated T-Invest API events.
- Runtime aggression control via `+` / `-` in the terminal or `.trading_control.json`.
- `run.sh` menu entries for LLM dry-run, sandbox, production and auto modes.
- `README.md` with setup, configuration and launch instructions.

### Changed

- T-Invest SDK dependency now installs from T-Bank `invest-python` as `t-tech-investments`.
- Imports migrated from `tinkoff.invest` to `t_tech.invest`.
- Risk manager now restores FIFO cost basis and daily results from account operations.
- Production order routing now uses `config.is_sandbox` instead of checking for a `sandbox` attribute.
- Stop-order prices are rounded to the actual exchange price step.
- LLM prompt now asks the model to compare many tickers, return up to `LLM_MAX_TICKERS` decisions, dynamically adapt strategy by session results and explain strategy mode.
- Runtime aggression no longer reduces LLM market coverage; it affects execution size and polling interval.
- Default `LLM_MAX_TICKERS` is now `20`.

### Fixed

- `SignalType` export from `strategies`.
- `risk-status` compatibility with the new SDK operation shape.
- Portfolio screen compatibility with the new SDK average position price fields.
- Broker commission accounting when `PostOrder` returns zero commission and the fee appears as a child operation.
- SELL P&L being zero when selling positions opened before the current bot process.
- Empty LLM `decisions` responses now result in visible `HOLD` fallback and no trade.
- Transient T-Invest API errors in the LLM cycle now retry and log a short human-readable warning instead of a full traceback.
- ML strategy now returns `HOLD` when training data contains only one target class.

### Notes

- Production LLM modes place real orders. Test with `--dry-run` or Sandbox first.
- `.env`, `.env.0` and API keys must stay uncommitted.
