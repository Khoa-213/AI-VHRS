"""Sketches: UC-25 (FR-14, FR-34, FR-35, FR-38). Staff generate a sketch with the AI pipeline or upload an
edited trajectory; every save is a new version. Exactly one version is `final` (the one the customer sees
and the job is built from). Files live in object storage; the DB keeps paths, metrics and the SHA-256."""
from __future__ import annotations  # methods named `list` would otherwise shadow the builtin in later annotations

import copy
import json
from typing import Any

from sqlalchemy import select

from sqlalchemy.orm import Session

from app.core.errors import AppError
from app.integrations.storage import ObjectStorage
from app.models.account import Account
from app.models.order import ComplexityLevel, Order, OrderInputKind, OrderStatus, OrderType
from app.models.sketch import Sketch, SketchRegion
from app.repositories.catalog import CatalogRepository
from app.repositories.orders import OrderRepository
from app.repositories.workshop import SketchRepository
from app.services import audit, material_profiles
from app.services.stroke_ai import engine, regions as rg, render_image, trajectory as tj, watermark
from app.services.workshop_access import WorkshopAccess

DEFAULT_V_MAX = 30.0   # mm/s, used when the order has no pen yet ("để xưởng đề xuất")


def _assisted(order: Order) -> bool:
    return order.restoration_mode == "ASSISTED"


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
                 similarity: float | None, complexity: str | None, note: str | None,
                 regions: list[rg.RegionDraft] | None = None) -> Sketch:
        store = self._storage()
        version = self.sketches.next_version(order.id)
        base = f"orders/{order.id}/sketches/v{version}"
        paper = self.catalog.paper(order.paper_type_id) if order.paper_type_id else None
        ink = self.catalog.ink(order.ink_color_id) if order.ink_color_id else None
        pen = self.catalog.pen(order.pen_type_id) if order.pen_type_id else None
        profile = material_profiles.render_profile(self.session, order)          # U6: measured width when known
        width = profile.line_width_mm if profile else (pen.stroke_width_mm if pen else None)
        image_paths: list[str] = []
        for i, page in enumerate(pages, start=1):
            page.preview_path = f"{base}/preview_p{i}.png"
            store.write(page.preview_path,                         # U2: visible AI mark, never in the strokes
                        watermark.apply_bytes(tj.render_preview(page), order.code, fmt="png"), "image/png")
            img = render_image.render_jpeg(
                page, ink_hex=ink.hex_code if ink else None,
                stroke_width_mm=float(width) if width else None,
                paper_surface=paper.surface if paper else None)
            image_paths.append(f"{base}/sketch_p{i}.jpg")
            store.write(image_paths[-1], watermark.apply_bytes(img, order.code, fmt="jpg"), "image/jpeg")
        raw = tj.dumps(tj.to_dict(pages, eng))
        path = f"{base}/trajectory.json"
        store.write(path, raw, "application/json")
        row = self.sketches.add(Sketch(
            order_id=order.id, version=version, created_by=self.actor.id, trajectory_uri=path,
            preview_url=pages[0].preview_path, image_urls=image_paths, similarity_score=similarity,
            suggested_complexity=ComplexityLevel(complexity) if complexity else None,
            estimated_writing_sec=metrics.estimated_writing_sec, total_stroke_mm=metrics.total_stroke_mm,
            pen_lift_count=metrics.pen_lift_count, approach_note=(note or None), content_hash=tj.content_hash(raw),
            render_profile_id=profile.id if profile else None))
        for r in regions or []:                                       # U4
            self.session.add(SketchRegion(
                sketch_id=row.id, page_no=r.page_no, region_no=r.region_no, x0=r.bbox[0], y0=r.bbox[1], x1=r.bbox[2],
                y1=r.bbox[3], stroke_start=r.stroke_start, stroke_end=r.stroke_end, label=r.label,
                confidence=r.confidence, metrics=r.metrics, text=r.text, source=r.source, note=r.note,
                edited_by=r.edited_by))
        self.session.flush()
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
                chars=order.char_count or 0, font_loader=store.read,
                layout=first.layout if first else None)             # the first text row starts the joined text: offsets hold
        row = self._persist(order, gen.pages, gen.engine, gen.metrics, gen.similarity, gen.complexity, approach_note,
                            gen.regions)
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

    def image_urls(self, row: Sketch) -> list[str]:
        """Signed links of the customer-facing JPEGs (older sketches without one fall back to the PNG previews)."""
        if self.storage is None:
            return []
        if row.image_urls:
            return [self.storage.create_download_url(p, 600) for p in row.image_urls]
        return self.preview_urls(row)

    def trajectory_url(self, row: Sketch) -> str | None:
        return self.storage.create_download_url(row.trajectory_uri, 600) if self.storage else None

    def detail(self, order_id: int, version: int) -> tuple[Sketch, dict[str, Any], list[str]]:
        order = self.access.order(order_id)
        row = self._get(order, version)
        raw = self._storage().read(row.trajectory_uri)
        if raw is None:
            raise AppError(409, "FILE_MISSING", "Không đọc được file quỹ đạo từ kho lưu trữ.")
        data = json.loads(raw)
        return row, data, [self._storage().create_download_url(p["preview_path"], 600)
                           for p in data.get("pages", []) if p.get("preview_path")]

    # ---- U4: restoration regions ----
    def regions_of(self, row: Sketch) -> list[SketchRegion]:
        return list(self.session.scalars(select(SketchRegion).where(SketchRegion.sketch_id == row.id)
                                         .order_by(SketchRegion.page_no, SketchRegion.region_no)))

    def regions(self, order_id: int, version: int) -> list[SketchRegion]:
        return self.regions_of(self._get(self.access.order(order_id), version))

    def edit_region(self, order_id: int, version: int, region_id: int, *, action: str, note: str,
                    strokes: list[list[list[float]]] | None = None, label: str | None = None,
                    text: str | None = None, font: str | None = None) -> Sketch:
        """Replace / rewrite / remove the strokes of ONE region; a new sketch version is saved, every other stroke is
        copied unchanged (same bytes in the trajectory file) and the other regions keep their numbers and labels."""
        order = self._editable_order(order_id)
        row = self._get(order, version)
        latest = self.sketches.next_version(order.id) - 1
        if row.version != latest:                                    # two Staff editing: optimistic check
            raise AppError(409, "SKETCH_VERSION_CONFLICT",
                           f"Phác thảo đã có phiên bản mới hơn (v{latest}); hãy mở phiên bản mới nhất rồi sửa.",
                           {"latest_version": latest})
        regions = self.regions_of(row)
        target = next((r for r in regions if r.id == region_id), None)
        if target is None:
            raise AppError(404, "REGION_NOT_FOUND", "Không tìm thấy vùng trong phiên bản phác thảo này.")
        new_label = "INFERRED" if action == "TEXT" else (label or "RESTORED") if action == "REPLACE_STROKES" else None
        if new_label == "INFERRED" and not _assisted(order):
            raise AppError(409, "INFERRED_NOT_ALLOWED",
                           "Khách chọn phục dựng trung thành: không được thêm nét suy đoán. Hãy vẽ lại theo đúng ảnh gốc "
                           "(nhãn RESTORED) hoặc hỏi khách chuyển sang chế độ hỗ trợ.", {"regions": [target.region_no]})
        store = self._storage()
        raw = store.read(row.trajectory_uri)
        if raw is None:
            raise AppError(409, "FILE_MISSING", "Không đọc được file quỹ đạo từ kho lưu trữ.")
        data = json.loads(raw)
        pages = tj.parse(data)
        if target.page_no > len(pages):
            raise AppError(409, "REGION_MISMATCH", "Vùng không khớp file quỹ đạo.")
        page = pages[target.page_no - 1]
        box = (float(target.x0), float(target.y0), float(target.x1), float(target.y1))
        if action == "REPLACE_STROKES":
            new = rg.strokes_from_points(strokes or [], page)
        elif action == "TEXT":
            new = rg.text_in_box(text or "", box, page.paper_size, font)
        else:
            new = []
        page.strokes[target.stroke_start:target.stroke_end] = new
        if not any(p.strokes for p in pages):
            raise AppError(422, "NO_CONTENT", "Phác thảo không còn nét nào.")
        delta = len(new) - (target.stroke_end - target.stroke_start)

        drafts = []
        for r in regions:
            if r.id == target.id:
                if action == "REMOVE":
                    continue
                drafts.append(rg.RegionDraft(
                    r.page_no, r.region_no, r.stroke_start, r.stroke_start + len(new), rg.bbox_of(new), new_label, None,
                    text=(text or "").strip() if action == "TEXT" else r.text, source="STAFF", note=note,
                    edited_by=self.actor.id))
                continue
            shift = delta if r.page_no == target.page_no and r.stroke_start >= target.stroke_end else 0
            drafts.append(rg.RegionDraft(
                r.page_no, r.region_no, r.stroke_start + shift, r.stroke_end + shift,
                (float(r.x0), float(r.y0), float(r.x1), float(r.y1)), r.label,
                float(r.confidence) if r.confidence is not None else None, text=r.text, source=r.source, note=r.note,
                edited_by=r.edited_by, metrics=r.metrics))
        eng = copy.deepcopy(data.get("engine") or {})
        eng.setdefault("region_edits", []).append({"from_version": row.version, "page": target.page_no,
                                                    "region": target.region_no, "action": action,
                                                    "label": new_label})
        v_max, _ = self._pen(order)
        metrics = tj.compute_metrics(pages, v_max)
        new_row = self._persist(order, pages, eng, metrics, None,
                                row.suggested_complexity.value if row.suggested_complexity else None, row.approach_note,
                                drafts)
        audit.record(self.session, actor_id=self.actor.id, action="SKETCH_REGION_EDIT", entity_type="sketch",
                     entity_id=new_row.id, old={"version": row.version, "region": target.region_no,
                                                "label": target.label},
                     new={"version": new_row.version, "action": action, "label": new_label, "note": note}, ip=self.ip)
        return new_row

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
        inferred = [r.region_no for r in self.regions_of(row) if r.label == "INFERRED"]
        if inferred and not _assisted(order):                       # U4: FAITHFUL never ships a guessed part
            raise AppError(409, "INFERRED_NOT_ALLOWED",
                           "Khách chọn phục dựng trung thành: phác thảo không được có vùng suy đoán.",
                           {"regions": inferred})
        if not row.is_final:
            self.sketches.clear_final(order.id)             # unique index allows only one final per order
            row.is_final = True
            self.session.flush()
            audit.record(self.session, actor_id=self.actor.id, action="SKETCH_FINALIZE", entity_type="sketch",
                         entity_id=row.id, new={"order_id": order.id, "version": version}, ip=self.ip)
        return row
