"""ORM mapping for customer reviews and the workshop showcase (Phase 5c; tables from the baseline, `hidden_at` from migration 0015).

* `reviews`: one per order (UNIQUE order_id); the trigger `trg_reviews_guard` refuses a review of an order that is not the
  customer's own COMPLETED order (P0409). `updated_at` is set by a trigger.
* `review_photos`: storage paths (not URLs) of the photos the customer attached, cascade with the review.
* `showcase_posts`: sample products the workshop shows on the home page; `image_url` holds the storage path.
"""
from datetime import datetime

from sqlalchemy import BigInteger, Boolean, DateTime, Enum, FetchedValue, ForeignKey, Integer, SmallInteger, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.session import Base
from app.models.order import OrderType


class ReviewPhoto(Base):
    __tablename__ = "review_photos"
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    review_id: Mapped[int] = mapped_column(ForeignKey("reviews.id", ondelete="CASCADE"))
    url: Mapped[str] = mapped_column(Text)                       # storage path
    sort_order: Mapped[int] = mapped_column(SmallInteger, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=FetchedValue())


class Review(Base):
    __tablename__ = "reviews"
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    order_id: Mapped[int] = mapped_column(ForeignKey("orders.id", ondelete="CASCADE"), unique=True)
    customer_id: Mapped[int] = mapped_column(ForeignKey("accounts.id"))
    rating: Mapped[int] = mapped_column(SmallInteger)
    comment: Mapped[str | None] = mapped_column(Text)
    hidden_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=FetchedValue())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=FetchedValue(),
                                                 server_onupdate=FetchedValue())
    photos: Mapped[list[ReviewPhoto]] = relationship(order_by=ReviewPhoto.sort_order, cascade="all, delete-orphan",
                                                     lazy="selectin")


class ShowcasePost(Base):
    __tablename__ = "showcase_posts"
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    image_url: Mapped[str] = mapped_column(Text)                 # storage path
    title: Mapped[str] = mapped_column(String(200))
    description: Mapped[str | None] = mapped_column(Text)
    order_type: Mapped[OrderType | None] = mapped_column(Enum(OrderType, name="order_type", create_type=False))
    posted_by: Mapped[int] = mapped_column(ForeignKey("accounts.id"))
    is_visible: Mapped[bool] = mapped_column(Boolean, default=True)
    sort_order: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=FetchedValue())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=FetchedValue(),
                                                 server_onupdate=FetchedValue())
