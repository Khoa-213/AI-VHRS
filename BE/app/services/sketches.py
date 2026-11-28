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
from app.models.order import ComplexityLevel, Order, OrderInputKind, OrderStatus, OrderType, StyleStatus
from app.models.sketch import Sketch, SketchRegion, SketchRevision
from app.models.studio import StudioDraft, StudioRevision
from app.repositories.catalog import CatalogRepository
from app.repositories.orders import OrderRepository
from app.repositories.workshop import SketchRepository
from app.services import audit, material_profiles, sketch_compare
from app.services import sketch_geometry as geo
from app.services.certificates import CertificateService
from app.services.stroke_ai import engine, physical_mark, regions as rg, render_image, trajectory as tj, watermark
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
                 regions: list[rg.RegionDraft] | None = None, doc: dict[str, Any] | None = None) -> Sketch:
        store = self._storage()
        # V2 Phase H: every version keeps its vhrs-sketch/2 document. Given (customer v1, Staff geometry edit) = the same ids;
        # otherwise derived from these pages (generation / upload / region edit: new ids). Built before the U8 line is added
        if doc is None:
            doc = geo.from_generated(pages, eng, regions)
        # U8: the physical watermark line is regenerated on every save (an upload / edit can neither drop nor fake it)
        wm = None
        if physical_mark.required(order.order_type.value, order.physical_watermark):
            wm = physical_mark.apply(pages, CertificateService(self.session).ensure(order).code)
        removed = physical_mark.strip(pages) if wm is None else 0
        if wm is not None or removed:
            metrics = tj.compute_metrics(pages, self._pen(order)[0])
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
        g_hash = geo.geometry_hash(doc)
        if g_hash != geo.pages_geometry_hash(pages):              # the two files must draw exactly the same strokes
            raise AppError(500, "GEOMETRY_MISMATCH", "Tài liệu phác thảo không khớp quỹ đạo; đã huỷ lưu.")
        store.write(path, raw, "application/json")
        doc_path = f"{base}/document.json"
        store.write(doc_path, geo.dumps(doc), "application/json")
        row = self.sketches.add(Sketch(
            order_id=order.id, version=version, created_by=self.actor.id, trajectory_uri=path,
            preview_url=pages[0].preview_path, image_urls=image_paths, similarity_score=similarity,
            suggested_complexity=ComplexityLevel(complexity) if complexity else None,
            estimated_writing_sec=metrics.estimated_writing_sec, total_stroke_mm=metrics.total_stroke_mm,
            pen_lift_count=metrics.pen_lift_count, approach_note=(note or None), content_hash=tj.content_hash(raw),
            render_profile_id=profile.id if profile else None, watermark=wm, document_uri=doc_path, geometry_hash=g_hash))
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
        v_max, _ = self._pen(order)
        gen = run_engine(self.session, self._storage(), order, paper_size=self._paper_size(order, paper_size), seed=seed)
        if order.order_type == OrderType.OT1_COPY_RESTORE:
            self._customer_region_edits(order, gen, v_max)
        from app.services.sketch_work import order_word_texts
        doc = geo.from_generated(gen.pages, gen.engine,
                                 gen.regions if order.order_type == OrderType.OT1_COPY_RESTORE else None,
                                 order_word_texts(self.session, order))
        row = self._persist(order, gen.pages, gen.engine, gen.metrics, gen.similarity, gen.complexity, approach_note,
                            gen.regions, doc)
        return row, gen.warnings

    def adopt_customer_revision(self, order: Order) -> Sketch | None:
        """V2, D2: when the Staff take the order, official version v1 is EXACTLY the customer's working sketch (the strokes
        of `orders.current_sketch_revision_id`), not a new generation. Only the U8 verification line is added (as on every
        official save). OT-1 word regions keep their labels / confidence / text. Returns None when the customer made none."""
        from app.services.sketch_work import load_geometry
        if order.current_sketch_revision_id is None or self.sketches.next_version(order.id) != 1:
            return None
        rev = self.session.get(SketchRevision, order.current_sketch_revision_id)
        doc = load_geometry(self._storage(), rev)
        pages = geo.to_pages(doc)
        from app.services.htr_hints import hints_for          # E2b: the AI text hints go with v1 (metrics.htr)
        hints = hints_for(self.session, order, doc, outdated=False)    # sending checked the sketch is not outdated
        regions = _regions_from_doc(doc, lambda page_no, region_no, w: ("CUSTOMER", None),
                                    hints=(hints or {}).get("words"))
        eng = {"name": "customer-working-sketch", "version": engine.ENGINE_VERSION, "source_revision_id": rev.id,
               "source_revision_seq": rev.seq, "geometry_hash": rev.geometry_hash, "base_engine": doc.get("engine")}
        metrics = tj.compute_metrics(pages, self._pen(order)[0])
        row = self._persist(order, pages, eng, metrics, None, (rev.metrics or {}).get("suggested_complexity"),
                            f"Phác thảo khách gửi (bản làm việc r{rev.seq})", regions or None, doc)
        row.source_revision_id = rev.id
        self.session.flush()
        return row

    def _customer_region_edits(self, order: Order, gen: engine.Generated, v_max: float) -> None:
        """U5: the regions the customer removed / wrote in the studio are applied to the official sketch too (source
        CUSTOMER), so the Staff start from what the customer approved in the preview. An edit that no longer fits (the
        images were rotated or cropped since) is skipped and reported, never guessed."""
        draft = self.session.scalar(select(StudioDraft).where(StudioDraft.order_id == order.id))
        rev = self.session.get(StudioRevision, draft.current_revision_id) if draft and draft.current_revision_id else None
        edits = (rev.content.get("region_edits") or []) if rev else []
        if not edits:
            return
        gen.regions, applied, skipped = rg.apply_edits(gen.pages, gen.regions, edits, assisted=_assisted(order), strict=False)
        if not any(p.strokes for p in gen.pages):
            raise AppError(422, "NO_CONTENT", "Phác thảo không còn nét nào sau chỉnh sửa vùng của khách.")
        gen.metrics = tj.compute_metrics(gen.pages, v_max)
        gen.engine["customer_region_edits"] = {"draft_id": draft.id, "revision_id": rev.id, "applied": applied,
                                               "skipped": skipped}
        if applied:
            gen.warnings.append("CUSTOMER_REGION_EDITS_APPLIED")
        if skipped:
            gen.warnings.append("CUSTOMER_REGION_EDITS_SKIPPED")

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

    # ---- V2 Phase H: the version's document and Staff geometry edits ----
    def document_of(self, row: Sketch) -> dict[str, Any]:
        """The `vhrs-sketch/2` document of an official version. Saved since 0025: read and checked against its hash.
        Older versions (H-c, no backfill): derived from the trajectory file (checked against `content_hash`) and its U4
        regions, with `derived: true`; nothing is written for them."""
        store = self._storage()
        if row.document_uri:
            raw = store.read(row.document_uri)
            if raw is None:
                raise AppError(409, "FILE_MISSING", "Không đọc được file tài liệu phác thảo từ kho lưu trữ.")
            doc = json.loads(raw)
            if geo.geometry_hash(doc) != row.geometry_hash:
                raise AppError(409, "GEOMETRY_TAMPERED", "File tài liệu phác thảo không khớp mã băm đã lưu; không dùng được.")
            return geo.ensure_structure(doc)                 # Phase F: lines / paragraphs for documents saved before them
        raw = store.read(row.trajectory_uri)
        if raw is None:
            raise AppError(409, "FILE_MISSING", "Không đọc được file quỹ đạo từ kho lưu trữ.")
        if row.content_hash and tj.content_hash(raw) != row.content_hash:
            raise AppError(409, "GEOMETRY_TAMPERED", "File quỹ đạo không khớp mã băm đã lưu; không dùng được.")
        data = json.loads(raw)
        regions = self.regions_of(row)
        doc = geo.from_generated(tj.parse(data), {"name": "derived-from-trajectory", "sketch_version": row.version,
                                                  "base_engine": data.get("engine")}, regions or None)
        doc["derived"] = True
        return doc

    def edit_strokes(self, order_id: int, version: int, *, op: str, stroke_ids: list[str] | None,
                     word_ids: list[str] | None, params: dict[str, Any] | None, note: str,
                     line_ids: list[str] | None = None, paragraph_ids: list[str] | None = None) -> tuple[Sketch, dict[str, Any]]:
        """V2 Phase H: one Geometry Engine edit by the Staff on the LATEST version -> a new version (never in place). Same
        limits per order type as the customer / assistant (H-a); strokes outside the selection are verified unchanged;
        ids the edit did not touch are kept, so a later compare / the customer's markers still line up."""
        order = self._editable_order(order_id)
        row = self._get(order, version)
        latest = self.sketches.next_version(order.id) - 1
        if row.version != latest:                                    # two Staff editing: optimistic check
            raise AppError(409, "SKETCH_VERSION_CONFLICT",
                           f"Phác thảo đã có phiên bản mới hơn (v{latest}); hãy mở phiên bản mới nhất rồi sửa.",
                           {"latest_version": latest})
        doc = self.document_of(row)
        doc.pop("derived", None)
        ids = list(stroke_ids or []) + geo.group_strokes(doc, word_ids, line_ids, paragraph_ids)
        new, report = geo.apply(doc, op, ids, params, geo.limits_for(order.order_type.value))
        geo.mark_edit(new, report, "STAFF")
        operation = {"op": op, "stroke_ids": stroke_ids or [], "word_ids": word_ids or [], "params": params or {},
                     **({"line_ids": line_ids} if line_ids else {}), **({"paragraph_ids": paragraph_ids} if paragraph_ids else {})}
        eng = {"name": "staff-geometry-edit", "version": engine.ENGINE_VERSION, "from_version": row.version,
               "operation": operation, "note": note, "base_engine": doc.get("engine")}
        new["engine"] = eng
        old_regions = {(r.page_no, r.region_no): r for r in self.regions_of(row)}
        touched = set(report["changed"]) | set(report["added"]) | set(report["removed"])

        def source_of(page_no: int, region_no: int, w: dict[str, Any]) -> tuple[str, int | None]:
            if touched & set(w["stroke_ids"]):
                return "STAFF", self.actor.id
            old = old_regions.get((page_no, region_no))
            return (old.source, old.edited_by) if old else ("STAFF", self.actor.id)

        carried = {}                                       # E2b: the AI text hint stays with its region across edits
        for page_no, p in enumerate(new["pages"], start=1):
            for n, w in enumerate(p["words"], start=1):
                old = old_regions.get((page_no, w.get("region_no") or n))
                if old is not None and (old.metrics or {}).get("htr"):
                    carried[w["id"]] = old.metrics["htr"]
        # SD-02 (audit 2026-11-27): a word the Staff changed is no longer "traced from ink clearly visible in the image". It
        # kept the label ORIGINAL, so the customer was told nothing. It becomes RESTORED ("redrawn by Staff from the image",
        # stroke_ai/regions.py), which the customer's quotation lists as an uncertain part.
        for p_ in new["pages"]:
            for w in p_["words"]:
                if w.get("label") == "ORIGINAL" and touched & set(w["stroke_ids"]):
                    w["label"] = "RESTORED"
        regions = _regions_from_doc(new, source_of, hints=carried) if old_regions else None
        pages = geo.to_pages(new)
        metrics = tj.compute_metrics(pages, self._pen(order)[0])
        new_row = self._persist(order, pages, eng, metrics, None,
                                row.suggested_complexity.value if row.suggested_complexity else None, row.approach_note,
                                regions, new)
        audit.record(self.session, actor_id=self.actor.id, action="SKETCH_GEOMETRY_EDIT", entity_type="sketch",
                     entity_id=new_row.id, old={"version": row.version},
                     new={"version": new_row.version, **operation, "changed": report["changed"],
                          "removed": report["removed"], "added": report["added"], "note": note}, ip=self.ip)
        return new_row, report

    def compare(self, order_id: int, from_version: int, to_version: int) -> dict[str, Any]:
        """U2: what changed between two versions (metrics, strokes per page with an overlay image, regions)."""
        order = self.access.order(order_id)
        a, b = self._get(order, from_version), self._get(order, to_version)
        return sketch_compare.compare(self._storage(), a, b, self.regions_of(a), self.regions_of(b), order_id=order.id,
                                      order_code=order.code)

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
        regions = self.regions_of(row)
        inferred = [r.region_no for r in regions if r.label == "INFERRED"]
        if inferred and not _assisted(order):                       # U4: FAITHFUL never ships a guessed part
            raise AppError(409, "INFERRED_NOT_ALLOWED",
                           "Khách chọn phục dựng trung thành: phác thảo không được có vùng suy đoán.",
                           {"regions": inferred})
        if order.order_type == OrderType.OT1_COPY_RESTORE and not _assisted(order) and not regions:
            # SD-02: a hand-uploaded trajectory has no regions at all, so the check above passed whatever it contained and the
            # customer was shown no uncertain part. Without regions nothing says which strokes come from the customer's ink.
            raise AppError(409, "FAITHFUL_NEEDS_REGIONS",
                           "Khách chọn phục dựng trung thành, nhưng phác thảo này không có thông tin vùng (bản tải tay) nên không "
                           "chứng minh được nét nào lấy từ ảnh của khách. Hãy dùng bản AI sinh rồi chỉnh trên đó, hoặc hỏi khách "
                           "chuyển sang chế độ hỗ trợ.")
        if not row.is_final:
            self.sketches.clear_final(order.id)             # unique index allows only one final per order
            row.is_final = True
            self.session.flush()
            audit.record(self.session, actor_id=self.actor.id, action="SKETCH_FINALIZE", entity_type="sketch",
                         entity_id=row.id, new={"order_id": order.id, "version": version}, ip=self.ip)
        return row

def _regions_from_doc(doc: dict[str, Any], source_of, hints: dict[str, dict[str, Any]] | None = None) -> list[rg.RegionDraft]:
    """U4 region rows of a document's labelled words (OT-1), with their stroke range in `geo.to_pages(doc)`. A word whose
    strokes are no longer contiguous is left out (a region is a stroke range). `source_of(page_no, region_no, word)` ->
    (source, edited_by). `hints` (E2b, word id -> {text, status}) is kept in `metrics.htr` (a hint, never `text`)."""
    regions: list[rg.RegionDraft] = []
    for page_no, p in enumerate(doc["pages"], start=1):
        pos = {st["id"]: i for i, st in enumerate(p["strokes"])}
        for n, w in enumerate(p["words"], start=1):
            idx = sorted(pos[s] for s in w["stroke_ids"])
            if w.get("label") and idx == list(range(idx[0], idx[-1] + 1)):          # OT-1 words only, contiguous
                region_no = w.get("region_no") or n
                source, edited_by = source_of(page_no, region_no, w)
                regions.append(rg.RegionDraft(page_no=page_no, region_no=region_no, stroke_start=idx[0],
                                              stroke_end=idx[-1] + 1, bbox=tuple(w["bbox"]), label=w["label"],
                                              confidence=w.get("confidence"), text=w.get("text"), source=source,
                                              edited_by=edited_by,
                                              metrics={"htr": hints[w["id"]]} if hints and w["id"] in hints else None))
    return regions


def run_engine(session: Session, store: ObjectStorage, order: Order, *, paper_size: str, seed: int | None) -> engine.Generated:
    """The AI pipeline on an order's inputs (OT-1 photos / OT-3 text + drawing). Shared by the Staff's official sketch and the
    customer's working sketch (V2), so both run exactly the same code. Raises AppError with the engine's own codes."""
    catalog, orders = CatalogRepository(session), OrderRepository(session)
    pen = catalog.pen(order.pen_type_id) if order.pen_type_id else None
    v_max, category = (float(pen.v_max_mm_s) if pen else DEFAULT_V_MAX), (pen.category if pen else None)
    size = paper_size
    inputs = orders.inputs(order.id)
    style = None
    if order.order_type == OrderType.OT2_LEARNED_STYLE:
        style = learned_style(session, store, order, inputs)    # OT-2 Phase O3: only with an approved style (O3-a)
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
        return engine.generate_ot1(sources, paper_size=size, v_max_mm_s=v_max, pen_category=category,
                                   chars=order.char_count or 0,
                                   recovery_engine=catalog.setting("ot1_recovery_engine", "v2"))   # OT-1 v2, R4
    else:
        text_rows = [r for r in inputs if r.kind == OrderInputKind.TEXT_CONTENT]
        canvas_rows = [r for r in inputs if r.kind == OrderInputKind.CANVAS]
        text = "\n".join(r.text_content or "" for r in text_rows)
        first = text_rows[0] if text_rows else None
        template = catalog.template(first.template_id) if first and first.template_id else None
        return engine.generate_ot3(
            text, canvas_rows[0].canvas_data if canvas_rows else None,
            font_uri=template.font_uri if template else None,
            font_size_mm=float(first.font_size_mm) if first and first.font_size_mm else None,
            alignment=first.alignment if first else None, paper_size=size,
            seed=seed, v_max_mm_s=v_max, pen_category=category,
            chars=order.char_count or 0, font_loader=store.read,
            layout=first.layout if first else None,             # the first text row starts the joined text: offsets hold
            style=style)


def learned_style(session: Session, store: ObjectStorage, order: Order, inputs) -> dict[str, Any]:
    """OT-2 Phase O3: the approved style the order's text row names, with its glyph set read from storage.

    O3-a: an OT-2 order without a chosen style (only a free-form sample photo) is still drawn by hand by the Staff
    (422 AI_TYPE_UNSUPPORTED). A style that is no longer approved, belongs to someone else or whose glyph file is gone is
    409 STYLE_UNAVAILABLE: the order never silently switches to another source (Q2)."""
    import hashlib

    from app.models.order import HandwritingStyle
    row = next((r for r in inputs if r.kind == OrderInputKind.TEXT_CONTENT and r.handwriting_style_id), None)
    if row is None:
        raise AppError(422, "AI_TYPE_UNSUPPORTED",
                       "Đơn viết theo nét chữ đã học chỉ sinh phác thảo tự động khi khách chọn bộ nét đã duyệt. "
                       "Đơn chỉ có ảnh mẫu chữ: hãy tải phác thảo thủ công hoặc từ chối đơn.")
    style = session.get(HandwritingStyle, row.handwriting_style_id)
    data = None
    if (style is not None and style.status == StyleStatus.APPROVED and style.owner_id == order.customer_id
            and style.glyph_set_uri):
        data = store.read(style.glyph_set_uri)
    if data is None:
        raise AppError(409, "STYLE_UNAVAILABLE",
                       "Bộ nét chữ của đơn không còn dùng được (đã xoá, chưa duyệt hoặc mất file). "
                       "Hãy chọn bộ nét khác.", {"style_id": row.handwriting_style_id})
    try:
        glyph_set = json.loads(data)
    except ValueError as exc:
        raise AppError(409, "STYLE_UNAVAILABLE", "Bộ nét chữ của đơn không đọc được.",
                       {"style_id": style.id}) from exc
    return {"id": style.id, "sha256": hashlib.sha256(data).hexdigest(), "glyph_set": glyph_set}
