"""The AI chat data policy and the customer's consent to it (owner request 2026-11-24, migration 0031).

The customer agrees ONCE per account to the current version of the policy; when the version changes they are asked again.
They can take the consent back at any time: the assistant then refuses (422 AI_CONSENT_REQUIRED) until they agree again,
and the order forms keep working. Every accept / withdraw is in `audit_logs` with its `policy_version`.

The text: `system_settings.ai_chat_policy` ({title, version, body}) when the owner has stored one, otherwise the built-in DRAFT
below (`is_draft: true`), to be reviewed by the owner before launch. `{days}` in the body is the retention period
(`image_retention_days`, the same as the customer's photos, BR-23); the list of AI providers in use is added under the body
from the configuration, so adding a provider does not change the version.
"""
from __future__ import annotations

import re
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import select, text, update
from sqlalchemy.orm import Session

from app.models.account import Account
from app.models.studio import AiChatConsent
from app.repositories.catalog import CatalogRepository
from app.services import audit

DEFAULT_DAYS = 90
# Approved by the owner on 2026-11-24 (their text, "*" emphasis removed). {days}: image_retention_days; {providers}: the AI
# providers in use. A change of wording needs a new "version" (customers are asked again).
DEFAULT_POLICY = {
    "title": "QUYỀN RIÊNG TƯ KHI SỬ DỤNG TRỢ LÝ AI",
    "version": "AI-1.0",
    "approved_at": "2026-11-24",
    "body": """1. Phạm vi hỗ trợ của trợ lý AI

Trợ lý AI hỗ trợ Quý khách soạn nội dung, lựa chọn giấy, bút, mực, tạo và chỉnh sửa phác thảo cho đơn hàng đang soạn.

Nội dung do AI tạo có thể chưa chính xác. Các mức giá được đề cập trong cuộc trò chuyện chỉ mang tính ước tính. Báo giá chính thức sẽ được xưởng cung cấp sau khi tiếp nhận đơn hàng.

2. Dữ liệu được gửi đến nhà cung cấp AI

Để tạo câu trả lời, hệ thống gửi các dữ liệu sau đến nhà cung cấp AI bên ngoài:

- Tin nhắn Quý khách gửi cho trợ lý AI.
- Nội dung và các lựa chọn của đơn hàng đang soạn, bao gồm nội dung chữ viết, mẫu chữ, giấy, bút, mực, số lượng và ghi chú.
- Các thông số kích thước của phác thảo.

Ảnh do Quý khách tải lên không được gửi đến nhà cung cấp AI.

3. Quyền truy cập nội dung trò chuyện

Khi đơn hàng còn là bản nháp, chỉ Quý khách có quyền xem các cuộc trò chuyện của đơn hàng trên hệ thống. Nhân viên và quản lý xưởng không có quyền truy cập nội dung này.

Sau khi Quý khách gửi đơn hàng, nhân viên phụ trách tiếp nhận, xử lý đơn hàng và quản lý xưởng được quyền đọc các cuộc trò chuyện liên quan nhằm hiểu yêu cầu của Quý khách và kiểm tra các cảnh báo an toàn, chẳng hạn yêu cầu làm giả chữ ký hoặc giấy tờ.

Quyền truy cập của nhân viên và quản lý xưởng chỉ giới hạn ở việc xem; không cho phép chỉnh sửa nội dung trò chuyện.

4. Lưu trữ và xoá nội dung trò chuyện

Các cuộc trò chuyện được lưu trữ trên hệ thống của xưởng và gắn với từng đơn hàng.

Nội dung trò chuyện được xoá sau {days} ngày kể từ khi đơn hàng hoàn tất hoặc bị huỷ. Khi Quý khách xoá một đơn hàng nháp, các cuộc trò chuyện thuộc đơn hàng đó cũng được xoá.

Thông tin cảnh báo an toàn, nếu có, vẫn được lưu trong nhật ký hệ thống khi cuộc trò chuyện bị xoá.

5. Quyền của Quý khách

Quý khách có quyền:

- Xem lại các cuộc trò chuyện của mình trên hệ thống.
- Xoá từng cuộc trò chuyện khi đơn hàng còn là bản nháp. Việc xoá cuộc trò chuyện không đồng thời xoá thông tin cảnh báo an toàn đã được ghi nhận trong nhật ký hệ thống.
- Rút lại sự đồng ý sử dụng trợ lý AI bất cứ lúc nào.

Khi Quý khách rút lại sự đồng ý, trợ lý AI sẽ ngừng trả lời cho đến khi Quý khách đồng ý trở lại. Quý khách vẫn có thể tự nhập thông tin, tạo và gửi đơn hàng thông qua các ô nhập trên hệ thống.

6. Lưu ý khi cung cấp thông tin

Quý khách vui lòng chỉ cung cấp thông tin cần thiết để trợ lý AI hỗ trợ đơn hàng. Không gửi số căn cước, mật khẩu, số thẻ, số tài khoản ngân hàng hoặc thông tin nhạy cảm khác không cần thiết cho đơn hàng qua cuộc trò chuyện.

7. Nhà cung cấp AI

Nhà cung cấp AI hiện được sử dụng: {providers}.""",
}
NO_PROVIDER = "chưa có nhà cung cấp nào được bật (trợ lý AI đang tắt)"
_HEADING = re.compile(r"^(\d+)\.[ \t]+(\S.*)$")
PROVIDER_NAMES = {"anthropic": "Anthropic (Claude)", "openai": "OpenAI (ChatGPT)", "gemini": "Google (Gemini)"}


def _retention_days(catalog: CatalogRepository) -> int:
    try:
        return max(1, int(catalog.setting("image_retention_days", DEFAULT_DAYS)))
    except (TypeError, ValueError):
        return DEFAULT_DAYS


def _providers(names: list[str] | None) -> list[str]:
    if names is None:
        from app.services.ai import llm
        names = [i.name for i in llm.provider_infos() if i.configured]
    return [PROVIDER_NAMES.get(n, n) for n in names]


def sections(body: str) -> list[dict[str, str]]:
    """The body cut at its numbered headings: [{title, body}], so the web app can show the headings. A heading is a line
    "N. ..." with an empty line (or the start) before it and an empty line after it, so a numbered list inside a section
    stays in the section."""
    lines = body.split("\n")
    out: list[dict[str, Any]] = []
    for i, line in enumerate(lines):
        heading = (_HEADING.match(line) is not None and (i == 0 or not lines[i - 1].strip())
                   and (i + 1 == len(lines) or not lines[i + 1].strip()))
        if heading:
            out.append({"title": line.strip(), "lines": []})
        elif out:
            out[-1]["lines"].append(line)
    return [{"title": x["title"], "body": "\n".join(x["lines"]).strip()} for x in out]


def current(session: Session, providers: list[str] | None = None) -> dict[str, Any]:
    """The policy in force: {title, version, body, sections, providers, retention_days, retention_enforced, is_draft}."""
    catalog = CatalogRepository(session)
    stored = catalog.setting("ai_chat_policy")
    stored_ok = isinstance(stored, dict) and bool(stored.get("version")) and bool(stored.get("body"))
    policy = stored if stored_ok else DEFAULT_POLICY
    days = _retention_days(catalog)
    names = _providers(providers)
    in_use = ", ".join(names) if names else NO_PROVIDER
    template = str(policy["body"])
    body = template.replace("{days}", str(days)).replace("{providers}", in_use)
    if "{providers}" not in template:                       # a stored text without the place for the providers
        body += "\n\nNhà cung cấp AI hiện được sử dụng: " + in_use + "."
    return {"title": str(policy.get("title") or DEFAULT_POLICY["title"]), "version": str(policy["version"])[:20], "body": body,
            "sections": sections(body), "providers": names, "retention_days": days,
            "retention_enforced": catalog.setting("photo_purge_enabled", False) is True,
            "is_draft": not stored_ok and not DEFAULT_POLICY.get("approved_at")}


def version(session: Session) -> str:
    stored = CatalogRepository(session).setting("ai_chat_policy")
    if isinstance(stored, dict) and stored.get("version") and stored.get("body"):
        return str(stored["version"])[:20]
    return DEFAULT_POLICY["version"]


# ---------------------------------------------------------------------------------------------------------- consent
def accepted_at(session: Session, account_id: int, policy_version: str) -> datetime | None:
    row = session.scalar(select(AiChatConsent).where(AiChatConsent.account_id == account_id,
                                                     AiChatConsent.policy_version == policy_version))
    return row.accepted_at if row is not None and row.withdrawn_at is None else None


def has_consent(session: Session, account_id: int, policy_version: str) -> bool:
    return accepted_at(session, account_id, policy_version) is not None


def accept(session: Session, account: Account, policy_version: str, *, ip: str | None) -> datetime:
    """Record the consent to this version (again after a withdrawal: the same row, a new time). Returns when it was given."""
    at = session.execute(text(
        "INSERT INTO ai_chat_consents (account_id, policy_version) VALUES (:a, :v) "
        "ON CONFLICT (account_id, policy_version) DO UPDATE SET accepted_at = now(), withdrawn_at = NULL "
        "RETURNING accepted_at"), {"a": account.id, "v": policy_version}).scalar_one()
    audit.record(session, actor_id=account.id, action="AI_POLICY_ACCEPT", entity_type="account", entity_id=account.id,
                 new={"policy_version": policy_version}, ip=ip, policy_version=policy_version)
    session.expire_all()
    return at


def withdraw(session: Session, account: Account, *, ip: str | None) -> bool:
    """Take back every consent of the account. False: there was none to take back."""
    now = datetime.now(timezone.utc)
    versions = list(session.scalars(update(AiChatConsent).where(AiChatConsent.account_id == account.id,
                                                                AiChatConsent.withdrawn_at.is_(None))
                                    .values(withdrawn_at=now).returning(AiChatConsent.policy_version)))
    if not versions:
        return False
    audit.record(session, actor_id=account.id, action="AI_POLICY_WITHDRAW", entity_type="account", entity_id=account.id,
                 old={"policy_versions": sorted(versions)}, ip=ip, policy_version=version(session))
    session.expire_all()
    return True


def status(session: Session, account_id: int) -> dict[str, Any]:
    """{policy_version, accepted, accepted_at} for the version in force."""
    v = version(session)
    at = accepted_at(session, account_id, v)
    return {"policy_version": v, "accepted": at is not None, "accepted_at": at}
