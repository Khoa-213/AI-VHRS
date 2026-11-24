"""AI chat sessions and the AI chat data policy (migration 0031, owner request 2026-11-24).

* The customer agrees once per account to the version of the policy in force (asked again when it changes, can withdraw).
* An order has several conversations ("new chat"): a new one does not remember the others but sees the order.
* The customer's conversations are listed across orders (sidebar), renamed, deleted while the order is a draft (text wiped,
  safety flags kept for the workshop); the retention job wipes the text of orders finished long ago.
The model is a scripted provider (no real LLM call).
"""
import pytest

from app.db.session import _factory
from app.services import background_jobs as bj
from app.services.ai import chat_policy, chat_sessions
from app.services.ai.llm import Reply
from tests.test_api_orders import API, _sql
from tests.test_api_workshop import W, _err, _user, cust, staff, store, wcat  # noqa: F401
from tests.test_background_jobs import purge_switch
from tests.test_u5_studio import Script, _call, providers  # noqa: F401
from tests.test_v2_ai_proposals import _draft

ME = f"{API}/me/assistant"


def _msg(client, h, oid, text_, **extra):
    """A message without the consent flag (unless given)."""
    return client.post(f"{API}/orders/{oid}/assistant/messages", headers=h, json={"text": text_, **extra})


def _say(client, h, oid, text_, **extra):
    r = _msg(client, h, oid, text_, ai_consent=True, **extra)
    assert r.status_code == 200, r.text
    return r.json()


def _conv(client, h, oid, **params):
    return client.get(f"{API}/orders/{oid}/assistant/messages", headers=h, params=params)


def _sessions(client, h, oid):
    r = client.get(f"{API}/orders/{oid}/assistant/sessions", headers=h)
    assert r.status_code == 200, r.text
    return r.json()


def _me(client, h):
    return client.get(f"{API}/me", headers=h).json()["id"]


def _users(seen):
    return [t["text"] for t in seen["transcript"] if t["role"] == "user"]


# ---------------------------------------------------------------------------------------------------------- policy, consent
def test_the_policy_is_public_and_the_customer_agrees_once_for_every_order(client, cust, wcat, store, providers):
    p = client.get(f"{API}/privacy-policy/ai-chat")
    assert p.status_code == 200, p.text
    policy = p.json()
    with _factory()() as s:
        assert policy["version"] == chat_policy.version(s)
    # the text the owner approved (2026-11-24): 7 sections, the days and the providers filled in, no markup left
    assert policy["is_draft"] is False and "*" not in policy["body"] + policy["title"] and "{" not in policy["body"]
    assert [x["title"][:2] for x in policy["sections"]] == ["1.", "2.", "3.", "4.", "5.", "6.", "7."]
    assert f"sau {policy['retention_days']} ngày" in policy["sections"][3]["body"]
    assert "quản lý xưởng được quyền đọc" in policy["sections"][2]["body"]
    assert policy["sections"][6]["body"].startswith("Nhà cung cấp AI hiện được sử dụng: ")
    assert client.get(f"{ME}/consent", headers=cust).json() == {"policy_version": policy["version"], "accepted": False,
                                                                  "accepted_at": None}
    oid, _ = _draft(client, cust, wcat)
    providers["list"] = [Script("anthropic", [])]
    r = _msg(client, cust, oid, "Chào")
    assert r.status_code == 422 and _err(r) == "AI_CONSENT_REQUIRED"
    assert r.json()["error"]["details"]["policy_version"] == policy["version"]
    assert _conv(client, cust, oid).json()["consented_at"] is None
    r = client.post(f"{ME}/consent", headers=cust, json={"policy_version": "AI-0.1"})
    assert r.status_code == 409 and _err(r) == "POLICY_VERSION_CHANGED"
    assert r.json()["error"]["details"]["policy_version"] == policy["version"]
    r = client.post(f"{ME}/consent", headers=cust, json={"policy_version": policy["version"]})
    assert r.status_code == 200 and r.json()["accepted"] and r.json()["accepted_at"]
    # agreed once: messages need no flag, on this order and on another one
    assert _msg(client, cust, oid, "Chào").status_code == 200
    oid2, _ = _draft(client, cust, wcat)
    assert _msg(client, cust, oid2, "Chào lần nữa").status_code == 200
    conv = _conv(client, cust, oid2).json()
    assert conv["consented_at"] and conv["policy_version"] == policy["version"] and conv["policy_accepted"] is True
    # withdrawn: refused again (twice is fine); the FE's tick (ai_consent) agrees again
    w = client.delete(f"{ME}/consent", headers=cust)
    assert w.status_code == 200 and w.json()["accepted"] is False
    assert client.delete(f"{ME}/consent", headers=cust).status_code == 200
    r = _msg(client, cust, oid, "Còn đó không")
    assert r.status_code == 422 and _err(r) == "AI_CONSENT_REQUIRED"
    assert _conv(client, cust, oid).json()["policy_accepted"] is False
    assert _msg(client, cust, oid, "Còn đó không", ai_consent=True).status_code == 200
    uid = _me(client, cust)
    assert _sql("select count(*) from audit_logs where action='AI_POLICY_ACCEPT' and entity_type='account' and entity_id=:u "
                "and policy_version=:v", u=uid, v=policy["version"]) == 2
    assert _sql("select count(*) from audit_logs where action='AI_POLICY_WITHDRAW' and entity_id=:u", u=uid) == 1
    assert _sql("select count(*) from ai_chat_consents where account_id=:u and withdrawn_at is null", u=uid) == 1
    # the status of the assistant says it too
    st = client.get(f"{API}/studio/assistant/status", headers=cust).json()
    assert st["policy_version"] == policy["version"] and st["policy_accepted"] is True


def test_a_new_version_of_the_policy_is_asked_again(client, cust, wcat, store, providers, monkeypatch):
    oid, _ = _draft(client, cust, wcat)
    providers["list"] = [Script("anthropic", [])]
    _say(client, cust, oid, "Chào")
    monkeypatch.setattr(chat_policy, "version", lambda session: "AI-TEST-2")
    r = _msg(client, cust, oid, "Chào")
    assert r.status_code == 422 and r.json()["error"]["details"]["policy_version"] == "AI-TEST-2"
    assert client.get(f"{ME}/consent", headers=cust).json()["accepted"] is False
    assert client.post(f"{ME}/consent", headers=cust, json={"policy_version": "AI-TEST-2"}).json()["accepted"] is True
    assert _msg(client, cust, oid, "Chào").status_code == 200


def test_only_customers_use_the_consent_and_the_sidebar(client):
    assert client.get(f"{ME}/consent").status_code == 401
    for role in ("STAFF", "MANAGER", "ADMIN", "TECHNICAL_STAFF"):
        h = _user(client, role)[0]
        for method, path in (("GET", "/consent"), ("POST", "/consent"), ("DELETE", "/consent"), ("GET", "/sessions")):
            r = client.request(method, f"{ME}{path}", headers=h, json={"policy_version": "x"} if method == "POST" else None)
            assert r.status_code == 403 and _err(r) == "FORBIDDEN", (role, method, path, r.text)


# ---------------------------------------------------------------------------------------------------------- new chat
def test_a_new_chat_starts_fresh_on_the_same_order_and_an_old_one_can_be_continued(client, cust, wcat, store, providers):
    oid, _ = _draft(client, cust, wcat)
    a = Script("anthropic", [Reply("Một.", [], 1, 1)])
    providers["list"] = [a]
    sid_a = _say(client, cust, oid, "Câu thứ nhất về thiệp")["session_id"]
    b = Script("anthropic", [Reply("Hai.", [], 1, 1)])
    providers["list"] = [b]
    second = _say(client, cust, oid, "Câu thứ hai", new_session=True, client_ref="pytest-new-b")
    sid_b = second["session_id"]
    assert sid_b != sid_a and second["reply"]["content"] == "Hai."
    assert _users(b.seen[0]) == ["Câu thứ hai"]                              # remembers nothing of the first chat ...
    assert '"order_code"' in b.seen[0]["system"]                            # ... but sees the order
    # the same message again (same client_ref) is the stored turn: no third conversation
    again = _say(client, cust, oid, "Câu thứ hai", new_session=True, client_ref="pytest-new-b")
    assert again["replayed"] and again["session_id"] == sid_b
    # continuing the first chat brings its history back
    c = Script("anthropic", [Reply("Ba.", [], 1, 1)])
    providers["list"] = [c]
    assert _say(client, cust, oid, "Tiếp chuyện cũ", session_id=sid_a)["session_id"] == sid_a
    assert _users(c.seen[0]) == ["Câu thứ nhất về thiệp", "Tiếp chuyện cũ"]
    # without session_id: the conversation used last; with it: that one
    conv = _conv(client, cust, oid).json()
    assert conv["session"]["id"] == sid_a
    assert [m["content"] for m in conv["messages"] if m["role"] == "USER"] == ["Câu thứ nhất về thiệp", "Tiếp chuyện cũ"]
    assert [m["content"] for m in _conv(client, cust, oid, session_id=sid_b).json()["messages"]] == ["Câu thứ hai", "Hai."]
    listed = _sessions(client, cust, oid)
    assert [s["id"] for s in listed] == [sid_a, sid_b]
    assert listed[1]["title"] == "Câu thứ hai" and listed[1]["title_is_custom"] is False and listed[1]["message_count"] == 2
    assert all(s["can_chat"] and s["order_id"] == oid for s in listed)
    # wrong choices
    r = _msg(client, cust, oid, "x", session_id=sid_a, new_session=True)
    assert r.status_code == 422 and _err(r) == "INVALID_SESSION_CHOICE"
    r = _msg(client, cust, oid, "x", session_id=999999999)
    assert r.status_code == 404 and _err(r) == "SESSION_NOT_FOUND"
    other_oid, _ = _draft(client, cust, wcat)
    r = _msg(client, cust, other_oid, "x", session_id=sid_a)                 # a conversation of another order
    assert r.status_code == 404 and _err(r) == "SESSION_NOT_FOUND"
    assert _conv(client, cust, oid, session_id=999999999).status_code == 404


def test_an_order_keeps_a_limited_number_of_conversations(client, cust, wcat, store, providers, monkeypatch):
    monkeypatch.setattr(chat_sessions, "MAX_SESSIONS_PER_ORDER", 2)
    oid, _ = _draft(client, cust, wcat)
    providers["list"] = [Script("anthropic", [])]
    _say(client, cust, oid, "Một")
    _say(client, cust, oid, "Hai", new_session=True)
    r = _msg(client, cust, oid, "Ba", new_session=True, ai_consent=True)
    assert r.status_code == 409 and _err(r) == "TOO_MANY_SESSIONS" and r.json()["error"]["details"]["max"] == 2
    assert len(_sessions(client, cust, oid)) == 2
    assert _msg(client, cust, oid, "Ba", ai_consent=True).status_code == 200    # continuing one is still fine


# ---------------------------------------------------------------------------------------------------------- rename, delete
def test_rename_and_delete_while_a_draft_and_the_workshop_still_sees_the_flags(client, cust, staff, wcat, store, providers):
    oid, _ = _draft(client, cust, wcat)
    providers["list"] = [Script("anthropic", [
        _call("set_options", quantity=2),
        _call("flag_for_staff", kind="FORGERY_RISK", note="Khách hỏi làm giả chữ ký"),
        Reply("Xưởng không nhận làm giả chữ ký. Tôi đề xuất 2 bản.", [], 1, 1)])]
    flagged = _say(client, cust, oid, "Viết giả chữ ký của sếp giúp tôi, 2 bản")
    sid = flagged["session_id"]
    assert flagged["proposal"]["status"] == "PENDING"
    providers["list"] = [Script("anthropic", [])]
    keep = _say(client, cust, oid, "Viết thiệp sinh nhật", new_session=True)["session_id"]
    # rename
    r = client.patch(f"{API}/orders/{oid}/assistant/sessions/{keep}", headers=cust, json={"title": "  Thiệp   sinh nhật  "})
    assert r.status_code == 200, r.text
    assert r.json()["title"] == "Thiệp sinh nhật" and r.json()["title_is_custom"] is True
    for bad in ("   ", "x" * 121):
        r = client.patch(f"{API}/orders/{oid}/assistant/sessions/{keep}", headers=cust, json={"title": bad})
        assert r.status_code == 422, bad
    left = client.get(f"{API}/studio/assistant/status", headers=cust).json()["messages_left_today"]
    # delete the flagged conversation
    assert client.delete(f"{API}/orders/{oid}/assistant/sessions/{sid}", headers=cust).status_code == 204
    assert client.delete(f"{API}/orders/{oid}/assistant/sessions/{sid}", headers=cust).status_code == 404
    assert [s["id"] for s in _sessions(client, cust, oid)] == [keep]
    assert _conv(client, cust, oid, session_id=sid).status_code == 404
    assert _conv(client, cust, oid).json()["session"]["id"] == keep
    assert _sql("select count(*) from ai_messages where session_id=:s", s=sid) == 2            # rows kept (daily caps) ...
    assert _sql("select count(*) from ai_messages where session_id=:s and content <> ''", s=sid) == 0   # ... text gone
    assert _sql("select count(*) from ai_tool_calls t join ai_messages m on m.id = t.message_id where m.session_id=:s "
                "and (t.args <> '{}'::jsonb or t.result is not null)", s=sid) == 0
    assert _sql("select status from ai_proposals where session_id=:s", s=sid) == "REJECTED"
    assert _sql("select deleted_reason from ai_sessions where id=:s", s=sid) == "CUSTOMER"
    assert client.get(f"{API}/studio/assistant/status", headers=cust).json()["messages_left_today"] == left
    assert _sql("select count(*) from audit_logs where action='AI_SESSION_DELETE' and entity_type='order' and entity_id=:o",
                o=oid) == 1
    # another customer can do nothing with them
    other = _user(client, "CUSTOMER")[0]
    assert client.patch(f"{API}/orders/{oid}/assistant/sessions/{keep}", headers=other, json={"title": "x"}).status_code == 404
    assert client.delete(f"{API}/orders/{oid}/assistant/sessions/{keep}", headers=other).status_code == 404
    # once the order is sent: no delete; the Staff read both conversations, the deleted one without text but with its flag
    assert client.post(f"{API}/orders/{oid}/submit", headers=cust, json={"terms_accepted": True}).status_code == 200
    r = client.delete(f"{API}/orders/{oid}/assistant/sessions/{keep}", headers=cust)
    assert r.status_code == 409 and _err(r) == "ORDER_NOT_EDITABLE"
    assert [s["id"] for s in _sessions(client, cust, oid)] == [keep] and not _sessions(client, cust, oid)[0]["can_chat"]
    assert _sessions(client, cust, oid)[0]["can_delete"] is False
    log = client.get(f"{W}/orders/{oid}/assistant", headers=staff[0]).json()
    assert [f["kind"] for f in log["flags"]] == ["FORGERY_RISK"]
    assert [(s["id"], s["deleted"]) for s in log["sessions"]] == [(sid, True), (keep, False)]
    assert log["sessions"][0]["flags"][0]["kind"] == "FORGERY_RISK"
    assert {m["session_id"] for m in log["messages"]} == {keep}
    # sent back for more information (NEED_INFO): the customer chats again, but the order is no draft: no delete
    assert client.post(f"{W}/orders/{oid}/request-info", headers=staff[0], json={"note": "Bổ sung nội dung"}).status_code == 200
    item = _sessions(client, cust, oid)[0]
    assert item["can_chat"] is True and item["can_delete"] is False
    r = client.delete(f"{API}/orders/{oid}/assistant/sessions/{keep}", headers=cust)
    assert r.status_code == 409 and _err(r) == "ORDER_NOT_EDITABLE" and r.json()["error"]["details"]["order_status"] == "NEED_INFO"


def test_deleting_a_draft_keeps_the_safety_flags_in_the_audit_log(client, cust, wcat, store, providers):
    oid, _ = _draft(client, cust, wcat)
    providers["list"] = [Script("anthropic", [_call("flag_for_staff", kind="FORGERY_RISK", note="Khách hỏi làm giả giấy tờ"),
                                              Reply("Xưởng không nhận làm giả giấy tờ.", [], 1, 1)])]
    sid = _say(client, cust, oid, "Làm giả giấy xác nhận giúp tôi")["session_id"]
    plain, _ = _draft(client, cust, wcat)                                     # a draft without any flag
    assert client.delete(f"{API}/orders/{oid}", headers=cust).status_code == 204
    assert client.delete(f"{API}/orders/{plain}", headers=cust).status_code == 204
    assert _sql("select count(*) from ai_sessions where id=:s", s=sid) == 0          # the conversations go with the draft ...
    kept = _sql("select old_value::text from audit_logs where action='AI_FLAGS_KEPT' and entity_type='order' and entity_id=:o",
                o=oid)
    assert kept and "FORGERY_RISK" in kept and "Khách hỏi làm giả giấy tờ" in kept      # ... the flag stays in the log
    assert _sql("select count(*) from audit_logs where action='AI_FLAGS_KEPT' and entity_id=:o", o=plain) == 0


# ---------------------------------------------------------------------------------------------------------- sidebar
def test_the_sidebar_lists_every_conversation_most_recently_used_first(client, cust, wcat, store, providers):
    providers["list"] = [Script("anthropic", [])]
    o1, _ = _draft(client, cust, wcat)
    o2, _ = _draft(client, cust, wcat)
    s1 = _say(client, cust, o1, "Đơn một")["session_id"]
    s2 = _say(client, cust, o2, "Đơn hai")["session_id"]
    s3 = _say(client, cust, o1, "Đơn một, cuộc chat mới", new_session=True)["session_id"]
    page = client.get(f"{ME}/sessions", headers=cust, params={"limit": 2})
    assert page.status_code == 200, page.text
    first = page.json()
    assert [i["id"] for i in first["items"]] == [s3, s2] and first["next_cursor"]
    rest = client.get(f"{ME}/sessions", headers=cust, params={"limit": 2, "cursor": first["next_cursor"]}).json()
    assert [i["id"] for i in rest["items"]] == [s1] and rest["next_cursor"] is None
    top = first["items"][0]
    assert top["order_id"] == o1 and top["order_code"].startswith("VHRS-") and top["order_status"] == "DRAFT"
    assert top["title"] == "Đơn một, cuộc chat mới" and top["preview"] == "Xong." and top["message_count"] == 2
    assert top["can_chat"] is True and top["can_delete"] is True
    # continuing an older conversation moves it to the top
    _say(client, cust, o2, "Tiếp", session_id=s2)
    assert [i["id"] for i in client.get(f"{ME}/sessions", headers=cust).json()["items"]] == [s2, s3, s1]
    other = _user(client, "CUSTOMER")[0]
    assert client.get(f"{ME}/sessions", headers=other).json() == {"items": [], "next_cursor": None}
    r = client.get(f"{ME}/sessions", headers=cust, params={"cursor": "abc"})
    assert r.status_code == 422 and _err(r) == "INVALID_CURSOR"


# ---------------------------------------------------------------------------------------------------------- retention
def test_the_retention_job_wipes_conversations_of_orders_finished_long_enough_ago(client, cust, wcat, store, providers,
                                                                                    monkeypatch):
    providers["list"] = [Script("anthropic", [])]
    done, _ = _draft(client, cust, wcat)
    open_, _ = _draft(client, cust, wcat)
    sid = _say(client, cust, done, "Nội dung riêng của đơn đã xong")["session_id"]
    keep = _say(client, cust, open_, "Đơn còn đang soạn")["session_id"]
    assert client.post(f"{API}/orders/{done}/submit", headers=cust, json={"terms_accepted": True}).status_code == 200
    assert client.post(f"{API}/orders/{done}/cancel", headers=cust, json={"reason": "pytest"}).status_code == 200

    def run(oid, **kw):
        with _factory()() as s:
            return bj.JOBS["ai_chat_purge"](s, order_ids=[oid], **kw)
    assert run(done, enabled=True) == {"dry_run": False, "deleted": 0}         # cancelled just now: not yet
    monkeypatch.setattr(bj, "PURGE_AFTER_DAYS", 0)                             # "90 days ago" = now
    purge_switch(monkeypatch, False)
    assert run(done) == {"dry_run": True, "would_delete": 1}                    # switch off (system_settings): counted only
    assert _sql("select count(*) from ai_messages where session_id=:s and content <> ''", s=sid) == 2
    purge_switch(monkeypatch, True)
    assert run(done) == {"dry_run": False, "deleted": 1}                        # switch on
    assert _sql("select count(*) from ai_messages where session_id=:s and content <> ''", s=sid) == 0
    assert _sql("select deleted_reason from ai_sessions where id=:s", s=sid) == "RETENTION"
    assert _sql("select count(*) from audit_logs where action='AI_SESSION_PURGE' and entity_type='order' and entity_id=:o",
                o=done) == 1
    assert run(done, enabled=True) == {"dry_run": False, "deleted": 0}         # already wiped
    assert run(open_, enabled=True) == {"dry_run": False, "deleted": 0}        # a draft is never touched
    assert _sql("select count(*) from ai_messages where session_id=:s and content <> ''", s=keep) == 2
    assert [i["id"] for i in client.get(f"{ME}/sessions", headers=cust).json()["items"]] == [keep]


@pytest.mark.parametrize("title,expected", [("  Một   câu  ", "Một câu"), ("x" * 70, "x" * 59 + "…")])
def test_titles_and_previews_are_one_clean_line(title, expected):
    assert chat_sessions._clip(title, chat_sessions.AUTO_TITLE) == expected
