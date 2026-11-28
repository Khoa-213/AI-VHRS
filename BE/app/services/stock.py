"""Stock in and out (migration 0033, owner decisions 2026-11-27 Q1-Q4).

Every change of a material's `stock_qty` goes through `Ledger.move`, which locks the material row, applies the change and
writes one append-only `stock_movements` row with the level after it. Who changes what:

* the Manager receives goods on a receipt with several lines (RECEIPT) and corrects a count (ADJUST, existing endpoints);
* the technician issues the paper of a job before Prepare, and a new pen (with its ink, unit: pens) only when the pen on the
  robot is replaced (ISSUE);
* at Writing done the paper the job did not use goes back (RETURN); using more than was issued is recorded as an extra
  ISSUE that never blocks the finish (the stock floors at 0 and the shortfall is kept on the row).
"""
from __future__ import annotations

from datetime import date
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.errors import AppError
from app.models.account import Account, AuditLog
from app.models.catalog import InkColor, PaperType, PenType
from app.models.ops import JobStatus, ProductionJob
from app.models.order import Order
from app.models.sketch import Sketch
from app.models.stock import StockMovement, StockReceipt
from app.services import audit

MODELS: dict[str, Any] = {"PAPER": PaperType, "PEN": PenType, "INK": InkColor}
UNIT = {"PAPER": "tờ", "PEN": "cây", "INK": "cây"}
NAME = {"PAPER": "Giấy", "PEN": "Bút", "INK": "Mực"}

# Jobs whose materials are still to be issued: their paper is "kept" for them in the Manager's overview.
_WAITING = (JobStatus.SCHEDULED,)


class Ledger:
    """Writes stock movements. The caller owns the transaction."""

    def __init__(self, session: Session, actor_id: int | None):
        self.s, self.actor_id = session, actor_id

    def lock_item(self, item_kind: str, item_id: int):
        model = MODELS[item_kind]
        row = self.s.scalar(select(model).where(model.id == item_id).with_for_update())
        if row is None:
            raise AppError(404, "ITEM_NOT_FOUND", f"Không tìm thấy vật tư {item_kind} #{item_id}.")
        return row

    def move(self, kind: str, item_kind: str, item_id: int, quantity: int, *, job_id: int | None = None,
             receipt_id: int | None = None, reason: str | None = None, floor: bool = False) -> StockMovement:
        """Apply `quantity` (signed) to the item. Going below 0 is refused (409 STOCK_SHORT) unless `floor`: then the
        level stops at 0 and what was missing is kept as `shortfall` (a finish is never blocked by a stale count)."""
        if quantity == 0:
            raise AppError(422, "STOCK_ZERO", "Số lượng phải khác 0.")
        row = self.lock_item(item_kind, item_id)
        after = row.stock_qty + quantity
        short = 0
        if after < 0:
            if not floor:
                raise AppError(409, "STOCK_SHORT", f"{NAME[item_kind]} '{row.name}' chỉ còn {row.stock_qty} {UNIT[item_kind]}, "
                               f"cần {-quantity}.", {"item_kind": item_kind, "item_id": item_id, "stock": row.stock_qty,
                                                     "needed": -quantity})
            short, after = -after, 0
        row.stock_qty = after
        mv = StockMovement(kind=kind, item_kind=item_kind, item_id=item_id, quantity=quantity, stock_after=after,
                           shortfall=short, job_id=job_id, receipt_id=receipt_id, actor_id=self.actor_id, reason=reason)
        self.s.add(mv)
        self.s.flush()
        return mv

    def job_net(self, job_id: int) -> dict[str, dict[int, int]]:
        """What a job holds now, per item: issued minus returned (positive = taken from the shelf)."""
        rows = self.s.execute(
            select(StockMovement.item_kind, StockMovement.item_id, func.sum(StockMovement.quantity))
            .where(StockMovement.job_id == job_id, StockMovement.kind.in_(("ISSUE", "RETURN")))
            .group_by(StockMovement.item_kind, StockMovement.item_id)).all()
        out: dict[str, dict[int, int]] = {k: {} for k in MODELS}
        for item_kind, item_id, total in rows:
            out[item_kind][item_id] = -int(total or 0)
        return out

    def job_moves(self, job_id: int) -> list[StockMovement]:
        return list(self.s.scalars(select(StockMovement).where(StockMovement.job_id == job_id)
                                   .order_by(StockMovement.id)))


# ---------------------------------------------------------------------------------------------- K1 (audit 2026-11-28)
# Paper a job took came back only at "Writing done". A job that failed (incident), or was cancelled (unscheduled, rescheduled,
# order cancelled), kept its sheets for ever: no stock action is allowed on a job that is no longer open, so the shelf level
# stayed too low after every incident or re-plan and only a manual count could correct it.
SETTLE_ACTION = "STOCK_SETTLE"                              # audit row = this job's paper was settled once (the marker)
ENDED_UNFINISHED = (JobStatus.FAILED, JobStatus.CANCELLED)


def paper_held(session: Session, job_id: int) -> dict[int, int]:
    """Sheets the job still holds, per paper: issued minus returned, where that is above zero."""
    return {item_id: n for item_id, n in Ledger(session, None).job_net(job_id)["PAPER"].items() if n > 0}


def stock_settled(session: Session, job_id: int) -> bool:
    return session.scalar(select(AuditLog.id).where(AuditLog.action == SETTLE_ACTION, AuditLog.entity_type == "production_job",
                                                    AuditLog.entity_id == job_id).limit(1)) is not None


def _give_back(session: Session, job_id: int, held: dict[int, int], back: int, *, actor_id: int | None, reason: str) -> None:
    for item_id in sorted(held):                            # one lock order everywhere
        n = min(held[item_id], back)
        if n > 0:
            Ledger(session, actor_id).move("RETURN", "PAPER", item_id, n, job_id=job_id, reason=reason[:500])
            back -= n


def return_unprepared(session: Session, job: ProductionJob, *, actor_id: int | None, reason: str, ip: str | None = None) -> int:
    """A job that ends while still SCHEDULED was never prepared: it used nothing, so everything it took goes back at once.
    The caller has just cancelled the job (unschedule, reschedule, order cancelled). Returns the sheets given back."""
    held = paper_held(session, job.id)
    total = sum(held.values())
    if total == 0 or stock_settled(session, job.id):
        return 0
    _give_back(session, job.id, held, total, actor_id=actor_id, reason=f"Trả giấy: job huỷ trước khi chuẩn bị ({reason})")
    audit.record(session, actor_id=actor_id, action=SETTLE_ACTION, entity_type="production_job", entity_id=job.id,
                 new={"held": total, "waste": 0, "returned": total, "automatic": True}, reason=reason[:500], ip=ip)
    return total


def settle_job(session: Session, job: ProductionJob, *, actor_id: int, waste: int, ip: str | None = None) -> dict[str, int]:
    """A job that was started and then ended without "written" (an incident, or cancelled half-way). Somebody at the robot
    counts the sheets that were spoiled; the rest goes back to the shelf. Once per job. The caller holds the job's row lock."""
    if job.status not in ENDED_UNFINISHED:
        raise AppError(409, "STOCK_SETTLE_NOT_ALLOWED", "Chỉ quyết toán giấy cho job đã hỏng hoặc đã huỷ. Job đang làm thì giấy thừa "
                       "được trả ở bước Viết xong.", {"job_status": job.status.value})
    if stock_settled(session, job.id):
        raise AppError(409, "STOCK_ALREADY_SETTLED", "Giấy của job này đã được quyết toán rồi.")
    held = paper_held(session, job.id)
    total = sum(held.values())
    if total == 0:
        raise AppError(409, "NOTHING_TO_SETTLE", "Job này không còn giữ tờ giấy nào.")
    if waste < 0 or waste > total:
        raise AppError(422, "WASTE_OUT_OF_RANGE", f"Số tờ hỏng phải từ 0 tới {total} (số tờ job đang giữ).", {"held": total})
    back = total - waste
    _give_back(session, job.id, held, back, actor_id=actor_id, reason=f"Quyết toán giấy job {job.status.value} (hỏng {waste})")
    audit.record(session, actor_id=actor_id, action=SETTLE_ACTION, entity_type="production_job", entity_id=job.id,
                 new={"held": total, "waste": waste, "returned": back, "automatic": False}, ip=ip)
    return {"job_id": job.id, "held": total, "waste": waste, "returned": back}


def item_name(session: Session, item_kind: str, item_id: int) -> str:
    row = session.get(MODELS[item_kind], item_id)
    return row.name if row is not None else f"#{item_id}"


class StockService:
    """The Manager's side: overview with what scheduled jobs keep, receipts, the ledger."""

    def __init__(self, session: Session, manager: Account, ip: str | None = None):
        self.s, self.manager, self.ip = session, manager, ip
        self.ledger = Ledger(session, manager.id)

    # ------------------------------------------------------------------ overview
    def overview(self) -> list[dict[str, Any]]:
        kept: dict[int, int] = {}
        # Paper kept for scheduled jobs that have not taken it yet: copies x sheets per copy. K3 (stock audit 2026-11-28): it
        # used to count one sheet per copy, so a document of several pages warned too late. The sheets per copy are the pages
        # of the job's sketch (one customer picture per page); a sketch from before those pictures counts as one page.
        rows = self.s.execute(
            select(Order.paper_type_id, Order.quantity * func.greatest(func.coalesce(func.cardinality(Sketch.image_urls), 0), 1),
                   ProductionJob.id)
            .join(ProductionJob, ProductionJob.order_id == Order.id)
            .join(Sketch, Sketch.id == ProductionJob.sketch_id)
            .where(ProductionJob.status.in_(_WAITING), Order.paper_type_id.is_not(None))).all()
        issued_jobs = set(self.s.scalars(select(StockMovement.job_id).where(
            StockMovement.kind == "ISSUE", StockMovement.item_kind == "PAPER",
            StockMovement.job_id.in_([r[2] for r in rows] or [-1]))))
        for paper_id, qty, job_id in rows:
            if job_id not in issued_jobs:
                kept[paper_id] = kept.get(paper_id, 0) + max(qty or 1, 1)
        out = []
        for item_kind, model in MODELS.items():
            for row in self.s.scalars(select(model).order_by(model.is_active.desc(), model.name, model.id)):
                k = kept.get(row.id, 0) if item_kind == "PAPER" else 0
                free = row.stock_qty - k
                status = "SHORT" if free < 0 else "LOW" if row.stock_qty < row.min_qty else "OK"
                spec = (f"{row.size.value} · {row.gsm} gsm" if item_kind == "PAPER"
                        else f"{row.category} · {row.stroke_width_mm} mm" if item_kind == "PEN"
                        else (row.hex_code or ""))
                out.append({"item_kind": item_kind, "item_id": row.id, "code": getattr(row, "code", None),
                            "name": row.name, "spec": spec, "unit": UNIT[item_kind], "hex_code": getattr(row, "hex_code", None),
                            "pen_type_id": getattr(row, "pen_type_id", None), "is_active": row.is_active,
                            "stock_qty": row.stock_qty, "min_qty": row.min_qty, "kept_for_jobs": k, "free": free,
                            "status": status})
        return out

    # ------------------------------------------------------------------ receipts
    def _receipt_out(self, rec: StockReceipt) -> dict[str, Any]:
        lines = list(self.s.scalars(select(StockMovement).where(StockMovement.receipt_id == rec.id)
                                    .order_by(StockMovement.id)))
        return {"id": rec.id, "code": rec.code, "supplier": rec.supplier, "received_on": rec.received_on, "note": rec.note,
                "created_by": rec.created_by, "created_at": rec.created_at,
                "lines": [{"item_kind": m.item_kind, "item_id": m.item_id, "name": item_name(self.s, m.item_kind, m.item_id),
                           "quantity": m.quantity, "stock_after": m.stock_after} for m in lines]}

    def create_receipt(self, *, supplier: str | None, received_on: date | None, note: str | None,
                       client_ref: str | None, lines: list[dict[str, Any]]) -> tuple[dict[str, Any], bool]:
        """(receipt, created). The same `client_ref` again returns the receipt already made (a double submit)."""
        if client_ref:
            old = self.s.scalar(select(StockReceipt).where(StockReceipt.client_ref == client_ref))
            if old is not None:
                return self._receipt_out(old), False
        seen = set()
        for ln in lines:
            key = (ln["item_kind"], ln["item_id"])
            if key in seen:
                raise AppError(422, "DUPLICATE_LINE", "Một vật tư chỉ được một dòng trong phiếu nhập.", {"item": list(key)})
            seen.add(key)
        rec = StockReceipt(supplier=supplier, received_on=received_on or date.today(), note=note, client_ref=client_ref,
                           created_by=self.manager.id)
        try:
            with self.s.begin_nested():
                self.s.add(rec)
                self.s.flush()
        except IntegrityError:                                  # the same client_ref saved by a request running alongside
            old = self.s.scalar(select(StockReceipt).where(StockReceipt.client_ref == client_ref))
            if old is None:
                raise
            return self._receipt_out(old), False
        rec.code = f"NK-{rec.id:04d}"
        # Lock the items in one order (kind, id) so two receipts touching the same items cannot deadlock.
        for ln in sorted(lines, key=lambda x: (x["item_kind"], x["item_id"])):
            self.ledger.move("RECEIPT", ln["item_kind"], ln["item_id"], ln["quantity"], receipt_id=rec.id,
                             reason=supplier)
        self.s.flush()
        audit.record(self.s, actor_id=self.manager.id, action="STOCK_RECEIPT", entity_type="stock_receipt",
                     entity_id=rec.id, new={"code": rec.code, "lines": [[ln["item_kind"], ln["item_id"], ln["quantity"]]
                                                                        for ln in lines]}, ip=self.ip)
        return self._receipt_out(rec), True

    def receipt(self, receipt_id: int) -> dict[str, Any]:
        rec = self.s.get(StockReceipt, receipt_id)
        if rec is None:
            raise AppError(404, "NOT_FOUND", "Không tìm thấy phiếu nhập.")
        return self._receipt_out(rec)

    # ------------------------------------------------------------------ ledger
    def movements(self, **kw: Any) -> tuple[list[dict[str, Any]], int]:
        return list_movements(self.s, **kw)


def list_movements(session: Session, *, kind: str | None = None, item_kind: str | None = None, item_id: int | None = None,
                   job_id: int | None = None, page: int = 1, page_size: int = 50) -> tuple[list[dict[str, Any]], int]:
    """Ledger rows, newest first, with the item, receipt code and actor names the screens show."""
    s = session
    q = select(StockMovement)
    if kind:
        q = q.where(StockMovement.kind == kind)
    if item_kind:
        q = q.where(StockMovement.item_kind == item_kind)
    if item_id is not None:
        q = q.where(StockMovement.item_id == item_id)
    if job_id is not None:
        q = q.where(StockMovement.job_id == job_id)
    total = s.scalar(select(func.count()).select_from(q.subquery())) or 0
    rows = list(s.scalars(q.order_by(StockMovement.created_at.desc(), StockMovement.id.desc())
                          .offset((page - 1) * page_size).limit(page_size)))
    codes = dict(s.execute(select(StockReceipt.id, StockReceipt.code).where(
        StockReceipt.id.in_({m.receipt_id for m in rows if m.receipt_id} or {-1}))).all())
    actors = dict(s.execute(select(Account.id, Account.full_name).where(
        Account.id.in_({m.actor_id for m in rows if m.actor_id} or {-1}))).all())
    names: dict[tuple[str, int], str] = {}
    out = []
    for m in rows:
        key = (m.item_kind, m.item_id)
        if key not in names:
            names[key] = item_name(s, *key)
        out.append({"id": m.id, "kind": m.kind, "item_kind": m.item_kind, "item_id": m.item_id, "item_name": names[key],
                    "unit": UNIT[m.item_kind], "quantity": m.quantity, "stock_after": m.stock_after,
                    "shortfall": m.shortfall, "job_id": m.job_id, "receipt_id": m.receipt_id,
                    "receipt_code": codes.get(m.receipt_id), "actor_id": m.actor_id, "actor_name": actors.get(m.actor_id),
                    "reason": m.reason, "created_at": m.created_at})
    return out, total
