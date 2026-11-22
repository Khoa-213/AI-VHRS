"""Upgrade U5 (Q1): LLM providers behind one interface, called over HTTP with httpx (no vendor SDK), with failover.

The orchestrator speaks a neutral transcript; each adapter turns it into its provider's format and back:

    {"role": "user", "text": str}
    {"role": "assistant", "text": str, "tool_calls": [ToolCall], "raw": <the provider's own turn>, "provider": name}
    {"role": "tool", "results": [{"id": str, "name": str, "result": dict}]}

An assistant turn keeps its provider's raw form so the same provider gets it back unchanged (Gemini 3 requires its thought
signatures back with the function calls of the turn). A turn never mixes providers: on failure the orchestrator restarts the
customer's turn on the next provider (assistant.py).

Errors are `ProviderError(reason)`: TIMEOUT, NETWORK, RATE_LIMITED, SERVER, AUTH, BAD_REQUEST, BAD_RESPONSE, BLOCKED. Every
reason moves on to the next provider (a request one provider refuses may still work on another); each attempt is logged.
"""
from __future__ import annotations

import json
import uuid
from dataclasses import dataclass, field
from typing import Any, Protocol

import httpx

from app.core.config import get_settings


@dataclass(frozen=True)
class ToolSpec:
    name: str
    description: str
    parameters: dict[str, Any]          # JSON schema subset all three providers accept: type/properties/required/enum/items


@dataclass
class ToolCall:
    id: str
    name: str
    args: dict[str, Any]


@dataclass
class Reply:
    text: str
    tool_calls: list[ToolCall]
    input_tokens: int
    output_tokens: int
    raw: Any = None
    finish: str | None = None


# Room for a tool call that carries a whole order text (update_text sends the full text; Vietnamese is ~1 token per 2 characters,
# orders take 20000 characters). Was 1024 / 2048, which cut such a call (2026-11-22).
MAX_OUTPUT_TOKENS = 12000


@dataclass
class ProviderError(Exception):
    reason: str
    status: int | None = None
    detail: str = ""

    def __str__(self) -> str:
        return f"{self.reason}({self.status}): {self.detail[:200]}"


class Provider(Protocol):
    name: str
    model: str

    def complete(self, system: str, transcript: list[dict[str, Any]], tools: list[ToolSpec]) -> Reply: ...


def _classify(resp: httpx.Response) -> ProviderError:
    s = resp.status_code
    reason = ("RATE_LIMITED" if s == 429 else "AUTH" if s in (401, 403) else "BAD_REQUEST" if 400 <= s < 500
              else "SERVER")
    return ProviderError(reason, s, resp.text[:500])


class _HttpProvider:
    name = "base"

    def __init__(self, api_key: str, model: str, *, timeout: float | None = None, transport: httpx.BaseTransport | None = None):
        self.api_key, self.model = api_key, model
        self.timeout = timeout or get_settings().llm_timeout_seconds
        self.transport = transport

    def _post(self, url: str, headers: dict[str, str], body: dict[str, Any]) -> dict[str, Any]:
        try:
            with httpx.Client(transport=self.transport, timeout=self.timeout) as http:
                resp = http.post(url, headers=headers, json=body)
        except httpx.TimeoutException as exc:
            raise ProviderError("TIMEOUT", None, str(exc)) from exc
        except httpx.HTTPError as exc:
            raise ProviderError("NETWORK", None, str(exc)) from exc
        if resp.status_code != 200:
            raise _classify(resp)
        try:
            return resp.json()
        except ValueError as exc:
            raise ProviderError("BAD_RESPONSE", 200, resp.text[:300]) from exc


def _merge_users(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Two user texts in a row (an earlier turn whose reply failed) become one: Claude requires alternating roles."""
    out: list[dict[str, Any]] = []
    for it in items:
        if out and it["role"] == "user" and out[-1]["role"] == "user":
            out[-1] = {"role": "user", "text": out[-1]["text"] + "\n\n" + it["text"]}
        else:
            out.append(it)
    return out


# ---------------------------------------------------------------------------------------------------------- Gemini
class GeminiProvider(_HttpProvider):
    name = "gemini"
    base_url = "https://generativelanguage.googleapis.com/v1beta"

    def _contents(self, transcript: list[dict[str, Any]]) -> list[dict[str, Any]]:
        out = []
        for it in _merge_users(transcript):
            if it["role"] == "user":
                out.append({"role": "user", "parts": [{"text": it["text"]}]})
            elif it["role"] == "assistant":
                if it.get("provider") == self.name and it.get("raw"):
                    out.append(it["raw"])
                else:
                    parts = ([{"text": it["text"]}] if it.get("text") else []) + [
                        {"functionCall": {"name": c.name, "args": c.args}} for c in it.get("tool_calls", [])]
                    out.append({"role": "model", "parts": parts or [{"text": ""}]})
            else:
                out.append({"role": "user", "parts": [
                    {"functionResponse": {"name": r["name"], "response": {"result": r["result"]}}} for r in it["results"]]})
        return out

    def complete(self, system: str, transcript: list[dict[str, Any]], tools: list[ToolSpec]) -> Reply:
        body: dict[str, Any] = {"systemInstruction": {"parts": [{"text": system}]}, "contents": self._contents(transcript),
                                "generationConfig": {"temperature": 0.3, "maxOutputTokens": MAX_OUTPUT_TOKENS}}
        if tools:
            body["tools"] = [{"functionDeclarations": [
                {"name": t.name, "description": t.description, "parameters": t.parameters} for t in tools]}]
        data = self._post(f"{self.base_url}/models/{self.model}:generateContent",
                          {"x-goog-api-key": self.api_key, "content-type": "application/json"}, body)
        cands = data.get("candidates") or []
        if not cands:
            block = (data.get("promptFeedback") or {}).get("blockReason")
            raise ProviderError("BLOCKED" if block else "BAD_RESPONSE", 200, str(block or data)[:300])
        content = cands[0].get("content") or {"role": "model", "parts": []}
        parts = content.get("parts") or []
        text = "".join(p.get("text", "") for p in parts if "text" in p and not p.get("thought"))
        calls = [ToolCall(p["functionCall"].get("id") or uuid.uuid4().hex[:12], p["functionCall"]["name"],
                          p["functionCall"].get("args") or {}) for p in parts if "functionCall" in p]
        usage = data.get("usageMetadata") or {}
        return Reply(text.strip(), calls, int(usage.get("promptTokenCount") or 0),
                     int(usage.get("candidatesTokenCount") or 0) + int(usage.get("thoughtsTokenCount") or 0),
                     raw={"role": "model", "parts": parts}, finish=cands[0].get("finishReason"))


# ---------------------------------------------------------------------------------------------------------- Claude
class AnthropicProvider(_HttpProvider):
    name = "anthropic"
    url = "https://api.anthropic.com/v1/messages"

    def _messages(self, transcript: list[dict[str, Any]]) -> list[dict[str, Any]]:
        out = []
        for it in _merge_users(transcript):
            if it["role"] == "user":
                out.append({"role": "user", "content": it["text"]})
            elif it["role"] == "assistant":
                if it.get("provider") == self.name and it.get("raw"):
                    out.append({"role": "assistant", "content": it["raw"]})
                else:
                    blocks = ([{"type": "text", "text": it["text"]}] if it.get("text") else []) + [
                        {"type": "tool_use", "id": c.id, "name": c.name, "input": c.args} for c in it.get("tool_calls", [])]
                    out.append({"role": "assistant", "content": blocks or [{"type": "text", "text": "..."}]})
            else:
                out.append({"role": "user", "content": [
                    {"type": "tool_result", "tool_use_id": r["id"], "content": json.dumps(r["result"], ensure_ascii=False)}
                    for r in it["results"]]})
        return out

    def complete(self, system: str, transcript: list[dict[str, Any]], tools: list[ToolSpec]) -> Reply:
        body: dict[str, Any] = {"model": self.model, "max_tokens": MAX_OUTPUT_TOKENS, "system": system,
                                "messages": self._messages(transcript), "temperature": 0.3}
        if tools:
            body["tools"] = [{"name": t.name, "description": t.description, "input_schema": t.parameters} for t in tools]
        data = self._post(self.url, {"x-api-key": self.api_key, "anthropic-version": "2023-06-01",
                                     "content-type": "application/json"}, body)
        blocks = data.get("content") or []
        text = "".join(b.get("text", "") for b in blocks if b.get("type") == "text")
        calls = [ToolCall(b["id"], b["name"], b.get("input") or {}) for b in blocks if b.get("type") == "tool_use"]
        usage = data.get("usage") or {}
        return Reply(text.strip(), calls, int(usage.get("input_tokens") or 0), int(usage.get("output_tokens") or 0),
                     raw=blocks, finish=data.get("stop_reason"))


# ---------------------------------------------------------------------------------------------------------- OpenAI
class OpenAIProvider(_HttpProvider):
    name = "openai"
    url = "https://api.openai.com/v1/chat/completions"

    def _messages(self, system: str, transcript: list[dict[str, Any]]) -> list[dict[str, Any]]:
        out: list[dict[str, Any]] = [{"role": "system", "content": system}]
        for it in transcript:
            if it["role"] == "user":
                out.append({"role": "user", "content": it["text"]})
            elif it["role"] == "assistant":
                if it.get("provider") == self.name and it.get("raw"):
                    out.append(it["raw"])
                else:
                    msg: dict[str, Any] = {"role": "assistant", "content": it.get("text") or None}
                    if it.get("tool_calls"):
                        msg["tool_calls"] = [{"id": c.id, "type": "function", "function": {
                            "name": c.name, "arguments": json.dumps(c.args, ensure_ascii=False)}} for c in it["tool_calls"]]
                    out.append(msg)
            else:
                out.extend({"role": "tool", "tool_call_id": r["id"], "content": json.dumps(r["result"], ensure_ascii=False)}
                           for r in it["results"])
        return out

    def complete(self, system: str, transcript: list[dict[str, Any]], tools: list[ToolSpec]) -> Reply:
        body: dict[str, Any] = {"model": self.model, "messages": self._messages(system, transcript),
                                "max_completion_tokens": MAX_OUTPUT_TOKENS}
        if tools:
            body["tools"] = [{"type": "function", "function": {"name": t.name, "description": t.description,
                                                               "parameters": t.parameters}} for t in tools]
        data = self._post(self.url, {"authorization": f"Bearer {self.api_key}", "content-type": "application/json"}, body)
        choices = data.get("choices") or []
        if not choices:
            raise ProviderError("BAD_RESPONSE", 200, str(data)[:300])
        msg = choices[0].get("message") or {}
        calls = []
        for c in msg.get("tool_calls") or []:
            try:
                args = json.loads(c["function"].get("arguments") or "{}")
            except ValueError:
                args = {"_invalid_json": c["function"].get("arguments")}
            calls.append(ToolCall(c["id"], c["function"]["name"], args if isinstance(args, dict) else {}))
        usage = data.get("usage") or {}
        raw = {"role": "assistant", "content": msg.get("content"), **({"tool_calls": msg["tool_calls"]} if msg.get("tool_calls") else {})}
        return Reply((msg.get("content") or "").strip(), calls, int(usage.get("prompt_tokens") or 0),
                     int(usage.get("completion_tokens") or 0), raw=raw, finish=choices[0].get("finish_reason"))


# ---------------------------------------------------------------------------------------------------------- registry
@dataclass
class ProviderInfo:
    name: str
    model: str | None
    configured: bool
    missing: list[str] = field(default_factory=list)


def provider_infos() -> list[ProviderInfo]:
    """Which providers the environment configures, in the order they are tried. Never returns a key."""
    s = get_settings()
    known = {"anthropic": (s.anthropic_api_key, s.anthropic_model, "ANTHROPIC"),
             "openai": (s.openai_api_key, s.openai_model, "OPENAI"),
             "gemini": (s.gemini_api_key, s.gemini_model, "GEMINI")}
    out = []
    for name in [n.strip().lower() for n in s.llm_provider_order.split(",") if n.strip()]:
        if name not in known:
            continue
        key, model, env = known[name]
        missing = ([f"{env}_API_KEY"] if not key else []) + ([f"{env}_MODEL"] if not model else [])
        out.append(ProviderInfo(name, model, not missing, missing))
    return out


def configured_providers() -> list[Provider]:
    s = get_settings()
    build = {"anthropic": lambda: AnthropicProvider(s.anthropic_api_key, s.anthropic_model),
             "openai": lambda: OpenAIProvider(s.openai_api_key, s.openai_model),
             "gemini": lambda: GeminiProvider(s.gemini_api_key, s.gemini_model)}
    return [build[i.name]() for i in provider_infos() if i.configured]


def prices() -> dict[str, tuple[float, float]]:
    raw = get_settings().llm_prices
    if not raw:
        return {}
    try:
        data = json.loads(raw)
        return {str(k): (float(v[0]), float(v[1])) for k, v in data.items()}
    except (ValueError, TypeError, IndexError, KeyError):
        return {}


def cost_usd(model: str, input_tokens: int, output_tokens: int) -> float | None:
    p = prices().get(model)
    if p is None:
        return None
    return round(input_tokens * p[0] / 1_000_000 + output_tokens * p[1] / 1_000_000, 6)
