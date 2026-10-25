"""Robot Agent link: the workstation agent connects OUT to the backend; commands are durable rows it pulls.

* `robot_agents`: one credential per robot (only the SHA-256 of the key is stored; the key is shown once, by a Manager).
* `robot_commands`: what Technical Staff ask the agent to do (LOAD, PREFLIGHT, DRY_RUN, RUN, PAUSE, RESUME, STOP, PAPER_CHANGED,
  IDENTIFY). A command is never replayed: it is PENDING until the agent pulls it (DELIVERED), and a PENDING command past its
  `expires_at` becomes EXPIRED instead of being run late. `idempotency_key` makes a retried request create one command.

Nothing is changed or deleted in existing tables.

Revision ID: 0010
Revises: 0009
"""
import sqlalchemy as sa
from alembic import op

revision = "0010"
down_revision = "0009"
branch_labels = None
depends_on = None

STATEMENTS = [
    """CREATE TABLE IF NOT EXISTS robot_agents (
         id BIGSERIAL PRIMARY KEY,
         robot_id BIGINT NOT NULL REFERENCES robots(id),
         key_hash CHAR(64) NOT NULL,
         key_prefix VARCHAR(12) NOT NULL,
         created_by BIGINT NOT NULL REFERENCES accounts(id),
         created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
         revoked_at TIMESTAMPTZ,
         last_seen_at TIMESTAMPTZ)""",
    "CREATE UNIQUE INDEX IF NOT EXISTS ux_robot_agents_active ON robot_agents (robot_id) WHERE revoked_at IS NULL",
    "CREATE UNIQUE INDEX IF NOT EXISTS ux_robot_agents_key ON robot_agents (key_hash)",
    """CREATE TABLE IF NOT EXISTS robot_commands (
         id UUID PRIMARY KEY,
         robot_id BIGINT NOT NULL REFERENCES robots(id),
         job_id BIGINT REFERENCES production_jobs(id),
         kind VARCHAR(20) NOT NULL,
         params JSONB NOT NULL DEFAULT '{}'::jsonb,
         status VARCHAR(10) NOT NULL DEFAULT 'PENDING',
         result JSONB,
         error_code VARCHAR(40),
         error_message TEXT,
         idempotency_key VARCHAR(80),
         created_by BIGINT NOT NULL REFERENCES accounts(id),
         created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
         expires_at TIMESTAMPTZ NOT NULL,
         delivered_at TIMESTAMPTZ,
         finished_at TIMESTAMPTZ,
         CONSTRAINT chk_robot_command_kind CHECK (kind IN
           ('LOAD','PREFLIGHT','DRY_RUN','RUN','PAUSE','RESUME','STOP','PAPER_CHANGED','IDENTIFY')),
         CONSTRAINT chk_robot_command_status CHECK (status IN
           ('PENDING','DELIVERED','DONE','FAILED','EXPIRED','CANCELLED')))""",
    "CREATE INDEX IF NOT EXISTS ix_robot_commands_robot_status ON robot_commands (robot_id, status, created_at)",
    "CREATE INDEX IF NOT EXISTS ix_robot_commands_job ON robot_commands (job_id, created_at DESC)",
    "CREATE UNIQUE INDEX IF NOT EXISTS ux_robot_commands_idem ON robot_commands (created_by, idempotency_key) WHERE idempotency_key IS NOT NULL",
    "ALTER TABLE robot_agents ENABLE ROW LEVEL SECURITY",
    "ALTER TABLE robot_commands ENABLE ROW LEVEL SECURITY",
]


TECH, MGR = "TECHNICAL_STAFF", "MANAGER"
# (code, level, title, action, notify roles, e-mail): a lost agent-to-backend link is NOT a lost robot link, so it is orange, not red:
# the agent finishes the stroke it is on, lifts the pen and pauses; the physical E-Stop stays the real safety.
CATALOG = [
    ("BACKEND_LINK_LOST", 3, "Máy trạm mất kết nối tới hệ thống trong lúc đang viết: robot đã viết xong nét hiện tại, nhấc bút và tạm dừng.",
     "Kiểm tra mạng của máy trạm. Khi kết nối lại, chọn tiếp tục hoặc dừng job. Nếu thấy robot chuyển động bất thường, dùng nút dừng khẩn vật lý.",
     [TECH, MGR], False),
]


def upgrade() -> None:
    conn = op.get_bind()
    for stmt in STATEMENTS:
        conn.exec_driver_sql(stmt)
    ins = sa.text("""INSERT INTO alert_catalog (code, level, title_vi, action_vi, estop_advised, notify_roles, send_email)
                     VALUES (:code, :level, :title, :action, :estop, :roles, :mail) ON CONFLICT (code) DO NOTHING""")
    for code, level, title, action, roles, mail in CATALOG:
        conn.execute(ins, dict(code=code, level=level, title=title, action=action, estop=(level == 4), roles=roles, mail=(level == 4)))


def downgrade() -> None:
    conn = op.get_bind()
    conn.exec_driver_sql("DELETE FROM alert_catalog WHERE code = 'BACKEND_LINK_LOST' AND NOT EXISTS "
                         "(SELECT 1 FROM robot_alerts WHERE code = 'BACKEND_LINK_LOST')")
    conn.exec_driver_sql("DROP TABLE IF EXISTS robot_commands")
    conn.exec_driver_sql("DROP TABLE IF EXISTS robot_agents")
