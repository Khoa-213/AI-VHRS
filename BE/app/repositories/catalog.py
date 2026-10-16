"""Data access for the material catalog, pricing config and system settings. No business rules."""
from typing import Any

from sqlalchemy import func, select, update
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

    # ---- manager-side (FR-30, FR-41, FR-42): includes inactive rows, lock on write ----
    def all_papers(self) -> list[PaperType]:
        return list(self.s.scalars(select(PaperType).order_by(PaperType.name, PaperType.id)))

    def all_pens(self) -> list[PenType]:
        return list(self.s.scalars(select(PenType).order_by(PenType.name, PenType.id)))

    def all_inks(self, pen_id: int | None = None) -> list[InkColor]:
        stmt = select(InkColor).order_by(InkColor.pen_type_id, InkColor.name)
        if pen_id is not None:
            stmt = stmt.where(InkColor.pen_type_id == pen_id)
        return list(self.s.scalars(stmt))

    def all_templates(self) -> list[Template]:
        return list(self.s.scalars(select(Template).order_by(Template.name, Template.id)))

    def compat_rows(self) -> list[PaperPenCompat]:
        return list(self.s.scalars(select(PaperPenCompat).order_by(PaperPenCompat.paper_type_id,
                                                                   PaperPenCompat.pen_type_id)))

    def compat(self, paper_id: int, pen_id: int) -> PaperPenCompat | None:
        return self.s.get(PaperPenCompat, (paper_id, pen_id))

    def lock(self, model, pk: int):
        return self.s.scalar(select(model).where(model.id == pk).with_for_update())

    def code_taken(self, model, code: str) -> bool:
        return self.s.scalar(select(model.id).where(model.code == code)) is not None

    def add(self, row):
        self.s.add(row)
        self.s.flush()
        self.s.refresh(row)
        return row

    def pricing_versions(self) -> list[PricingConfig]:
        return list(self.s.scalars(select(PricingConfig).order_by(PricingConfig.version.desc())))

    def pricing_version(self, version: int) -> PricingConfig | None:
        return self.s.scalar(select(PricingConfig).where(PricingConfig.version == version))

    def lock_active_pricing(self) -> PricingConfig | None:
        return self.s.scalar(select(PricingConfig).where(PricingConfig.is_active).with_for_update())

    def next_pricing_version(self) -> int:
        return (self.s.scalar(select(func.max(PricingConfig.version))) or 0) + 1

    def deactivate_pricing(self) -> None:
        self.s.execute(update(PricingConfig).where(PricingConfig.is_active).values(is_active=False))
        self.s.flush()
