"""Phase 5c: customer reviews (FR-58, UC-20/59) and the workshop showcase (FR-54, UC-55).

* `/orders/{id}/review*`            the customer reviews their own COMPLETED order (one review, editable for 30 days)
* `/manager/reviews*`               the Manager reads every review and hides / shows one again (reason in the audit log)
* `/workshop/showcase*`             Staff and Manager post sample products for the home page
* `/catalog/reviews`, `/catalog/showcase`   public (no login): shown reviews with a shortened name, visible showcase posts
"""
from datetime import datetime
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Query, Request, status
from pydantic import BaseModel, Field

from app.api.deps import SessionDep, client_ip, require_roles
from app.api.schemas import ErrorOut
from app.api.v1.orders import optional_storage
from app.integrations.storage import ObjectStorage
from app.models.account import Account, RoleCode
from app.models.order import OrderType
from app.services import reviews as rv

StorageDep = Annotated[ObjectStorage | None, Depends(optional_storage)]
CustomerDep = Annotated[Account, Depends(require_roles(RoleCode.CUSTOMER.value))]
ManagerDep = Annotated[Account, Depends(require_roles(RoleCode.MANAGER.value))]
PosterDep = Annotated[Account, Depends(require_roles(RoleCode.STAFF.value, RoleCode.MANAGER.value))]
_ERR = {404: {"model": ErrorOut}, 409: {"model": ErrorOut}, 422: {"model": ErrorOut}, 503: {"model": ErrorOut}}

customer_router = APIRouter(prefix="/orders/{order_id}/review", tags=["Reviews"])
manager_router = APIRouter(prefix="/manager/reviews", tags=["Reviews"])
showcase_router = APIRouter(prefix="/workshop/showcase", tags=["Showcase"])
public_router = APIRouter(prefix="/catalog", tags=["Catalog"])


# ---- schemas
class UploadIn(BaseModel):
    mime_type: str = Field(description="image/jpeg | image/png")
    size_bytes: int = Field(ge=1)


class UploadOut(BaseModel):
    path: str = Field(description="Gửi lại đúng đường dẫn này trong `photos` / `image_path`.")
    upload_url: str
    method: str
    expires_in: int


class ReviewIn(BaseModel):
    rating: int = Field(ge=1, le=5, description="Số sao 1–5")
    comment: str | None = Field(default=None, max_length=2000)
    photos: list[str] = Field(default_factory=list, max_length=5,
                              description="Đường dẫn ảnh đã tải lên (`path` của upload-url), tối đa 5; PUT thay toàn bộ danh sách.")


class ReviewPhotoOut(BaseModel):
    id: int
    path: str
    url: str | None


class ReviewOut(BaseModel):
    id: int
    order_id: int
    rating: int
    comment: str | None
    photos: list[ReviewPhotoOut]
    hidden: bool = Field(description="Manager đã ẩn: không hiện công khai, không sửa được nữa.")
    created_at: datetime
    updated_at: datetime
    editable_until: datetime


class ManagedReviewOut(ReviewOut):
    order_code: str
    order_type: OrderType
    customer_name: str
    hidden_at: datetime | None


class ManagedReviewPage(BaseModel):
    items: list[ManagedReviewOut]
    total: int
    page: int
    page_size: int


class HideIn(BaseModel):
    reason: str = Field(min_length=5, max_length=300, description="Lý do (ghi vào nhật ký hoạt động)")


class PublicReviewOut(BaseModel):
    id: int
    rating: int
    comment: str | None
    customer_name: str = Field(description="Tên rút gọn, ví dụ 'Nguyễn V. A.'")
    order_type: OrderType
    photos: list[str] = Field(description="Liên kết xem ảnh có hạn 1 giờ")
    created_at: datetime


class PublicReviewsOut(BaseModel):
    average: float | None
    count: int
    by_star: dict[str, int]
    items: list[PublicReviewOut]
    next_before_id: int | None


class ShowcaseIn(BaseModel):
    image_path: str = Field(description="`path` của `POST /workshop/showcase/upload-url`")
    title: str = Field(min_length=1, max_length=200)
    description: str | None = Field(default=None, max_length=2000)
    order_type: OrderType | None = None
    is_visible: bool = True
    sort_order: int = Field(default=0, ge=0, le=100000, description="Nhỏ hiện trước")


class ShowcasePatch(BaseModel):
    image_path: str | None = None
    title: str | None = Field(default=None, min_length=1, max_length=200)
    description: str | None = Field(default=None, max_length=2000)
    order_type: OrderType | None = None
    is_visible: bool | None = None
    sort_order: int | None = Field(default=None, ge=0, le=100000)


class ShowcaseOut(BaseModel):
    id: int
    image_url: str | None
    title: str
    description: str | None
    order_type: OrderType | None
    sort_order: int
    created_at: datetime


class ShowcaseStaffOut(ShowcaseOut):
    image_path: str
    is_visible: bool
    posted_by: int
    updated_at: datetime


# ---- the customer's review
def _review_svc(session: SessionDep, customer: CustomerDep, request: Request, storage: StorageDep) -> rv.ReviewService:
    return rv.ReviewService(session, customer, storage, client_ip(request))


ReviewSvc = Annotated[rv.ReviewService, Depends(_review_svc)]


@customer_router.get("", response_model=ReviewOut, responses=_ERR, summary="FR-58 Đánh giá của đơn (404 REVIEW_NOT_FOUND nếu chưa có)")
def get_review(order_id: int, svc: ReviewSvc) -> dict[str, Any]:
    return rv.review_out(svc.get(order_id), svc.storage)


@customer_router.post("/photos/upload-url", response_model=UploadOut, status_code=status.HTTP_201_CREATED, responses=_ERR,
                      summary="FR-58 Xin liên kết tải ảnh đánh giá (jpg/png ≤ 5 MB; đơn phải COMPLETED). PUT file vào `upload_url`")
def review_upload(order_id: int, body: UploadIn, svc: ReviewSvc) -> UploadOut:
    path, target = svc.request_upload(order_id, body.mime_type, body.size_bytes)
    return UploadOut(path=path, upload_url=target.url, method=target.method, expires_in=target.expires_in)


@customer_router.post("", response_model=ReviewOut, status_code=status.HTTP_201_CREATED, responses=_ERR,
                      summary="UC-59 · FR-58 Đánh giá đơn đã hoàn thành: 1–5 sao, nhận xét, tối đa 5 ảnh (mỗi đơn 1 đánh giá)")
def create_review(order_id: int, body: ReviewIn, svc: ReviewSvc) -> dict[str, Any]:
    return rv.review_out(svc.create(order_id, body.rating, body.comment, body.photos), svc.storage)


@customer_router.put("", response_model=ReviewOut, responses=_ERR,
                     summary="FR-58 Sửa đánh giá trong 30 ngày sau khi đăng (thay toàn bộ: sao, nhận xét, danh sách ảnh)")
def update_review(order_id: int, body: ReviewIn, svc: ReviewSvc) -> dict[str, Any]:
    return rv.review_out(svc.update(order_id, body.rating, body.comment, body.photos), svc.storage)


# ---- Manager moderation
def _mod_svc(session: SessionDep, manager: ManagerDep, request: Request, storage: StorageDep) -> rv.ReviewModeration:
    return rv.ReviewModeration(session, manager, storage, client_ip(request))


ModSvc = Annotated[rv.ReviewModeration, Depends(_mod_svc)]


@manager_router.get("", response_model=ManagedReviewPage, summary="FR-58 Mọi đánh giá (lọc theo đã ẩn, số sao), mới nhất trước")
def list_reviews(svc: ModSvc, hidden: bool | None = None, rating: int | None = Query(default=None, ge=1, le=5),
                 page: int = Query(1, ge=1), page_size: int = Query(20, ge=1, le=100)) -> ManagedReviewPage:
    items, total = svc.list(hidden=hidden, rating=rating, page=page, page_size=page_size)
    return ManagedReviewPage(items=items, total=total, page=page, page_size=page_size)


@manager_router.post("/{review_id}/hide", response_model=ReviewOut, responses=_ERR,
                     summary="FR-58 Ẩn đánh giá vi phạm khỏi trang công khai (kèm lý do; không xoá)")
def hide_review(review_id: int, body: HideIn, svc: ModSvc) -> dict[str, Any]:
    return rv.review_out(svc.set_hidden(review_id, True, body.reason), svc.storage)


@manager_router.post("/{review_id}/unhide", response_model=ReviewOut, responses=_ERR, summary="FR-58 Hiện lại đánh giá đã ẩn")
def unhide_review(review_id: int, body: HideIn, svc: ModSvc) -> dict[str, Any]:
    return rv.review_out(svc.set_hidden(review_id, False, body.reason), svc.storage)


# ---- showcase (Staff, Manager)
def _showcase_svc(session: SessionDep, actor: PosterDep, request: Request, storage: StorageDep) -> rv.ShowcaseService:
    return rv.ShowcaseService(session, actor, storage, client_ip(request))


ShowSvc = Annotated[rv.ShowcaseService, Depends(_showcase_svc)]


def _staff_out(svc: rv.ShowcaseService, rows: list) -> list[dict[str, Any]]:
    urls = rv.sign_all(svc.storage, [r.image_url for r in rows], 600)
    return [rv.showcase_out(r, urls, staff=True) for r in rows]


@showcase_router.post("/upload-url", response_model=UploadOut, status_code=status.HTTP_201_CREATED, responses=_ERR,
                      summary="FR-54 Xin liên kết tải ảnh showcase (jpg/png ≤ 10 MB). PUT file vào `upload_url`, rồi tạo bài với `path`")
def showcase_upload(body: UploadIn, svc: ShowSvc) -> UploadOut:
    path, target = svc.request_upload(body.mime_type, body.size_bytes)
    return UploadOut(path=path, upload_url=target.url, method=target.method, expires_in=target.expires_in)


@showcase_router.get("", response_model=list[ShowcaseStaffOut], summary="FR-54 Mọi bài showcase (cả bài đang ẩn)")
def showcase_list(svc: ShowSvc) -> list[dict[str, Any]]:
    return _staff_out(svc, svc.list())


@showcase_router.post("", response_model=ShowcaseStaffOut, status_code=status.HTTP_201_CREATED, responses=_ERR,
                      summary="UC-55 · FR-54 Đăng ảnh sản phẩm mẫu lên trang chủ (tiêu đề, mô tả, loại đơn, ẩn/hiện, thứ tự)")
def showcase_create(body: ShowcaseIn, svc: ShowSvc) -> dict[str, Any]:
    return _staff_out(svc, [svc.create(body.model_dump())])[0]


@showcase_router.patch("/{post_id}", response_model=ShowcaseStaffOut, responses=_ERR,
                       summary="FR-54 Sửa bài showcase: chỉ các trường được gửi (ẩn/hiện, thứ tự, ảnh mới...)")
def showcase_update(post_id: int, body: ShowcasePatch, svc: ShowSvc) -> dict[str, Any]:
    data = body.model_dump(exclude_unset=True)
    for key in ("image_path", "title", "is_visible", "sort_order"):
        if key in data and data[key] is None:
            data.pop(key)                                          # null on a required field means "unchanged"
    return _staff_out(svc, [svc.update(post_id, data)])[0]


@showcase_router.delete("/{post_id}", status_code=status.HTTP_204_NO_CONTENT, responses=_ERR,
                        summary="FR-54 Xoá bài showcase (xoá luôn ảnh trong kho)")
def showcase_delete(post_id: int, svc: ShowSvc) -> None:
    svc.delete(post_id)


# ---- public (no login)
@public_router.get("/reviews", response_model=PublicReviewsOut,
                   summary="FR-58 Đánh giá công khai: điểm trung bình, số lượt theo sao, đánh giá mới nhất (không cần đăng nhập)",
                   description="Phân trang bằng `before_id` = `next_before_id` của trang trước. Đánh giá bị Manager ẩn không có ở đây.")
def public_reviews(session: SessionDep, storage: StorageDep, limit: int = Query(10, ge=1, le=rv.PUBLIC_PAGE_MAX),
                   before_id: int | None = Query(default=None, ge=1), order_type: OrderType | None = None) -> dict[str, Any]:
    return rv.public_reviews(session, storage, limit=limit, before_id=before_id, order_type=order_type)


@public_router.get("/showcase", response_model=list[ShowcaseOut],
                   summary="FR-54 · FR-04 Sản phẩm mẫu cho trang chủ (bài đang hiện, theo thứ tự; không cần đăng nhập)")
def public_showcase(session: SessionDep, storage: StorageDep, order_type: OrderType | None = None,
                    limit: int = Query(20, ge=1, le=rv.PUBLIC_PAGE_MAX)) -> list[dict[str, Any]]:
    return rv.public_showcase(session, storage, order_type=order_type, limit=limit)
