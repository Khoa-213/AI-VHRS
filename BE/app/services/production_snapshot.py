"""Upgrade U1: issue, verify and revoke the signed production snapshot of an order (docs/UPGRADE_AI_ROBOT_PLAN.md 3.4).

When: the snapshot is issued when the deposit is confirmed by the gateway's signed webhook (best effort: a missing key or
an unreadable trajectory file must never make the payment webhook fail), and again, mandatorily, when a Manager schedules
the job (`ensure`). Re-scheduling reuses the active snapshot. Cancelling the order revokes it.

What it pins (by VALUE, so a later catalog edit cannot change a locked job): the final sketch version and the SHA-256 the
server computed for its trajectory file when the sketch was saved (the file itself is compared with this signed hash on
every package download), the paper / pen / ink values, the approved quotation and the confirmed deposit.

Verification (`check`) runs on every package download and before writing; a failure is recorded (job event, audit row,
incident) and committed BEFORE the request answers 409, so the evidence survives.
"""
from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core import production_signing as ps
from app.core.config import get_settings
from app.core.errors import AppError
from app.models.order import Order
from app.models.ops import PaymentStatus, PaymentType, ProductionSnapshot
from app.models.sketch import QuotationStatus, SketchApproval
from app.repositories.catalog import CatalogRepository
from app.repositories.ops import PaymentRepository
from app.repositories.workshop import QuotationRepository, SketchRepository
from app.services import audit, material_profiles
from app.services.stroke_ai import trajectory as tj

log = logging.getLogger("app.snapshot")


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _iso(value: datetime | None) -> str | None:
    return value.astimezone(timezone.utc).isoformat() if value else None


def _num(value: Any) -> Any:
    """Decimal -> fixed text; int / str pass through (floats never reach a signed payload)."""
    return None if value is None else ps._plain(value)


def materials_of(catalog: CatalogRepository, order: Order) -> dict[str, Any]:
    """The production-relevant values of the order's materials, as strings (a signed payload holds no floats)."""
    paper = catalog.paper(order.paper_type_id) if order.paper_type_id else None
    pen = catalog.pen(order.pen_type_id) if order.pen_type_id else None
    ink = catalog.ink(order.ink_color_id) if order.ink_color_id else None
    return {
        "paper": ({"id": paper.id, "code": paper.code, "name": paper.name, "gsm": paper.gsm, "surface": paper.surface,
                   "size": paper.size.value} if paper else None),
        "pen": ({"id": pen.id, "code": pen.code, "name": pen.name, "category": pen.category,
                 "stroke_width_mm": _num(pen.stroke_width_mm), "f_target_n": _num(pen.f_target_n),
                 "f_min_n": _num(pen.f_min_n), "f_max_n": _num(pen.f_max_n), "f_hard_n": _num(pen.f_hard_n),
                 "v_max_mm_s": _num(pen.v_max_mm_s)} if pen else None),
        "ink": ({"id": ink.id, "name": ink.name, "hex_code": ink.hex_code} if ink else None),
        # U6: the measured profile of this combination (None = not calibrated yet)
        "profile": material_profiles.profile_block(material_profiles.profile_for(
            catalog.s, order.paper_type_id, order.pen_type_id, order.ink_color_id)),
    }


def material_drift(locked: dict[str, Any], live: dict[str, Any]) -> list[str]:
    """Human-readable differences between the values locked in the snapshot and the catalog today."""
    out = []
    # U6: packages locked before migration 0019 carry no "profile" key; they are compared on paper / pen / ink only
    for kind in ("paper", "pen", "ink") + (("profile",) if "profile" in locked else ()):
        a, b = locked.get(kind) or {}, live.get(kind) or {}
        for key in sorted(set(a) | set(b)):
            if a.get(key) != b.get(key):
                out.append(f"{kind}.{key}: đã khoá {a.get(key)!r}, danh mục hiện tại {b.get(key)!r}")
    return out


class SnapshotService:
    def __init__(self, session: Session):
        self.session = session
        self.cfg = get_settings()
        self.catalog = CatalogRepository(session)
        self.sketches = SketchRepository(session)

    # ------------------------------------------------------------------ reads
    def active(self, order_id: int) -> ProductionSnapshot | None:
        return self.session.scalar(select(ProductionSnapshot).where(
            ProductionSnapshot.order_id == order_id, ProductionSnapshot.revoked_at.is_(None)))

    def get(self, snapshot_id: int) -> ProductionSnapshot | None:
        return self.session.get(ProductionSnapshot, snapshot_id)

    @staticmethod
    def block(snap: ProductionSnapshot) -> dict[str, Any]:
        """What the technician / agent receives: enough to verify the signature offline."""
        return {"snapshot_id": snap.id, "package_id": str(snap.package_id), "schema": snap.schema_version,
                "payload": snap.payload, "payload_sha256": snap.payload_sha256, "signature": snap.signature,
                "key_id": snap.key_id}

    # ------------------------------------------------------------------ issue
    def issue(self, order: Order, *, actor_id: int | None) -> ProductionSnapshot:
        """Idempotent: an active snapshot of the same final sketch is returned as is; one of an older sketch is revoked."""
        key = self.cfg.production_signing_key
        if not key:
            raise AppError(503, "PRODUCTION_SIGNING_NOT_CONFIGURED",
                           "Máy chủ chưa có khoá ký gói sản xuất (PRODUCTION_SIGNING_KEY). Liên hệ quản trị.")
        sketch = self.sketches.final(order.id)
        if sketch is None or not sketch.content_hash:
            raise AppError(409, "SKETCH_REQUIRED", "Đơn chưa có phác thảo chốt để khoá.")
        current = self.active(order.id)
        if current is not None:
            if current.sketch_id == sketch.id:
                return current
            self.revoke(current, "Phác thảo chốt đã đổi sang phiên bản khác", actor_id=actor_id)
        quotation = QuotationRepository(self.session).latest(order.id, (QuotationStatus.APPROVED,))
        if quotation is None or quotation.sketch_id != sketch.id:
            raise AppError(409, "APPROVAL_REQUIRED", "Khách chưa duyệt báo giá của đúng phiên bản phác thảo này.")
        deposit = PaymentRepository(self.session).success(order.id, PaymentType.DEPOSIT)
        if deposit is None or deposit.status != PaymentStatus.SUCCESS:
            raise AppError(409, "DEPOSIT_REQUIRED", "Chưa có khoản cọc được cổng thanh toán xác nhận.")
        approval = self.session.scalar(select(SketchApproval).where(SketchApproval.quotation_id == quotation.id))
        package_id = str(uuid.uuid4())
        payload = {
            "schema": ps.SCHEMA, "package_id": package_id, "issued_at": _iso(_now()),
            "order": {"id": order.id, "code": order.code, "type": order.order_type.value, "quantity": order.quantity},
            "sketch": {"id": sketch.id, "version": sketch.version, "trajectory_sha256": sketch.content_hash,
                       "trajectory_uri": sketch.trajectory_uri, "trajectory_format": tj.FORMAT,
                       "estimated_writing_sec": sketch.estimated_writing_sec},
            "materials": materials_of(self.catalog, order),
            "quotation": {"id": quotation.id, "version": quotation.version, "final_total": _num(quotation.final_total),
                          "approved_at": _iso(quotation.customer_responded_at)},
            # U2: the customer's approval record (None for quotations approved before migration 0017)
            "approval": {"id": approval.id, "sketch_version": approval.sketch_version,
                         "sketch_content_hash": approval.sketch_content_hash, "image_paths": list(approval.image_paths),
                         "ip": approval.ip, "approved_at": _iso(approval.approved_at)} if approval else None,
            "deposit": {"payment_id": deposit.id, "amount": _num(deposit.amount), "gateway": deposit.gateway.value,
                        "paid_at": _iso(deposit.paid_at)},
            "watermark": None,                                # physical watermark: upgrade U8
        }
        text = ps.canonical(payload)
        snap = ProductionSnapshot(
            package_id=package_id, order_id=order.id, sketch_id=sketch.id, quotation_id=quotation.id, payment_id=deposit.id,
            schema_version=ps.SCHEMA, payload=text, payload_sha256=ps.sha256_hex(text),
            signature=ps.sign(text, key), key_id=self.cfg.production_signing_key_id, created_by=actor_id)
        self.session.add(snap)
        self.session.flush()
        audit.record(self.session, actor_id=actor_id, action="PRODUCTION_SNAPSHOT_ISSUE", entity_type="production_snapshot",
                     entity_id=snap.id, new={"order_id": order.id, "sketch_id": sketch.id, "package_id": package_id,
                                             "key_id": snap.key_id, "payload_sha256": snap.payload_sha256})
        return snap

    def try_issue(self, order: Order) -> ProductionSnapshot | None:
        """For the payment webhook: never raises. Scheduling issues it again (mandatory) if this one could not."""
        try:
            with self.session.begin_nested():
                return self.issue(order, actor_id=None)
        except Exception as exc:                                   # noqa: BLE001 - the webhook must stay PROCESSED
            log.warning("production snapshot not issued at deposit for order %s: %s", order.id, getattr(exc, "code", exc))
            return None

    # ------------------------------------------------------------------ revoke
    def revoke(self, snap: ProductionSnapshot, reason: str, *, actor_id: int | None) -> None:
        if snap.revoked_at is not None:
            return
        snap.revoked_at, snap.revoked_reason = _now(), reason
        self.session.flush()
        audit.record(self.session, actor_id=actor_id, action="PRODUCTION_SNAPSHOT_REVOKE", entity_type="production_snapshot",
                     entity_id=snap.id, new={"order_id": snap.order_id, "reason": reason})

    def revoke_for_order(self, order_id: int, reason: str, *, actor_id: int | None) -> None:
        snap = self.active(order_id)
        if snap is not None:
            self.revoke(snap, reason, actor_id=actor_id)

    # ------------------------------------------------------------------ verify
    def check(self, snap: ProductionSnapshot | None, *, order_id: int, sketch_id: int,
              trajectory_sha256: str | None) -> dict[str, Any]:
        """Raise ps.SignatureError when anything does not match; return the verified payload."""
        if snap is None:
            raise ps.SignatureError("SNAPSHOT_MISSING", "Job trỏ tới gói sản xuất không còn tồn tại.")
        if snap.revoked_at is not None:
            raise ps.SignatureError("SNAPSHOT_REVOKED", f"Gói sản xuất đã bị thu hồi: {snap.revoked_reason}")
        if snap.order_id != order_id or snap.sketch_id != sketch_id:
            raise ps.SignatureError("SNAPSHOT_WRONG_JOB", "Gói sản xuất không thuộc job này.")
        return ps.verify_package(self.block(snap), self.cfg.production_key_ring, trajectory_sha256=trajectory_sha256,
                                 job_order_id=order_id, job_sketch_id=sketch_id)
