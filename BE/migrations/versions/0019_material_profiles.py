"""Upgrade U6: extended material specs with their source, measured paper + pen + ink profiles, preview tier.

* `paper_types.specs`, `pen_types.specs`, `ink_colors.specs` JSONB NOT NULL DEFAULT '{}': descriptive fields, each with
  its source (SUPPLIER / MEASURED / ASSUMED), validated by app/domain/material_specs.py.
* `material_profiles`: what a paper + pen + ink combination (optionally on one robot) really does on a test sheet: line
  width, darkness, bleed, recommended speed; status UNCALIBRATED -> MEASURED -> VERIFIED, who measured / verified, how,
  evidence. At most one profile per combination (robot NULL = any robot).
* `sketches.render_profile_id`: the profile whose measured line width drew the customer image (NULL = nominal pen
  width, a "visual" preview).

Additive only: no existing row changes (the new JSONB columns default to '{}'). Rollback: `alembic downgrade 0018`.

Revision ID: 0019
Revises: 0018
"""
from alembic import op

revision = "0019"
down_revision = "0018"
branch_labels = None
depends_on = None

UPGRADE = [
    "ALTER TABLE paper_types ADD COLUMN IF NOT EXISTS specs JSONB NOT NULL DEFAULT '{}'::jsonb",
    "ALTER TABLE pen_types ADD COLUMN IF NOT EXISTS specs JSONB NOT NULL DEFAULT '{}'::jsonb",
    "ALTER TABLE ink_colors ADD COLUMN IF NOT EXISTS specs JSONB NOT NULL DEFAULT '{}'::jsonb",
    """CREATE TABLE IF NOT EXISTS material_profiles (
        id             BIGSERIAL PRIMARY KEY,
        paper_type_id  BIGINT NOT NULL REFERENCES paper_types(id),
        pen_type_id    BIGINT NOT NULL REFERENCES pen_types(id),
        ink_color_id   BIGINT NOT NULL REFERENCES ink_colors(id),
        robot_id       BIGINT REFERENCES robots(id),
        line_width_mm  NUMERIC(4,2) CHECK (line_width_mm > 0),
        darkness       NUMERIC(4,3) CHECK (darkness BETWEEN 0 AND 1),
        bleed_mm       NUMERIC(4,2) CHECK (bleed_mm >= 0),
        v_max_mm_s     NUMERIC(5,1) CHECK (v_max_mm_s > 0),
        status         VARCHAR(12) NOT NULL DEFAULT 'UNCALIBRATED'
                       CHECK (status IN ('UNCALIBRATED', 'MEASURED', 'VERIFIED')),
        method         TEXT,
        evidence_uri   TEXT,
        note           TEXT,
        measured_by    BIGINT REFERENCES accounts(id),
        measured_at    TIMESTAMPTZ,
        verified_by    BIGINT REFERENCES accounts(id),
        verified_at    TIMESTAMPTZ,
        created_at     TIMESTAMPTZ NOT NULL DEFAULT now(),
        updated_at     TIMESTAMPTZ NOT NULL DEFAULT now(),
        CONSTRAINT chk_profile_measured CHECK (status = 'UNCALIBRATED' OR (line_width_mm IS NOT NULL AND measured_at IS NOT NULL)),
        CONSTRAINT chk_profile_verified CHECK (status <> 'VERIFIED' OR verified_at IS NOT NULL)
    )""",
    """CREATE UNIQUE INDEX IF NOT EXISTS ux_material_profile_combo
       ON material_profiles (paper_type_id, pen_type_id, ink_color_id, COALESCE(robot_id, 0))""",
    "ALTER TABLE sketches ADD COLUMN IF NOT EXISTS render_profile_id BIGINT REFERENCES material_profiles(id)",
]

DOWNGRADE = [
    "ALTER TABLE sketches DROP COLUMN IF EXISTS render_profile_id",
    "DROP TABLE IF EXISTS material_profiles",
    "ALTER TABLE ink_colors DROP COLUMN IF EXISTS specs",
    "ALTER TABLE pen_types DROP COLUMN IF EXISTS specs",
    "ALTER TABLE paper_types DROP COLUMN IF EXISTS specs",
]


def upgrade() -> None:
    conn = op.get_bind()
    for stmt in UPGRADE:
        conn.exec_driver_sql(stmt)


def downgrade() -> None:
    conn = op.get_bind()
    for stmt in DOWNGRADE:
        conn.exec_driver_sql(stmt)
