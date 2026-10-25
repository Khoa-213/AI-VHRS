"""Seed the workshop master data on the database configured in BE/.env (Supabase).

Idempotent and non-destructive: every insert is ON CONFLICT DO NOTHING, so re-running never overwrites
what the Manager / Admin edited later. Run from BE/:

    .venv/bin/python scripts/seed_workshop_data.py            # apply
    .venv/bin/python scripts/seed_workshop_data.py --dry-run  # show what would be inserted

ASSUMPTIONS to be replaced by the workshop: the prices and stock quantities below are starting values
(the SRS only gives illustrative prices); paper/pen compatibility follows BR-06; the privacy policy text is
a DRAFT derived from BR-23, BR-24, NFR-09 and NFR-12 and must be reviewed by the owner before launch.
Pen force profiles and the demo accounts already come from the baseline SQL and are not touched here.
"""
import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sqlalchemy import text  # noqa: E402

from app.db.session import get_engine  # noqa: E402

# (code, name, gsm, surface, size, unit_price VND, stock)
PAPERS = [
    ("PLAIN80_A4", "Giấy trắng 80 gsm A4", 80, "PLAIN", "A4", 1000, 500),
    ("PLAIN80_A5", "Giấy trắng 80 gsm A5", 80, "PLAIN", "A5", 600, 500),
    ("ART120_A4", "Giấy mỹ thuật 120 gsm A4", 120, "ART", "A4", 15000, 200),
    ("ART120_A5", "Giấy mỹ thuật 120 gsm A5", 120, "ART", "A5", 8000, 300),
    ("COATED150_A4", "Giấy couché bóng 150 gsm A4", 150, "COATED", "A4", 6000, 100),
    ("CARD250_A5", "Giấy thiệp 250 gsm A5", 250, "CARD", "A5", 12000, 200),
    ("CARD250_A6", "Giấy thiệp 250 gsm A6", 250, "CARD", "A6", 7000, 300),
]
# pen code -> (surcharge VND, stock); only applied while the pen is still untouched (surcharge = 0, stock = 0)
PEN_PRICES = {"BALL07": (2000, 100), "GEL05": (5000, 100), "FINE03": (6000, 100), "FOUNT": (10000, 100),
              "BRUSH": (15000, 100)}
# pen code -> [(ink name, hex)]
INKS = {
    "BALL07": [("Đen", "#000000"), ("Xanh dương", "#1F3A93"), ("Đỏ", "#C0392B")],
    "GEL05": [("Đen", "#000000"), ("Xanh dương", "#1F3A93"), ("Đỏ", "#C0392B")],
    "FINE03": [("Đen", "#000000"), ("Xanh dương", "#1F3A93")],
    "FOUNT": [("Đen", "#000000"), ("Xanh đen", "#1B2A49")],
    "BRUSH": [("Đen", "#000000")],
}
# single-line fonts (Hershey, public domain); font_uri is resolved by services/stroke_ai/text_to_stroke.py
TEMPLATES = [
    ("HERSHEY_SIMPLEX", "Nét đơn – Đứng thanh", "hershey:futural", "SINGLE_LINE_FONT", None),
    ("HERSHEY_ROMAN", "Nét đơn – La Mã", "hershey:rowmans", "SINGLE_LINE_FONT", None),
    ("HERSHEY_SCRIPT", "Nét đơn – Thư pháp ngả", "hershey:scripts", "SINGLE_LINE_FONT", None),
    ("HERSHEY_CURSIVE", "Nét đơn – Viết tay liền nét", "hershey:cursive", "SINGLE_LINE_FONT", None),
    # Outline fonts (SIL OFL) thinned to pen strokes. The font file, LICENSE.txt, glyph cache and preview.png must exist in Storage under
    # fonts/<slug>/: upload them with `scripts/add_outline_font.py --apply` (it also inserts these rows). Registry: app/assets/fonts/REGISTRY.md
    ("PLAYPEN_SANS", "Playpen Sans", "outline:fonts/playpen-sans/PlaypenSans.ttf", "TYPOGRAPHY", "fonts/playpen-sans/preview.png"),
    ("PANGOLIN", "Pangolin", "outline:fonts/pangolin/Pangolin-Regular.ttf", "TYPOGRAPHY", "fonts/pangolin/preview.png"),
    ("PATRICK_HAND", "Patrick Hand", "outline:fonts/patrick-hand/PatrickHand-Regular.ttf", "TYPOGRAPHY", "fonts/patrick-hand/preview.png"),
    ("MALI_LIGHT", "Mali Light", "outline:fonts/mali-light/Mali-Light.ttf", "TYPOGRAPHY", "fonts/mali-light/preview.png"),
]
SETTINGS = {
    # LI-10 / Phiếu đăng ký: Creative writing (OT-2) is R&D, so customers can only order OT-1 and OT-3 for now.
    "order_types_enabled": (["OT1_COPY_RESTORE", "OT3_TEMPLATE"],
                            "LI-10: loại đơn đang nhận. Thêm OT2_LEARNED_STYLE để bật lại loại Sáng tạo."),
    "privacy_policy": ({
        "version": "1.0",
        "title": "Chính sách riêng tư – Xưởng Nét Việt",
        "body": (
            "1. Dữ liệu chúng tôi nhận: ảnh bản gốc, mẫu chữ viết tay, nội dung chữ, hình vẽ, thông tin liên hệ và "
            "địa chỉ giao hàng bạn cung cấp cho đơn.\n"
            "2. Mục đích: chỉ dùng để thực hiện đơn của bạn (phục dựng nét, sinh phác thảo, báo giá, viết bằng robot, "
            "giao hàng). Không dùng cho mục đích khác.\n"
            "3. Thời hạn lưu: ảnh và bộ nét của bạn bị xóa sau 90 ngày kể từ khi đơn hoàn tất, trừ khi bạn đồng ý "
            "để xưởng lưu bộ nét.\n"
            "4. Xưởng không nhận viết chữ ký, giấy tờ pháp lý hoặc văn bản có dấu hiệu giả mạo.\n"
            "5. Bạn xác nhận có quyền sử dụng tài liệu và nét chữ bạn gửi lên.\n"
            "6. Thanh toán thực hiện qua cổng thanh toán; xưởng không lưu thông tin thẻ hay tài khoản ngân hàng.\n"
            "7. Mọi thay đổi trạng thái, giá và lịch sản xuất của đơn được ghi nhật ký (ai, khi nào, lý do).")},
        "Chính sách riêng tư hiện hành (FR-52). BẢN NHÁP: chủ xưởng cần duyệt trước khi vận hành."),
}


# Phase 3. ASSUMPTION: one Fairino FR3 at one writing station (the project's robot); the Manager edits or adds robots.
# This is only a database row: nothing here talks to the robot.
ROBOTS = [("FR3-01", "FAIRINO_FR3", "Bàn viết 1")]
SETTINGS.update({
    "working_hours": ({"days": [1, 2, 3, 4, 5, 6], "start": "08:00", "end": "17:00", "utc_offset_min": 420},
                      "Giờ làm việc của xưởng cho lập lịch sản xuất (ISO weekday 1=T2; giờ địa phương = UTC + utc_offset_min). "
                      "GIẢ ĐỊNH: T2–T7, 08:00–17:00; Manager cần xác nhận."),
    "schedule_params": ({"prep_min": 15, "photo_min": 5, "lead_min": 60, "eta_buffer_days": 2},
                        "Tham số lập lịch: chuẩn bị 15', chụp ảnh 5' (FR-40); bắt đầu sớm nhất sau lead_min phút; "
                        "ETA = ngày viết xong + eta_buffer_days. GIẢ ĐỊNH, cần xác nhận."),
})


def compatible(gsm: int, surface: str, pen_category: str) -> tuple[bool, str | None]:
    """BR-06 default compatibility rules."""
    if gsm <= 80 and pen_category in ("BRUSH", "MARKER"):
        return False, "Giấy ≤ 80 gsm: bút lông/bút dạ đậm làm thấm, rách giấy (BR-06)"
    if surface in ("GLOSSY", "COATED") and pen_category == "FOUNTAIN":
        return False, "Giấy bóng/couché: mực bút máy không bám (BR-06)"
    if gsm >= 250 and pen_category not in ("GEL", "BALLPOINT", "FINELINER"):
        return False, "Thiệp ≥ 250 gsm chỉ dùng bút gel, bút bi, bút kim (BR-06)"
    return True, None


def run(dry: bool) -> None:
    engine = get_engine()
    with engine.connect() as c:
        tx = c.begin()
        counts: dict[str, int] = {}

        def exec_count(label: str, sql: str, params: dict) -> None:
            n = c.execute(text(sql), params).rowcount
            counts[label] = counts.get(label, 0) + max(n, 0)

        for code, name, gsm, surface, size, price, stock in PAPERS:
            exec_count("paper_types", """insert into paper_types (code,name,gsm,surface,size,unit_price,stock_qty)
                values (:c,:n,:g,:s,:z,:p,:k) on conflict (code) do nothing""",
                       dict(c=code, n=name, g=gsm, s=surface, z=size, p=price, k=stock))
        for code, (price, stock) in PEN_PRICES.items():
            exec_count("pen_types updated", """update pen_types set surcharge=:p, stock_qty=:k, updated_at=now()
                where code=:c and surcharge=0 and stock_qty=0""", dict(c=code, p=price, k=stock))
        for code, inks in INKS.items():
            for name, hex_code in inks:
                exec_count("ink_colors", """insert into ink_colors (pen_type_id,name,hex_code,unit_price,stock_qty)
                    select id,:n,:h,0,100 from pen_types where code=:c on conflict (pen_type_id,name) do nothing""",
                           dict(c=code, n=name, h=hex_code))
        for code, name, uri, kind, preview in TEMPLATES:
            exec_count("templates", """insert into templates (code,name,kind,font_uri,preview_url)
                values (:c,:n,cast(:k as template_kind),:u,:p) on conflict (code) do nothing""",
                       dict(c=code, n=name, u=uri, k=kind, p=preview))

        for code, robot_type, station in ROBOTS:
            exec_count("robots", """insert into robots (code,robot_type,station,status,is_simulated)
                values (:c,:t,:s,'AVAILABLE',false) on conflict (code) do nothing""", dict(c=code, t=robot_type, s=station))

        papers = c.execute(text("select id,gsm,surface::text from paper_types where code = any(:codes)"),
                           {"codes": [p[0] for p in PAPERS]}).all()
        pens = c.execute(text("select id,category::text from pen_types where code = any(:codes)"),
                         {"codes": list(PEN_PRICES)}).all()
        for pid, gsm, surface in papers:
            for qid, category in pens:
                ok, note = compatible(gsm, surface, category)
                exec_count("paper_pen_compats", """insert into paper_pen_compats (paper_type_id,pen_type_id,is_compatible,note)
                    values (:a,:b,:ok,:note) on conflict (paper_type_id,pen_type_id) do nothing""",
                           dict(a=pid, b=qid, ok=ok, note=note))
        for key, (value, description) in SETTINGS.items():
            exec_count("system_settings", """insert into system_settings (key,value,description)
                values (:k, cast(:v as jsonb), :d) on conflict (key) do nothing""",
                       dict(k=key, v=json.dumps(value, ensure_ascii=False), d=description))

        print(("DRY RUN - rolled back. " if dry else "Applied. ") + "Rows inserted/updated:")
        for k, v in counts.items():
            print(f"  {k:20s} {v}")
        tx.rollback() if dry else tx.commit()


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    run(ap.parse_args().dry_run)
