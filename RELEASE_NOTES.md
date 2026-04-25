# Release Notes

## Unreleased

### Added

- LLM Trading Control with autonomous `BUY` / `SELL` / `HOLD` decisions.
- Provider support for OpenAI, DeepSeek, Qwen, GigaChat, Anthropic and OpenRouter.
- Market scanner that builds a T-Invest shortlist of tradable RUB shares and ETFs.
- Prompt context with market candidates, portfolio positions, FIFO P&L, commissions, daily risk and aggression level.
- Human-readable `LLM REQUEST` and `LLM RESPONSE` console output.
- Runtime aggression control via `+` / `-` in the terminal or `.trading_control.json`.
- `run.sh` menu entries for LLM dry-run, sandbox, production and auto modes.
- `README.md` with setup, configuration and launch instructions.

### Changed

- T-Invest SDK dependency now installs from T-Bank `invest-python` as `t-tech-investments`.
- Imports migrated from `tinkoff.invest` to `t_tech.invest`.
- Risk manager now restores FIFO cost basis and daily results from account operations.
- Production order routing now uses `config.is_sandbox` instead of checking for a `sandbox` attribute.
- Stop-order prices are rounded to the actual exchange price step.
- LLM prompt now asks the model to compare multiple tickers, dynamically adapt strategy by session results and explain strategy mode.

### Fixed

- `SignalType` export from `strategies`.
- `risk-status` compatibility with the new SDK operation shape.
- Broker commission accounting when `PostOrder` returns zero commission and the fee appears as a child operation.
- SELL P&L being zero when selling positions opened before the current bot process.
- Empty LLM `decisions` responses now result in visible `HOLD` fallback and no trade.

### Notes

- Production LLM modes place real orders. Test with `--dry-run` or Sandbox first.
- `.env`, `.env.0` and API keys must stay uncommitted.
