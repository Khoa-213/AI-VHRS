"""Sketches: UC-25 (FR-14, FR-34, FR-35, FR-38). Staff generate a sketch with the AI pipeline or upload an
edited trajectory; every save is a new version. Exactly one version is `final` (the one the customer sees
and the job is built from). Files live in object storage; the DB keeps paths, metrics and the SHA-256."""
from __future__ import annotations  # methods named `list` would otherwise shadow the builtin in later annotations

import json
from typing import Any

from sqlalchemy.orm import Session

from app.core.errors import AppError
from app.integrations.storage import ObjectStorage
from app.models.account import Account
from app.models.order import ComplexityLevel, Order, OrderInputKind, OrderStatus, OrderType
from app.models.sketch import Sketch
from app.repositories.catalog import CatalogRepository
from app.repositories.orders import OrderRepository
from app.repositories.workshop import SketchRepository
from app.services import audit
from app.services.stroke_ai import engine, trajectory as tj
from app.services.workshop_access import WorkshopAccess

DEFAULT_V_MAX = 30.0   # mm/s, used when the order has no pen yet ("để xưởng đề xuất")


class SketchService:
    def __init__(self, session: Session, actor: Account, storage: ObjectStorage | None, ip: str | None = None):
        self.session, self.actor, self.storage, self.ip = session, actor, storage, ip
        self.access = WorkshopAccess(session, actor)
        self.sketches = SketchRepository(session)
        self.orders = OrderRepository(session)
        self.catalog = CatalogRepository(session)

    # ---- helpers ----
    def _storage(self) -> ObjectStorage:
        if self.storage is None:
            raise AppError(503, "STORAGE_NOT_CONFIGURED", "Chưa cấu hình dịch vụ lưu trữ file.")
        return self.storage

    def _editable_order(self, order_id: int) -> Order:
        order = self.access.order(order_id, write=True, lock=True)
        if order.order_status != OrderStatus.ACCEPTED:
            raise AppError(409, "ORDER_NOT_ACCEPTED", "Chỉ tạo/sửa phác thảo khi đơn đang ở trạng thái đã tiếp nhận.")
        return order

    def _pen(self, order: Order) -> tuple[float, str | None]:
        pen = self.catalog.pen(order.pen_type_id) if order.pen_type_id else None
        return (float(pen.v_max_mm_s) if pen else DEFAULT_V_MAX), (pen.category if pen else None)

    def _paper_size(self, order: Order, override: str | None) -> str:
        if override:
            return override
        paper = self.catalog.paper(order.paper_type_id) if order.paper_type_id else None
        return paper.size.value if paper else "A4"

    def _persist(self, order: Order, pages: list[tj.Page], eng: dict[str, Any], metrics: tj.Metrics,
                 similarity: float | None, complexity: str | None, note: str | None) -> Sketch:
        store = self._storage()
        version = self.sketches.next_version(order.id)
        base = f"orders/{order.id}/sketches/v{version}"
        for i, page in enumerate(pages, start=1):
            page.preview_path = f"{base}/preview_p{i}.png"
            store.write(page.preview_path, tj.render_preview(page), "image/png")
        raw = tj.dumps(tj.to_dict(pages, eng))
        path = f"{base}/trajectory.json"
        store.write(path, raw, "application/json")
        row = self.sketches.add(Sketch(
            order_id=order.id, version=version, created_by=self.actor.id, trajectory_uri=path,
            preview_url=pages[0].preview_path, similarity_score=similarity,
            suggested_complexity=ComplexityLevel(complexity) if complexity else None,
            estimated_writing_sec=metrics.estimated_writing_sec, total_stroke_mm=metrics.total_stroke_mm,
            pen_lift_count=metrics.pen_lift_count, approach_note=(note or None), content_hash=tj.content_hash(raw)))
        audit.record(self.session, actor_id=self.actor.id, action="SKETCH_CREATE", entity_type="sketch",
                     entity_id=row.id, new={"order_id": order.id, "version": version, "engine": eng.get("name")},
                     ip=self.ip)
        return row

    # ---- generate (AI) ----
    def generate(self, order_id: int, *, paper_size: str | None, approach_note: str | None,
                 seed: int | None) -> tuple[Sketch, list[str]]:
        order = self._editable_order(order_id)
        store = self._storage()
        v_max, category = self._pen(order)
        size = self._paper_size(order, paper_size)
        inputs = self.orders.inputs(order.id)

        if order.order_type == OrderType.OT2_LEARNED_STYLE:
            raise AppError(422, "AI_TYPE_UNSUPPORTED",
                           "Loại Sáng tạo theo nét chữ đã học chưa hỗ trợ sinh phác thảo tự động (R&D, LI-10). "
                           "Hãy tải phác thảo thủ công hoặc từ chối đơn.")
        if order.order_type == OrderType.OT1_COPY_RESTORE:
            images = [r for r in inputs if r.kind == OrderInputKind.ORIGINAL_IMAGE]
            if any(r.mime_type == "application/pdf" for r in images):
                raise AppError(422, "PDF_NOT_SUPPORTED_AI",
                               "Chưa phục dựng tự động từ file PDF; hãy yêu cầu khách tải ảnh jpg/png.")
            sources = []
            for r in images:
                if r.quality_result is None:
                    continue                                    # upload never confirmed
                data = store.read(r.file_url) if r.file_url else None
                if data is None:
                    raise AppError(409, "FILE_MISSING", "Không đọc được ảnh gốc từ kho lưu trữ.")
                sources.append(engine.ImageSource(data, r.rotation_deg or 0, r.crop_box))
            gen = engine.generate_ot1(sources, paper_size=size, v_max_mm_s=v_max, pen_category=category,
                                      chars=order.char_count or 0)
        else:
            text_rows = [r for r in inputs if r.kind == OrderInputKind.TEXT_CONTENT]
            canvas_rows = [r for r in inputs if r.kind == OrderInputKind.CANVAS]
            text = "\n".join(r.text_content or "" for r in text_rows)
            first = text_rows[0] if text_rows else None
            template = self.catalog.template(first.template_id) if first and first.template_id else None
            gen = engine.generate_ot3(
                text, canvas_rows[0].canvas_data if canvas_rows else None,
                font_uri=template.font_uri if template else None,
                font_size_mm=float(first.font_size_mm) if first and first.font_size_mm else None,
                alignment=first.alignment if first else None, paper_size=size,
                seed=seed if seed is not None else order.id, v_max_mm_s=v_max, pen_category=category,
                chars=order.char_count or 0)
        row = self._persist(order, gen.pages, gen.engine, gen.metrics, gen.similarity, gen.complexity, approach_note)
        return row, gen.warnings

    # ---- manual / edited trajectory ----
    def create_manual(self, order_id: int, trajectory: dict[str, Any], approach_note: str | None,
                      complexity: str | None) -> Sketch:
        order = self._editable_order(order_id)
        pages = tj.parse(trajectory)
        v_max, _ = self._pen(order)
        metrics = tj.compute_metrics(pages, v_max)
        return self._persist(order, pages, {"name": "manual-edit", "version": engine.ENGINE_VERSION}, metrics, None,
                             complexity, approach_note)

    # ---- read / update ----
    def _get(self, order: Order, version: int) -> Sketch:
        row = self.sketches.get(order.id, version)
        if row is None:
            raise AppError(404, "SKETCH_NOT_FOUND", "Không tìm thấy phiên bản phác thảo.")
        return row

    def list(self, order_id: int) -> list[Sketch]:
        return self.sketches.list(self.access.order(order_id).id)

    def preview_urls(self, row: Sketch) -> list[str]:
        """Signed links of every page preview (page paths are recorded inside the trajectory file)."""
        if self.storage is None:
            return []
        raw = self.storage.read(row.trajectory_uri)
        if raw is None:
            return []
        paths = [p.get("preview_path") for p in json.loads(raw).get("pages", []) if p.get("preview_path")]
        return [self.storage.create_download_url(p, 600) for p in paths]

    def detail(self, order_id: int, version: int) -> tuple[Sketch, dict[str, Any], list[str]]:
        order = self.access.order(order_id)
        row = self._get(order, version)
        raw = self._storage().read(row.trajectory_uri)
        if raw is None:
            raise AppError(409, "FILE_MISSING", "Không đọc được file quỹ đạo từ kho lưu trữ.")
        data = json.loads(raw)
        return row, data, [self._storage().create_download_url(p["preview_path"], 600)
                           for p in data.get("pages", []) if p.get("preview_path")]

    def patch(self, order_id: int, version: int, changes: dict[str, Any]) -> Sketch:
        order = self._editable_order(order_id)
        row = self._get(order, version)
        if "approach_note" in changes:
            row.approach_note = changes["approach_note"] or None
        if changes.get("suggested_complexity") is not None:
            row.suggested_complexity = ComplexityLevel(changes["suggested_complexity"])
        self.session.flush()
        return row

    def finalize(self, order_id: int, version: int) -> Sketch:
        order = self._editable_order(order_id)
        row = self._get(order, version)
        if not row.is_final:
            self.sketches.clear_final(order.id)             # unique index allows only one final per order
            row.is_final = True
            self.session.flush()
            audit.record(self.session, actor_id=self.actor.id, action="SKETCH_FINALIZE", entity_type="sketch",
                         entity_id=row.id, new={"order_id": order.id, "version": version}, ip=self.ip)
        return row
