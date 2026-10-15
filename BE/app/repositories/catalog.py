"""Data access for the material catalog, pricing config and system settings. No business rules."""
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.catalog import (InkColor, PaperPenCompat, PaperType, PenType, PricingConfig, SystemSetting,
                                Template)


class CatalogRepository:
    def __init__(self, session: Session):
        self.s = session

    def papers(self) -> list[PaperType]:
        return list(self.s.scalars(select(PaperType).where(PaperType.is_active).order_by(PaperType.name)))

    def paper(self, paper_id: int) -> PaperType | None:
        return self.s.get(PaperType, paper_id)

    def pens(self) -> list[PenType]:
        return list(self.s.scalars(select(PenType).where(PenType.is_active).order_by(PenType.name)))

    def pens_for_paper(self, paper_id: int) -> list[PenType]:
        stmt = (select(PenType).join(PaperPenCompat, PaperPenCompat.pen_type_id == PenType.id)
                .where(PaperPenCompat.paper_type_id == paper_id, PaperPenCompat.is_compatible, PenType.is_active)
                .order_by(PenType.name))
        return list(self.s.scalars(stmt))

    def pen(self, pen_id: int) -> PenType | None:
        return self.s.get(PenType, pen_id)

    def inks_for_pen(self, pen_id: int) -> list[InkColor]:
        return list(self.s.scalars(select(InkColor).where(InkColor.pen_type_id == pen_id, InkColor.is_active)
                                   .order_by(InkColor.name)))

    def ink(self, ink_id: int) -> InkColor | None:
        return self.s.get(InkColor, ink_id)

    def is_compatible(self, paper_id: int, pen_id: int) -> bool:
        """A missing matrix row counts as NOT compatible (BR-05: only listed pens are offered)."""
        row = self.s.get(PaperPenCompat, (paper_id, pen_id))
        return bool(row and row.is_compatible)

    def templates(self) -> list[Template]:
        return list(self.s.scalars(select(Template).where(Template.is_active).order_by(Template.name)))

    def template(self, template_id: int) -> Template | None:
        return self.s.get(Template, template_id)

    def active_pricing(self) -> PricingConfig | None:
        return self.s.scalar(select(PricingConfig).where(PricingConfig.is_active))

    def setting(self, key: str, default: Any = None) -> Any:
        row = self.s.get(SystemSetting, key)
        return default if row is None else row.value
