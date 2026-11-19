"""V2 Phase C: the assistant's tools on an order DRAFT (owner decision D1: the order is the source, not a studio draft).

Same rules as the studio tools (tools.py):
* The model picks a tool and its arguments; every argument is checked by the code the forms use (OrderService for content and
  materials, SketchWorkService + the Geometry Engine for strokes). The model never writes coordinates: `edit_strokes` takes an
  operation name, stroke / word ids and parameters inside the order type's limits (`sketch_geometry.Limits`).
* When the customer selected strokes / words on the FE and sent the selection with the message, `edit_strokes` may only touch
  that selection (`OUTSIDE_SELECTION` otherwise). Without a selection the model may name ids it read with `get_sketch`.
* Every stroke edit is a `sketch_revisions` row with author AI, the tool name, the provider and the model; the customer undoes
  it like any edit. Content / material changes are not revisions (the order form has no history): the result says what the
  value was before, and the sketch reports `inputs_changed` until it is drawn again.
* Nothing here submits, pays, cancels or reaches another order: those are not tools.
"""
from __future__ import annotations

from decimal import Decimal
from typing import Any, Callable

from app.core.errors import AppError
from app.models.order import Order, OrderInputKind, OrderType
from app.repositories.orders import OrderRepository
from app.services import audit
from app.services import sketch_geometry as geo
from app.services.ai.llm import ToolSpec
from app.services.ai.tools import FLAG_KINDS, _obj, list_materials, list_templates
from app.services.orders import OrderService
from app.services.sketch_work import SketchWorkService

_TEXT_FOR_MODEL = 3000
_WORDS_FOR_MODEL = 200            # words listed by get_sketch (ids, text, box); more -> truncated, the model is told
_STROKES_FOR_MODEL = 60           # strokes of the selection described individually

SPECS: list[ToolSpec] = [
    ToolSpec("get_order", "Đọc đơn hiện tại: loại đơn, nội dung, vật tư, giá ước tính, phác thảo hiện tại và vùng khách đang chọn.",
             _obj({})),
    ToolSpec("list_materials",
             "Danh sách vật tư thật đang bán. Không có paper_type_id: trả các loại giấy. Có paper_type_id: trả các bút dùng "
             "được với giấy đó, mỗi bút kèm màu mực. Chỉ được dùng id lấy từ công cụ này.",
             _obj({"paper_type_id": {"type": "integer", "description": "id loại giấy đã chọn"}})),
    ToolSpec("list_templates", "Danh sách mẫu chữ đang bật (đơn viết theo mẫu chữ).", _obj({})),
    ToolSpec("update_text",
             "Sửa nội dung chữ / mẫu chữ / cỡ chữ / căn lề của đơn viết theo mẫu. Chỉ gửi trường cần đổi. Chỉ đổi nội dung khi "
             "khách yêu cầu rõ; giữ nguyên câu chữ của khách. Không hoàn tác được bằng undo: kết quả có giá trị cũ.",
             _obj({"text": {"type": "string", "description": "toàn bộ nội dung mới"},
                   "template_id": {"type": "integer"},
                   "font_size_mm": {"type": "number", "description": "chiều cao chữ hoa, mm"},
                   "alignment": {"type": "string", "enum": ["LEFT", "CENTER", "RIGHT", "JUSTIFY"]}})),
    ToolSpec("choose_materials", "Chọn giấy, bút, màu mực (id từ list_materials), hoặc để xưởng đề xuất vật tư.",
             _obj({"paper_type_id": {"type": "integer"}, "pen_type_id": {"type": "integer"},
                   "ink_color_id": {"type": "integer"}, "workshop_suggest_materials": {"type": "boolean"}})),
    ToolSpec("set_options", "Đổi số bản, dòng xác thực trên tờ giấy, chế độ phục dựng (đơn phục dựng), ghi chú cho xưởng.",
             _obj({"quantity": {"type": "integer", "description": "1-10000"},
                   "physical_watermark": {"type": "boolean"},
                   "restoration_mode": {"type": "string", "enum": ["FAITHFUL", "ASSISTED"]},
                   "customer_note": {"type": "string"}})),
    ToolSpec("check_order",
             "Kiểm tra đơn như khi gửi: còn thiếu gì, phác thảo có cần tạo lại không, giá ước tính. Gọi sau khi sửa để báo "
             "khách kết quả thật.", _obj({})),
    ToolSpec("generate_sketch",
             "Tạo (lại) phác thảo nét từ nội dung đơn. Tạo lại thì các sửa nét trước đó không còn trong bản mới (vẫn hoàn tác "
             "được). Nếu khách đã sửa nét, hỏi khách trước khi tạo lại.", _obj({})),
    ToolSpec("get_sketch",
             "Đọc phác thảo hiện tại: các từ (id, chữ nếu biết, khung mm, số nét) theo từng trang, giới hạn sửa của loại đơn "
             "và chi tiết các nét khách đang chọn. Toạ độ mm, gốc góc trên trái, y hướng xuống.",
             _obj({"page": {"type": "integer", "description": "chỉ một trang (mặc định: tất cả)"}})),
    ToolSpec("edit_strokes",
             "Sửa hình học bằng MỘT lệnh có cấu trúc trên các nét (stroke_ids) hoặc cả từ (word_ids). Không bao giờ gửi toạ độ. "
             "op và params: translate {dx_mm, dy_mm}; rotate {degrees}; scale {factor}; slant {degrees, dương = nghiêng "
             "phải}; curvature {factor: 1 giữ nguyên, <1 thẳng bớt, >1 cong thêm}; smooth {passes 1-5}; extend / trim "
             "{mm, end: start|end}; join (đúng 2 nét); split {at 0.05-0.95}; delete. Tham số phải nằm trong limits của "
             "get_sketch. Khi khách đã chọn vùng, chỉ được sửa trong vùng đó.",
             _obj({"op": {"type": "string", "enum": list(geo.OPS)},
                   "stroke_ids": {"type": "array", "items": {"type": "string"}},
                   "word_ids": {"type": "array", "items": {"type": "string"}},
                   "params": {"type": "object", "description": "tham số của lệnh, ví dụ {\"dx_mm\": 1.5}"},
                   "note": {"type": "string", "description": "mô tả ngắn cho lịch sử, tiếng Việt"}}, ["op"])),
    ToolSpec("undo_sketch", "Hoàn tác thay đổi phác thảo gần nhất (của khách hoặc của trợ lý).", _obj({})),
    ToolSpec("redo_sketch", "Làm lại thay đổi phác thảo vừa hoàn tác.", _obj({})),
    ToolSpec("flag_for_staff",
             "Gắn cờ để nhân viên xưởng xem khi nhận đơn. Bắt buộc dùng FORGERY_RISK khi khách muốn làm giả chữ ký, giấy tờ, "
             "văn bản pháp lý hoặc mạo danh người khác.",
             _obj({"kind": {"type": "string", "enum": list(FLAG_KINDS)}, "note": {"type": "string"}}, ["kind", "note"])),
]


class OrderTools:
    kind = "order"
    revision_field = "sketch_revision_id"

    def __init__(self, orders: OrderService, work: SketchWorkService, order_id: int, ai_session: Any,
                 selection: dict[str, list[str]] | None = None):
        self.orders, self.work, self.order_id, self.ai_session = orders, work, order_id, ai_session
        self.session, self.catalog = orders.session, orders.catalog
        self.selection = {"stroke_ids": list((selection or {}).get("stroke_ids") or []),
                          "word_ids": list((selection or {}).get("word_ids") or [])}
        self.provider: str | None = None
        self.model: str | None = None
        self._run: dict[str, Callable[[dict[str, Any]], tuple[dict[str, Any], int | None]]] = {
            "get_order": self._get_order, "list_materials": self._list_materials, "list_templates": self._list_templates,
            "update_text": self._update_text, "choose_materials": self._choose_materials, "set_options": self._set_options,
            "check_order": self._check, "generate_sketch": self._generate, "get_sketch": self._get_sketch,
            "edit_strokes": self._edit, "undo_sketch": self._undo, "redo_sketch": self._redo, "flag_for_staff": self._flag}

    def bind(self, provider: Any) -> None:
        self.provider, self.model = provider.name, provider.model

    def order(self) -> Order:
        return self.work.order(self.order_id)

    def specs(self) -> list[ToolSpec]:
        t = self.order().order_type
        hide = set()
        if t != OrderType.OT3_TEMPLATE:
            hide |= {"list_templates", "update_text"}
        if t == OrderType.OT2_LEARNED_STYLE:                 # no automatic sketch yet (R&D, owner decision on OT-2)
            hide |= {"generate_sketch"}
        return [s for s in SPECS if s.name not in hide]

    def run(self, name: str, args: dict[str, Any]) -> tuple[dict[str, Any], int | None, bool]:
        """(result for the model, sketch revision id it made or None, ok). A refused call is a result, never an exception.
        A refused write is rolled back to a savepoint, so a half-made change never stays."""
        if name not in self._run or name not in {s.name for s in self.specs()}:
            return {"ok": False, "error": "UNKNOWN_TOOL", "message": f"Không có công cụ {name}."}, None, False
        if not isinstance(args, dict):
            return {"ok": False, "error": "INVALID_ARGS", "message": "Tham số phải là object."}, None, False
        sp = self.session.begin_nested()
        try:
            result, rev = self._run[name](args)
            sp.commit()
            return {"ok": True, **result}, rev, True
        except AppError as exc:
            sp.rollback()
            return {"ok": False, "error": exc.code, "message": exc.message,
                    **({"details": exc.details} if exc.details else {})}, None, False
        except (TypeError, ValueError, KeyError) as exc:
            sp.rollback()
            return {"ok": False, "error": "INVALID_ARGS", "message": str(exc)[:200]}, None, False

    # ------------------------------------------------------------------ read
    def _text_row(self, order: Order):
        return next((r for r in OrderRepository(self.session).inputs(order.id) if r.kind == OrderInputKind.TEXT_CONTENT), None)

    def summary(self) -> dict[str, Any]:
        order = self.order()
        cat = self.catalog
        paper = cat.paper(order.paper_type_id) if order.paper_type_id else None
        pen = cat.pen(order.pen_type_id) if order.pen_type_id else None
        ink = cat.ink(order.ink_color_id) if order.ink_color_id else None
        out: dict[str, Any] = {
            "order_code": order.code, "order_type": order.order_type.value, "status": order.order_status.value,
            "quantity": order.quantity,
            "paper": {"id": paper.id, "name": paper.name, "size": paper.size.value} if paper else None,
            "pen": {"id": pen.id, "name": pen.name} if pen else None,
            "ink": {"id": ink.id, "name": ink.name} if ink else None,
            "workshop_suggest_materials": order.workshop_suggest_materials,
            "physical_watermark": order.physical_watermark, "customer_note": order.customer_note,
            "estimate": _estimate(order)}
        inputs = OrderRepository(self.session).inputs(order.id)
        if order.order_type == OrderType.OT1_COPY_RESTORE:
            out["restoration_mode"] = order.restoration_mode
            out["images"] = [{"n": n + 1, "quality_warning": bool(r.is_quality_warning),
                              "quality": {k: v for k, v in (r.quality_result or {}).items()
                                          if k in ("analysed", "sharpness", "brightness", "contrast", "reason")}}
                             for n, r in enumerate(x for x in inputs if x.kind == OrderInputKind.ORIGINAL_IMAGE)]
        else:
            row = self._text_row(order)
            text = (row.text_content if row else None) or ""
            tpl = cat.template(row.template_id) if row and row.template_id else None
            out.update({"text": text[:_TEXT_FOR_MODEL], "text_truncated": len(text) > _TEXT_FOR_MODEL,
                        "template": {"id": tpl.id, "name": tpl.name} if tpl else None,
                        "font_size_mm": float(row.font_size_mm) if row and row.font_size_mm is not None else None,
                        "alignment": row.alignment if row else None,
                        "has_styled_parts": bool(((row.layout if row else None) or {}).get("spans")),
                        "has_drawing": any(x.kind == OrderInputKind.CANVAS for x in inputs)})
        out["sketch"] = self._sketch_brief(order)
        out["selection"] = self.selection if (self.selection["stroke_ids"] or self.selection["word_ids"]) else None
        return out

    def _sketch_brief(self, order: Order) -> dict[str, Any] | None:
        if order.current_sketch_revision_id is None:
            return None
        v = self.work.view(order.id)
        rev, doc = v["revision"], v["document"]
        return {"revision_id": rev.id, "seq": rev.seq, "author": rev.author, "inputs_changed": v["inputs_changed"],
                "can_undo": v["can_undo"], "can_redo": v["can_redo"], "pages": len(doc["pages"]),
                "words": sum(len(p["words"]) for p in doc["pages"]), "strokes": sum(len(p["strokes"]) for p in doc["pages"]),
                "metrics": {k: (rev.metrics or {}).get(k) for k in ("total_stroke_mm", "pen_lift_count", "estimated_writing_sec")}}

    def _get_order(self, _: dict[str, Any]) -> tuple[dict[str, Any], None]:
        return {"order": self.summary()}, None

    def _list_materials(self, a: dict[str, Any]) -> tuple[dict[str, Any], None]:
        return list_materials(self.catalog, a), None

    def _list_templates(self, _: dict[str, Any]) -> tuple[dict[str, Any], None]:
        return list_templates(self.catalog), None

    def _check(self, _: dict[str, Any]) -> tuple[dict[str, Any], None]:
        order = self.order()
        problems: list[dict[str, Any]] = []
        try:
            self.orders._validate_complete(order, OrderRepository(self.session).inputs(order.id), True)
        except AppError as exc:
            problems = list(exc.details or [])
        brief = self._sketch_brief(order)
        if brief and brief["inputs_changed"]:
            problems.append({"field": "sketch", "message": "Nội dung đã đổi sau khi tạo phác thảo; cần tạo lại phác thảo."})
        return {"ready": not problems, "problems": problems, "estimate": _estimate(order), "sketch": brief,
                "note": "Giá là ước tính; xưởng báo giá chính thức sau khi nhận đơn. Khách tự bấm Gửi đơn."}, None

    def _get_sketch(self, a: dict[str, Any]) -> tuple[dict[str, Any], None]:
        order = self.order()
        v = self.work.view(order.id)
        doc = v["document"]
        only = a.get("page")
        pages, listed = [], 0
        for p in doc["pages"]:
            if only is not None and p["no"] != int(only):
                continue
            words = []
            for w in p["words"]:
                if listed >= _WORDS_FOR_MODEL:
                    break
                listed += 1
                words.append({"id": w["id"], "text": w.get("text"), "bbox": w["bbox"], "strokes": len(w["stroke_ids"]),
                              **({"label": w["label"]} if w.get("label") else {})})
            loose = [st["id"] for st in p["strokes"] if not st.get("word")]
            pages.append({"no": p["no"], "width_mm": p["width_mm"], "height_mm": p["height_mm"], "words": words,
                          "strokes_without_word": loose[:50]})
        total = sum(len(p["words"]) for p in doc["pages"])
        sel = self._selected_strokes(doc)
        lim = geo.limits_for(order.order_type.value)
        return {"revision_id": v["revision"].id, "inputs_changed": v["inputs_changed"], "pages": pages,
                "words_truncated": listed < total if only is None else False,
                "limits": {"max_shift_mm": lim.max_shift_mm, "max_rotate_deg": lim.max_rotate_deg,
                           "scale_range": list(lim.scale_range), "max_slant_deg": lim.max_slant_deg,
                           "curvature_range": list(lim.curvature_range), "max_extend_mm": lim.max_extend_mm,
                           "max_join_gap_mm": lim.max_join_gap_mm},
                "selection": [_describe_stroke(st) for st in sel[:_STROKES_FOR_MODEL]] if sel else None}, None

    def _selected_strokes(self, doc: dict[str, Any]) -> list[dict[str, Any]]:
        ids = set(self._selected_ids(doc))
        return [st for p in doc["pages"] for st in p["strokes"] if st["id"] in ids]

    def _selected_ids(self, doc: dict[str, Any]) -> list[str]:
        ids = list(self.selection["stroke_ids"])
        if self.selection["word_ids"]:
            ids += geo.word_strokes(doc, self.selection["word_ids"])
        return ids

    # ------------------------------------------------------------------ change: content
    def _pick(self, a: dict[str, Any], keys: tuple[str, ...]) -> dict[str, Any]:
        ch = {k: a[k] for k in keys if k in a}
        if not ch:
            raise AppError(422, "NOTHING_TO_CHANGE", f"Cần ít nhất một trong {list(keys)}.")
        return ch

    def _after_change(self, order: Order, before: dict[str, Any], warnings: list[str]) -> dict[str, Any]:
        brief = self._sketch_brief(order)
        return {"before": before, "warnings": warnings, "order": self.summary(),
                "sketch_outdated": bool(brief and brief["inputs_changed"])}

    def _update_text(self, a: dict[str, Any]) -> tuple[dict[str, Any], None]:
        ch = self._pick(a, ("text", "template_id", "font_size_mm", "alignment"))
        order = self.order()
        row = self._text_row(order)
        cur = {"text_content": row.text_content if row else "", "template_id": row.template_id if row else None,
               "handwriting_style_id": row.handwriting_style_id if row else None,
               "font_size_mm": row.font_size_mm if row else None, "alignment": row.alignment if row else None,
               "layout": row.layout if row else None}
        before = {"text": cur["text_content"], "template_id": cur["template_id"],
                  "font_size_mm": float(cur["font_size_mm"]) if cur["font_size_mm"] is not None else None,
                  "alignment": cur["alignment"]}
        new = dict(cur)
        warnings: list[str] = []
        if "text" in ch:
            new["text_content"] = str(ch["text"])
            if new["text_content"] != cur["text_content"] and (cur["layout"] or {}).get("spans"):
                new["layout"] = {k: v for k, v in cur["layout"].items() if k != "spans"}   # offsets of the old text
                warnings.append("STYLED_PARTS_RESET")
        if "template_id" in ch:
            new["template_id"] = int(ch["template_id"])
        if "font_size_mm" in ch:
            new["font_size_mm"] = Decimal(str(ch["font_size_mm"]))
        if "alignment" in ch:
            new["alignment"] = ch["alignment"]
        self.orders.set_text(order.id, new)
        return self._after_change(self.order(), before, warnings), None

    def _update(self, ch: dict[str, Any]) -> tuple[dict[str, Any], None]:
        order = self.order()
        before = {k: getattr(order, k) for k in ch}
        _, warnings = self.orders.update(order.id, ch)
        return self._after_change(self.order(), _jsonable_before(before), warnings), None

    def _choose_materials(self, a: dict[str, Any]) -> tuple[dict[str, Any], None]:
        return self._update(self._pick(a, ("paper_type_id", "pen_type_id", "ink_color_id", "workshop_suggest_materials")))

    def _set_options(self, a: dict[str, Any]) -> tuple[dict[str, Any], None]:
        ch = self._pick(a, ("quantity", "physical_watermark", "restoration_mode", "customer_note"))
        if "quantity" in ch and not (isinstance(ch["quantity"], int) and 1 <= ch["quantity"] <= 10000):
            raise AppError(422, "INVALID_QUANTITY", "Số bản phải từ 1 đến 10000.")
        if "customer_note" in ch and ch["customer_note"] is not None:
            ch["customer_note"] = str(ch["customer_note"])[:2000]
        return self._update(ch)

    # ------------------------------------------------------------------ change: sketch
    def _generate(self, _: dict[str, Any]) -> tuple[dict[str, Any], int]:
        rev, doc, warnings = self.work.generate(self.order_id)
        self.selection = {"stroke_ids": [], "word_ids": []}           # the old ids do not exist in a new generation
        return {"revision_id": rev.id, "seq": rev.seq, "warnings": warnings, "pages": len(doc["pages"]),
                "words": sum(len(p["words"]) for p in doc["pages"]),
                "note": "Phác thảo mới có bộ id mới; vùng chọn cũ không còn."}, rev.id

    def _edit(self, a: dict[str, Any]) -> tuple[dict[str, Any], int]:
        op = a.get("op")
        if op not in geo.OPS:
            raise AppError(422, "INVALID_EDIT", f"op phải là một trong {list(geo.OPS)}.")
        stroke_ids = [str(x) for x in (a.get("stroke_ids") or [])]
        word_ids = [str(x) for x in (a.get("word_ids") or [])]
        params = a.get("params") or {}
        if not isinstance(params, dict):
            raise AppError(422, "INVALID_EDIT_PARAMS", "params phải là object.")
        order = self.order()
        current = self.work.view(order.id)
        if self.selection["stroke_ids"] or self.selection["word_ids"]:
            doc = current["document"]
            allowed = set(self._selected_ids(doc))
            wanted = set(stroke_ids) | set(geo.word_strokes(doc, word_ids) if word_ids else [])
            if not wanted <= allowed:
                raise AppError(403, "OUTSIDE_SELECTION",
                               "Chỉ được sửa các nét / từ khách đang chọn.", {"not_selected": sorted(wanted - allowed)[:20]})
        note = str(a.get("note") or "")[:200] or None
        rev, _doc, report = self.work.edit(order.id, base_revision_id=current["revision"].id, op=op, stroke_ids=stroke_ids,
                                           word_ids=word_ids, params=params, note=note, author="AI", tool="edit_strokes",
                                           provider=self.provider, model=self.model)
        return {"revision_id": rev.id, "seq": rev.seq, "note": rev.note,
                "report": {k: report.get(k) for k in ("op", "page", "changed", "added", "removed", "max_point_shift_mm",
                                                      "untouched_verified")}}, rev.id

    def _undo(self, _: dict[str, Any]) -> tuple[dict[str, Any], None]:
        rev = self.work.undo(self.order_id)
        return {"revision_id": rev.id, "seq": rev.seq}, None

    def _redo(self, _: dict[str, Any]) -> tuple[dict[str, Any], None]:
        rev = self.work.redo(self.order_id)
        return {"revision_id": rev.id, "seq": rev.seq}, None

    def _flag(self, a: dict[str, Any]) -> tuple[dict[str, Any], None]:
        kind = a.get("kind")
        if kind not in FLAG_KINDS:
            raise AppError(422, "INVALID_FLAG", f"kind phải là một trong {list(FLAG_KINDS)}.")
        from datetime import datetime, timezone
        entry = {"kind": kind, "note": str(a.get("note") or "")[:500], "by": "AI",
                 "at": datetime.now(timezone.utc).isoformat()}
        self.ai_session.flags = [*(self.ai_session.flags or []), entry]
        self.session.flush()
        audit.record(self.session, actor_id=self.orders.customer.id, action="AI_FLAG", entity_type="order",
                     entity_id=self.order_id, new={"kind": kind}, ip=self.orders.ip)
        return {"flagged": kind}, None


def _estimate(order: Order) -> dict[str, Any] | None:
    if order.estimated_price_min is None:
        return None
    return {"price_min": int(order.estimated_price_min), "price_max": int(order.estimated_price_max or order.estimated_price_min),
            "currency": "VND", "is_estimate": True}


def _describe_stroke(st: dict[str, Any]) -> dict[str, Any]:
    pts = st["points"]
    length = sum(((pts[i + 1][0] - pts[i][0]) ** 2 + (pts[i + 1][1] - pts[i][1]) ** 2) ** 0.5 for i in range(len(pts) - 1))
    xs, ys = [p[0] for p in pts], [p[1] for p in pts]
    return {"id": st["id"], "word": st.get("word"), "kind": st["kind"], "points": len(pts), "length_mm": round(length, 2),
            "start": pts[0], "end": pts[-1], "bbox": [min(xs), min(ys), max(xs), max(ys)]}


def _jsonable_before(d: dict[str, Any]) -> dict[str, Any]:
    out = {}
    for k, v in d.items():
        out[k] = int(v) if isinstance(v, Decimal) else (v.value if hasattr(v, "value") else v)
    return out
