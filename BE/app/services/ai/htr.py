"""V2 Phase E2b: read the handwriting on a customer's photo (one page) into a plain transcript.

Measured in Phase E1 (`docs/benchmarks/E_htr_benchmark_2026-11-19.md`): Gemini, whole page, CER 0.024 on 50 public
pages; it answers "[?]" on blank / noisy pages and did not fill hidden parts. The prompt below is the one measured there.
Claude is the fallback when Gemini fails (owner 2026-11-19, decision E2-d); it has not been measured on handwriting.
Called over HTTP with httpx (no SDK) like the assistant (`llm.py`); keys stay in the environment. A refusal by one provider
(`RECITATION`, safety) moves on to the next; the result is a transcript or "nothing read", never a guess.
"""
from __future__ import annotations

import base64
from dataclasses import dataclass, field
from typing import Any

import cv2
import httpx
import numpy as np

from app.core.config import get_settings
from app.core.errors import AppError
from app.services.ai.llm import ProviderError, _HttpProvider
from app.services.handwriting_image import _apply_orientation

PROMPT = ("Chép lại NGUYÊN VĂN toàn bộ chữ viết tay tiếng Việt trong ảnh, theo thứ tự đọc, giữ dấu và dấu câu. "
          "Không sửa chính tả, không thêm, không tóm tắt, không giải thích. Chữ nào không đọc được thì ghi [?] đúng chỗ "
          "đó, tuyệt đối không đoán hay tự điền. Nếu ảnh không có chữ viết tay thì chỉ trả lời [?]. Chỉ trả về phần chữ.")
MAX_SIDE_PX = 2000           # enough for handwriting, keeps one page around 1-2k input tokens
REFUSED = {"RECITATION", "SAFETY", "PROHIBITED_CONTENT", "BLOCKLIST", "SPII", "refusal"}


@dataclass
class Transcript:
    provider: str
    model: str
    text: str
    finish: str | None
    input_tokens: int
    output_tokens: int


@dataclass
class Reading:
    """Outcome of one page: `transcript` is None when nobody could read it; `attempts` lists every provider tried."""
    transcript: Transcript | None
    attempts: list[dict[str, Any]] = field(default_factory=list)


def page_jpeg(data: bytes, rotation_deg: int = 0, crop_box: dict[str, Any] | None = None) -> bytes:
    """The photo as the customer set it (rotation, crop), scaled down, as JPEG."""
    img = cv2.imdecode(np.frombuffer(data, np.uint8), cv2.IMREAD_COLOR)
    if img is None:
        raise AppError(422, "INVALID_IMAGE", "Không đọc được ảnh.")
    img = _apply_orientation(img, rotation_deg, crop_box)
    scale = MAX_SIDE_PX / max(img.shape[:2])
    if scale < 1:
        img = cv2.resize(img, None, fx=scale, fy=scale, interpolation=cv2.INTER_AREA)
    return cv2.imencode(".jpg", img, [cv2.IMWRITE_JPEG_QUALITY, 90])[1].tobytes()


class GeminiReader(_HttpProvider):
    name = "gemini"
    base_url = "https://generativelanguage.googleapis.com/v1beta"

    def read(self, jpeg: bytes) -> Transcript:
        body = {"contents": [{"role": "user", "parts": [
            {"inline_data": {"mime_type": "image/jpeg", "data": base64.b64encode(jpeg).decode()}}, {"text": PROMPT}]}],
            "generationConfig": {"temperature": 0, "maxOutputTokens": 4096}}
        data = self._post(f"{self.base_url}/models/{self.model}:generateContent",
                          {"x-goog-api-key": self.api_key, "content-type": "application/json"}, body)
        cands = data.get("candidates") or []
        if not cands:
            block = (data.get("promptFeedback") or {}).get("blockReason")
            raise ProviderError("BLOCKED" if block else "BAD_RESPONSE", 200, str(block or "no candidate")[:300])
        finish = cands[0].get("finishReason")
        parts = (cands[0].get("content") or {}).get("parts") or []
        text = "".join(p.get("text", "") for p in parts if not p.get("thought")).strip()
        if finish in REFUSED or not text:
            raise ProviderError("BLOCKED", 200, str(finish or "empty"))
        u = data.get("usageMetadata") or {}
        return Transcript(self.name, self.model, text, finish, int(u.get("promptTokenCount") or 0),
                          int(u.get("candidatesTokenCount") or 0) + int(u.get("thoughtsTokenCount") or 0))


class AnthropicReader(_HttpProvider):
    name = "anthropic"
    url = "https://api.anthropic.com/v1/messages"

    def read(self, jpeg: bytes) -> Transcript:
        body = {"model": self.model, "max_tokens": 4096, "temperature": 0, "messages": [{"role": "user", "content": [
            {"type": "image", "source": {"type": "base64", "media_type": "image/jpeg",
                                         "data": base64.b64encode(jpeg).decode()}},
            {"type": "text", "text": PROMPT}]}]}
        data = self._post(self.url, {"x-api-key": self.api_key, "anthropic-version": "2023-06-01",
                                     "content-type": "application/json"}, body)
        finish = data.get("stop_reason")
        text = "".join(b.get("text", "") for b in data.get("content") or [] if b.get("type") == "text").strip()
        if finish in REFUSED or not text:
            raise ProviderError("BLOCKED", 200, str(finish or "empty"))
        u = data.get("usage") or {}
        return Transcript(self.name, self.model, text, finish, int(u.get("input_tokens") or 0),
                          int(u.get("output_tokens") or 0))


def configured_readers() -> list[Any]:
    """Readers with a key, in HTR_PROVIDER_ORDER. Never exposes a key."""
    s = get_settings()
    build = {"gemini": (GeminiReader, s.gemini_api_key, s.gemini_model),
             "anthropic": (AnthropicReader, s.anthropic_api_key, s.anthropic_model)}
    out = []
    for name in [n.strip().lower() for n in s.htr_provider_order.split(",") if n.strip()]:
        cls, key, model = build.get(name, (None, None, None))
        if cls is not None and key and model:
            out.append(cls(key, model, timeout=s.htr_timeout_seconds))
    return out


def reader_names() -> list[str]:
    return [r.name for r in configured_readers()]


def read_page(jpeg: bytes, readers: list[Any]) -> Reading:
    """Try each reader in turn; any failure (network, quota, refusal, empty answer) moves on to the next."""
    attempts: list[dict[str, Any]] = []
    for r in readers:
        try:
            t = r.read(jpeg)
        except ProviderError as exc:
            attempts.append({"provider": r.name, "model": r.model, "ok": False, "reason": exc.reason,
                             "status": exc.status, "detail": exc.detail[:120]})
            continue
        except httpx.HTTPError as exc:                 # transport errors not wrapped by _post
            attempts.append({"provider": r.name, "model": r.model, "ok": False, "reason": "NETWORK",
                             "status": None, "detail": str(exc)[:120]})
            continue
        attempts.append({"provider": r.name, "model": r.model, "ok": True, "finish": t.finish})
        return Reading(t, attempts)
    return Reading(None, attempts)
