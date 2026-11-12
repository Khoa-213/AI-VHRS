"""Upgrade U6: measured paper + pen + ink profiles and the preview tier shown with every sketch image.

Preview tiers (docs/UPGRADE_AI_ROBOT_PLAN.md VII.4), worked out from facts, never chosen by hand:
  VISUAL            drawn with the pen's NOMINAL line width: an illustration of the plan, not of the real ink;
  CALIBRATED        drawn with the line width MEASURED for this exact paper + pen + ink (profile MEASURED / VERIFIED,
                    unchanged since the image was drawn);
  PRODUCTION_READY  CALIBRATED with a VERIFIED profile AND the order's signed production package (U1) locks this very
                    sketch: what the robot will write.
A profile RE-MEASURED after the image was drawn drops the image back to VISUAL (the picture no longer matches the numbers);
verifying it or editing its note does not. All times come from the database clock (sketch.created_at does too).
Robot-specific profiles exist in the data model; the preview uses the robot-independent one (robot_id NULL) because the
robot is only chosen at scheduling.
"""
from __future__ import annotations

from decimal import Decimal
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.errors import AppError
from app.models.account import Account
from app.models.catalog import MaterialProfile
from app.models.ops import ProductionSnapshot
from app.models.order import Order
from app.models.sketch import Sketch
from app.repositories.catalog import CatalogRepository
from app.services import audit

USABLE = ("MEASURED", "VERIFIED")
FIELDS = ("line_width_mm", "darkness", "bleed_mm", "v_max_mm_s", "method", "evidence_uri", "note")
MEASURES = ("line_width_mm", "darkness", "bleed_mm", "v_max_mm_s")
TIER_NOTES = {
    "VISUAL": "Ảnh minh hoạ: nét vẽ theo độ rộng danh định của bút, chưa đo trên giấy và mực thật.",
    "CALIBRATED": "Ảnh đã hiệu chuẩn: độ rộng nét lấy từ phép đo thật của đúng loại giấy, bút và mực này.",
    "PRODUCTION_READY": "Ảnh sát thành phẩm: vật tư đã hiệu chuẩn và được xác nhận, gói sản xuất đã khoá đúng phác thảo này.",
}


def profile_for(session: Session, paper_id: int | None, pen_id: int | None, ink_id: int | None,
                robot_id: int | None = None) -> MaterialProfile | None:
    if not (paper_id and pen_id and ink_id):
        return None
    return session.scalar(select(MaterialProfile).where(
        MaterialProfile.paper_type_id == paper_id, MaterialProfile.pen_type_id == pen_id,
        MaterialProfile.ink_color_id == ink_id,
        MaterialProfile.robot_id.is_(None) if robot_id is None else MaterialProfile.robot_id == robot_id))


def render_profile(session: Session, order: Order) -> MaterialProfile | None:
    """The profile whose measured width should draw this order's customer image, if any."""
    p = profile_for(session, order.paper_type_id, order.pen_type_id, order.ink_color_id)
    return p if p is not None and p.status in USABLE and p.line_width_mm else None


def preview_tier(session: Session, sketch: Sketch) -> str:
    if not sketch.render_profile_id:
        return "VISUAL"
    p = session.get(MaterialProfile, sketch.render_profile_id)
    if p is None or p.status not in USABLE or (p.measured_at and sketch.created_at and p.measured_at > sketch.created_at):
        return "VISUAL"
    if p.status == "VERIFIED":
        locked = session.scalar(select(ProductionSnapshot.id).where(
            ProductionSnapshot.order_id == sketch.order_id, ProductionSnapshot.sketch_id == sketch.id,
            ProductionSnapshot.revoked_at.is_(None)))
        if locked:
            return "PRODUCTION_READY"
    return "CALIBRATED"


def profile_block(p: MaterialProfile | None) -> dict[str, Any] | None:
    """Strings only: the block goes into the signed production package (U1)."""
    if p is None:
        return None

    def num(v: Decimal | None) -> str | None:
        return None if v is None else format(v.normalize(), "f")

    return {"id": p.id, "status": p.status, "line_width_mm": num(p.line_width_mm), "darkness": num(p.darkness),
            "bleed_mm": num(p.bleed_mm), "v_max_mm_s": num(p.v_max_mm_s),
            "measured_at": p.measured_at.isoformat() if p.measured_at else None}


class MaterialProfileService:
    def __init__(self, session: Session, manager: Account, ip: str | None = None):
        self.session, self.manager, self.ip = session, manager, ip
        self.catalog = CatalogRepository(session)

    def list(self, paper_id: int | None = None, pen_id: int | None = None, ink_id: int | None = None) -> list[MaterialProfile]:
        q = select(MaterialProfile)
        if paper_id:
            q = q.where(MaterialProfile.paper_type_id == paper_id)
        if pen_id:
            q = q.where(MaterialProfile.pen_type_id == pen_id)
        if ink_id:
            q = q.where(MaterialProfile.ink_color_id == ink_id)
        return list(self.session.scalars(q.order_by(MaterialProfile.id)))

    def _get(self, profile_id: int, *, lock: bool = False) -> MaterialProfile:
        q = select(MaterialProfile).where(MaterialProfile.id == profile_id)
        row = self.session.scalar(q.with_for_update() if lock else q)
        if row is None:
            raise AppError(404, "PROFILE_NOT_FOUND", "Không tìm thấy hồ sơ vật tư.")
        return row

    def _audit(self, action: str, row: MaterialProfile, old: dict | None, new: dict | None) -> None:
        audit.record(self.session, actor_id=self.manager.id, action=action, entity_type="material_profile",
                     entity_id=row.id, old=old, new=new, ip=self.ip)

    @staticmethod
    def _plain(row: MaterialProfile, fields=FIELDS + ("status",)) -> dict[str, Any]:
        return {f: (str(getattr(row, f)) if isinstance(getattr(row, f), Decimal) else getattr(row, f)) for f in fields}

    def create(self, data: dict[str, Any]) -> MaterialProfile:
        paper, pen, ink = (self.catalog.paper(data["paper_type_id"]), self.catalog.pen(data["pen_type_id"]),
                           self.catalog.ink(data["ink_color_id"]))
        if paper is None or pen is None or ink is None:
            raise AppError(404, "MATERIAL_NOT_FOUND", "Không tìm thấy giấy, bút hoặc mực.")
        if ink.pen_type_id != pen.id:
            raise AppError(422, "INK_NOT_FOR_PEN", "Mực này không thuộc loại bút đã chọn.")
        if not self.catalog.is_compatible(paper.id, pen.id):
            raise AppError(422, "PEN_INCOMPATIBLE", "Giấy và bút này không tương thích; không lập hồ sơ.")
        if profile_for(self.session, paper.id, pen.id, ink.id, data.get("robot_id")) is not None:
            raise AppError(409, "PROFILE_EXISTS", "Tổ hợp vật tư này đã có hồ sơ; hãy sửa hồ sơ đó.")
        row = MaterialProfile(paper_type_id=paper.id, pen_type_id=pen.id, ink_color_id=ink.id,
                              robot_id=data.get("robot_id"), status="UNCALIBRATED",
                              **{f: data.get(f) for f in FIELDS})
        if row.line_width_mm is not None:
            row.status, row.measured_by, row.measured_at = "MEASURED", self.manager.id, func.now()
        self.session.add(row)
        self.session.flush()
        self.session.refresh(row)
        self._audit("MATERIAL_PROFILE_CREATE", row, None, self._plain(row))
        return row

    def update(self, profile_id: int, changes: dict[str, Any]) -> MaterialProfile:
        row = self._get(profile_id, lock=True)
        old = self._plain(row)
        touched = {k: v for k, v in changes.items() if k in FIELDS}
        if not touched:
            raise AppError(422, "NO_CHANGES", "Không có thay đổi nào để lưu.")
        for k, v in touched.items():
            setattr(row, k, v)
        if any(k in MEASURES for k in touched):              # new numbers = a new measurement, verification is void
            if row.line_width_mm is None:
                raise AppError(422, "LINE_WIDTH_REQUIRED", "Hồ sơ đã đo phải có độ rộng nét.")
            row.status, row.measured_by, row.measured_at = "MEASURED", self.manager.id, func.now()
            row.verified_by = row.verified_at = None
        row.updated_at = func.now()
        self.session.flush()
        self.session.refresh(row)
        self._audit("MATERIAL_PROFILE_UPDATE", row, old, self._plain(row))
        return row

    def verify(self, profile_id: int, note: str | None) -> MaterialProfile:
        row = self._get(profile_id, lock=True)
        if row.status == "UNCALIBRATED":
            raise AppError(409, "PROFILE_NOT_MEASURED", "Hồ sơ chưa có số đo, không xác nhận được.")
        if row.status == "VERIFIED":
            return row
        row.status, row.verified_by, row.verified_at, row.updated_at = "VERIFIED", self.manager.id, func.now(), func.now()
        if note:
            row.note = note
        self.session.flush()
        self.session.refresh(row)
        self._audit("MATERIAL_PROFILE_VERIFY", row, {"status": "MEASURED"},
                    {"status": "VERIFIED", "same_person_as_measurer": row.verified_by == row.measured_by})
        return row
