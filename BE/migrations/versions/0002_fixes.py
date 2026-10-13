"""Fixes D1–D8 from the Phase 0 review + Supabase hardening (approved).

 D1  Cancelling after the robot started (BR-16, ETA postponed > 7 days) was impossible.
 D2  PHOTO_UPLOADED guard counted soft-deleted photos.
 D3  orders.eta_postponed_days is now maintained by the guard trigger from ETA changes.
 D5  system_settings table (UC-49/50, screen 33).
 D6  orders.awaiting_acceptance_at / acceptance_reminded_at for auto-accept + reminders.
 D7  partial unique indexes: one live quotation, one successful payment per type.
 S2  RLS on every public table; no PostgREST access for anon/authenticated.

Revision ID: 0002
Revises: 0001
"""
from alembic import op

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None

STATEMENTS = [
    # ---- D6 columns -----------------------------------------------------------------
    "ALTER TABLE orders ADD COLUMN IF NOT EXISTS awaiting_acceptance_at TIMESTAMPTZ",
    "ALTER TABLE orders ADD COLUMN IF NOT EXISTS acceptance_reminded_at TIMESTAMPTZ",

    # ---- D1 + D3 + D6: order state guard ----------------------------------------------
    r"""
CREATE OR REPLACE FUNCTION fn_order_state_guard() RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE
  o_ok boolean := TRUE;
  p_ok boolean := TRUE;
BEGIN
  IF TG_OP = 'INSERT' THEN
    IF NEW.order_status <> 'DRAFT' OR NEW.production_status <> 'NOT_STARTED' THEN
      RAISE EXCEPTION 'Đơn mới phải ở DRAFT / NOT_STARTED' USING ERRCODE = 'P0409';
    END IF;
    RETURN NEW;
  END IF;

  -- D3: cumulative ETA postponement is derived here, never trusted from the client.
  IF NEW.eta IS DISTINCT FROM OLD.eta AND OLD.eta IS NOT NULL AND NEW.eta IS NOT NULL AND NEW.eta > OLD.eta THEN
    NEW.eta_postponed_days := OLD.eta_postponed_days + (NEW.eta - OLD.eta);
  ELSE
    NEW.eta_postponed_days := OLD.eta_postponed_days;
  END IF;

  IF NEW.order_status IS DISTINCT FROM OLD.order_status THEN
    o_ok := CASE OLD.order_status
      WHEN 'DRAFT'                  THEN NEW.order_status IN ('SUBMITTED')
      WHEN 'SUBMITTED'              THEN NEW.order_status IN ('ACCEPTED','REJECTED','NEED_INFO','CANCELLED')
      WHEN 'NEED_INFO'              THEN NEW.order_status IN ('SUBMITTED','CANCELLED')
      WHEN 'ACCEPTED'               THEN NEW.order_status IN ('AWAITING_PRIVACY','CANCELLED')
                                         OR (NEW.order_status = 'QUOTED' AND NEW.privacy_accepted_at IS NOT NULL)
      WHEN 'AWAITING_PRIVACY'       THEN NEW.order_status IN ('QUOTED','CANCELLED')
      WHEN 'QUOTED'                 THEN NEW.order_status IN ('AWAITING_DEPOSIT','ACCEPTED','CANCELLED')
      WHEN 'AWAITING_DEPOSIT'       THEN NEW.order_status IN ('CONFIRMED','CANCELLED')
      WHEN 'CONFIRMED'              THEN NEW.order_status IN ('AWAITING_ACCEPTANCE','CANCELLED')
      WHEN 'AWAITING_ACCEPTANCE'    THEN NEW.order_status IN ('AWAITING_FINAL_PAYMENT','CONFIRMED')
      WHEN 'AWAITING_FINAL_PAYMENT' THEN NEW.order_status IN ('READY_TO_DELIVER')
      WHEN 'READY_TO_DELIVER'       THEN NEW.order_status IN ('DELIVERING','COMPLETED')
      WHEN 'DELIVERING'             THEN NEW.order_status IN ('COMPLETED')
      ELSE FALSE
    END;
    IF NOT o_ok THEN
      RAISE EXCEPTION 'Chuyển trạng thái đơn không hợp lệ: % -> %', OLD.order_status, NEW.order_status
        USING ERRCODE = 'P0409';
    END IF;
  END IF;

  IF NEW.production_status IS DISTINCT FROM OLD.production_status THEN
    p_ok := CASE OLD.production_status
      WHEN 'NOT_STARTED'      THEN NEW.production_status IN ('PENDING_SCHEDULE')
      WHEN 'PENDING_SCHEDULE' THEN NEW.production_status IN ('SCHEDULED')
      WHEN 'SCHEDULED'        THEN NEW.production_status IN ('PREPARING','PENDING_SCHEDULE')
      WHEN 'PREPARING'        THEN NEW.production_status IN ('WRITING','FAILED')
      WHEN 'WRITING'          THEN NEW.production_status IN ('PAUSED','WRITTEN','FAILED')
      WHEN 'PAUSED'           THEN NEW.production_status IN ('WRITING','FAILED')
      WHEN 'FAILED'           THEN NEW.production_status IN ('PENDING_SCHEDULE')
      WHEN 'WRITTEN'          THEN NEW.production_status IN ('PHOTO_UPLOADED','REWRITE_REQUIRED')
      WHEN 'PHOTO_UPLOADED'   THEN NEW.production_status IN ('FINISHED','REWRITE_REQUIRED')
      WHEN 'REWRITE_REQUIRED' THEN NEW.production_status IN ('PENDING_SCHEDULE')
      ELSE FALSE
    END;
    -- D1: a cancelled order may reset production from ANY state (BR-14 pre-start, BR-16 after start).
    IF NOT p_ok AND NEW.order_status = 'CANCELLED' AND NEW.production_status = 'NOT_STARTED' THEN
      p_ok := TRUE;
    END IF;
    IF NOT p_ok THEN
      RAISE EXCEPTION 'Chuyển trạng thái sản xuất không hợp lệ: % -> %', OLD.production_status, NEW.production_status
        USING ERRCODE = 'P0409';
    END IF;
  END IF;

  -- BR-17 / bảng 2.5.3. D1: a CANCELLED order is exempt from the "production only when CONFIRMED" rule.
  IF NEW.order_status <> 'CANCELLED' AND NEW.production_status <> 'NOT_STARTED' AND NEW.order_status NOT IN
       ('CONFIRMED','AWAITING_ACCEPTANCE','AWAITING_FINAL_PAYMENT','READY_TO_DELIVER','DELIVERING','COMPLETED') THEN
    RAISE EXCEPTION 'Sản xuất chỉ bắt đầu khi đơn CONFIRMED (BR-17)' USING ERRCODE = 'P0409';
  END IF;
  IF NEW.order_status = 'CONFIRMED' AND OLD.order_status = 'AWAITING_DEPOSIT' AND NEW.production_status <> 'PENDING_SCHEDULE' THEN
    RAISE EXCEPTION 'Cọc thành công phải chuyển sản xuất sang PENDING_SCHEDULE' USING ERRCODE = 'P0409';
  END IF;
  IF NEW.order_status = 'AWAITING_ACCEPTANCE' AND NEW.production_status <> 'PHOTO_UPLOADED' THEN
    RAISE EXCEPTION 'Đơn chỉ chờ nghiệm thu khi sản xuất PHOTO_UPLOADED (BR-17)' USING ERRCODE = 'P0409';
  END IF;
  IF NEW.order_status IN ('AWAITING_FINAL_PAYMENT','READY_TO_DELIVER','DELIVERING','COMPLETED')
     AND NEW.production_status <> 'FINISHED' THEN
    RAISE EXCEPTION 'Đơn chỉ được thanh toán cuối/giao khi sản xuất FINISHED (BR-17)' USING ERRCODE = 'P0409';
  END IF;
  IF OLD.order_status = 'AWAITING_ACCEPTANCE' AND NEW.order_status = 'CONFIRMED'
     AND NEW.production_status NOT IN ('REWRITE_REQUIRED','PENDING_SCHEDULE') THEN
    RAISE EXCEPTION 'Yêu cầu viết lại phải chuyển sản xuất sang REWRITE_REQUIRED' USING ERRCODE = 'P0409';
  END IF;
  -- BR-14 / BR-16
  IF NEW.order_status = 'CANCELLED' AND OLD.order_status = 'CONFIRMED'
     AND OLD.production_status IN ('WRITING','PAUSED','WRITTEN','PHOTO_UPLOADED','REWRITE_REQUIRED','FAILED')
     AND NEW.eta_postponed_days <= 7 THEN
    RAISE EXCEPTION 'Không thể huỷ đơn đã bắt đầu viết (BR-14)' USING ERRCODE = 'P0409';
  END IF;

  IF NEW.order_status IS DISTINCT FROM OLD.order_status THEN
    CASE NEW.order_status
      WHEN 'SUBMITTED' THEN NEW.submitted_at := COALESCE(NEW.submitted_at, now());
      WHEN 'CONFIRMED' THEN NEW.confirmed_at := COALESCE(NEW.confirmed_at, now());
      WHEN 'AWAITING_ACCEPTANCE' THEN NEW.awaiting_acceptance_at := now(); NEW.acceptance_reminded_at := NULL;
      WHEN 'COMPLETED' THEN NEW.completed_at := now();
      WHEN 'CANCELLED' THEN NEW.cancelled_at := now();
      ELSE NULL;
    END CASE;
  END IF;
  IF OLD.order_status = 'DRAFT' AND NEW.order_status = 'DRAFT' THEN
    NEW.last_saved_at := now();
  END IF;
  RETURN NEW;
END $$
""",

    # ---- D2: photo guard ignores soft-deleted photos -----------------------------------
    r"""
CREATE OR REPLACE FUNCTION fn_photo_uploaded_guard() RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE v_job bigint;
BEGIN
  IF NEW.production_status = 'PHOTO_UPLOADED' AND OLD.production_status IS DISTINCT FROM 'PHOTO_UPLOADED' THEN
    SELECT id INTO v_job FROM production_jobs
     WHERE order_id = NEW.id AND status IN ('WRITTEN','PHOTO_UPLOADED')
     ORDER BY created_at DESC LIMIT 1;
    IF v_job IS NULL
       OR (SELECT count(*) FROM product_photos WHERE job_id = v_job AND deleted_at IS NULL) < 2
       OR NOT EXISTS (SELECT 1 FROM product_photos WHERE job_id = v_job AND kind = 'OVERALL'  AND deleted_at IS NULL)
       OR NOT EXISTS (SELECT 1 FROM product_photos WHERE job_id = v_job AND kind = 'CLOSE_UP' AND deleted_at IS NULL)
       OR EXISTS (SELECT 1 FROM product_photos WHERE job_id = v_job AND deleted_at IS NULL
                    AND qc_result IS DISTINCT FROM 'PASS') THEN
      RAISE EXCEPTION 'Cần ≥ 2 ảnh (toàn cảnh + cận cảnh) và QC đạt trước PHOTO_UPLOADED (BR-21)' USING ERRCODE = 'P0409';
    END IF;
  END IF;
  RETURN NEW;
END $$
""",

    # ---- D5: system settings -----------------------------------------------------------
    """
CREATE TABLE IF NOT EXISTS system_settings (
  key         VARCHAR(60) PRIMARY KEY,
  value       JSONB NOT NULL,
  description TEXT,
  updated_by  BIGINT REFERENCES accounts(id),
  updated_at  TIMESTAMPTZ NOT NULL DEFAULT now()
)""",
    """
INSERT INTO system_settings (key, value, description) VALUES
  ('quotation_valid_days',        '7'::jsonb,   'BR-08: hiệu lực báo giá (ngày)'),
  ('auto_accept_days',            '7'::jsonb,   'FR-28: tự nghiệm thu sau (ngày)'),
  ('accept_reminder_days',        '3'::jsonb,   'Nhắc nghiệm thu sau (ngày)'),
  ('eta_cancel_threshold_days',   '7'::jsonb,   'BR-16: dời ETA lũy kế vượt ngưỡng thì được huỷ hoàn 100%'),
  ('price_adjust_threshold_pct',  '15'::jsonb,  'BR-09: ngưỡng điều chỉnh giá của Staff'),
  ('image_retention_days',        '90'::jsonb,  'BR-23: xoá ảnh sau (ngày)'),
  ('max_upload_mb',               '20'::jsonb,  'BR-04'),
  ('max_pages_per_order',         '10'::jsonb,  'BR-04'),
  ('max_paper_size',              '"A4"'::jsonb,'BR-07'),
  ('fallback_shipping_fees',      '{"FLAT_BOX_A5": 25000, "FLAT_BOX_A4": 30000, "TUBE": 45000}'::jsonb,
                                  'FR-21: phí dự phòng khi API hãng lỗi (giá trị khởi tạo, Admin chỉnh)'),
  ('integrations_enabled',        '{"VNPAY": false, "MOMO": false, "GHN": false, "GHTK": false, "SMTP": false, "SMS": false}'::jsonb,
                                  'UC-49: bật/tắt tích hợp. Khoá API nằm ở secret store/env, không lưu DB.')
ON CONFLICT (key) DO NOTHING""",

    # ---- D7: duplicate protection ------------------------------------------------------
    "CREATE UNIQUE INDEX IF NOT EXISTS ux_quotations_one_live ON quotations (order_id) "
    "WHERE status IN ('DRAFT','PENDING_APPROVAL','SENT')",
    "CREATE UNIQUE INDEX IF NOT EXISTS ux_payments_one_success_per_type ON payments (order_id, type) "
    "WHERE status = 'SUCCESS' AND type IN ('DEPOSIT','FINAL','SHIPPING')",

    # ---- S2: RLS + no REST exposure ----------------------------------------------------
    r"""
DO $$
DECLARE t record;
BEGIN
  FOR t IN SELECT tablename FROM pg_tables WHERE schemaname = 'public' LOOP
    EXECUTE format('ALTER TABLE public.%I ENABLE ROW LEVEL SECURITY', t.tablename);
  END LOOP;
  IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'anon') THEN
    REVOKE ALL ON ALL TABLES    IN SCHEMA public FROM anon, authenticated;
    REVOKE ALL ON ALL SEQUENCES IN SCHEMA public FROM anon, authenticated;
    REVOKE ALL ON ALL FUNCTIONS IN SCHEMA public FROM anon, authenticated;
    ALTER DEFAULT PRIVILEGES IN SCHEMA public REVOKE ALL ON TABLES    FROM anon, authenticated;
    ALTER DEFAULT PRIVILEGES IN SCHEMA public REVOKE ALL ON SEQUENCES FROM anon, authenticated;
    ALTER DEFAULT PRIVILEGES IN SCHEMA public REVOKE ALL ON FUNCTIONS FROM anon, authenticated;
  END IF;
END $$
""",
]


def upgrade() -> None:
    conn = op.get_bind()
    for stmt in STATEMENTS:
        # psycopg treats % as a placeholder marker; escape it for plpgsql RAISE / format().
        conn.exec_driver_sql(stmt.replace("%", "%%"))


def downgrade() -> None:
    conn = op.get_bind()
    for stmt in (
        "DROP INDEX IF EXISTS ux_payments_one_success_per_type",
        "DROP INDEX IF EXISTS ux_quotations_one_live",
        "DROP TABLE IF EXISTS system_settings",
        "ALTER TABLE orders DROP COLUMN IF EXISTS acceptance_reminded_at",
        "ALTER TABLE orders DROP COLUMN IF EXISTS awaiting_acceptance_at",
    ):
        conn.exec_driver_sql(stmt)
    # fn_order_state_guard / fn_photo_uploaded_guard are not reverted: the previous bodies had the bugs
    # described above. Restore them from AI-VHRS_database_postgresql.sql if truly required.
