"""The parcel an order ships as (FR-21): package type from the paper size, weight from the sheets that were written."""
from __future__ import annotations

from app.core.errors import AppError
from app.domain import carrier_rules as cr
from app.domain import delivery_rules as dr
from app.models.catalog import PaperType
from app.models.order import Order
from app.repositories.catalog import CatalogRepository
from app.repositories.ops import JobRepository


def paper_and_package(catalog: CatalogRepository, order: Order) -> tuple[PaperType, str, str]:
    paper = catalog.paper(order.paper_type_id) if order.paper_type_id else None
    if paper is None:
        raise AppError(409, "DELIVERY_NOT_READY", "Đơn chưa có loại giấy để xác định gói hàng.")
    try:
        return paper, paper.size.value, dr.package_type(paper.size.value)
    except dr.DeliveryRuleError as exc:
        raise AppError(422, exc.code, exc.message, exc.details) from exc


def build_parcel(catalog: CatalogRepository, jobs: JobRepository, order: Order) -> cr.Parcel:
    paper, size, package = paper_and_package(catalog, order)
    sheets = order.quantity * (jobs.written_pages(order.id) or 1)
    try:
        return cr.parcel_for(package, size, paper.gsm, sheets, order.total_amount or 0)
    except cr.CarrierRuleError as exc:
        raise AppError(422, exc.code, exc.message, exc.details) from exc
