"""Data access for payments, robots and production jobs. No business rules."""
from __future__ import annotations  # methods named `list` would otherwise shadow the builtin in later annotations

from datetime import datetime, timezone

from sqlalchemy import func, select, update
from sqlalchemy.orm import Session

from app.models.ops import (ACTIVE_JOB_STATUSES, Calibration, Incident, JobEvent, JobStatus, Payment, PaymentGateway,
                            PaymentStatus, PaymentType, ProductionJob, ProductPhoto, Robot, RobotStatus)


class PaymentRepository:
    def __init__(self, session: Session):
        self.s = session

    def add(self, row: Payment) -> Payment:
        self.s.add(row)
        self.s.flush()
        self.s.refresh(row)
        return row

    def get(self, payment_id: int, *, lock: bool = False) -> Payment | None:
        stmt = select(Payment).where(Payment.id == payment_id)
        return self.s.scalar(stmt.with_for_update() if lock else stmt)

    def by_txn(self, gateway: PaymentGateway, txn_id: str, *, lock: bool = False) -> Payment | None:
        stmt = select(Payment).where(Payment.gateway == gateway, Payment.gateway_txn_id == txn_id)
        return self.s.scalar(stmt.with_for_update() if lock else stmt)

    def for_order(self, order_id: int) -> list[Payment]:
        return list(self.s.scalars(select(Payment).where(Payment.order_id == order_id)
                                   .order_by(Payment.created_at, Payment.id)))

    def by_group(self, order_id: int, group_txn: str) -> list[Payment]:
        """Rows paid together in one gateway transaction (FINAL + SHIPPING share `gateway_payload.group_txn`)."""
        return list(self.s.scalars(select(Payment).where(
            Payment.order_id == order_id, Payment.gateway_payload["group_txn"].astext == group_txn).order_by(Payment.id)))

    def pending_final(self, order_id: int) -> list[Payment]:
        """Open FINAL / SHIPPING rows (the final payment is one transaction made of these two)."""
        return list(self.s.scalars(select(Payment).where(
            Payment.order_id == order_id, Payment.type.in_((PaymentType.FINAL, PaymentType.SHIPPING)),
            Payment.status == PaymentStatus.PENDING).order_by(Payment.id)))

    def pending(self, order_id: int, ptype: PaymentType) -> list[Payment]:
        return list(self.s.scalars(select(Payment).where(
            Payment.order_id == order_id, Payment.type == ptype, Payment.status == PaymentStatus.PENDING)
            .order_by(Payment.id)))

    def success(self, order_id: int, ptype: PaymentType) -> Payment | None:
        return self.s.scalar(select(Payment).where(
            Payment.order_id == order_id, Payment.type == ptype, Payment.status == PaymentStatus.SUCCESS))


class RobotRepository:
    def __init__(self, session: Session):
        self.s = session

    def add(self, row: Robot) -> Robot:
        self.s.add(row)
        self.s.flush()
        self.s.refresh(row)
        return row

    def get(self, robot_id: int, *, lock: bool = False) -> Robot | None:
        stmt = select(Robot).where(Robot.id == robot_id)
        return self.s.scalar(stmt.with_for_update() if lock else stmt)

    def by_code(self, code: str) -> Robot | None:
        return self.s.scalar(select(Robot).where(Robot.code == code))

    def list(self, status: RobotStatus | None = None) -> list[Robot]:
        stmt = select(Robot).order_by(Robot.code)
        if status is not None:
            stmt = stmt.where(Robot.status == status)
        return list(self.s.scalars(stmt))


class JobRepository:
    def __init__(self, session: Session):
        self.s = session

    def add(self, row: ProductionJob) -> ProductionJob:
        self.s.add(row)
        self.s.flush()
        self.s.refresh(row)
        return row

    def get(self, job_id: int, *, lock: bool = False) -> ProductionJob | None:
        stmt = select(ProductionJob).where(ProductionJob.id == job_id)
        return self.s.scalar(stmt.with_for_update() if lock else stmt)

    def for_order(self, order_id: int) -> list[ProductionJob]:
        return list(self.s.scalars(select(ProductionJob).where(ProductionJob.order_id == order_id)
                                   .order_by(ProductionJob.id)))

    def active_for_order(self, order_id: int) -> ProductionJob | None:
        return self.s.scalar(select(ProductionJob).where(ProductionJob.order_id == order_id,
                                                         ProductionJob.status.in_(ACTIVE_JOB_STATUSES)))

    def latest_in(self, order_id: int, statuses: tuple[JobStatus, ...], *, lock: bool = False) -> ProductionJob | None:
        stmt = (select(ProductionJob).where(ProductionJob.order_id == order_id, ProductionJob.status.in_(statuses))
                .order_by(ProductionJob.id.desc()).limit(1))
        return self.s.scalar(stmt.with_for_update() if lock else stmt)

    def previous_outcomes(self, order_id: int) -> set[JobStatus]:
        return set(self.s.scalars(select(ProductionJob.status).where(ProductionJob.order_id == order_id)))

    def busy(self, *, since: datetime, exclude_job_id: int | None = None) -> list[ProductionJob]:
        """Active jobs that end after `since`: they occupy their robot and technician."""
        stmt = select(ProductionJob).where(ProductionJob.status.in_(ACTIVE_JOB_STATUSES),
                                           ProductionJob.slot_end > since)
        if exclude_job_id is not None:
            stmt = stmt.where(ProductionJob.id != exclude_job_id)
        return list(self.s.scalars(stmt))

    def future_for_robot(self, robot_id: int, since: datetime) -> list[ProductionJob]:
        return list(self.s.scalars(select(ProductionJob).where(
            ProductionJob.robot_id == robot_id, ProductionJob.status.in_(ACTIVE_JOB_STATUSES),
            ProductionJob.slot_end > since).order_by(ProductionJob.slot_start)))

    def search(self, *, statuses: list[JobStatus] | None, robot_id: int | None, technician_id: int | None,
               start: datetime | None, end: datetime | None, offset: int, limit: int
               ) -> tuple[list[ProductionJob], int]:
        stmt = select(ProductionJob)
        if statuses:
            stmt = stmt.where(ProductionJob.status.in_(statuses))
        if robot_id is not None:
            stmt = stmt.where(ProductionJob.robot_id == robot_id)
        if technician_id is not None:
            stmt = stmt.where(ProductionJob.technician_id == technician_id)
        if start is not None:
            stmt = stmt.where(ProductionJob.slot_end > start)
        if end is not None:
            stmt = stmt.where(ProductionJob.slot_start < end)
        total = self.s.scalar(select(func.count()).select_from(stmt.subquery())) or 0
        rows = list(self.s.scalars(stmt.order_by(ProductionJob.slot_start, ProductionJob.id)
                                   .offset(offset).limit(limit)))
        return rows, total

    def load_by_technician(self, since: datetime) -> dict[int, int]:
        rows = self.s.execute(select(ProductionJob.technician_id, func.count()).where(
            ProductionJob.status.in_(ACTIVE_JOB_STATUSES), ProductionJob.slot_end > since)
            .group_by(ProductionJob.technician_id)).all()
        return {t: n for t, n in rows}


class CalibrationRepository:
    def __init__(self, session: Session):
        self.s = session

    def add(self, row: Calibration) -> Calibration:
        self.s.add(row)
        self.s.flush()
        self.s.refresh(row)
        return row

    def invalidate_all(self, job_id: int) -> None:
        self.s.execute(update(Calibration).where(Calibration.job_id == job_id, Calibration.is_valid)
                       .values(is_valid=False))

    def latest(self, job_id: int) -> Calibration | None:
        return self.s.scalar(select(Calibration).where(Calibration.job_id == job_id)
                             .order_by(Calibration.id.desc()).limit(1))

    def valid(self, job_id: int) -> Calibration | None:
        return self.s.scalar(select(Calibration).where(Calibration.job_id == job_id, Calibration.is_valid)
                             .order_by(Calibration.id.desc()).limit(1))


class EventRepository:
    def __init__(self, session: Session):
        self.s = session

    def add(self, row: JobEvent) -> JobEvent:
        self.s.add(row)
        self.s.flush()
        self.s.refresh(row)
        return row

    def for_job(self, job_id: int, *, offset: int, limit: int) -> tuple[list[JobEvent], int]:
        stmt = select(JobEvent).where(JobEvent.job_id == job_id)
        total = self.s.scalar(select(func.count()).select_from(stmt.subquery())) or 0
        rows = list(self.s.scalars(stmt.order_by(JobEvent.id).offset(offset).limit(limit)))
        return rows, total


class IncidentRepository:
    def __init__(self, session: Session):
        self.s = session

    def add(self, row: Incident) -> Incident:
        self.s.add(row)
        self.s.flush()
        self.s.refresh(row)
        return row

    def get(self, incident_id: int, *, lock: bool = False) -> Incident | None:
        stmt = select(Incident).where(Incident.id == incident_id)
        return self.s.scalar(stmt.with_for_update() if lock else stmt)

    def for_job(self, job_id: int) -> list[Incident]:
        return list(self.s.scalars(select(Incident).where(Incident.job_id == job_id).order_by(Incident.id)))

    def search(self, *, resolved: bool | None, robot_id: int | None, offset: int, limit: int
               ) -> tuple[list[Incident], int]:
        stmt = select(Incident)
        if resolved is not None:
            stmt = stmt.where(Incident.resolved_at.is_not(None) if resolved else Incident.resolved_at.is_(None))
        if robot_id is not None:
            stmt = stmt.where(Incident.robot_id == robot_id)
        total = self.s.scalar(select(func.count()).select_from(stmt.subquery())) or 0
        rows = list(self.s.scalars(stmt.order_by(Incident.created_at.desc(), Incident.id.desc())
                                   .offset(offset).limit(limit)))
        return rows, total


class PhotoRepository:
    def __init__(self, session: Session):
        self.s = session

    def add(self, row: ProductPhoto) -> ProductPhoto:
        self.s.add(row)
        self.s.flush()
        self.s.refresh(row)
        return row

    def get(self, job_id: int, photo_id: int) -> ProductPhoto | None:
        return self.s.scalar(select(ProductPhoto).where(
            ProductPhoto.id == photo_id, ProductPhoto.job_id == job_id, ProductPhoto.deleted_at.is_(None)))

    def by_path(self, job_id: int, path: str) -> ProductPhoto | None:
        return self.s.scalar(select(ProductPhoto).where(ProductPhoto.job_id == job_id, ProductPhoto.url == path))

    def live(self, job_id: int) -> list[ProductPhoto]:
        return list(self.s.scalars(select(ProductPhoto).where(
            ProductPhoto.job_id == job_id, ProductPhoto.deleted_at.is_(None)).order_by(ProductPhoto.id)))

    def soft_delete(self, row: ProductPhoto) -> None:
        row.deleted_at = datetime.now(timezone.utc)
        self.s.flush()
