"""Shipping label PDF (UC-29 "in nhãn"). DejaVu Sans is bundled because the built-in PDF fonts cannot draw Vietnamese.

Real carriers print their own label; this one is used for the MOCK carrier, and it says so on the sheet."""
from pathlib import Path

from fpdf import FPDF

ASSETS = Path(__file__).resolve().parents[1] / "assets"


def render_label(*, waybill_code: str, carrier: str, service_name: str, order_code: str, receiver: str, phone: str,
                 address_line: str, weight_g: int, mock: bool) -> bytes:
    pdf = FPDF(format=(100, 150), unit="mm")                      # a common thermal-label size
    pdf.set_auto_page_break(False)
    pdf.add_font("dv", "", str(ASSETS / "fonts" / "DejaVuSans.ttf"))
    pdf.add_font("dv", "B", str(ASSETS / "fonts" / "DejaVuSans-Bold.ttf"))
    pdf.add_page()
    pdf.set_font("dv", "B", 13)
    pdf.cell(0, 7, f"{carrier} · {service_name}", new_x="LMARGIN", new_y="NEXT")
    pdf.set_font("dv", "B", 18)
    pdf.multi_cell(0, 9, waybill_code, new_x="LMARGIN", new_y="NEXT")
    pdf.set_font("dv", "", 9)
    pdf.cell(0, 5, f"Đơn hàng: {order_code}   ·   Khối lượng: {weight_g} g", new_x="LMARGIN", new_y="NEXT")
    pdf.ln(3)
    pdf.set_font("dv", "B", 10)
    pdf.cell(0, 6, "NGƯỜI NHẬN", new_x="LMARGIN", new_y="NEXT")
    pdf.set_font("dv", "", 11)
    pdf.multi_cell(0, 6, f"{receiver}\n{phone}\n{address_line}", new_x="LMARGIN", new_y="NEXT")
    pdf.ln(3)
    pdf.set_font("dv", "", 8)
    pdf.multi_cell(0, 4.5, "Gửi từ: Xưởng Nét Việt. Không thu hộ (COD). Hàng dễ gãy, vui lòng giữ phẳng.",
                   new_x="LMARGIN", new_y="NEXT")
    if mock:
        pdf.set_y(128)
        pdf.set_font("dv", "B", 11)
        pdf.set_text_color(200, 0, 0)
        pdf.cell(0, 6, "MÔ PHỎNG (MOCK): không phải vận đơn thật", align="C")
    return bytes(pdf.output())
