"""Phase 4e: notification texts (SRS 5.3). No database."""
from app.domain import notification_messages as nm
from app.models.notification import NotificationType


def test_the_srs_messages_go_by_email_too_and_keep_their_code():
    for code, msg_code in (("MSG07", "MSG07"), ("MSG08", "MSG08"), ("MSG10", "MSG10"), ("ETA_POSTPONED", "MSG11"),
                           ("MSG12", "MSG12"), ("MSG15", "MSG15")):
        m = nm.render(code, {"code": "VH-1"})
        assert m.email is True and m.msg_code == msg_code, code
    for code in ("DEPOSIT_PAID", "MESSAGE", "JOB_ASSIGNED", "ETA_CHANGED", "REFUND_SENT"):
        assert nm.render(code, {"code": "VH-1"}).email is False


def test_texts_follow_the_srs_wording():
    assert nm.render("MSG10", {"code": "VH-9", "total": "1234000.00"}).body == \
        "Đơn VH-9 đã có phác thảo và báo giá 1.234.000đ (chưa gồm phí giao hàng)."
    m = nm.render("ETA_POSTPONED", {"code": "VH-9", "eta": "2026-11-20", "reason": "Robot bảo trì"})
    assert m.body == "Thời gian giao dự kiến của đơn VH-9 được dời sang 20/11/2026. Lý do: Robot bảo trì."
    assert nm.render("MSG07", {"code": "VH-9", "reason": None}).body.endswith(": không có lý do.")
    assert "08:30 05/11/2026" in nm.render("JOB_ASSIGNED", {"code": "VH-9", "slot_start": "2026-11-05T01:30:00+00:00"}).body


def test_every_type_exists_in_the_database_enum_and_codes_fit_the_column():
    types = {t.value for t in NotificationType}
    for code in nm.CATALOG:
        m = nm.render(code, {"code": "VH-1"})
        assert m.type in types and (m.msg_code is None or len(m.msg_code) <= 10) and len(m.title) <= 200


def test_an_unknown_code_still_reaches_the_person():
    m = nm.render("SOMETHING_NEW", {"code": "VH-1"})
    assert m.type == "SYSTEM" and m.email is False and "VH-1" in m.body


def test_cancel_text_mentions_the_refund_only_when_there_is_one():
    assert "hoàn" not in nm.render("ORDER_CANCELLED", {"code": "A", "refund_amount": "0"}).body
    assert "500.000đ" in nm.render("ORDER_CANCELLED", {"code": "A", "refund_amount": "500000"}).body
