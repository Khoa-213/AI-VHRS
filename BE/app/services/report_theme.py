"""Shared look and wording for exported reports (FR-50: Excel and PDF of the Manager report).

Colours are the workshop palette of the web app (`FE/src/components/ws/ws.css`, the screens Managers work in): one accent
(`--acc`), dark ink for text and table heads, warm neutral lines and fills, green / red only for state. Both the Excel and
the PDF builder read from here, so the two files cannot drift apart. Formatting helpers only change how a value is shown;
they never round or recompute a figure.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path
from typing import Any

ASSETS = Path(__file__).resolve().parents[1] / "assets"
LOGO = ASSETS / "report_logo.png"          # cropped from FE/src/assets/logo-light.png (the official AI-VHRS mark)
BRAND = "AI-VHRS"
WORKSHOP = "Xưởng Nét Việt"
SOURCE = "Số liệu đọc trực tiếp từ cơ sở dữ liệu vận hành AI-VHRS tại thời điểm xuất, không qua bộ nhớ đệm."


@dataclass(frozen=True)
class Palette:
    accent: str = "D4401B"        # ws --acc
    accent_soft: str = "FBE7E2"   # ws --acc-soft (13 % accent on white)
    accent_mid: str = "EFB6A8"    # ws --acc-mid (38 % accent on white)
    ink: str = "201F23"           # ws --ink: titles, table heads
    ink2: str = "45515C"          # ws --ink2: body text
    ink3: str = "596269"          # ws --ink3: captions, labels
    muted: str = "8A9097"         # empty values
    line: str = "E9E7E1"          # ws --line: row rules
    field: str = "F4F3EF"         # ws --field: tiles, metadata band
    zebra: str = "FAF9F6"         # half-way between white and --field: alternate rows
    green: str = "395917"         # ws --green3
    green_soft: str = "E6EFEA"    # ws --green1
    danger: str = "C81E1E"        # theme --danger (light)
    danger_soft: str = "FBE4E4"


C = Palette()


def rgb(hex6: str) -> tuple[int, int, int]:
    return int(hex6[0:2], 16), int(hex6[2:4], 16), int(hex6[4:6], 16)


GROUP_LABEL = {"day": "ngày", "week": "tuần", "month": "tháng"}
BUCKET_HEAD = {"day": "Ngày", "week": "Tuần (từ thứ Hai)", "month": "Tháng"}
ORDER_TYPE_LABEL = {"OT1_COPY_RESTORE": "Sao chép / phục dựng chữ viết tay",   # same wording as services/certificates.py
                    "OT2_LEARNED_STYLE": "Viết theo nét chữ đã học",
                    "OT3_TEMPLATE": "Viết theo mẫu chữ"}

# Excel number formats. Money is whole đồng; the unit sits in the column title so the cells stay plain numbers.
XL_MONEY = '#,##0;[Red]-#,##0;0'
XL_INT = '#,##0'
XL_PCT = '0.0%'
XL_DATE = 'dd/mm/yyyy'
XL_MONTH = 'mm/yyyy'
XL_DATETIME = 'dd/mm/yyyy hh:mm'


def d(v: Any) -> str:
    """dd/mm/yyyy; '' for nothing."""
    return v.strftime("%d/%m/%Y") if isinstance(v, (date, datetime)) else ("" if v is None else str(v))


def bucket(v: Any, group: str) -> str:
    if group == "month" and isinstance(v, (date, datetime)):
        return v.strftime("%m/%Y")
    if group == "week" and isinstance(v, (date, datetime)):
        return f"Tuần {d(v)}"
    return d(v)


def money(v: Any, unit: bool = False) -> str:
    """1500000 -> '1.500.000' (Vietnamese grouping); negatives keep their sign."""
    n = int(v or 0)
    s = f"{abs(n):,}".replace(",", ".")
    return ("-" if n < 0 else "") + s + (" đ" if unit else "")


def num(v: Any) -> str:
    return f"{int(v or 0):,}".replace(",", ".")


def pct(v: float | None) -> str:
    return "–" if v is None else f"{v * 100:.1f}%".replace(".", ",")


def period_text(rep: dict[str, Any]) -> str:
    return f"Từ {d(rep['from'])} đến {d(rep['to'])}"


def group_text(rep: dict[str, Any]) -> str:
    return f"Gom theo {GROUP_LABEL.get(rep['group'], rep['group'])}"


def order_type(code: str) -> str:
    return ORDER_TYPE_LABEL.get(code, code)
