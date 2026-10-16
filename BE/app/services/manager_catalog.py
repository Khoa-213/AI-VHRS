"""Manager-side catalog and pricing administration: FR-30 (versioned prices), FR-39 (robots), FR-41 (materials,
compatibility, stock), FR-42 (templates, handwriting styles).

Every change is audited with its old and new values. Codes are immutable once created. Rows are never deleted
(orders and quotations reference them); they are switched off with is_active instead.
"""
from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.errors import AppError
from app.domain import pricing_config_rules
from app.models.account import Account
from app.models.catalog import InkColor, PaperPenCompat, PaperType, PenType, PricingConfig, Template
from app.models.ops import ACTIVE_JOB_STATUSES, Robot, RobotStatus
from app.models.order import HandwritingStyle, StyleStatus
from app.repositories.catalog import CatalogRepository
from app.repositories.ops import JobRepository, RobotRepository
from app.services import audit
from app.services.stroke_ai.text_to_stroke import FONT_PREFIX, SUPPORTED_FONTS

PRICING_FIELDS = ("u_ot1", "u_ot2", "u_ot3", "w_min", "s_ot1", "s_ot2", "s_ot3", "k_simple", "k_medium", "k_complex",
                  "discount_tiers", "p_min_pct", "adjust_threshold_pct", "canvas_mm_per_char")


def _plain(v: Any) -> Any:
    """JSON-safe form of a value for the audit log."""
    return str(v) if isinstance(v, Decimal) else (v.value if hasattr(v, "value") else v)


def _snapshot(row: Any, fields: tuple[str, ...] | list[str]) -> dict[str, Any]:
    return {f: _plain(getattr(row, f)) for f in fields}


class ManagerCatalogService:
    def __init__(self, session: Session, manager: Account, ip: str | None = None):
        self.session, self.manager, self.ip = session, manager, ip
        self.catalog = CatalogRepository(session)
        self.robots = RobotRepository(session)
        self.jobs = JobRepository(session)

    def _audit(self, action: str, entity: str, entity_id: int, old: dict | None = None, new: dict | None = None,
               reason: str | None = None) -> None:
        audit.record(self.session, actor_id=self.manager.id, action=action, entity_type=entity, entity_id=entity_id,
                     old=old, new=new, reason=reason, ip=self.ip)

    def _apply(self, row: Any, changes: dict[str, Any], fields: tuple[str, ...]) -> tuple[dict, dict]:
        old, new = {}, {}
        for f in fields:
            if changes.get(f) is not None and changes[f] != getattr(row, f):      # null = field not provided
                old[f], new[f] = _snapshot(row, [f])[f], _plain(changes[f])
                setattr(row, f, changes[f])
        if not new:
            raise AppError(422, "NO_CHANGES", "Không có thay đổi nào để lưu.")
        self.session.flush()
        self.session.refresh(row)
        return old, new

    def _new_code(self, model: Any, code: str) -> None:
        if self.catalog.code_taken(model, code):
            raise AppError(409, "CODE_TAKEN", f"Mã '{code}' đã tồn tại.")

    # ------------------------------------------------------------------ papers
    def create_paper(self, data: dict[str, Any]) -> PaperType:
        self._new_code(PaperType, data["code"])
        row = self.catalog.add(PaperType(**data))
        self._audit("CATALOG_PAPER_CREATE", "paper_type", row.id, new=_snapshot(row, list(data)))
        return row

    def update_paper(self, paper_id: int, changes: dict[str, Any]) -> PaperType:
        row = self._locked(PaperType, paper_id, "Không tìm thấy loại giấy.")
        old, new = self._apply(row, changes, ("name", "gsm", "surface", "size", "unit_price", "is_active"))
        self._audit("CATALOG_PAPER_UPDATE", "paper_type", row.id, old, new)
        return row

    # ------------------------------------------------------------------ pens / inks
    def create_pen(self, data: dict[str, Any]) -> PenType:
        self._new_code(PenType, data["code"])
        row = self.catalog.add(PenType(**data))
        self._audit("CATALOG_PEN_CREATE", "pen_type", row.id, new=_snapshot(row, list(data)))
        return row

    def update_pen(self, pen_id: int, changes: dict[str, Any]) -> PenType:
        row = self._locked(PenType, pen_id, "Không tìm thấy loại bút.")
        merged = {f: changes[f] if changes.get(f) is not None else getattr(row, f)
                  for f in ("f_min_n", "f_target_n", "f_max_n", "f_hard_n")}
        if not (0 < merged["f_min_n"] < merged["f_target_n"] < merged["f_max_n"] < merged["f_hard_n"]):
            raise AppError(422, "INVALID_FORCE_PROFILE", "Cần 0 < F_min < F_target < F_max < F_hard.")
        old, new = self._apply(row, changes, ("name", "category", "stroke_width_mm", "f_target_n", "f_min_n", "f_max_n",
                                              "f_hard_n", "v_max_mm_s", "surcharge", "is_active"))
        self._audit("CATALOG_PEN_UPDATE", "pen_type", row.id, old, new)
        return row

    def create_ink(self, pen_id: int, data: dict[str, Any]) -> InkColor:
        if self.catalog.pen(pen_id) is None:
            raise AppError(404, "PEN_NOT_FOUND", "Không tìm thấy loại bút.")
        if any(i.name.lower() == data["name"].lower() for i in self.catalog.all_inks(pen_id)):
            raise AppError(409, "NAME_TAKEN", "Bút này đã có màu mực cùng tên.")
        row = self.catalog.add(InkColor(pen_type_id=pen_id, **data))
        self._audit("CATALOG_INK_CREATE", "ink_color", row.id, new=_snapshot(row, ["pen_type_id", *data]))
        return row

    def update_ink(self, ink_id: int, changes: dict[str, Any]) -> InkColor:
        row = self._locked(InkColor, ink_id, "Không tìm thấy màu mực.")
        old, new = self._apply(row, changes, ("name", "hex_code", "unit_price", "is_active"))
        self._audit("CATALOG_INK_UPDATE", "ink_color", row.id, old, new)
        return row

    # ------------------------------------------------------------------ stock (FR-41)
    def adjust_stock(self, kind: str, row_id: int, mode: str, quantity: int, reason: str) -> Any:
        model = {"paper": PaperType, "pen": PenType, "ink": InkColor}[kind]
        row = self._locked(model, row_id, "Không tìm thấy vật tư.")
        before = row.stock_qty
        after = quantity if mode == "SET" else before + quantity
        if after < 0:
            raise AppError(422, "STOCK_NEGATIVE", "Tồn kho không được âm.", {"current": before})
        row.stock_qty = after
        self.session.flush()
        self.session.refresh(row)
        self._audit("STOCK_ADJUST", {"paper": "paper_type", "pen": "pen_type", "ink": "ink_color"}[kind], row.id,
                    {"stock_qty": before}, {"stock_qty": after}, reason=reason)
        return row

    # ------------------------------------------------------------------ compatibility (BR-05, BR-06)
    def set_compat(self, paper_id: int, pen_id: int, compatible: bool, note: str | None) -> PaperPenCompat:
        if self.catalog.paper(paper_id) is None or self.catalog.pen(pen_id) is None:
            raise AppError(404, "NOT_FOUND", "Không tìm thấy loại giấy hoặc loại bút.")
        row = self.catalog.compat(paper_id, pen_id)
        old = None if row is None else {"is_compatible": row.is_compatible, "note": row.note}
        if row is None:
            row = self.catalog.add(PaperPenCompat(paper_type_id=paper_id, pen_type_id=pen_id, is_compatible=compatible,
                                                  note=note, updated_by=self.manager.id))
        else:
            row.is_compatible, row.note, row.updated_by = compatible, note, self.manager.id
            self.session.flush()
        self._audit("CATALOG_COMPAT_SET", "paper_pen_compat", paper_id, old,
                    {"pen_type_id": pen_id, "is_compatible": compatible, "note": note})
        return row

    # ------------------------------------------------------------------ templates (FR-42)
    @staticmethod
    def _check_font(font_uri: str) -> None:
        if not font_uri.startswith(FONT_PREFIX) or font_uri[len(FONT_PREFIX):] not in SUPPORTED_FONTS:
            raise AppError(422, "UNSUPPORTED_FONT", "font_uri phải có dạng 'hershey:<tên>' với font được hỗ trợ.",
                           {"supported": sorted(SUPPORTED_FONTS)})

    def create_template(self, data: dict[str, Any]) -> Template:
        self._new_code(Template, data["code"])
        self._check_font(data["font_uri"])
        row = self.catalog.add(Template(created_by=self.manager.id, **data))
        self._audit("TEMPLATE_CREATE", "template", row.id, new=_snapshot(row, ["code", "name", "kind", "font_uri",
                                                                              "is_active"]))
        return row

    def update_template(self, template_id: int, changes: dict[str, Any]) -> Template:
        row = self._locked(Template, template_id, "Không tìm thấy mẫu chữ.")
        if changes.get("font_uri") is not None:
            self._check_font(changes["font_uri"])
        old, new = self._apply(row, changes, ("name", "kind", "font_uri", "is_active"))
        self._audit("TEMPLATE_UPDATE", "template", row.id, old, new)
        return row

    # ------------------------------------------------------------------ handwriting styles (FR-42)
    def styles(self, status: StyleStatus | None) -> list[HandwritingStyle]:
        stmt = select(HandwritingStyle).order_by(HandwritingStyle.created_at.desc(), HandwritingStyle.id.desc())
        if status is not None:
            stmt = stmt.where(HandwritingStyle.status == status)
        return list(self.session.scalars(stmt))

    def _style(self, style_id: int) -> HandwritingStyle:
        row = self.catalog.lock(HandwritingStyle, style_id)
        if row is None:
            raise AppError(404, "STYLE_NOT_FOUND", "Không tìm thấy bộ nét.")
        if row.status != StyleStatus.PENDING_REVIEW:
            raise AppError(409, "STYLE_NOT_PENDING", "Bộ nét không ở trạng thái chờ duyệt.")
        return row

    def approve_style(self, style_id: int) -> HandwritingStyle:
        row = self._style(style_id)
        if not row.right_to_use_confirmed:                           # FR-07 / BR-23
            raise AppError(409, "RIGHT_TO_USE_NOT_CONFIRMED", "Khách chưa xác nhận quyền sử dụng nét chữ này.")
        row.status, row.approved_by, row.approved_at = StyleStatus.APPROVED, self.manager.id, datetime.now(timezone.utc)
        self.session.flush()
        self._audit("STYLE_APPROVE", "handwriting_style", row.id, {"status": "PENDING_REVIEW"}, {"status": "APPROVED"})
        return row

    def reject_style(self, style_id: int, reason: str) -> HandwritingStyle:
        row = self._style(style_id)
        row.status, row.approved_by, row.approved_at = StyleStatus.REJECTED, self.manager.id, datetime.now(timezone.utc)
        self.session.flush()
        self._audit("STYLE_REJECT", "handwriting_style", row.id, {"status": "PENDING_REVIEW"}, {"status": "REJECTED"},
                    reason=reason)
        return row

    # ------------------------------------------------------------------ robots (FR-39)
    def create_robot(self, data: dict[str, Any]) -> Robot:
        if self.robots.by_code(data["code"]) is not None:
            raise AppError(409, "CODE_TAKEN", f"Mã robot '{data['code']}' đã tồn tại.")
        if data.get("status") == RobotStatus.BUSY:
            raise AppError(422, "STATUS_NOT_SETTABLE", "BUSY do hệ thống đặt khi robot có job đang chạy.")
        row = self.robots.add(Robot(**data))
        self._audit("ROBOT_CREATE", "robot", row.id, new=_snapshot(row, ["code", "robot_type", "station", "status",
                                                                        "is_simulated"]))
        return row

    def update_robot(self, robot_id: int, changes: dict[str, Any]) -> tuple[Robot, list[int]]:
        row = self.robots.get(robot_id, lock=True)
        if row is None:
            raise AppError(404, "ROBOT_NOT_FOUND", "Không tìm thấy robot.")
        if changes.get("status") == RobotStatus.BUSY:
            raise AppError(422, "STATUS_NOT_SETTABLE", "BUSY do hệ thống đặt khi robot có job đang chạy.")
        old, new = self._apply(row, changes, ("robot_type", "station", "status", "is_simulated",
                                              "supported_pen_categories", "note"))
        self._audit("ROBOT_UPDATE", "robot", row.id, old, new)
        affected: list[int] = []
        if row.status in (RobotStatus.MAINTENANCE, RobotStatus.BROKEN):
            # Jobs already planned on this robot must be moved by the Manager (reschedule); list them.
            affected = [j.id for j in self.jobs.future_for_robot(row.id, datetime.now(timezone.utc))
                        if j.status in ACTIVE_JOB_STATUSES]
        return row, affected

    # ------------------------------------------------------------------ pricing versions (FR-30)
    def pricing_current(self) -> PricingConfig:
        cfg = self.catalog.active_pricing()
        if cfg is None:
            raise AppError(404, "PRICING_NOT_CONFIGURED", "Chưa có bảng giá đang áp dụng.")
        return cfg

    def pricing_versions(self) -> list[PricingConfig]:
        return self.catalog.pricing_versions()

    def save_pricing(self, changes: dict[str, Any], note: str | None) -> PricingConfig:
        """Each save creates a NEW version and makes it the active one; old versions and the quotations that
        used them stay untouched (a quotation keeps its own price snapshot, BR-08)."""
        base = self.catalog.lock_active_pricing()
        values = {f: (changes[f] if f in changes else (getattr(base, f) if base else None)) for f in PRICING_FIELDS}
        missing = [f for f, v in values.items() if v is None]
        if missing:
            raise AppError(422, "PRICING_INCOMPLETE", "Chưa có bảng giá hiện hành; cần nhập đủ mọi tham số.",
                           {"missing": missing})
        if base is not None and all(self._same(values[f], getattr(base, f)) for f in PRICING_FIELDS):
            raise AppError(422, "NO_CHANGES", "Không có thay đổi nào so với bảng giá hiện hành.")
        problems = pricing_config_rules.validate(values)
        if problems:
            raise AppError(422, "INVALID_PRICING", "Tham số bảng giá không hợp lệ.", problems)
        self.catalog.deactivate_pricing()
        row = self.catalog.add(PricingConfig(version=self.catalog.next_pricing_version(), is_active=True,
                                             note=note, created_by=self.manager.id, **values))
        diff_old = {} if base is None else {f: _snapshot(base, [f])[f] for f in PRICING_FIELDS
                                            if not self._same(values[f], getattr(base, f))}
        diff_new = {f: _snapshot(row, [f])[f] for f in diff_old} if base else _snapshot(row, list(PRICING_FIELDS))
        self._audit("PRICING_CONFIG_SAVE", "pricing_config", row.id, diff_old or None,
                    {"version": row.version, **diff_new}, reason=note)
        return row

    @staticmethod
    def _same(a: Any, b: Any) -> bool:
        if isinstance(b, list):
            return a == b
        return Decimal(str(a)) == Decimal(str(b))

    # ------------------------------------------------------------------ helpers
    def _locked(self, model: Any, pk: int, message: str) -> Any:
        row = self.catalog.lock(model, pk)
        if row is None:
            raise AppError(404, "NOT_FOUND", message)
        return row

