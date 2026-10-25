"""Robot operations: runs, alerts and the alert catalogue (robot integration, 2026-10-23). Additive only.

* `robots`: controller / firmware / SDK / agent versions, connection state, last time seen, last mode (MOCK | SIM | REAL).
* `robot_runs`: one row per run of the Robot Agent on a job (also dry runs and refused attempts). A REAL run must carry the
  operator who authorized it (CHECK), and a robot has at most ONE open run (unique partial index): the database itself refuses a
  second controller.
* `alert_catalog`: the fixed list of alerts with the plain-Vietnamese sentence, the action for the operator, the level (1 green,
  2 yellow, 3 orange = the robot has already stopped itself, 4 red = press the physical E-Stop now), who is told and whether an
  e-mail goes out. Level 4 and "E-Stop advised" are the same thing (CHECK). The Manager edits wording and thresholds.
* `robot_alerts`: raised alerts. Title / action are copied from the catalogue at raise time so later wording changes never rewrite
  history. One OPEN alert per (robot, code, job): a repeat increments `occurrences` instead of flooding the screen.

Seed: the 16 catalogue rows (idempotent). Row-level security is enabled like on every other table. Nothing existing is changed.
Downgrade drops the three new tables and the new `robots` columns (only the new robot-ops data is lost).

Revision ID: 0008
Revises: 0007
"""
import sqlalchemy as sa
from alembic import op

revision = "0008"
down_revision = "0007"
branch_labels = None
depends_on = None

DDL = [
    """ALTER TABLE robots
         ADD COLUMN IF NOT EXISTS controller_version VARCHAR(60),
         ADD COLUMN IF NOT EXISTS firmware_version VARCHAR(80),
         ADD COLUMN IF NOT EXISTS sdk_version VARCHAR(60),
         ADD COLUMN IF NOT EXISTS agent_version VARCHAR(30),
         ADD COLUMN IF NOT EXISTS connection_state VARCHAR(10) NOT NULL DEFAULT 'UNKNOWN',
         ADD COLUMN IF NOT EXISTS last_seen_at TIMESTAMPTZ,
         ADD COLUMN IF NOT EXISTS last_mode VARCHAR(10)""",
    """DO $$
BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'chk_robots_connection_state' AND conrelid = 'public.robots'::regclass) THEN
    ALTER TABLE robots ADD CONSTRAINT chk_robots_connection_state CHECK (connection_state IN ('ONLINE', 'OFFLINE', 'UNKNOWN'));
  END IF;
  IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'chk_robots_last_mode' AND conrelid = 'public.robots'::regclass) THEN
    ALTER TABLE robots ADD CONSTRAINT chk_robots_last_mode CHECK (last_mode IS NULL OR last_mode IN ('MOCK', 'SIM', 'REAL'));
  END IF;
END $$""",
    """CREATE TABLE IF NOT EXISTS alert_catalog (
         code VARCHAR(40) PRIMARY KEY,
         level SMALLINT NOT NULL CHECK (level BETWEEN 1 AND 4),
         title_vi TEXT NOT NULL,
         action_vi TEXT NOT NULL,
         estop_advised BOOLEAN NOT NULL DEFAULT FALSE,
         notify_roles TEXT[] NOT NULL DEFAULT '{}',
         send_email BOOLEAN NOT NULL DEFAULT FALSE,
         threshold JSONB,
         is_active BOOLEAN NOT NULL DEFAULT TRUE,
         updated_by BIGINT REFERENCES accounts(id),
         updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
         CONSTRAINT chk_alert_level4_is_estop CHECK ((level = 4) = estop_advised)
       )""",
    """CREATE TABLE IF NOT EXISTS robot_runs (
         id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
         run_id VARCHAR(40) NOT NULL UNIQUE,
         job_id BIGINT NOT NULL REFERENCES production_jobs(id),
         robot_id BIGINT NOT NULL REFERENCES robots(id),
         mode VARCHAR(10) NOT NULL CHECK (mode IN ('MOCK', 'SIM', 'REAL')),
         dry_run BOOLEAN NOT NULL DEFAULT FALSE,
         started_at TIMESTAMPTZ NOT NULL DEFAULT now(),
         ended_at TIMESTAMPTZ,
         result VARCHAR(20) CHECK (result IN ('DONE', 'STOPPED', 'FAULT', 'UNKNOWN', 'DRY_RUN_DONE', 'REFUSED')),
         completed_strokes INTEGER NOT NULL DEFAULT 0 CHECK (completed_strokes >= 0),
         total_strokes INTEGER NOT NULL DEFAULT 0 CHECK (total_strokes >= 0),
         plan_digest VARCHAR(64),
         authorized_by BIGINT REFERENCES accounts(id),
         authorized_at TIMESTAMPTZ,
         agent_version VARCHAR(30),
         robot_info JSONB,
         summary JSONB,
         created_by BIGINT NOT NULL REFERENCES accounts(id),
         CONSTRAINT chk_run_real_authorized CHECK (mode <> 'REAL' OR authorized_by IS NOT NULL OR result IS NOT DISTINCT FROM 'REFUSED'),
         CONSTRAINT chk_run_ended CHECK (ended_at IS NULL OR ended_at >= started_at),
         CONSTRAINT chk_run_progress CHECK (total_strokes = 0 OR completed_strokes <= total_strokes)
       )""",
    "CREATE INDEX IF NOT EXISTS ix_robot_runs_job ON robot_runs (job_id, started_at)",
    "CREATE INDEX IF NOT EXISTS ix_robot_runs_robot ON robot_runs (robot_id, started_at DESC)",
    "CREATE UNIQUE INDEX IF NOT EXISTS ux_robot_runs_one_open ON robot_runs (robot_id) WHERE ended_at IS NULL",
    """CREATE TABLE IF NOT EXISTS robot_alerts (
         id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
         robot_id BIGINT NOT NULL REFERENCES robots(id),
         job_id BIGINT REFERENCES production_jobs(id),
         run_id BIGINT REFERENCES robot_runs(id),
         code VARCHAR(40) NOT NULL REFERENCES alert_catalog(code),
         level SMALLINT NOT NULL CHECK (level BETWEEN 1 AND 4),
         title_vi TEXT NOT NULL,
         action_vi TEXT NOT NULL,
         estop_advised BOOLEAN NOT NULL DEFAULT FALSE,
         details JSONB,
         occurrences INTEGER NOT NULL DEFAULT 1 CHECK (occurrences >= 1),
         raised_at TIMESTAMPTZ NOT NULL DEFAULT now(),
         last_raised_at TIMESTAMPTZ NOT NULL DEFAULT now(),
         emailed_at TIMESTAMPTZ,
         acknowledged_by BIGINT REFERENCES accounts(id),
         acknowledged_at TIMESTAMPTZ,
         resolved_by BIGINT REFERENCES accounts(id),
         resolved_at TIMESTAMPTZ,
         resolution_note TEXT,
         CONSTRAINT chk_alert_ack_pair CHECK ((acknowledged_by IS NULL) = (acknowledged_at IS NULL)),
         CONSTRAINT chk_alert_level4_is_estop CHECK ((level = 4) = estop_advised)
       )""",
    "CREATE INDEX IF NOT EXISTS ix_robot_alerts_open ON robot_alerts (robot_id, level DESC, raised_at DESC) WHERE resolved_at IS NULL",
    "CREATE INDEX IF NOT EXISTS ix_robot_alerts_job ON robot_alerts (job_id, raised_at)",
    """CREATE UNIQUE INDEX IF NOT EXISTS ux_robot_alerts_one_open
         ON robot_alerts (robot_id, code, COALESCE(job_id, 0)) WHERE resolved_at IS NULL""",
    "ALTER TABLE alert_catalog ENABLE ROW LEVEL SECURITY",
    "ALTER TABLE robot_runs ENABLE ROW LEVEL SECURITY",
    "ALTER TABLE robot_alerts ENABLE ROW LEVEL SECURITY",
    "DROP TRIGGER IF EXISTS trg_alert_catalog_updated_at ON alert_catalog",
    "CREATE TRIGGER trg_alert_catalog_updated_at BEFORE UPDATE ON alert_catalog FOR EACH ROW EXECUTE FUNCTION fn_set_updated_at()",
]

TECH, MGR = "TECHNICAL_STAFF", "MANAGER"
# (code, level, title, action, notify roles, e-mail). Thresholds stay NULL until the team measures them on the robot.
CATALOG = [
    ("STOP_NOT_EFFECTIVE", 4, "Đã gửi lệnh dừng nhưng đầu bút vẫn đang di chuyển.",
     "BẤM NÚT E-STOP NGAY. Phần mềm không thể tự dừng robot trong trường hợp này.", [TECH, MGR], True),
    ("LINK_LOST_MOVING", 4, "Mất kết nối với robot khi robot đang chạy.",
     "Nếu robot còn chuyển động, BẤM NÚT E-STOP NGAY. Sau đó kiểm tra dây mạng và nguồn.", [TECH, MGR], True),
    ("TRACKING_ERROR", 4, "Đầu bút lệch xa đường đã định.",
     "BẤM NÚT E-STOP NGAY. Không chạy lại cho tới khi xác định nguyên nhân.", [TECH, MGR], True),
    ("CONTROLLER_SAFETY_FAULT", 4, "Robot báo lỗi an toàn hoặc va chạm trong lúc di chuyển.",
     "BẤM NÚT E-STOP NGAY nếu robot chưa đứng yên, rồi gọi Manager.", [TECH, MGR], True),
    ("OVER_FORCE_STILL", 4, "Lực ép vẫn vượt giới hạn dù đã gửi lệnh dừng.",
     "BẤM NÚT E-STOP NGAY. Bút hoặc giấy có thể đang bị kẹt.", [TECH, MGR], True),
    ("OVER_FORCE", 3, "Bút ép quá mạnh, robot đã tự dừng và nhấc bút.",
     "Kiểm tra bút và tờ giấy (cong, kẹt, sai độ cao). Sau đó chọn tiếp tục hoặc bỏ qua nét dở; không tự chạy lại từ đầu.",
     [TECH, MGR], False),
    ("SENSOR_LOST", 3, "Mất tín hiệu cảm biến lực, robot đã dừng.",
     "Kiểm tra dây USB của gripper rồi chạy lại bước kiểm tra trước khi viết.", [TECH, MGR], False),
    ("STROKE_LOST", 3, "Bút rời khỏi giấy khi đang viết, robot đã tạm dừng.",
     "Kiểm tra giấy có bị nhấc lên hoặc bút có hết mực không, rồi tiếp tục hoặc bỏ qua nét dở.", [TECH], False),
    ("RUN_OUTCOME_UNKNOWN", 3, "Mất kết nối giữa chừng: chưa biết bản viết đã đến đâu.",
     "Nhìn tờ giấy, xác định nét nào đã viết xong, rồi chọn nét bắt đầu lại. Không tự chạy lại từ đầu.", [TECH, MGR], False),
    ("STROKE_INTERRUPTED", 3, "Một nét đang viết dở khi dừng.",
     "Xem nét dở trên giấy rồi chọn viết lại nét đó hoặc bỏ qua.", [TECH], False),
    ("PREFLIGHT_REFUSED", 2, "Chưa chạy được vì bước kiểm tra trước khi chạy không đạt.",
     "Đọc lý do hiển thị và xử lý (hiệu chuẩn, gripper, vị trí bút). Robot không di chuyển.", [TECH], False),
    ("CALIBRATION_OLD", 2, "Hiệu chuẩn đã cũ.", "Nên hiệu chuẩn lại mặt giấy trước khi viết tiếp.", [TECH], False),
    ("FORCE_NEAR_LIMIT", 2, "Lực ép thường xuyên sát giới hạn.", "Kiểm tra bút, giấy và độ cao đặt bút.", [TECH], False),
    ("DROPPED_FRAMES", 2, "Cảm biến lực mất nhiều gói tin.", "Kiểm tra dây USB của gripper.", [TECH], False),
    ("AGENT_OFFLINE", 2, "Máy trạm điều khiển không báo về máy chủ.",
     "Kiểm tra máy trạm và mạng. Nếu robot đang chạy, đứng cạnh nút E-Stop.", [MGR], False),
    ("PAPER_CHANGE", 1, "Cần đặt tờ giấy mới cho trang kế tiếp.", "Đặt giấy mới, kẹp chặt rồi xác nhận để tiếp tục.", [TECH], False),
]


def upgrade() -> None:
    conn = op.get_bind()
    for stmt in DDL:
        conn.exec_driver_sql(stmt)
    ins = sa.text("""INSERT INTO alert_catalog (code, level, title_vi, action_vi, estop_advised, notify_roles, send_email)
                     VALUES (:code, :level, :title, :action, :estop, :roles, :mail) ON CONFLICT (code) DO NOTHING""")
    for code, level, title, action, roles, mail in CATALOG:
        conn.execute(ins, dict(code=code, level=level, title=title, action=action, estop=(level == 4), roles=roles, mail=(level == 4)))


def downgrade() -> None:
    conn = op.get_bind()
    for stmt in ("DROP TABLE IF EXISTS robot_alerts", "DROP TABLE IF EXISTS robot_runs", "DROP TABLE IF EXISTS alert_catalog",
                 "ALTER TABLE robots DROP CONSTRAINT IF EXISTS chk_robots_connection_state",
                 "ALTER TABLE robots DROP CONSTRAINT IF EXISTS chk_robots_last_mode",
                 """ALTER TABLE robots DROP COLUMN IF EXISTS controller_version, DROP COLUMN IF EXISTS firmware_version,
                      DROP COLUMN IF EXISTS sdk_version, DROP COLUMN IF EXISTS agent_version, DROP COLUMN IF EXISTS connection_state,
                      DROP COLUMN IF EXISTS last_seen_at, DROP COLUMN IF EXISTS last_mode"""):
        conn.exec_driver_sql(stmt)
