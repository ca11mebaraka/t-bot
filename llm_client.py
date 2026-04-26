"""
Минимальный клиент для LLM-провайдеров.

Использует только стандартную библиотеку, чтобы не добавлять обязательные SDK
для каждого провайдера. OpenAI, DeepSeek, Qwen, OpenRouter и GigaChat работают
через OpenAI-compatible chat completions; Anthropic использует Messages API.
"""
import json
import logging
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Any

from config import Config

logger = logging.getLogger(__name__)


class LLMError(RuntimeError):
    pass


@dataclass
class LLMMessage:
    role: str
    content: str


@dataclass
class LLMRawResponse:
    provider: str
    model: str
    content: str
    raw: dict[str, Any]


_DEFAULT_BASE_URLS = {
    "openai": "https://api.openai.com/v1",
    "deepseek": "https://api.deepseek.com",
    "qwen": "https://dashscope.aliyuncs.com/compatible-mode/v1",
    "gigachat": "https://gigachat.devices.sberbank.ru/api/v1",
    "anthropic": "https://api.anthropic.com/v1",
    "openrouter": "https://openrouter.ai/api/v1",
}

_DEFAULT_MODELS = {
    "openai": "gpt-4o-mini",
    "deepseek": "deepseek-chat",
    "qwen": "qwen-plus",
    "gigachat": "GigaChat",
    "anthropic": "claude-3-5-sonnet-latest",
    "openrouter": "openai/gpt-4o-mini",
}


def _json_post(
    url: str,
    payload: dict[str, Any],
    headers: dict[str, str],
    timeout: int,
) -> dict[str, Any]:
    body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    request = urllib.request.Request(
        url,
        data=body,
        headers={
            "Content-Type": "application/json",
            **headers,
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            raw = response.read().decode("utf-8")
    except urllib.error.HTTPError as exc:
        details = exc.read().decode("utf-8", errors="replace")
        raise LLMError(f"LLM HTTP {exc.code}: {details}") from exc
    except urllib.error.URLError as exc:
        raise LLMError(f"LLM request failed: {exc}") from exc

    try:
        return json.loads(raw)
    except json.JSONDecodeError as exc:
        raise LLMError(f"LLM returned non-JSON response: {raw[:500]}") from exc


class LLMClient:
    def __init__(self, config: Config):
        self.config = config
        self.provider = config.llm_provider
        self.model = config.llm_model or _DEFAULT_MODELS.get(self.provider, "")
        self.base_url = (config.llm_base_url or _DEFAULT_BASE_URLS.get(self.provider, "")).rstrip("/")
        self.api_key = config.resolved_llm_api_key

        if self.provider != "mock" and not config.llm_mock_response:
            if not self.provider:
                raise LLMError("LLM_PROVIDER не задан")
            if not self.model:
                raise LLMError(f"LLM_MODEL не задан и нет default для provider={self.provider}")
            if not self.base_url:
                raise LLMError(f"LLM_BASE_URL не задан и нет default для provider={self.provider}")
            if not self.api_key:
                raise LLMError(f"API key для provider={self.provider} не задан")

    def complete(self, messages: list[LLMMessage], response_format_json: bool = True) -> LLMRawResponse:
        if self.provider == "mock" or self.config.llm_mock_response:
            content = self.config.llm_mock_response or '{"decisions":[{"action":"HOLD","reason":"mock"}]}'
            return LLMRawResponse(provider="mock", model="mock", content=content, raw={})

        if self.provider == "anthropic":
            return self._complete_anthropic(messages)
        return self._complete_openai_compatible(messages, response_format_json=response_format_json)

    def _complete_openai_compatible(
        self,
        messages: list[LLMMessage],
        response_format_json: bool,
    ) -> LLMRawResponse:
        payload: dict[str, Any] = {
            "model": self.model,
            "messages": [{"role": msg.role, "content": msg.content} for msg in messages],
            "temperature": 0.1,
        }
        if response_format_json:
            payload["response_format"] = {"type": "json_object"}

        headers = {"Authorization": f"Bearer {self.api_key}"}
        if self.provider == "openrouter":
            headers["HTTP-Referer"] = "https://localhost/t-bot"
            headers["X-OpenRouter-Title"] = "T-Bot"
            if self.config.llm_session_id:
                payload["session_id"] = self.config.llm_session_id

        raw = _json_post(
            f"{self.base_url}/chat/completions",
            payload=payload,
            headers=headers,
            timeout=self.config.llm_timeout,
        )
        try:
            content = raw["choices"][0]["message"]["content"]
        except (KeyError, IndexError, TypeError) as exc:
            raise LLMError(f"Unexpected LLM response shape: {raw}") from exc
        return LLMRawResponse(provider=self.provider, model=self.model, content=content, raw=raw)

    def _complete_anthropic(self, messages: list[LLMMessage]) -> LLMRawResponse:
        system_parts = [msg.content for msg in messages if msg.role == "system"]
        user_messages = [
            {"role": "user" if msg.role == "system" else msg.role, "content": msg.content}
            for msg in messages
            if msg.role != "system"
        ]
        payload = {
            "model": self.model,
            "max_tokens": 2048,
            "temperature": 0.1,
            "system": "\n\n".join(system_parts),
            "messages": user_messages,
        }
        raw = _json_post(
            f"{self.base_url}/messages",
            payload=payload,
            headers={
                "x-api-key": self.api_key,
                "anthropic-version": "2023-06-01",
            },
            timeout=self.config.llm_timeout,
        )
        try:
            content = "".join(part.get("text", "") for part in raw["content"])
        except (KeyError, TypeError) as exc:
            raise LLMError(f"Unexpected Anthropic response shape: {raw}") from exc
        return LLMRawResponse(provider=self.provider, model=self.model, content=content, raw=raw)
