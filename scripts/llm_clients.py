from __future__ import annotations

import json
import os
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Any, Literal, Protocol


class LLMError(RuntimeError):
    pass


Provider = Literal["openai", "gemini", "deepseek", "grok"]


@dataclass(frozen=True)
class LLMConfig:
    provider: Provider
    model: str
    temperature: float = 0.2
    max_output_tokens: int = 900
    timeout_s: int = 90
    retries: int = 5


class LLMClient(Protocol):
    def generate_text(self, *, prompt: str, system: str | None = None) -> str: ...


def _sleep_backoff(attempt: int) -> None:
    time.sleep(min(2.0**attempt, 10.0))


def _post_json(
    url: str,
    *,
    headers: dict[str, str],
    payload: dict[str, Any],
    timeout_s: int,
    retries: int,
) -> Any:
    body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    last_err: Exception | None = None
    for attempt in range(max(1, retries)):
        try:
            req = urllib.request.Request(
                url,
                method="POST",
                data=body,
                headers={
                    "content-type": "application/json",
                    **headers,
                },
            )
            with urllib.request.urlopen(req, timeout=timeout_s) as resp:
                raw = resp.read().decode("utf-8", errors="replace")
                try:
                    return json.loads(raw)
                except Exception as e:  # noqa: BLE001
                    raise LLMError(f"Invalid JSON response from {url}: {raw[:4000]}") from e
        except urllib.error.HTTPError as e:
            try:
                detail = e.read().decode("utf-8", errors="replace")
            except Exception:
                detail = ""
            last_err = LLMError(f"HTTP {e.code} from {url}: {detail[:2000]}")
        except Exception as e:  # noqa: BLE001
            last_err = e
        _sleep_backoff(attempt)
    raise LLMError(f"POST failed after retries: {url}") from last_err


def _join_openai_url(base_url: str, path: str) -> str:
    base = base_url.rstrip("/")
    if base.endswith("/v1"):
        return f"{base}{path}"
    return f"{base}/v1{path}"


class OpenAICompatibleChatClient:
    def __init__(
        self,
        *,
        api_key: str,
        base_url: str,
        model: str,
        temperature: float,
        max_output_tokens: int,
        timeout_s: int,
        retries: int,
        user_agent: str = "AI4SciProgressAtlas/0.1",
    ) -> None:
        self._api_key = api_key
        self._base_url = base_url
        self._model = model
        self._temperature = temperature
        self._max_output_tokens = max_output_tokens
        self._timeout_s = timeout_s
        self._retries = retries
        self._ua = user_agent

    def generate_text(self, *, prompt: str, system: str | None = None) -> str:
        url = _join_openai_url(self._base_url, "/chat/completions")
        messages: list[dict[str, str]] = []
        if system:
            messages.append({"role": "system", "content": system})
        messages.append({"role": "user", "content": prompt})

        data = _post_json(
            url,
            headers={
                "authorization": f"Bearer {self._api_key}",
                "user-agent": self._ua,
            },
            payload={
                "model": self._model,
                "messages": messages,
                "temperature": self._temperature,
                "max_tokens": self._max_output_tokens,
            },
            timeout_s=self._timeout_s,
            retries=self._retries,
        )
        choices = data.get("choices") or []
        if not choices:
            raise LLMError(f"No choices returned: {str(data)[:1500]}")
        msg = (choices[0] or {}).get("message") or {}
        content = msg.get("content")
        if not isinstance(content, str) or not content.strip():
            raise LLMError(f"Empty content returned: {str(data)[:1500]}")
        return content.strip()


class GeminiClient:
    def __init__(
        self,
        *,
        api_key: str,
        model: str,
        temperature: float,
        max_output_tokens: int,
        thinking_budget: int | None = 0,
        timeout_s: int,
        retries: int,
        base_url: str = "https://generativelanguage.googleapis.com/v1beta",
        user_agent: str = "AI4SciProgressAtlas/0.1",
    ) -> None:
        self._api_key = api_key
        self._model = model
        self._temperature = temperature
        self._max_output_tokens = max_output_tokens
        self._thinking_budget = thinking_budget
        self._timeout_s = timeout_s
        self._retries = retries
        self._base_url = base_url.rstrip("/")
        self._ua = user_agent

    def generate_text(self, *, prompt: str, system: str | None = None) -> str:
        url = f"{self._base_url}/models/{self._model}:generateContent?key={self._api_key}"
        payload: dict[str, Any] = {
            "contents": [
                {
                    "role": "user",
                    "parts": [{"text": prompt}],
                }
            ],
            "generationConfig": {
                "temperature": self._temperature,
                "maxOutputTokens": self._max_output_tokens,
            },
        }
        if system:
            payload["systemInstruction"] = {"parts": [{"text": system}]}
        if self._thinking_budget is not None:
            payload["generationConfig"]["thinkingConfig"] = {"thinkingBudget": int(self._thinking_budget)}

        data = _post_json(
            url,
            headers={
                "user-agent": self._ua,
            },
            payload=payload,
            timeout_s=self._timeout_s,
            retries=self._retries,
        )
        candidates = data.get("candidates") or []
        if not candidates:
            raise LLMError(f"No candidates returned: {str(data)[:1500]}")
        parts = ((candidates[0] or {}).get("content") or {}).get("parts") or []
        texts = [p.get("text") for p in parts if isinstance(p, dict) and isinstance(p.get("text"), str)]
        out = "\n".join(t.strip() for t in texts if t and t.strip()).strip()
        if not out:
            raise LLMError(f"Empty text returned: {str(data)[:1500]}")
        return out


def load_llm_from_env(*, provider: Provider | None = None) -> tuple[LLMConfig, LLMClient]:
    """
    Env vars:
      - LLM_PROVIDER: openai|gemini|deepseek|grok (optional)

    OpenAI:
      - OPENAI_API_KEY (required)
      - OPENAI_MODEL (default: gpt-4o-mini)
      - OPENAI_BASE_URL (default: https://api.openai.com)

    Gemini:
      - GEMINI_API_KEY or GOOGLE_API_KEY (required)
      - GEMINI_MODEL (default: gemini-2.5-flash)
      - GEMINI_THINKING_BUDGET or LLM_THINKING_BUDGET (default: 0)

    DeepSeek (OpenAI-compatible):
      - DEEPSEEK_API_KEY (required)
      - DEEPSEEK_MODEL (default: deepseek-chat)
      - DEEPSEEK_BASE_URL (default: https://api.deepseek.com)

    Grok/xAI (OpenAI-compatible):
      - GROK_API_KEY or XAI_API_KEY (required)
      - GROK_MODEL (default: grok-2-latest)
      - GROK_BASE_URL (default: https://api.x.ai)
    """
    env_provider = (os.getenv("LLM_PROVIDER") or "").strip().lower()
    p: Provider | None = provider or (env_provider if env_provider in {"openai", "gemini", "deepseek", "grok"} else None)  # type: ignore[assignment]

    if p is None:
        if os.getenv("DEEPSEEK_API_KEY"):
            p = "deepseek"
        elif os.getenv("OPENAI_API_KEY"):
            p = "openai"
        elif os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY"):
            p = "gemini"
        elif os.getenv("GROK_API_KEY") or os.getenv("XAI_API_KEY"):
            p = "grok"
        else:
            raise LLMError("No provider configured. Set LLM_PROVIDER and the corresponding API key env var.")

    temperature = float(os.getenv("LLM_TEMPERATURE") or "0.2")
    max_output_tokens = int(os.getenv("LLM_MAX_OUTPUT_TOKENS") or "900")
    timeout_s = int(os.getenv("LLM_TIMEOUT_S") or "90")
    retries = int(os.getenv("LLM_RETRIES") or "5")

    if p == "openai":
        api_key = os.getenv("OPENAI_API_KEY") or ""
        if not api_key:
            raise LLMError("Missing OPENAI_API_KEY")
        model = os.getenv("OPENAI_MODEL") or "gpt-4o-mini"
        base_url = os.getenv("OPENAI_BASE_URL") or "https://api.openai.com"
        cfg = LLMConfig(provider=p, model=model, temperature=temperature, max_output_tokens=max_output_tokens, timeout_s=timeout_s, retries=retries)
        return cfg, OpenAICompatibleChatClient(
            api_key=api_key,
            base_url=base_url,
            model=model,
            temperature=cfg.temperature,
            max_output_tokens=cfg.max_output_tokens,
            timeout_s=cfg.timeout_s,
            retries=cfg.retries,
        )

    if p == "gemini":
        api_key = os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY") or ""
        if not api_key:
            raise LLMError("Missing GEMINI_API_KEY (or GOOGLE_API_KEY)")
        model = os.getenv("GEMINI_MODEL") or "gemini-2.5-flash"
        thinking_budget_raw = (os.getenv("GEMINI_THINKING_BUDGET") or os.getenv("LLM_THINKING_BUDGET") or "").strip()
        thinking_budget: int | None = 0
        if thinking_budget_raw:
            if thinking_budget_raw.lower() in {"none", "null", "off"}:
                thinking_budget = None
            else:
                thinking_budget = int(thinking_budget_raw)
        cfg = LLMConfig(provider=p, model=model, temperature=temperature, max_output_tokens=max_output_tokens, timeout_s=timeout_s, retries=retries)
        return cfg, GeminiClient(
            api_key=api_key,
            model=model,
            temperature=cfg.temperature,
            max_output_tokens=cfg.max_output_tokens,
            thinking_budget=thinking_budget,
            timeout_s=cfg.timeout_s,
            retries=cfg.retries,
        )

    if p == "deepseek":
        api_key = os.getenv("DEEPSEEK_API_KEY") or ""
        if not api_key:
            raise LLMError("Missing DEEPSEEK_API_KEY")
        model = os.getenv("DEEPSEEK_MODEL") or "deepseek-chat"
        base_url = os.getenv("DEEPSEEK_BASE_URL") or "https://api.deepseek.com"
        cfg = LLMConfig(provider=p, model=model, temperature=temperature, max_output_tokens=max_output_tokens, timeout_s=timeout_s, retries=retries)
        return cfg, OpenAICompatibleChatClient(
            api_key=api_key,
            base_url=base_url,
            model=model,
            temperature=cfg.temperature,
            max_output_tokens=cfg.max_output_tokens,
            timeout_s=cfg.timeout_s,
            retries=cfg.retries,
            user_agent="AI4SciProgressAtlas/0.1 (deepseek)",
        )

    api_key = os.getenv("GROK_API_KEY") or os.getenv("XAI_API_KEY") or ""
    if not api_key:
        raise LLMError("Missing GROK_API_KEY (or XAI_API_KEY)")
    model = os.getenv("GROK_MODEL") or "grok-2-latest"
    base_url = os.getenv("GROK_BASE_URL") or "https://api.x.ai"
    cfg = LLMConfig(provider="grok", model=model, temperature=temperature, max_output_tokens=max_output_tokens, timeout_s=timeout_s, retries=retries)
    return cfg, OpenAICompatibleChatClient(
        api_key=api_key,
        base_url=base_url,
        model=model,
        temperature=cfg.temperature,
        max_output_tokens=cfg.max_output_tokens,
        timeout_s=cfg.timeout_s,
        retries=cfg.retries,
        user_agent="AI4SciProgressAtlas/0.1 (grok)",
    )
