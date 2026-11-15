"""Upgrade U5: the only things the assistant can do. Every tool is deterministic code the forms already use.

* The model chooses a tool and its arguments; the server checks every argument exactly as the forms do (StudioService), so
  the model cannot invent a material (the ids come from the catalog), pick an incompatible pen, or reach another draft.
* A tool that changes the draft makes a revision with author AI and the tool's name, so the customer can undo it.
* Results are plain JSON for the model. No tool returns robot coordinates and no tool accepts any: stroke geometry only comes
  from the stroke engine.
* Not offered yet: reading the handwriting of a photo (no HTR model, docs/UPGRADE_AI_ROBOT_PLAN.md 4) and editing regions of a
  restoration (the Staff do it on the official sketch, U4).
"""
from __future__ import annotations

from typing import Any, Callable

from app.core.errors import AppError
from app.models.studio import StudioDraft
from app.services.ai.llm import ToolSpec
from app.services.studio import StudioService

FLAG_KINDS = ("FORGERY_RISK", "PRIVACY", "OTHER")
_TEXT_FOR_MODEL = 3000                       # characters of the draft text shown to the model


def _obj(props: dict[str, Any], required: list[str] | None = None) -> dict[str, Any]:
    out: dict[str, Any] = {"type": "object", "properties": props}
    if required:
        out["required"] = required
    return out


SPECS: list[ToolSpec] = [
    ToolSpec("get_draft", "Đọc bản nháp hiện tại: nội dung, vật tư đã chọn, các vấn đề còn thiếu và giá ước tính.", _obj({})),
    ToolSpec("list_materials",
             "Danh sách vật tư thật đang bán. Không có paper_type_id: trả các loại giấy. Có paper_type_id: trả các bút dùng "
             "được với giấy đó, mỗi bút kèm màu mực. Chỉ được dùng id lấy từ công cụ này.",
             _obj({"paper_type_id": {"type": "integer", "description": "id loại giấy đã chọn"}})),
    ToolSpec("list_templates", "Danh sách mẫu chữ đang bật (chỉ cho bản nháp soạn chữ).", _obj({})),
    ToolSpec("update_text",
             "Sửa nội dung chữ / mẫu chữ / cỡ chữ / căn lề của bản nháp soạn chữ. Chỉ gửi trường cần đổi. Chỉ đổi nội dung khi "
             "khách yêu cầu rõ; giữ nguyên câu chữ của khách.",
             _obj({"text": {"type": "string", "description": "toàn bộ nội dung mới"},
                   "template_id": {"type": "integer"},
                   "font_size_mm": {"type": "number", "description": "chiều cao chữ hoa, mm (4-100)"},
                   "alignment": {"type": "string", "enum": ["LEFT", "CENTER", "RIGHT", "JUSTIFY"]}})),
    ToolSpec("choose_materials",
             "Chọn giấy, bút, màu mực (id từ list_materials), hoặc để xưởng đề xuất vật tư.",
             _obj({"paper_type_id": {"type": "integer"}, "pen_type_id": {"type": "integer"},
                   "ink_color_id": {"type": "integer"}, "workshop_suggest_materials": {"type": "boolean"}})),
    ToolSpec("set_options",
             "Đổi số bản, dòng xác thực trên tờ giấy (bắt buộc với phục dựng ảnh), chế độ phục dựng, ghi chú cho xưởng.",
             _obj({"quantity": {"type": "integer", "description": "1-10000"},
                   "physical_watermark": {"type": "boolean"},
                   "restoration_mode": {"type": "string", "enum": ["FAITHFUL", "ASSISTED"]},
                   "customer_note": {"type": "string"}})),
    ToolSpec("check_draft",
             "Kiểm tra bản nháp như khi gửi xưởng: nội dung có vừa khổ giấy không, ký tự nào không viết được, còn thiếu gì, "
             "số trang và giá ước tính. Gọi sau khi sửa để báo khách kết quả thật.", _obj({})),
    ToolSpec("undo", "Hoàn tác thay đổi gần nhất của bản nháp (của khách hoặc của trợ lý).", _obj({})),
    ToolSpec("redo", "Làm lại thay đổi vừa hoàn tác.", _obj({})),
    ToolSpec("flag_for_staff",
             "Gắn cờ để nhân viên xưởng xem khi nhận đơn. Bắt buộc dùng FORGERY_RISK khi khách muốn làm giả chữ ký, giấy tờ, "
             "văn bản pháp lý hoặc mạo danh người khác.",
             _obj({"kind": {"type": "string", "enum": list(FLAG_KINDS)}, "note": {"type": "string"}}, ["kind", "note"])),
]
SPEC_NAMES = {s.name for s in SPECS}


class StudioTools:
    def __init__(self, studio: StudioService, draft: StudioDraft):
        self.studio, self.draft = studio, draft
        self.catalog = studio.catalog
        self._run: dict[str, Callable[[dict[str, Any]], tuple[dict[str, Any], int | None]]] = {
            "get_draft": self._get_draft, "list_materials": self._list_materials, "list_templates": self._list_templates,
            "update_text": self._update_text, "choose_materials": self._choose_materials, "set_options": self._set_options,
            "check_draft": self._check, "undo": self._undo, "redo": self._redo, "flag_for_staff": self._flag}

    def specs(self) -> list[ToolSpec]:
        if self.draft.mode == "TEXT":
            return SPECS
        return [s for s in SPECS if s.name not in ("list_templates", "update_text")]

    def run(self, name: str, args: dict[str, Any]) -> tuple[dict[str, Any], int | None, bool]:
        """(result for the model, revision id it made or None, ok). A refused call is a result, never an exception."""
        if name not in self._run or name not in {s.name for s in self.specs()}:
            return {"ok": False, "error": "UNKNOWN_TOOL", "message": f"Không có công cụ {name}."}, None, False
        if not isinstance(args, dict):
            return {"ok": False, "error": "INVALID_ARGS", "message": "Tham số phải là object."}, None, False
        try:
            result, rev = self._run[name](args)
            return {"ok": True, **result}, rev, True
        except AppError as exc:
            return {"ok": False, "error": exc.code, "message": exc.message,
                    **({"details": exc.details} if exc.details else {})}, None, False
        except (TypeError, ValueError) as exc:
            return {"ok": False, "error": "INVALID_ARGS", "message": str(exc)[:200]}, None, False

    # ------------------------------------------------------------------ read
    def summary(self) -> dict[str, Any]:
        c = self.studio.content(self.draft)
        cat = self.catalog
        paper = cat.paper(c["paper_type_id"]) if c.get("paper_type_id") else None
        pen = cat.pen(c["pen_type_id"]) if c.get("pen_type_id") else None
        ink = cat.ink(c["ink_color_id"]) if c.get("ink_color_id") else None
        tpl = cat.template(c["template_id"]) if c.get("template_id") else None
        out: dict[str, Any] = {
            "mode": self.draft.mode, "quantity": c.get("quantity"),
            "paper": {"id": paper.id, "name": paper.name, "size": paper.size.value} if paper else None,
            "pen": {"id": pen.id, "name": pen.name} if pen else None,
            "ink": {"id": ink.id, "name": ink.name} if ink else None,
            "workshop_suggest_materials": c.get("workshop_suggest_materials"),
            "physical_watermark": c.get("physical_watermark"), "customer_note": c.get("customer_note"),
            "can_undo": self.studio.can_undo(self.draft), "can_redo": self.studio.can_redo(self.draft)}
        if self.draft.mode == "TEXT":
            text = c.get("text") or ""
            out.update({"text": text[:_TEXT_FOR_MODEL], "text_truncated": len(text) > _TEXT_FOR_MODEL, "text_length": len(text),
                        "template": {"id": tpl.id, "name": tpl.name} if tpl else None,
                        "font_size_mm": c.get("font_size_mm"), "alignment": c.get("alignment"),
                        "has_styled_parts": bool((c.get("layout") or {}).get("spans")), "has_drawing": bool(c.get("canvas"))})
        else:
            out.update({"restoration_mode": c.get("restoration_mode"),
                        "images": [{"n": n + 1, "quality_warning": bool(i.get("is_quality_warning")),
                                    "quality": {k: v for k, v in (i.get("quality_result") or {}).items()
                                                if k in ("analysed", "sharpness", "brightness", "contrast", "chars_min", "chars_max", "reason")}}
                                   for n, i in enumerate(c.get("images") or [])]})
        return out

    def _get_draft(self, _: dict[str, Any]) -> tuple[dict[str, Any], None]:
        check = self.studio.check(self.draft, render=False)
        return {"draft": self.summary(), "problems": check["problems"], "estimate": _money(check["estimate"])}, None

    def _list_materials(self, a: dict[str, Any]) -> tuple[dict[str, Any], None]:
        cat = self.catalog
        if a.get("paper_type_id") is None:
            return {"papers": [{"id": p.id, "name": p.name, "size": p.size.value, "surface": p.surface, "gsm": p.gsm,
                                "unit_price": int(p.unit_price)} for p in cat.papers()]}, None
        paper = cat.paper(int(a["paper_type_id"]))
        if paper is None or not paper.is_active:
            raise AppError(404, "PAPER_NOT_FOUND", "Không tìm thấy loại giấy.")
        pens = []
        for pen in cat.pens_for_paper(paper.id):
            inks = cat.inks_for_pen(pen.id)
            if inks:
                pens.append({"id": pen.id, "name": pen.name, "category": pen.category, "surcharge": int(pen.surcharge),
                             "inks": [{"id": i.id, "name": i.name, "hex": i.hex_code} for i in inks]})
        return {"paper": {"id": paper.id, "name": paper.name}, "pens": pens}, None

    def _list_templates(self, _: dict[str, Any]) -> tuple[dict[str, Any], None]:
        return {"templates": [{"id": t.id, "name": t.name, "kind": t.kind.value} for t in self.catalog.templates()]}, None

    def _check(self, _: dict[str, Any]) -> tuple[dict[str, Any], None]:
        r = self.studio.check(self.draft, render=True)
        return {"ready": r["ready"], "problems": r["problems"], "pages": r["pages"], "estimate": _money(r["estimate"]),
                "note": "Bản xem trước là ước tính; xưởng làm phác thảo chính thức sau khi nhận đơn."}, None

    # ------------------------------------------------------------------ change
    def _revise(self, changes: dict[str, Any], tool: str, note: str) -> tuple[dict[str, Any], int | None]:
        rev, warnings = self.studio.revise(self.draft, changes, author="AI", tool=tool, note=note)
        return {"changed": rev is not None, "warnings": warnings, "draft": self.summary()}, rev.id if rev else None

    def _pick(self, a: dict[str, Any], keys: tuple[str, ...]) -> dict[str, Any]:
        ch = {k: a[k] for k in keys if k in a}
        if not ch:
            raise AppError(422, "NOTHING_TO_CHANGE", f"Cần ít nhất một trong {list(keys)}.")
        return ch

    def _update_text(self, a: dict[str, Any]) -> tuple[dict[str, Any], int | None]:
        return self._revise(self._pick(a, ("text", "template_id", "font_size_mm", "alignment")), "update_text", "Trợ lý sửa nội dung")

    def _choose_materials(self, a: dict[str, Any]) -> tuple[dict[str, Any], int | None]:
        return self._revise(self._pick(a, ("paper_type_id", "pen_type_id", "ink_color_id", "workshop_suggest_materials")),
                            "choose_materials", "Trợ lý chọn vật tư")

    def _set_options(self, a: dict[str, Any]) -> tuple[dict[str, Any], int | None]:
        return self._revise(self._pick(a, ("quantity", "physical_watermark", "restoration_mode", "customer_note")),
                            "set_options", "Trợ lý đổi tuỳ chọn")

    def _undo(self, _: dict[str, Any]) -> tuple[dict[str, Any], None]:
        self.studio.undo(self.draft)
        return {"draft": self.summary()}, None

    def _redo(self, _: dict[str, Any]) -> tuple[dict[str, Any], None]:
        self.studio.redo(self.draft)
        return {"draft": self.summary()}, None

    def _flag(self, a: dict[str, Any]) -> tuple[dict[str, Any], None]:
        kind = a.get("kind")
        if kind not in FLAG_KINDS:
            raise AppError(422, "INVALID_FLAG", f"kind phải là một trong {list(FLAG_KINDS)}.")
        self.studio.flag(self.draft, kind, str(a.get("note") or ""), by="AI")
        return {"flagged": kind}, None


def _money(est: dict[str, Any] | None) -> dict[str, Any] | None:
    if est is None:
        return None
    return {**est, "price_min": int(est["price_min"]), "price_max": int(est["price_max"]), "currency": "VND"}
