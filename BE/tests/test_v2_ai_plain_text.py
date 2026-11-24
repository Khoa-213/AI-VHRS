"""What the order assistant writes onto an order is plain text with real line breaks (bug report 2026-11-24, order 12514:
gemini-3.5-flash-lite sent the line breaks of update_text as backslash + n, so the sketch was drawn with "\\n" in it).
The model is a scripted provider (no real LLM call).
"""
import pytest

from app.services.ai.llm import Reply
from app.services.ai.plain_text import for_paper, unescape
from tests.test_api_orders import API, _sql
from tests.test_api_workshop import cust, store, wcat  # noqa: F401
from tests.test_u5_studio import Script, _call, providers  # noqa: F401
from tests.test_v2_ai_proposals import _apply, _draft, _say

# the argument stored for order 12514 (two backslashes before each n)
BROKEN = ("Thông tin đồ án:\\\\n- Thành viên (5 người):\\\\n+ Hoàng Bảo Ân\\\\n+ Hoàng Anh Khoa\\\\n\\\\n"
          "- Mentor (2 người):\\\\n+ Lâm Hữu Khánh Phương")
FIXED = "Thông tin đồ án:\n- Thành viên (5 người):\n+ Hoàng Bảo Ân\n+ Hoàng Anh Khoa\n\n- Mentor (2 người):\n+ Lâm Hữu Khánh Phương"


@pytest.mark.parametrize("raw,expected", [
    (BROKEN, FIXED),
    ("Dòng 1\\nDòng 2\\n\\nDòng 3", "Dòng 1\nDòng 2\n\nDòng 3"),                 # one backslash
    ("A\\r\\nB\\rC", "A\nB\nC"),
    ('Mẹ nói: \\"con ngoan\\"\\nThương mẹ', 'Mẹ nói: "con ngoan"\nThương mẹ'),      # quotes escaped with the breaks
    ("Tên:\\tAn\\nTuổi:\\t20", "Tên: An\nTuổi: 20"),
    ("Dòng 1\nprintf(\"x\\n\")", "Dòng 1\nprintf(\"x\\n\")"),                      # real breaks: a backslash + n is meant
    ("Chúc mừng sinh nhật mẹ!", "Chúc mừng sinh nhật mẹ!"),
])
def test_line_breaks_written_as_text_become_line_breaks(raw, expected):
    assert for_paper(raw) == expected
    assert for_paper(for_paper(raw)) == for_paper(raw)


@pytest.mark.parametrize("raw,expected", [
    ("# Thiệp mời\n**Kính gửi** quý khách,", "Thiệp mời\nKính gửi quý khách,"),
    ("> Chúc mừng sinh nhật mẹ yêu!\n> Con thương mẹ", "Chúc mừng sinh nhật mẹ yêu!\nCon thương mẹ"),
    ("```\nLời chúc\n```\nDùng `mực đen`", "Lời chúc\nDùng mực đen"),
    # what people write by hand stays: list markers, numbering, blanks, a footnote star, arithmetic
    ("- một\n+ hai\n* Ghi chú\n1. ba\nTên: ______\n2**3 = 8", "- một\n+ hai\n* Ghi chú\n1. ba\nTên: ______\n2**3 = 8"),
])
def test_chat_formatting_is_removed_and_handwriting_marks_stay(raw, expected):
    assert for_paper(raw) == expected


def test_unescape_alone_leaves_formatting_and_text_with_real_breaks():
    assert unescape("**Ghi chú**\\nGiao giờ hành chính") == "**Ghi chú**\nGiao giờ hành chính"
    assert unescape("A\nB\\nC") == "A\nB\\nC"


def test_the_assistant_stores_and_draws_real_line_breaks(client, cust, wcat, store, providers):
    oid, _ = _draft(client, cust, wcat)
    p = Script("anthropic", [_call("update_text", text=BROKEN),
                             _call("set_options", customer_note="Giao giờ hành chính\\nGọi trước khi giao"),
                             Reply("Tôi đã soạn thông tin đồ án.", [], 1, 1)])
    providers["list"] = [p]
    prop = _say(client, cust, oid, "Viết thông tin đồ án gồm 5 thành viên và 2 mentor").json()["proposal"]
    text_change = next(c for c in prop["changes"] if c["field"] == "text")
    assert text_change["after"] == FIXED
    note = next(c for c in prop["changes"] if c["field"] == "customer_note")
    assert note["after"] == "Giao giờ hành chính\nGọi trước khi giao"
    # the model is told what was stored, so it does not "fix" it again
    seen = [t for t in p.seen[1]["transcript"] if t["role"] == "tool"][0]["results"][0]["result"]
    assert seen["order"]["text"] == FIXED
    assert _apply(client, cust, oid, prop["id"]).status_code == 200
    stored = _sql("select text_content from order_inputs where order_id=:o and kind='TEXT_CONTENT'", o=oid)
    assert stored == FIXED and "\\" not in stored and stored.count("\n") == 6
    # the sketch drawn for the proposal is the clean text: one line of the sketch per line of the text
    words = client.get(f"{API}/orders/{oid}/sketch", headers=cust).json()["document"]["pages"][0]["words"]
    drawn = " ".join(w.get("text") or "" for w in words)
    assert "\\" not in drawn and "Thông" in drawn and "Phương" in drawn
