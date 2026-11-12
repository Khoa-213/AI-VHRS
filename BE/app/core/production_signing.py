"""Signed production packages (upgrade phase U1, docs/UPGRADE_AI_ROBOT_PLAN.md section 3.4).

The production snapshot is a JSON document that pins everything the robot must reproduce: the approved sketch version and
the SHA-256 of its trajectory file, the paper / pen / ink VALUES (not only their ids), the approved quotation and the
confirmed deposit. It is serialised canonically (sorted keys, no spaces, UTF-8, no floats) and signed with Ed25519.

Why a signature and not an HMAC: the Robot Agent on the workstation only needs the PUBLIC key to check a package. With an
HMAC it would have to hold the secret, and whoever holds that secret can mint packages. The private key lives only in the
backend's environment (`PRODUCTION_SIGNING_KEY`), never in the repository or the frontend.

Key rotation: every signature carries a `key_id`. The current key signs; older public keys stay in the verification ring
(`PRODUCTION_VERIFY_KEYS`) until no open job uses them. A leaked key is removed from the ring, which makes every package
it signed fail verification (they must be re-issued).

This module has no database or settings import, so the Robot Agent imports it as is.
"""
from __future__ import annotations

import base64
import hashlib
import json
from decimal import Decimal
from typing import Any

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey, Ed25519PublicKey
from cryptography.hazmat.primitives.serialization import Encoding, PublicFormat

SCHEMA = "vhrs-production/1"


class SignatureError(ValueError):
    """`code` is a stable machine-readable reason."""

    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code


def _b64(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).decode().rstrip("=")


def _unb64(text: str) -> bytes:
    text = text.strip()
    return base64.urlsafe_b64decode(text + "=" * (-len(text) % 4))


def _plain(value: Any) -> Any:
    """Floats are refused: their text form is not stable across languages. Money and measures go in as strings."""
    if isinstance(value, float):
        raise TypeError("floats are not allowed in a signed payload; use a string")
    if isinstance(value, Decimal):
        return format(value.normalize(), "f") if value == value.to_integral() else format(value, "f")
    if isinstance(value, dict):
        return {str(k): _plain(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_plain(v) for v in value]
    return value


def canonical(payload: dict[str, Any]) -> str:
    return json.dumps(_plain(payload), sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def sha256_hex(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def generate_private_key() -> str:
    return _b64(Ed25519PrivateKey.generate().private_bytes_raw())


def _private(key_b64: str) -> Ed25519PrivateKey:
    try:
        raw = _unb64(key_b64)
        return Ed25519PrivateKey.from_private_bytes(raw)
    except (ValueError, TypeError) as exc:
        raise SignatureError("SIGNING_KEY_INVALID", "PRODUCTION_SIGNING_KEY is not a base64 Ed25519 private key") from exc


def public_key_of(private_b64: str) -> str:
    return _b64(_private(private_b64).public_key().public_bytes(Encoding.Raw, PublicFormat.Raw))


def sign(text: str, private_b64: str) -> str:
    return _b64(_private(private_b64).sign(text.encode("utf-8")))


def verify(text: str, signature_b64: str, key_id: str, public_keys: dict[str, str]) -> None:
    """Raise SignatureError unless `signature_b64` is a valid signature of `text` by the key `key_id` of the ring."""
    public = public_keys.get(key_id)
    if not public:
        raise SignatureError("SIGNING_KEY_UNKNOWN", f"Khoá ký '{key_id}' không có trong danh sách khoá xác minh.")
    try:
        Ed25519PublicKey.from_public_bytes(_unb64(public)).verify(_unb64(signature_b64), text.encode("utf-8"))
    except (InvalidSignature, ValueError, TypeError) as exc:
        raise SignatureError("SIGNATURE_INVALID", "Chữ ký của gói sản xuất không hợp lệ.") from exc


def verify_package(snapshot: dict[str, Any], public_keys: dict[str, str], *, trajectory_sha256: str | None = None,
                   job_order_id: int | None = None, job_sketch_id: int | None = None) -> dict[str, Any]:
    """Check a snapshot block as served to the agent: {payload, payload_sha256, signature, key_id}. Returns the payload.

    Order matters: the signature first (nothing in an unsigned text is trusted), then the stated hash, then what the
    payload says about the job and the trajectory file actually downloaded."""
    text = snapshot.get("payload")
    if not isinstance(text, str):
        raise SignatureError("SNAPSHOT_MALFORMED", "Gói sản xuất thiếu nội dung đã ký.")
    verify(text, str(snapshot.get("signature") or ""), str(snapshot.get("key_id") or ""), public_keys)
    if sha256_hex(text) != snapshot.get("payload_sha256"):
        raise SignatureError("SNAPSHOT_HASH_MISMATCH", "Hash nội dung gói sản xuất không khớp.")
    payload = json.loads(text)
    if payload.get("schema") != SCHEMA:
        raise SignatureError("SNAPSHOT_SCHEMA_UNSUPPORTED", f"Không hỗ trợ định dạng gói '{payload.get('schema')}'.")
    if job_order_id is not None and payload.get("order", {}).get("id") != job_order_id:
        raise SignatureError("SNAPSHOT_WRONG_JOB", "Gói sản xuất thuộc đơn khác.")
    if job_sketch_id is not None and payload.get("sketch", {}).get("id") != job_sketch_id:
        raise SignatureError("SNAPSHOT_WRONG_JOB", "Gói sản xuất thuộc phiên bản phác thảo khác.")
    if trajectory_sha256 is not None and payload.get("sketch", {}).get("trajectory_sha256") != trajectory_sha256:
        raise SignatureError("TRAJECTORY_MISMATCH", "File quỹ đạo không khớp phác thảo đã ký.")
    return payload


def parse_key_ring(raw: str | dict[str, str] | None) -> dict[str, str]:
    if not raw:
        return {}
    if isinstance(raw, dict):
        return {str(k): str(v) for k, v in raw.items()}
    data = json.loads(raw)
    if not isinstance(data, dict):
        raise ValueError("the key ring must be a JSON object {key_id: public_key}")
    return {str(k): str(v) for k, v in data.items()}
