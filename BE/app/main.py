from fastapi import APIRouter, FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import text

from app.api.deps import SessionDep
from app.api.schemas import ErrorOut
from app.api.v1 import admin, auth, catalog, me, orders, pricing
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


@app.middleware("http")
async def security_headers(request: Request, call_next):
    response = await call_next(request)
    h = response.headers
    h["X-Content-Type-Options"] = "nosniff"
    h["X-Frame-Options"] = "DENY"
    h["Referrer-Policy"] = "no-referrer"
    h["Permissions-Policy"] = "camera=(), microphone=(), geolocation=()"
    if not request.url.path.startswith(_DOC_PATHS):
        # Pure JSON API: nothing may be embedded or cached. Swagger UI is excluded (it loads CDN assets).
        h["Content-Security-Policy"] = "default-src 'none'; frame-ancestors 'none'"
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
v1.include_router(admin.router)


@v1.get("/health", tags=["System"], summary="Kiểm tra API và kết nối DB")
def health(session: SessionDep) -> dict[str, str]:
    session.execute(text("select 1"))
    return {"status": "ok"}


app.include_router(v1, responses={
    401: {"model": ErrorOut, "description": "Chưa đăng nhập / token hết hạn hoặc bị thu hồi"},
    403: {"model": ErrorOut, "description": "Không đủ quyền"},
    429: {"model": ErrorOut, "description": "Quá nhiều yêu cầu (rate limit); xem header Retry-After"},
    409: {"model": ErrorOut, "description": "Xung đột dữ liệu / chuyển trạng thái không hợp lệ"},
    422: {"model": ErrorOut, "description": "Dữ liệu không hợp lệ"},
})
