"""V2 Phase B: the customer's working sketch of an order (owner decisions D1, D2, D3, 2026-11-17).

While the order is DRAFT (or NEED_INFO) the customer has ONE working sketch: the engine draws revision r1 from the order's
own inputs (the same `run_engine` the Staff use), then every change is a new `sketch_revisions` row made by the Geometry Engine
(`sketch_geometry.apply`). Undo / redo move the order's cursor (`orders.current_sketch_revision_id`). When the Staff accept
the order, official version v1 is that exact geometry (`SketchService.adopt_customer_revision`), not a new generation.

Rules
* Only the order's customer, only while the order is editable. After submit the working sketch is read-only.
* Every edit names the revision it was made on (`base_revision_id`): another tab / the assistant changed it in between ->
  `409 STALE_REVISION`, nothing is overwritten. The order row is locked while an edit is written.
* The revision records what the geometry was built from (`inputs_hash`). The customer changed the text / images / paper size
  afterwards -> `inputs_changed: true`; submitting then answers `409 SKETCH_OUTDATED` until the sketch is drawn again, so the
  Staff never receive strokes of an older text.
* The geometry file's hash is checked on every read (`GEOMETRY_TAMPERED` if the stored file was changed).

V2 Phase D (owner D-b, D-c, 2026-11-19)
* Drawing again replaces strokes the customer / assistant edited: `generate` refuses with `409 SKETCH_HAS_EDITS` (how many
  strokes, by whom) unless `discard_edits` is set. The old revisions stay, so undo still brings the edits back.
* Every drawing stores the form it was drawn from (`inputs_snapshot`: text input, canvas, materials); edits copy it. Undo /
  redo onto a revision of another drawing puts the form back to that snapshot (`inputs_restored`), so the form and the sketch
  agree. Form changes not drawn yet would be lost: refused with `409 UNDRAWN_INPUT_CHANGES` unless `discard_input_changes`.
  Images (OT-1) are not restored (files); revisions saved before migration 0026 have no snapshot and move the sketch only.
"""
from __future__ import annotations

import dataclasses
import hashlib
import json
import unicodedata
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.errors import AppError
from app.integrations.storage import ObjectStorage
from app.models.account import Account
from app.models.order import Order, OrderInputKind, OrderType
from app.models.sketch import SketchRevision
from app.repositories.catalog import CatalogRepository
from app.repositories.orders import OrderRepository
from app.services import audit
from app.services import sketch_geometry as geo
from app.services.stroke_ai import render_image, trajectory as tj, watermark

AUTHORS = ("ENGINE", "CUSTOMER", "AI", "STAFF")
DEFAULT_V_MAX = 30.0


def inputs_hash(session: Session, order: Order) -> str:
    """What the geometry depends on. Pen / ink / quantity are not in it (they change the look or the price, not the strokes)."""
    catalog = CatalogRepository(session)
    paper = catalog.paper(order.paper_type_id) if order.paper_type_id else None
    rows = []
    for r in OrderRepository(session).inputs(order.id):
        if r.kind == OrderInputKind.TEXT_CONTENT:
            rows.append({"k": "text", "t": unicodedata.normalize("NFC", r.text_content or ""), "tpl": r.template_id,
                         "size": str(r.font_size_mm) if r.font_size_mm is not None else None, "align": r.alignment,
                         "layout": r.layout})
        elif r.kind == OrderInputKind.CANVAS:
            rows.append({"k": "canvas", "c": r.canvas_data})
        elif r.kind == OrderInputKind.ORIGINAL_IMAGE and r.quality_result is not None:
            rows.append({"k": "image", "f": r.file_url, "rot": r.rotation_deg, "crop": r.crop_box})
    key = {"type": order.order_type.value, "paper": paper.size.value if paper else "A4",
           "restoration_mode": order.restoration_mode, "inputs": rows}
    return hashlib.sha256(json.dumps(key, sort_keys=True, default=str).encode()).hexdigest()


SNAPSHOT_VERSION = 1


def inputs_snapshot(session: Session, order: Order) -> dict[str, Any]:
    """The form a drawing is made from (V2 Phase D): the text input, the canvas and the materials. Images are not kept."""
    text = canvas = None
    for r in OrderRepository(session).inputs(order.id):
        if r.kind == OrderInputKind.TEXT_CONTENT:
            text = {"text_content": r.text_content, "template_id": r.template_id,
                    "handwriting_style_id": r.handwriting_style_id,
                    "font_size_mm": str(r.font_size_mm) if r.font_size_mm is not None else None,
                    "alignment": r.alignment, "layout": r.layout}
        elif r.kind == OrderInputKind.CANVAS:
            canvas = r.canvas_data
    return {"version": SNAPSHOT_VERSION, "text": text, "canvas": canvas, "paper_type_id": order.paper_type_id,
            "pen_type_id": order.pen_type_id, "ink_color_id": order.ink_color_id}


def load_geometry(storage: ObjectStorage, rev: SketchRevision) -> dict[str, Any]:
    raw = storage.read(rev.geometry_uri)
    if raw is None:
        raise AppError(409, "FILE_MISSING", "Không đọc được file hình học của phác thảo.")
    doc = json.loads(raw)
    if geo.geometry_hash(doc) != rev.geometry_hash:
        raise AppError(409, "GEOMETRY_TAMPERED", "File hình học không khớp mã băm đã lưu; không dùng được.")
    return geo.ensure_structure(doc)              # Phase F: a document saved before lines existed gets them on read


def order_word_texts(session: Session, order: Order) -> list[str] | None:
    """OT-3 words of the text in reading order (labels for the assistant: "dời chữ 'gửi'"). A drawing has no words."""
    if order.order_type != OrderType.OT3_TEMPLATE:
        return None
    row = next((r for r in OrderRepository(session).inputs(order.id) if r.kind == OrderInputKind.TEXT_CONTENT), None)
    if row is None or not row.text_content:
        return None
    return unicodedata.normalize("NFC", row.text_content).split()


def order_word_paragraphs(session: Session, order: Order) -> list[int] | None:
    """Phase F: the paragraph of each word of `order_word_texts` (a new line in the text starts a paragraph, as in the
    text composer)."""
    if order.order_type != OrderType.OT3_TEMPLATE:
        return None
    row = next((r for r in OrderRepository(session).inputs(order.id) if r.kind == OrderInputKind.TEXT_CONTENT), None)
    if row is None or not row.text_content:
        return None
    return [pi for pi, line in enumerate(unicodedata.normalize("NFC", row.text_content).split("\n")) for _ in line.split()]


def check_fresh(session: Session, order: Order) -> None:
    """Called when the order is sent: a working sketch drawn from older inputs must be redrawn first."""
    if order.current_sketch_revision_id is None:
        return
    rev = session.get(SketchRevision, order.current_sketch_revision_id)
    if rev is not None and rev.inputs_hash and rev.inputs_hash != inputs_hash(session, order):
        raise AppError(409, "SKETCH_OUTDATED",
                       "Nội dung đơn đã đổi sau khi tạo phác thảo; hãy tạo lại phác thảo trước khi gửi.")


class SketchWorkService:
    def __init__(self, session: Session, customer: Account, storage: ObjectStorage | None, ip: str | None = None):
        self.session, self.customer, self.storage, self.ip = session, customer, storage, ip
        self.catalog = CatalogRepository(session)
        self.inputs_restored = False          # V2 Phase D: the last undo / redo put the form back
        self.last_redraw: dict[str, Any] | None = None     # Phase F: what the last generate kept / re-applied / dropped

    # ------------------------------------------------------------------ access
    def _store(self) -> ObjectStorage:
        if self.storage is None:
            raise AppError(503, "STORAGE_NOT_CONFIGURED", "Chưa cấu hình dịch vụ lưu trữ file.")
        return self.storage

    def order(self, order_id: int, *, write: bool = False) -> Order:
        q = select(Order).where(Order.id == order_id, Order.customer_id == self.customer.id)
        order = self.session.scalar(q.with_for_update() if write else q)
        if order is None:
            raise AppError(404, "ORDER_NOT_FOUND", "Không tìm thấy đơn hàng.")
        if write:
            from app.services.orders import EDITABLE
            if order.order_status not in EDITABLE:
                raise AppError(409, "ORDER_NOT_EDITABLE", "Đơn đã gửi, phác thảo chỉ còn xem được.")
        return order

    def _rev(self, order: Order, rev_id: int | None) -> SketchRevision | None:
        if rev_id is None:
            return None
        rev = self.session.get(SketchRevision, rev_id)
        if rev is None or rev.order_id != order.id:
            raise AppError(404, "REVISION_NOT_FOUND", "Không tìm thấy phiên bản phác thảo.")
        return rev

    def _current(self, order: Order) -> SketchRevision:
        rev = self._rev(order, order.current_sketch_revision_id)
        if rev is None:
            raise AppError(404, "SKETCH_NOT_GENERATED", "Đơn chưa có phác thảo; hãy tạo phác thảo trước.")
        return rev

    def _redo_target(self, order: Order, rev: SketchRevision) -> SketchRevision | None:
        return self.session.scalar(select(SketchRevision).where(
            SketchRevision.order_id == order.id, SketchRevision.parent_id == rev.id).order_by(SketchRevision.seq.desc()).limit(1))

    def _v_max(self, order: Order) -> float:
        pen = self.catalog.pen(order.pen_type_id) if order.pen_type_id else None
        return float(pen.v_max_mm_s) if pen else DEFAULT_V_MAX

    # ------------------------------------------------------------------ write
    def _save(self, order: Order, doc: dict[str, Any], *, author: str, parent: SketchRevision | None, note: str,
              operation: dict[str, Any] | None = None, validation: dict[str, Any] | None = None,
              complexity: str | None = None, tool: str | None = None, provider: str | None = None,
              model: str | None = None, in_hash: str | None = None,
              snapshot: dict[str, Any] | None = None) -> SketchRevision:
        assert author in AUTHORS
        seq = (self.session.scalar(select(func.max(SketchRevision.seq)).where(SketchRevision.order_id == order.id)) or 0) + 1
        path = f"orders/{order.id}/work/r{seq}.json"
        self._store().write(path, geo.dumps(doc), "application/json")
        metrics = dataclasses.asdict(tj.compute_metrics(geo.to_pages(doc), self._v_max(order)))
        if complexity is None and parent is not None:
            complexity = (parent.metrics or {}).get("suggested_complexity")
        metrics["suggested_complexity"] = complexity
        rev = SketchRevision(order_id=order.id, parent_id=parent.id if parent else None, seq=seq, author=author,
                             actor_id=self.customer.id, tool_name=tool, provider=provider, model=model, note=note[:300],
                             operation=operation, geometry_uri=path, geometry_hash=geo.geometry_hash(doc),
                             inputs_hash=in_hash if in_hash is not None else (parent.inputs_hash if parent else None),
                             inputs_snapshot=snapshot if snapshot is not None else (parent.inputs_snapshot if parent else None),
                             metrics=metrics, validation=validation)
        self.session.add(rev)
        self.session.flush()
        order.current_sketch_revision_id = rev.id
        self.session.flush()
        audit.record(self.session, actor_id=self.customer.id, action="SKETCH_REVISION", entity_type="order",
                     entity_id=order.id, new={"revision_id": rev.id, "seq": seq, "author": author,
                                              "op": (operation or {}).get("op"), "tool": tool}, ip=self.ip)
        return rev

    def generate(self, order_id: int, *, discard_edits: bool = False) -> tuple[SketchRevision, dict[str, Any], list[str]]:
        """Draw the working sketch from the order's inputs (a new revision; the previous ones stay for undo)."""
        from app.services.sketches import run_engine
        order = self.order(order_id, write=True)
        if order.order_type == OrderType.OT2_LEARNED_STYLE:
            raise AppError(422, "AI_TYPE_UNSUPPORTED",
                           "Loại sáng tác theo nét chữ đã học chưa sinh được phác thảo tự động (đang nghiên cứu).")
        current = self._rev(order, order.current_sketch_revision_id)
        old = load_geometry(self._store(), current) if current is not None else None
        ops = self._edits_since_drawing(current)
        if old is not None and not discard_edits:                      # D-b: say what a new drawing would replace
            summary = geo.edit_summary(old)
            if summary["edited"]:
                back = sum(1 for o in ops if geo.reapplicable(o))
                raise AppError(409, "SKETCH_HAS_EDITS",
                               f"Phác thảo hiện tại có {summary['edited']} nét đã chỉnh; tạo lại sẽ vẽ nét mới, chỉ giữ lại "
                               f"{back}/{len(ops)} lệnh dời / xoay / đổi cỡ / nghiêng trên cả từ (vẫn hoàn tác được). "
                               "Gửi discard_edits=true để tiếp tục.",
                               {"edited_strokes": summary["edited"], "current_revision_id": current.id,
                                "by": {k: summary[k] for k in geo.EDITORS},
                                "edits": len(ops), "reapplicable_edits": back})
        paper = self.catalog.paper(order.paper_type_id) if order.paper_type_id else None
        gen = run_engine(self.session, self._store(), order, paper_size=paper.size.value if paper else "A4", seed=None)
        regions = gen.regions if order.order_type == OrderType.OT1_COPY_RESTORE else None
        doc = geo.from_generated(gen.pages, gen.engine, regions, self._word_texts(order),
                                 order_word_paragraphs(self.session, order))
        redraw = None
        if old is not None:                                            # Phase F: same ids for the same words, edits back
            redraw = {"ids": geo.carry_ids(old, doc)}
            doc, back = geo.reapply(doc, ops, geo.limits_for(order.order_type.value))
            redraw.update(back)
        self.last_redraw = redraw
        rev = self._save(order, doc, author="ENGINE", parent=current, note="Sinh phác thảo từ nội dung đơn",
                         operation={"op": "generate", "redraw": redraw} if redraw else None,
                         validation={"warnings": gen.warnings, **({"redraw": redraw} if redraw else {})},
                         complexity=gen.complexity, in_hash=inputs_hash(self.session, order),
                         snapshot=inputs_snapshot(self.session, order))
        return rev, doc, gen.warnings

    def _edits_since_drawing(self, rev: SketchRevision | None) -> list[dict[str, Any]]:
        """The edits on the way from the last drawing to `rev` (undone ones are not on that path), oldest first."""
        out = []
        while rev is not None and rev.author != "ENGINE":
            if rev.operation and rev.operation.get("op") in geo.OPS:
                out.append({**rev.operation, "author": rev.author})
            rev = self.session.get(SketchRevision, rev.parent_id) if rev.parent_id else None
        return out[::-1]

    def edit(self, order_id: int, *, base_revision_id: int, op: str, stroke_ids: list[str] | None = None,
             word_ids: list[str] | None = None, params: dict[str, Any] | None = None, note: str | None = None,
             line_ids: list[str] | None = None, paragraph_ids: list[str] | None = None,
             author: str = "CUSTOMER", tool: str | None = None, provider: str | None = None,
             model: str | None = None) -> tuple[SketchRevision, dict[str, Any], dict[str, Any]]:
        order = self.order(order_id, write=True)
        current = self._current(order)
        if base_revision_id != current.id:
            raise AppError(409, "STALE_REVISION", "Phác thảo đã đổi (tab khác hoặc trợ lý vừa sửa); hãy tải lại rồi sửa tiếp.",
                           {"current_revision_id": current.id})
        doc = load_geometry(self._store(), current)
        ids = list(stroke_ids or []) + geo.group_strokes(doc, word_ids, line_ids, paragraph_ids)
        new, report = geo.apply(doc, op, ids, params, geo.limits_for(order.order_type.value))
        geo.mark_edit(new, report, author)
        operation = {"op": op, "stroke_ids": stroke_ids or [], "word_ids": word_ids or [], "params": params or {},
                     **({"line_ids": line_ids} if line_ids else {}), **({"paragraph_ids": paragraph_ids} if paragraph_ids else {})}
        rev = self._save(order, new, author=author, parent=current, operation=operation, validation=report, tool=tool,
                         provider=provider, model=model, note=note or _describe(report))
        return rev, new, report

    def _word_texts(self, order: Order) -> list[str] | None:
        return order_word_texts(self.session, order)

    def undo(self, order_id: int, *, discard_input_changes: bool = False) -> SketchRevision:
        order = self.order(order_id, write=True)
        current = self._current(order)
        parent = self._rev(order, current.parent_id)
        if parent is None:
            raise AppError(409, "NOTHING_TO_UNDO", "Không còn gì để hoàn tác.")
        self._move(order, current, parent, discard_input_changes)
        return parent

    def redo(self, order_id: int, *, discard_input_changes: bool = False) -> SketchRevision:
        order = self.order(order_id, write=True)
        current = self._current(order)
        target = self._redo_target(order, current)
        if target is None:
            raise AppError(409, "NOTHING_TO_REDO", "Không còn gì để làm lại.")
        self._move(order, current, target, discard_input_changes)
        return target

    def _move(self, order: Order, current: SketchRevision, target: SketchRevision, discard_input_changes: bool) -> None:
        """Move the cursor; across drawings the form follows (D-c). Sets `self.inputs_restored`."""
        self.inputs_restored = False
        crossing = (target.inputs_snapshot is not None and target.inputs_hash is not None
                    and target.inputs_hash != current.inputs_hash)
        if crossing:
            now = inputs_hash(self.session, order)
            if not discard_input_changes and current.inputs_hash is not None and now != current.inputs_hash \
                    and now != target.inputs_hash:
                raise AppError(409, "UNDRAWN_INPUT_CHANGES",
                               "Nội dung đơn đã sửa sau lần tạo phác thảo gần nhất và chưa được vẽ; hoàn tác sẽ đưa nội "
                               "dung về bản cũ. Gửi discard_input_changes=true để tiếp tục.",
                               {"current_revision_id": current.id, "target_revision_id": target.id})
            if now != target.inputs_hash:
                self._restore_inputs(order, target.inputs_snapshot)
                self.inputs_restored = True
        order.current_sketch_revision_id = target.id
        self.session.flush()

    def _restore_inputs(self, order: Order, snap: dict[str, Any]) -> None:
        from decimal import Decimal

        from app.models.order import OrderInput
        from app.services.orders import OrderService
        repo = OrderRepository(self.session)
        rows = repo.inputs(order.id)
        before = inputs_snapshot(self.session, order)
        for kind, key in ((OrderInputKind.TEXT_CONTENT, "text"), (OrderInputKind.CANVAS, "canvas")):
            row = next((r for r in rows if r.kind == kind), None)
            value = snap.get(key)
            if value is None:
                if row is not None:
                    repo.delete_input(row)
                continue
            if kind == OrderInputKind.TEXT_CONTENT:
                fields = {**value, "font_size_mm": Decimal(value["font_size_mm"]) if value.get("font_size_mm") else None}
                if row is None:
                    repo.add_input(OrderInput(order_id=order.id, kind=kind, **fields))
                else:
                    for k, v in fields.items():
                        setattr(row, k, v)
            elif row is None:
                repo.add_input(OrderInput(order_id=order.id, kind=kind, canvas_data=value))
            else:
                row.canvas_data = value
        for k in ("paper_type_id", "pen_type_id", "ink_color_id"):
            setattr(order, k, snap.get(k))
        self.session.flush()
        OrderService(self.session, self.customer)._touch_and_price(order)       # the estimate follows the restored form
        audit.record(self.session, actor_id=self.customer.id, action="ORDER_INPUTS_RESTORED", entity_type="order",
                     entity_id=order.id, old=before, new=snap, ip=self.ip)

    # ------------------------------------------------------------------ read
    def view(self, order_id: int, revision_id: int | None = None) -> dict[str, Any]:
        order = self.order(order_id)
        rev = self._rev(order, revision_id) if revision_id is not None else self._current(order)
        doc = load_geometry(self._store(), rev)
        return {"order": order, "revision": rev, "document": doc, "is_current": rev.id == order.current_sketch_revision_id,
                "can_undo": rev.parent_id is not None, "can_redo": self._redo_target(order, rev) is not None,
                "inputs_changed": bool(rev.inputs_hash) and rev.inputs_hash != inputs_hash(self.session, order)}

    def revisions(self, order_id: int) -> tuple[Order, list[SketchRevision]]:
        order = self.order(order_id)
        return order, list(self.session.scalars(select(SketchRevision).where(SketchRevision.order_id == order.id)
                                                .order_by(SketchRevision.seq)))

    def preview(self, order_id: int, page: int, revision_id: int | None = None) -> bytes:
        """JPEG of one page in the order's ink / pen width / paper, with the visible AI mark (U2)."""
        data = self.view(order_id, revision_id)
        order, doc = data["order"], data["document"]
        pages = geo.to_pages(doc)
        if not 1 <= page <= len(pages):
            raise AppError(404, "PAGE_NOT_FOUND", f"Phác thảo có {len(pages)} trang.")
        paper = self.catalog.paper(order.paper_type_id) if order.paper_type_id else None
        ink = self.catalog.ink(order.ink_color_id) if order.ink_color_id else None
        pen = self.catalog.pen(order.pen_type_id) if order.pen_type_id else None
        img = render_image.render_jpeg(pages[page - 1], ink_hex=ink.hex_code if ink else None,
                                       stroke_width_mm=float(pen.stroke_width_mm) if pen and pen.stroke_width_mm else None,
                                       paper_surface=paper.surface if paper else None)
        return watermark.apply_bytes(img, order.code, fmt="jpg")


def _describe(report: dict[str, Any]) -> str:
    names = {"translate": "Dời", "rotate": "Xoay", "scale": "Đổi cỡ", "slant": "Đổi độ nghiêng", "curvature": "Đổi độ cong",
             "smooth": "Làm mượt", "extend": "Kéo dài", "trim": "Cắt ngắn", "join": "Nối", "split": "Tách", "delete": "Xoá"}
    n = len(report["changed"]) + len(report["removed"])
    return f"{names.get(report['op'], report['op'])} {n} nét (trang {report['page']})"
