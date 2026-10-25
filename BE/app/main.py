from pathlib import Path

from fastapi import APIRouter, FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from sqlalchemy import text

from app.api.deps import SessionDep
from app.api.schemas import ErrorOut
from app.api.v1 import (quality, robot_link, acceptance, admin, robot_ops, auth, catalog, customer_quotes, delivery, manager, manager_ops, me,
                        conversations, messages, orders, payments, pricing, scheduling, shipments, technician, workshop)
from app.core.config import get_settings
from app.core.errors import register_error_handlers

DESCRIPTION = """
Backend của **AI-VHRS – Xưởng Nét Việt** (đơn đặt viết tay bằng robot FR3).

**Cách thử trong Swagger**
1. Gọi `POST /auth/login` (hoặc bấm **Authorize**, nhập email vào `username`).
2. Các endpoint còn lại dùng `Authorization: Bearer <access_token>`.

**Quy ước**
- Lỗi luôn có dạng `{"error": {"code", "message", "details"}}`.
- Chuyển trạng thái đơn không hợp lệ trả `409 STATE_CONFLICT`.
- Danh sách có phân trang: `page`, `page_size` → `{items, total, page, page_size}`.
- Thời gian ISO-8601 (UTC); tiền tệ VND, số nguyên.
"""

TAGS = [
    {"name": "Auth", "description": "FR-01 · UC-01..03, UC-05. Đăng ký, đăng nhập, làm mới / thu hồi phiên, quên mật khẩu."},
    {"name": "Profile", "description": "FR-02 · UC-04. Hồ sơ cá nhân và nhiều địa chỉ giao hàng."},
    {"name": "Catalog", "description": "FR-04, FR-09 · UC-06, UC-11. Giấy, bút (lọc theo giấy), mực, mẫu chữ."},
    {"name": "Pricing", "description": "FR-10, FR-29 · UC-12. Giá ước tính tức thời."},
    {"name": "Orders", "description": "FR-05..11, FR-55/56 · UC-07..14. Customer tạo, lưu nháp, gửi đơn."},
    {"name": "Quotations", "description": "FR-52, UC-15. Đồng ý chính sách riêng tư, xem phác thảo + báo giá, yêu cầu chỉnh."},
    {"name": "Messages", "description": "FR-16 · UC-27. Trao đổi khách ↔ Staff trong đơn."},
    {"name": "Workshop", "description": "FR-12..16, FR-29..32 · UC-23..27. Staff/Manager: hàng đợi, tiếp nhận, phác thảo (AI), báo giá."},
    {"name": "Manager", "description": "UC-44, UC-47 · FR-30, FR-39, FR-41, FR-42. Chỉ MANAGER: phân công Staff, duyệt điều chỉnh giá, vật tư, mẫu chữ, robot, bảng giá có phiên bản."},
    {"name": "Payments", "description": "FR-17..20 · UC-16. Đặt cọc qua cổng thanh toán MOCK (không có tiền thật) + webhook có chữ ký."},
    {"name": "Scheduling", "description": "FR-37, FR-40 · BR-18. Manager: hàng đợi, gợi ý và xếp lịch sản xuất, đổi lịch."},
    {"name": "Technician", "description": "UC-31..39 · FR-43..49 · BR-19. Chỉ TECHNICAL_STAFF, chỉ job được giao: tải gói job (hash), chuẩn bị, hiệu chuẩn, kết quả mô phỏng, bắt đầu/kết thúc viết, sự kiện an toàn, sự cố. Chưa kết nối robot (chỉ làm khi chủ dự án yêu cầu)."},
    {"name": "Robot operations", "description": "Vận hành robot: lần chạy của Robot Agent, cảnh báo 4 mức (đỏ = bấm E-Stop ngay, kèm email), heartbeat, tình trạng robot, sức khoẻ, tuân thủ quy trình, danh mục cảnh báo."},
    {"name": "Acceptance", "description": "UC-18 · FR-28 · BR-13. Khách xem ảnh sản phẩm thật, nghiệm thu hoặc yêu cầu viết lại (1 lần miễn phí); tự nghiệm thu sau 7 ngày."},
    {"name": "Delivery", "description": "FR-18, FR-21, FR-23 · UC-20. Khách chọn giao hàng / nhận tại xưởng, thanh toán cuối (G − D) + phí ship (MOCK), xác nhận đã nhận. Staff bàn giao tại xưởng (`/workshop/orders/{id}/pickup/confirm`)."},
    {"name": "Shipments", "description": "FR-21, FR-22 · UC-29 · MSG15. Vận đơn: Staff tạo vận đơn đúng hãng + dịch vụ khách chọn; hãng (GHN/GHTK) báo hành trình qua callback; khách tra cứu. Mặc định hãng MOCK."},
    {"name": "Admin", "description": "FR-51 · UC-48, UC-51. Chỉ vai trò ADMIN."},
    {"name": "System", "description": "Kiểm tra sức khoẻ dịch vụ."},
]

_settings = get_settings()
app = FastAPI(
    title="AI-VHRS API", version="0.1.0", description=DESCRIPTION, openapi_tags=TAGS,
    swagger_ui_parameters={"persistAuthorization": True, "displayRequestDuration": True,
                           "tryItOutEnabled": True, "docExpansion": "list"},
    docs_url="/docs" if _settings.enable_docs else None,
    redoc_url="/redoc" if _settings.enable_docs else None,
    openapi_url="/openapi.json" if _settings.enable_docs else None,
)
app.add_middleware(CORSMiddleware, allow_origins=_settings.cors_origins,
                   allow_origin_regex=_settings.cors_origin_regex,
                   allow_methods=["*"], allow_headers=["*"], allow_credentials=True)
register_error_handlers(app)

_DOC_PATHS = ("/docs", "/redoc", "/openapi.json")


_VIEWER_PAGE = "/viewer/"
_VIEWER_CSP = ("default-src 'self'; script-src 'self' 'unsafe-inline' https://cdn.jsdelivr.net; style-src 'self' 'unsafe-inline'; "
               "img-src 'self' data: blob:; connect-src 'self'; worker-src blob:")


@app.middleware("http")
async def security_headers(request: Request, call_next):
    response = await call_next(request)
    h = response.headers
    path = request.url.path
    h["X-Content-Type-Options"] = "nosniff"
    h["Referrer-Policy"] = "no-referrer"
    h["Permissions-Policy"] = "camera=(), microphone=(), geolocation=()"
    if path.startswith(_VIEWER_PAGE):
        # The read-only 3D page: it loads three.js from a pinned CDN version and may be embedded by the FE origins only.
        ancestors = " ".join(["'self'", *_settings.cors_origins])
        h["Content-Security-Policy"] = f"{_VIEWER_CSP}; frame-ancestors {ancestors}"
        h["Cache-Control"] = "no-store"
    else:
        h["X-Frame-Options"] = "DENY"
        if not path.startswith(_DOC_PATHS):
            # Pure JSON API: nothing may be embedded or cached. Swagger UI is excluded (it loads CDN assets).
            h["Content-Security-Policy"] = "default-src 'none'; frame-ancestors 'none'"
            if "cache-control" not in h:                      # the public robot model sets its own long cache
                h["Cache-Control"] = "no-store"
    proto = request.headers.get("x-forwarded-proto") if get_settings().trust_proxy_headers else None
    if (proto or request.url.scheme) == "https":
        h["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
    return response

v1 = APIRouter(prefix="/api/v1")
v1.include_router(auth.router)
v1.include_router(me.router)
v1.include_router(catalog.router)
v1.include_router(pricing.router)
v1.include_router(orders.router)
v1.include_router(customer_quotes.router)
v1.include_router(messages.router)
v1.include_router(conversations.customer_router)
v1.include_router(conversations.workshop_router)
v1.include_router(workshop.router)
v1.include_router(manager.router)
v1.include_router(manager_ops.router)
v1.include_router(scheduling.router)
v1.include_router(technician.router)
v1.include_router(robot_ops.technician_router)
v1.include_router(robot_ops.manager_router)
v1.include_router(robot_link.technician_router)
v1.include_router(robot_link.manager_router)
v1.include_router(robot_link.agent_router)
v1.include_router(robot_link.viewer_router)
v1.include_router(quality.technician_router)
v1.include_router(quality.manager_router)
v1.include_router(acceptance.router)
v1.include_router(delivery.router)
v1.include_router(shipments.router)
v1.include_router(payments.router)
v1.include_router(admin.router)


@v1.get("/health", tags=["System"], summary="Kiểm tra API và kết nối DB")
def health(session: SessionDep) -> dict[str, str]:
    session.execute(text("select 1"))
    return {"status": "ok"}


app.mount("/viewer", StaticFiles(directory=Path(__file__).parent / "static" / "viewer"), name="viewer")
app.include_router(v1, responses={
    401: {"model": ErrorOut, "description": "Chưa đăng nhập / token hết hạn hoặc bị thu hồi"},
    403: {"model": ErrorOut, "description": "Không đủ quyền"},
    429: {"model": ErrorOut, "description": "Quá nhiều yêu cầu (rate limit); xem header Retry-After"},
    409: {"model": ErrorOut, "description": "Xung đột dữ liệu / chuyển trạng thái không hợp lệ"},
    422: {"model": ErrorOut, "description": "Dữ liệu không hợp lệ"},
})
