"""What each notification says (FR-27, Report 3 section 5.3). Pure, no database.

Callers pass an internal code (the SRS's `MSGxx`, or a name for events the SRS does not number) and its parameters; this module
turns it into the stored title / body, the `notification_type` of the database, whether an e-mail goes out as well (only the
messages the SRS marks "Email + in-app": MSG07, 08, 10, 11, 12, 15) and the SRS code kept in `notifications.msg_code`.
Texts are Vietnamese, as the SRS gives them; the app's other languages are not stored.
"""
from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation
from typing import Any

VN = timezone(timedelta(hours=7))


@dataclass(frozen=True)
class Message:
    type: str                 # notification_type enum value
    title: str
    body: str
    email: bool               # also send an e-mail (SRS: "Email + in-app")
    msg_code: str | None      # SRS code stored in notifications.msg_code (<= 10 chars)
    collapse: bool = False    # do not stack: skip when the account already has an unread one of this type for the order


def money(v: Any) -> str:
    try:
        n = int(Decimal(str(v)))
    except (InvalidOperation, ValueError, TypeError):
        return str(v)
    return f"{n:,}".replace(",", ".") + "đ"


def day(v: Any) -> str:
    try:
        return date.fromisoformat(str(v)[:10]).strftime("%d/%m/%Y")
    except ValueError:
        return str(v)


def moment(v: Any) -> str:
    try:
        d = datetime.fromisoformat(str(v))
    except ValueError:
        return str(v)
    if d.tzinfo is not None:
        d = d.astimezone(VN)
    return d.strftime("%H:%M %d/%m/%Y")


_EVENT = {"FORCE_LIMIT": "quá lực", "EMERGENCY_STOP": "dừng khẩn cấp", "SAFETY_STOP": "dừng an toàn"}
_SHIP = {"FAILED": "giao không thành công", "RETURNED": "bị hoàn về", "RETURNING": "đang hoàn về", "LOST": "thất lạc",
         "CANCELLED": "bị huỷ"}

# code -> (type, msg_code, email, collapse, title(p), body(p)); `p` holds the caller's parameters, always with `code`.
_T = tuple[str, str | None, bool, bool, Callable[[dict], str], Callable[[dict], str]]
CATALOG: dict[str, _T] = {
    # ---- customer, SRS 5.3
    "MSG07": ("ORDER_REJECTED", "MSG07", True, False, lambda p: f"Đơn {p['code']} chưa được nhận",
              lambda p: f"Rất tiếc, xưởng chưa thể nhận đơn {p['code']}: {p.get('reason') or 'không có lý do'}."),
    "MSG08": ("QUOTATION_EXPIRED", "MSG08", True, False, lambda p: f"Báo giá đơn {p['code']} đã hết hạn",
              lambda p: f"Báo giá cho đơn {p['code']} đã hết hạn và đơn được hủy."),
    "MSG10": ("QUOTATION_AVAILABLE", "MSG10", True, False, lambda p: f"Đơn {p['code']} đã có báo giá",
              lambda p: f"Đơn {p['code']} đã có phác thảo và báo giá {money(p.get('total'))} (chưa gồm phí giao hàng)."),
    "ETA_POSTPONED": ("ETA_POSTPONED", "MSG11", True, False, lambda p: f"Đơn {p['code']} dời ngày giao",
                      lambda p: f"Thời gian giao dự kiến của đơn {p['code']} được dời sang {day(p.get('eta'))}. "
                                f"Lý do: {p.get('reason') or 'không có'}."),
    "MSG12": ("PRODUCT_COMPLETED", "MSG12", True, False, lambda p: f"Sản phẩm đơn {p['code']} đã hoàn thành",
              lambda p: f"Sản phẩm của đơn {p['code']} đã hoàn thành. Vui lòng xem ảnh và nghiệm thu."),
    "MSG15": ("DELIVERING", "MSG15", True, False, lambda p: f"Đơn {p['code']} đang được giao",
              lambda p: f"Đơn {p['code']} đang được giao. Mã vận đơn: {p.get('waybill') or '-'}."),
    # ---- customer, not numbered by the SRS (in-app only)
    "ETA_CHANGED": ("ETA_POSTPONED", None, False, False, lambda p: f"Đơn {p['code']} đổi ngày giao",
                    lambda p: f"Thời gian giao dự kiến của đơn {p['code']} đổi thành {day(p.get('eta'))}. "
                              f"Lý do: {p.get('reason') or 'không có'}."),
    "DEPOSIT_PAID": ("PAYMENT", None, False, False, lambda p: f"Đã nhận tiền cọc đơn {p['code']}",
                     lambda p: f"Xưởng đã nhận {money(p.get('amount'))} tiền cọc cho đơn {p['code']} và sẽ xếp lịch sản xuất."),
    "FINAL_PAID": ("PAYMENT", None, False, False, lambda p: f"Đã thanh toán đơn {p['code']}",
                   lambda p: f"Xưởng đã nhận khoản thanh toán cuối của đơn {p['code']}."),
    "ORDER_CANCELLED": ("ORDER_STATUS_CHANGED", None, False, False, lambda p: f"Đơn {p['code']} đã huỷ",
                        lambda p: f"Đơn {p['code']} đã được huỷ."
                                  + (f" Số tiền được hoàn: {money(p['refund_amount'])}."
                                     if p.get("refund_amount") not in (None, "0", "0.00", 0) else "")),
    "REFUND_REQUESTED": ("PAYMENT", None, False, False, lambda p: f"Đang hoàn tiền đơn {p['code']}",
                         lambda p: f"Xưởng đang xử lý hoàn {money(p.get('amount'))} cho đơn {p['code']}."),
    "REFUND_SENT": ("PAYMENT", None, False, False, lambda p: f"Đã hoàn tiền đơn {p['code']}",
                    lambda p: f"Xưởng đã hoàn {money(p.get('amount'))} cho đơn {p['code']}."),
    "SHIPMENT_CREATED": ("DELIVERING", None, False, False, lambda p: f"Đơn {p['code']} đã có vận đơn",
                         lambda p: f"Đơn {p['code']} đã được tạo vận đơn {p.get('waybill') or '-'} và chờ hãng tới lấy."),
    "ORDER_COMPLETED": ("ORDER_STATUS_CHANGED", None, False, False, lambda p: f"Đơn {p['code']} đã hoàn tất",
                        lambda p: f"Đơn {p['code']} đã hoàn tất. Cảm ơn bạn đã sử dụng dịch vụ."),
    "DEPOSIT_OVERDUE": ("ORDER_STATUS_CHANGED", None, False, False, lambda p: f"Đơn {p['code']} đã huỷ do quá hạn cọc",
                        lambda p: f"Đơn {p['code']} đã được huỷ vì chưa đặt cọc trong {p.get('days')} ngày sau khi duyệt báo giá."),
    "ACCEPT_REMINDER": ("ORDER_STATUS_CHANGED", None, False, False, lambda p: f"Nhắc nghiệm thu đơn {p['code']}",
                        lambda p: f"Sản phẩm của đơn {p['code']} đang chờ bạn nghiệm thu. Đơn sẽ tự nghiệm thu lúc "
                                  f"{moment(p.get('due_at'))} nếu bạn không phản hồi."),
    "MESSAGE": ("NEW_MESSAGE", None, False, True, lambda p: f"Tin nhắn mới về đơn {p['code']}",
                lambda p: f"Bạn có tin nhắn mới về đơn {p['code']}."),
    # ---- workshop staff (in-app only)
    "MESSAGE_UNCLAIMED": ("NEW_MESSAGE", None, False, True, lambda p: f"Tin nhắn ở đơn chưa có Staff: {p['code']}",
                          lambda p: f"Khách của đơn {p['code']} nhắn tin nhưng đơn chưa có Staff phụ trách."),
    "REFUND_TO_PROCESS": ("PAYMENT", None, False, False, lambda p: f"Cần hoàn tiền đơn {p['code']}",
                          lambda p: f"Đơn {p['code']} đã huỷ, cần hoàn {money(p.get('amount'))} cho khách."),
    "ORDER_READY_TO_DELIVER": ("ORDER_STATUS_CHANGED", None, False, False, lambda p: f"Đơn {p['code']} sẵn sàng giao",
                               lambda p: f"Khách đã thanh toán đủ, đơn {p['code']} sẵn sàng giao."),
    "PRODUCT_ACCEPTED": ("ORDER_STATUS_CHANGED", None, False, False, lambda p: f"Khách nghiệm thu đơn {p['code']}",
                         lambda p: f"Khách đã nghiệm thu sản phẩm của đơn {p['code']}."),
    "PRODUCT_AUTO_ACCEPTED": ("ORDER_STATUS_CHANGED", None, False, False, lambda p: f"Đơn {p['code']} tự nghiệm thu",
                              lambda p: f"Đơn {p['code']} được tự nghiệm thu do khách không phản hồi đúng hạn."),
    "REWRITE_REQUESTED": ("PRODUCTION_STATUS_CHANGED", None, False, False, lambda p: f"Khách yêu cầu viết lại đơn {p['code']}",
                          lambda p: f"Khách yêu cầu viết lại đơn {p['code']} ({p.get('reason_code') or '-'}). Cần xếp lịch lại."),
    "SHIPMENT_PROBLEM": ("SYSTEM", None, False, False, lambda p: f"Vận đơn đơn {p['code']} gặp sự cố",
                         lambda p: f"Vận đơn của đơn {p['code']} {_SHIP.get(str(p.get('status')), str(p.get('status')))}."
                                   + (f" Lý do: {p['reason']}." if p.get("reason") else "")),
    "QC_FAILED": ("PRODUCTION_STATUS_CHANGED", None, False, False, lambda p: f"QC không đạt: đơn {p['code']}",
                  lambda p: f"Sản phẩm của đơn {p['code']} không đạt QC, cần xếp lịch viết lại."),
    "JOB_ASSIGNED": ("PRODUCTION_STATUS_CHANGED", None, False, False, lambda p: f"Việc mới: đơn {p['code']}",
                     lambda p: f"Bạn được giao viết đơn {p['code']} lúc {moment(p.get('slot_start'))}."),
    "JOB_CANCELLED": ("PRODUCTION_STATUS_CHANGED", None, False, False, lambda p: f"Huỷ việc: đơn {p['code']}",
                      lambda p: f"Đơn {p['code']} đã huỷ, job sản xuất của bạn cho đơn này cũng được huỷ."),
    "JOB_SAFETY_STOP": ("SYSTEM", None, False, False, lambda p: f"Robot dừng an toàn: đơn {p['code']}",
                        lambda p: f"Job của đơn {p['code']} dừng vì {_EVENT.get(str(p.get('event')), str(p.get('event')))}."),
    "REVIEW_POSTED": ("SYSTEM", None, False, False, lambda p: f"Khách đánh giá đơn {p['code']}",
                      lambda p: f"Khách đã đánh giá đơn {p['code']}: {p.get('rating')}/5 sao."),
    "INCIDENT_REPORTED": ("SYSTEM", None, False, False, lambda p: f"Sự cố: đơn {p['code']}",
                          lambda p: f"Kỹ thuật viên báo sự cố khi viết đơn {p['code']}."),
}


def render(code: str, params: dict[str, Any]) -> Message:
    p = {"code": "", **params}
    entry = CATALOG.get(code)
    if entry is None:                                      # an event without a text yet: still reaches the person
        return Message("SYSTEM", f"Cập nhật đơn {p['code']}".strip(), f"Đơn {p['code']} có cập nhật mới ({code}).", False,
                       None)
    type_, msg_code, email, collapse, title, body = entry
    return Message(type_, title(p)[:200], body(p), email, msg_code, collapse)
