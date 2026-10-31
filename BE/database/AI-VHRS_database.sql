-- =====================================================================================================================
-- AI-VHRS (Xưởng Nét Việt) - Script database đầy đủ cho PostgreSQL 15+ (Supabase dùng 17)
--
-- Trạng thái: tương đương Alembic revision 0013 (head), tức baseline + migration 0002..0013:
--   0002 sửa guard trạng thái, system_settings, chống trùng báo giá/thanh toán, RLS   0003 auth_sessions
--   0004 orders.shipping_*                0005 enum PAYOS                    0006 messages.kind (thẻ đơn hàng)
--   0007 chặn trùng lịch kỹ thuật viên    0008 robot_runs / robot_alerts / alert_catalog
--   0009 sketches.image_urls              0010 robot_agents / robot_commands  0011 quality_evaluations
--   0012 khoá phiên robot_agents          0013 lệnh ALIGN_START
--
-- Nội dung: extension, enum, bảng, ràng buộc, chỉ mục, hàm, trigger, view, row-level security, dữ liệu tham chiếu
-- (5 vai trò, tài khoản mẫu, bảng giá đầu, loại bút, tham số hệ thống, danh mục cảnh báo robot) và dòng alembic_version.
-- Không gồm danh mục giấy/mực/mẫu chữ/chính sách riêng tư: chạy `scripts/seed_workshop_data.py` sau đó nếu cần demo.
--
-- Cách chạy: copy toàn bộ file, dán vào pgAdmin Query Tool / Supabase SQL editor rồi chạy một lần (F5); hoặc
--   psql "postgresql://.../ai_vhrs" -v ON_ERROR_STOP=1 -f database/AI-VHRS_database.sql
-- Chạy lại nhiều lần được: mục 0 dọn đối tượng AI-VHRS còn sót, nhưng TỪ CHỐI nếu database có dữ liệu thật.
-- Thành công khi: SELECT count(*) FROM pg_tables WHERE schemaname = 'public';  trả về 38 (database chỉ chứa AI-VHRS).
--
-- Quy ước:
--   * Tên bảng số nhiều, snake_case. Khoá chính BIGINT GENERATED ALWAYS AS IDENTITY (roles: SMALLINT;
--     robot_agents, quality_evaluations: BIGSERIAL như trên DB thật; auth_sessions, robot_commands: UUID).
--   * Tiền VND: NUMERIC(14,0). Thời gian: TIMESTAMPTZ (hiển thị Asia/Ho_Chi_Minh). File chỉ lưu URL/đường dẫn storage.
--   * Ứng dụng truyền người thao tác cho trigger qua biến phiên:
--       SET LOCAL app.current_account_id = '<id>';  SET LOCAL app.status_reason = '<lý do>';
--   * Vi phạm máy trạng thái trả SQLSTATE 'P0409' (API trả 409).
--   * Cột do migration thêm vào nằm cuối bảng, đúng thứ tự cột của database đang chạy.
-- =====================================================================================================================

-- Thoát transaction hỏng của lần chạy lỗi trước (pgAdmin giữ phiên). Phiên sạch chỉ in WARNING, không sao.
ROLLBACK;

BEGIN;

SET client_encoding = 'UTF8';
SET check_function_bodies = false;
SET search_path TO public;

-- =====================================================================================================================
-- 0. DỌN ĐỐI TƯỢNG AI-VHRS CÒN SÓT (để chạy lại được nhiều lần trên database thử)
-- An toàn: TỪ CHỐI nếu database đã có dữ liệu thật (có đơn hàng, hoặc có tài khoản ngoài 5 tài khoản mẫu).
-- Chỉ xoá đúng các bảng / view / hàm / kiểu của AI-VHRS, không đụng schema khác của Supabase (auth, storage...).
-- =====================================================================================================================
DO $$
DECLARE
  n bigint;
BEGIN
  IF to_regclass('public.orders') IS NOT NULL THEN
    EXECUTE 'SELECT count(*) FROM public.orders' INTO n;
    IF n > 0 THEN
      RAISE EXCEPTION 'Database "%" đang có % đơn hàng thật: KHÔNG chạy script này ở đây (dừng, không thay đổi gì).',
        current_database(), n;
    END IF;
  END IF;
  IF to_regclass('public.accounts') IS NOT NULL THEN
    EXECUTE $q$SELECT count(*) FROM public.accounts WHERE lower(email) NOT IN
      ('admin@netviet.vn','manager@netviet.vn','staff@netviet.vn','tech@netviet.vn','customer@example.com')$q$ INTO n;
    IF n > 0 THEN
      RAISE EXCEPTION 'Database "%" đang có % tài khoản thật: KHÔNG chạy script này ở đây (dừng, không thay đổi gì).',
        current_database(), n;
    END IF;
  END IF;
END $$;

DROP VIEW IF EXISTS v_customer_drafts, v_order_eta_postponement CASCADE;

DROP TABLE IF EXISTS
  alembic_version, roles, accounts, phone_otps, auth_sessions, system_settings,
  paper_types, pen_types, ink_colors, paper_pen_compats, templates, pricing_configs,
  orders, handwriting_styles, order_inputs, sketches, quotations, payments, shipments, messages, status_histories,
  robots, production_jobs, calibrations, incidents, job_events, product_photos, quality_evaluations,
  alert_catalog, robot_runs, robot_alerts, robot_agents, robot_commands,
  audit_logs, notifications, reviews, review_photos, showcase_posts
  CASCADE;

DROP SEQUENCE IF EXISTS robot_agents_id_seq, quality_evaluations_id_seq CASCADE;

DROP FUNCTION IF EXISTS fn_set_updated_at(), fn_current_actor(), fn_order_state_guard(), fn_order_status_history(),
  fn_review_guard(), fn_photo_uploaded_guard() CASCADE;

DROP TYPE IF EXISTS
  account_status, order_type, order_status, production_status, reject_reason, complexity_level, paper_size,
  delivery_method, order_input_kind, template_kind, style_status, quotation_status, adjustment_status,
  payment_type, payment_status, payment_gateway, carrier, shipment_status, state_type, paper_surface,
  pen_category, robot_status, job_status, job_event_type, incident_type, photo_kind, qc_result,
  notification_type, notification_channel
  CASCADE;

CREATE EXTENSION IF NOT EXISTS pgcrypto;    -- crypt()/gen_salt() cho mật khẩu seed, gen_random_uuid()
CREATE EXTENSION IF NOT EXISTS btree_gist;  -- ràng buộc EXCLUDE chống trùng lịch robot / kỹ thuật viên (BR-18)

-- =====================================================================================================================
-- 1. KIỂU ENUM
-- =====================================================================================================================
CREATE TYPE account_status    AS ENUM ('ACTIVE', 'LOCKED', 'DISABLED');

-- BR-03: OT-1 Sao chép–Phục hồi, OT-2 Sáng tạo theo nét đã học, OT-3 Viết theo mẫu
CREATE TYPE order_type        AS ENUM ('OT1_COPY_RESTORE', 'OT2_LEARNED_STYLE', 'OT3_TEMPLATE');

-- Bảng 2.5.1 + AWAITING_PRIVACY (BR-25)
CREATE TYPE order_status AS ENUM (
  'DRAFT', 'SUBMITTED', 'NEED_INFO', 'REJECTED', 'ACCEPTED',
  'AWAITING_PRIVACY', 'QUOTED', 'AWAITING_DEPOSIT', 'CONFIRMED',
  'AWAITING_ACCEPTANCE', 'AWAITING_FINAL_PAYMENT', 'READY_TO_DELIVER',
  'DELIVERING', 'COMPLETED', 'CANCELLED');

-- Bảng 2.5.2
CREATE TYPE production_status AS ENUM (
  'NOT_STARTED', 'PENDING_SCHEDULE', 'SCHEDULED', 'PREPARING', 'WRITING',
  'PAUSED', 'FAILED', 'WRITTEN', 'PHOTO_UPLOADED', 'REWRITE_REQUIRED', 'FINISHED');

CREATE TYPE reject_reason     AS ENUM ('TOO_OLD', 'DAMAGED', 'MISSING_CONTENT', 'PROHIBITED_CONTENT', 'OTHER');  -- FR-13
CREATE TYPE complexity_level  AS ENUM ('SIMPLE', 'MEDIUM', 'COMPLEX');                -- K_cx 1.0 / 1.3 / 1.6
CREATE TYPE paper_size        AS ENUM ('A6', 'A5', 'A4');                             -- BR-07: tối đa A4
CREATE TYPE delivery_method   AS ENUM ('DELIVERY', 'PICKUP');                         -- FR-21 / FR-23

CREATE TYPE order_input_kind AS ENUM (
  'ORIGINAL_IMAGE',      -- OT-1: ảnh/pdf bản gốc (FR-06)
  'HANDWRITING_SAMPLE',  -- OT-2: ảnh mẫu chữ (FR-07)
  'TEXT_CONTENT',        -- OT-2/OT-3: nội dung chữ + mẫu/bộ nét đã chọn
  'CANVAS');             -- OT-3: hình vẽ canvas (FR-08)

CREATE TYPE template_kind     AS ENUM ('TYPOGRAPHY', 'CALLIGRAPHY', 'SINGLE_LINE_FONT');
CREATE TYPE style_status      AS ENUM ('PENDING_REVIEW', 'APPROVED', 'REJECTED', 'DELETED');

CREATE TYPE quotation_status AS ENUM (
  'DRAFT', 'PENDING_APPROVAL', 'SENT', 'APPROVED', 'CHANGES_REQUESTED',
  'EXPIRED', 'CANCELLED', 'SUPERSEDED');
CREATE TYPE adjustment_status AS ENUM ('NONE', 'WITHIN_THRESHOLD', 'PENDING_MANAGER', 'APPROVED', 'REJECTED');

CREATE TYPE payment_type      AS ENUM ('DEPOSIT', 'FINAL', 'SHIPPING', 'REFUND');
CREATE TYPE payment_status    AS ENUM ('PENDING', 'SUCCESS', 'FAILED', 'CANCELLED');
CREATE TYPE payment_gateway   AS ENUM ('VNPAY', 'MOMO', 'PAYOS');                     -- PAYOS: migration 0005

-- Chỉ còn dùng GHN; GHTK giữ lại để đọc được dữ liệu cũ (enum PostgreSQL không xoá giá trị được)
CREATE TYPE carrier           AS ENUM ('GHN', 'GHTK');
CREATE TYPE shipment_status   AS ENUM ('CREATED', 'PICKED_UP', 'DELIVERING', 'DELIVERED', 'FAILED', 'RETURNED', 'CANCELLED');

CREATE TYPE state_type        AS ENUM ('ORDER', 'PRODUCTION', 'ETA');

CREATE TYPE paper_surface     AS ENUM ('PLAIN', 'ART', 'GLOSSY', 'COATED', 'CARD', 'OTHER');
CREATE TYPE pen_category      AS ENUM ('BALLPOINT', 'GEL', 'FINELINER', 'FOUNTAIN', 'BRUSH', 'MARKER');

CREATE TYPE robot_status      AS ENUM ('AVAILABLE', 'BUSY', 'MAINTENANCE', 'BROKEN');   -- FR-39

-- Trạng thái riêng của một job (một đơn có thể có nhiều job khi viết lại / đổi robot)
CREATE TYPE job_status AS ENUM (
  'SCHEDULED', 'PREPARING', 'WRITING', 'PAUSED', 'WRITTEN', 'PHOTO_UPLOADED',
  'DONE', 'FAILED', 'REWRITE_REQUIRED', 'CANCELLED');

CREATE TYPE job_event_type AS ENUM (
  'DOWNLOADED', 'HASH_MISMATCH', 'CALIBRATED', 'SIMULATED', 'START', 'PROGRESS',
  'PAUSE', 'RESUME', 'ESTOP', 'OVER_FORCE', 'STROKE_LOST', 'SENSOR_LOST',
  'INCIDENT', 'WRITTEN', 'FORCE_SUMMARY');

CREATE TYPE incident_type     AS ENUM ('ROBOT', 'MATERIAL', 'FORCE_MODULE', 'OTHER');
CREATE TYPE photo_kind        AS ENUM ('OVERALL', 'CLOSE_UP', 'OTHER');               -- BR-21
CREATE TYPE qc_result         AS ENUM ('PASS', 'FAIL');

CREATE TYPE notification_type AS ENUM (
  'ORDER_ACCEPTED', 'ORDER_REJECTED', 'NEED_INFO', 'ORDER_STATUS_CHANGED',
  'PRODUCTION_STATUS_CHANGED', 'SKETCH_READY', 'QUOTATION_AVAILABLE',
  'QUOTATION_EXPIRED', 'ETA_POSTPONED', 'NEW_MESSAGE', 'PRODUCT_COMPLETED',
  'DELIVERING', 'PAYMENT', 'SYSTEM');
CREATE TYPE notification_channel AS ENUM ('EMAIL', 'IN_APP');

-- =====================================================================================================================
-- 2. TÀI KHOẢN, PHIÊN ĐĂNG NHẬP, THAM SỐ HỆ THỐNG
-- =====================================================================================================================
-- Phiên bản schema cho Alembic (ứng dụng chạy migration tiếp từ revision ghi ở đây)
CREATE TABLE alembic_version (
  version_num VARCHAR(32) NOT NULL,
  CONSTRAINT alembic_version_pkc PRIMARY KEY (version_num)
);

-- #1 Role (FR-03, FR-51)
CREATE TABLE roles (
  id          SMALLINT PRIMARY KEY,
  code        VARCHAR(30) NOT NULL UNIQUE,
  name        VARCHAR(100) NOT NULL,
  description TEXT
);

-- #2 Account (FR-01, FR-02, FR-51, FR-53). BR-01: mỗi tài khoản đúng 1 vai trò.
CREATE TABLE accounts (
  id                 BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  role_id            SMALLINT NOT NULL REFERENCES roles(id),
  email              VARCHAR(255) NOT NULL,
  password_hash      VARCHAR(255) NOT NULL,                 -- bcrypt
  full_name          VARCHAR(150) NOT NULL,
  phone              VARCHAR(20),
  phone_verified_at  TIMESTAMPTZ,                           -- FR-53: SĐT đã xác minh
  status             account_status NOT NULL DEFAULT 'ACTIVE',
  failed_login_count SMALLINT NOT NULL DEFAULT 0,           -- FR-01: khoá tạm sau 5 lần sai
  locked_until       TIMESTAMPTZ,
  -- FR-02 nhiều địa chỉ (mảng JSON). Địa chỉ hai cấp tỉnh -> phường/xã theo danh mục GHN:
  -- [{"label","receiver","phone","street","province_code","province_name","ward_code","ward_name","is_default"}]
  addresses          JSONB NOT NULL DEFAULT '[]'::jsonb CHECK (jsonb_typeof(addresses) = 'array'),
  created_by         BIGINT REFERENCES accounts(id),        -- BR-01: Admin tạo tài khoản nội bộ
  last_login_at      TIMESTAMPTZ,
  created_at         TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at         TIMESTAMPTZ NOT NULL DEFAULT now(),
  CONSTRAINT chk_accounts_failed_login CHECK (failed_login_count >= 0)
);
CREATE UNIQUE INDEX ux_accounts_email ON accounts (lower(email));
CREATE UNIQUE INDEX ux_accounts_verified_phone ON accounts (phone) WHERE phone_verified_at IS NOT NULL;
CREATE INDEX ix_accounts_role ON accounts (role_id);

-- #29 PhoneOtp (FR-53, UC-54)
CREATE TABLE phone_otps (
  id            BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  account_id    BIGINT NOT NULL REFERENCES accounts(id) ON DELETE CASCADE,
  phone         VARCHAR(20) NOT NULL,
  otp_hash      VARCHAR(255) NOT NULL,                      -- không lưu mã thô
  expires_at    TIMESTAMPTZ NOT NULL,
  attempt_count SMALLINT NOT NULL DEFAULT 0,
  max_attempts  SMALLINT NOT NULL DEFAULT 5,
  used_at       TIMESTAMPTZ,
  created_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
  CONSTRAINT chk_otp_attempts CHECK (attempt_count BETWEEN 0 AND max_attempts),
  CONSTRAINT chk_otp_expiry CHECK (expires_at > created_at)
);
CREATE INDEX ix_phone_otps_lookup ON phone_otps (phone, created_at DESC) WHERE used_at IS NULL;

-- Phiên đăng nhập phía server (0003): token mang `sid`, chỉ hợp lệ khi phiên còn, chưa thu hồi, chưa hết hạn
CREATE TABLE auth_sessions (
  id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  account_id  BIGINT NOT NULL REFERENCES accounts(id) ON DELETE CASCADE,
  created_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
  expires_at  TIMESTAMPTZ NOT NULL,
  revoked_at  TIMESTAMPTZ,
  ip_address  INET,
  user_agent  VARCHAR(255),
  CONSTRAINT chk_auth_sessions_expiry CHECK (expires_at > created_at)
);
CREATE INDEX ix_auth_sessions_account ON auth_sessions (account_id) WHERE revoked_at IS NULL;
CREATE INDEX ix_auth_sessions_expiry ON auth_sessions (expires_at);

-- Tham số hệ thống (0002; UC-49/50). Khoá API không lưu ở đây mà ở biến môi trường.
CREATE TABLE system_settings (
  key         VARCHAR(60) PRIMARY KEY,
  value       JSONB NOT NULL,
  description TEXT,
  updated_by  BIGINT REFERENCES accounts(id),
  updated_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- =====================================================================================================================
-- 3. DANH MỤC: VẬT LIỆU, MẪU CHỮ, BẢNG GIÁ
-- =====================================================================================================================
-- #13 PaperType (FR-41, FR-09)
CREATE TABLE paper_types (
  id          BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  code        VARCHAR(30) NOT NULL UNIQUE,
  name        VARCHAR(120) NOT NULL,
  gsm         SMALLINT NOT NULL CHECK (gsm > 0),
  surface     paper_surface NOT NULL,
  size        paper_size NOT NULL,                                 -- BR-07: tối đa A4
  unit_price  NUMERIC(14,0) NOT NULL CHECK (unit_price >= 0),      -- P_paper(type, size)
  stock_qty   INTEGER NOT NULL DEFAULT 0 CHECK (stock_qty >= 0),   -- trừ khi job WRITTEN (FR-41)
  is_active   BOOLEAN NOT NULL DEFAULT TRUE,
  created_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- #14 PenType (FR-41, FR-09); hồ sơ lực theo bảng mục 3.6.2 (BR-20)
CREATE TABLE pen_types (
  id              BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  code            VARCHAR(30) NOT NULL UNIQUE,
  name            VARCHAR(120) NOT NULL,
  category        pen_category NOT NULL,
  stroke_width_mm NUMERIC(4,2) NOT NULL CHECK (stroke_width_mm > 0),
  f_target_n      NUMERIC(4,2) NOT NULL DEFAULT 1.0 CHECK (f_target_n BETWEEN 0.3 AND 2.0),
  f_min_n         NUMERIC(4,2) NOT NULL,
  f_max_n         NUMERIC(4,2) NOT NULL,
  f_hard_n        NUMERIC(4,2) NOT NULL,
  v_max_mm_s      NUMERIC(5,1) NOT NULL CHECK (v_max_mm_s > 0),
  surcharge       NUMERIC(14,0) NOT NULL DEFAULT 0 CHECK (surcharge >= 0),   -- P_pen
  stock_qty       INTEGER NOT NULL DEFAULT 0 CHECK (stock_qty >= 0),
  is_active       BOOLEAN NOT NULL DEFAULT TRUE,
  created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
  CONSTRAINT chk_pen_force_band CHECK (f_min_n > 0 AND f_min_n < f_target_n AND f_target_n < f_max_n AND f_max_n < f_hard_n)
);

-- #15 InkColor (FR-41, FR-09): màu mực theo bút (BR-05)
CREATE TABLE ink_colors (
  id          BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  pen_type_id BIGINT NOT NULL REFERENCES pen_types(id) ON DELETE CASCADE,
  name        VARCHAR(60) NOT NULL,
  hex_code    CHAR(7) CHECK (hex_code ~ '^#[0-9A-Fa-f]{6}$'),
  unit_price  NUMERIC(14,0) NOT NULL DEFAULT 0 CHECK (unit_price >= 0),      -- P_ink
  stock_qty   INTEGER NOT NULL DEFAULT 0 CHECK (stock_qty >= 0),
  is_active   BOOLEAN NOT NULL DEFAULT TRUE,
  UNIQUE (pen_type_id, name),
  UNIQUE (id, pen_type_id)                  -- để orders kiểm tra mực thuộc đúng bút
);

-- #16 PaperPenCompat (FR-41, BR-05, BR-06)
CREATE TABLE paper_pen_compats (
  paper_type_id BIGINT NOT NULL REFERENCES paper_types(id) ON DELETE CASCADE,
  pen_type_id   BIGINT NOT NULL REFERENCES pen_types(id) ON DELETE CASCADE,
  is_compatible BOOLEAN NOT NULL,
  note          VARCHAR(255),
  updated_by    BIGINT REFERENCES accounts(id),
  updated_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
  PRIMARY KEY (paper_type_id, pen_type_id)
);

-- #5 Template (FR-04, FR-42)
CREATE TABLE templates (
  id          BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  code        VARCHAR(40) NOT NULL UNIQUE,
  name        VARCHAR(150) NOT NULL,
  kind        template_kind NOT NULL,
  font_uri    TEXT NOT NULL,                  -- file font một nét
  preview_url TEXT,
  is_active   BOOLEAN NOT NULL DEFAULT TRUE,  -- FR-42: active / inactive
  created_by  BIGINT REFERENCES accounts(id),
  created_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- #21 PricingConfig (FR-30): mỗi lần lưu tạo một phiên bản mới, chỉ một phiên bản active
CREATE TABLE pricing_configs (
  id                   BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  version              INTEGER NOT NULL UNIQUE,
  is_active            BOOLEAN NOT NULL DEFAULT FALSE,
  u_ot1                NUMERIC(14,0) NOT NULL CHECK (u_ot1 >= 0),   -- VND / ký tự theo loại đơn
  u_ot2                NUMERIC(14,0) NOT NULL CHECK (u_ot2 >= 0),
  u_ot3                NUMERIC(14,0) NOT NULL CHECK (u_ot3 >= 0),
  w_min                NUMERIC(14,0) NOT NULL CHECK (w_min >= 0),   -- công viết tối thiểu / bản
  s_ot1                NUMERIC(14,0) NOT NULL CHECK (s_ot1 >= 0),   -- phí setup theo loại đơn
  s_ot2                NUMERIC(14,0) NOT NULL CHECK (s_ot2 >= 0),
  s_ot3                NUMERIC(14,0) NOT NULL CHECK (s_ot3 >= 0),
  k_simple             NUMERIC(4,2) NOT NULL DEFAULT 1.0,
  k_medium             NUMERIC(4,2) NOT NULL DEFAULT 1.3,
  k_complex            NUMERIC(4,2) NOT NULL DEFAULT 1.6,
  -- d(Q): [{"min_qty":10,"pct":5},{"min_qty":50,"pct":10},{"min_qty":100,"pct":15}]
  discount_tiers       JSONB NOT NULL DEFAULT '[{"min_qty":10,"pct":5},{"min_qty":50,"pct":10},{"min_qty":100,"pct":15}]'::jsonb,
  p_min_pct            NUMERIC(5,2) NOT NULL DEFAULT 50 CHECK (p_min_pct > 0 AND p_min_pct <= 100),   -- BR-10
  adjust_threshold_pct NUMERIC(5,2) NOT NULL DEFAULT 15 CHECK (adjust_threshold_pct >= 0),            -- BR-09
  canvas_mm_per_char   NUMERIC(6,2) NOT NULL DEFAULT 40,             -- FR-29: N = tổng độ dài nét / 40 mm
  note                 TEXT,
  created_by           BIGINT REFERENCES accounts(id),
  created_at           TIMESTAMPTZ NOT NULL DEFAULT now(),
  CONSTRAINT chk_pricing_k CHECK (k_simple > 0 AND k_simple <= k_medium AND k_medium <= k_complex),
  CONSTRAINT chk_pricing_tiers CHECK (jsonb_typeof(discount_tiers) = 'array')
);
CREATE UNIQUE INDEX ux_pricing_configs_one_active ON pricing_configs (is_active) WHERE is_active;

-- =====================================================================================================================
-- 4. ĐƠN HÀNG
-- =====================================================================================================================
-- #3 Order (FR-05, FR-11..13, FR-19, FR-24..26, FR-28, FR-52, FR-55, FR-56)
CREATE TABLE orders (
  id                     BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  code                   VARCHAR(20) NOT NULL UNIQUE,              -- mã đơn hiển thị cho khách
  customer_id            BIGINT NOT NULL REFERENCES accounts(id),
  order_type             order_type NOT NULL,                     -- BR-03
  order_status           order_status NOT NULL DEFAULT 'DRAFT',
  production_status      production_status NOT NULL DEFAULT 'NOT_STARTED',
  -- Vật liệu (BR-07: 1 giấy, 1 bút, 1 màu mực). Có thể trống khi DRAFT hoặc khi "để xưởng gợi ý".
  paper_type_id          BIGINT REFERENCES paper_types(id),
  pen_type_id            BIGINT REFERENCES pen_types(id),
  ink_color_id           BIGINT,
  workshop_suggest_materials BOOLEAN NOT NULL DEFAULT FALSE,      -- UC-11 "để xưởng gợi ý"
  quantity               INTEGER NOT NULL DEFAULT 1 CHECK (quantity >= 1),
  char_count             INTEGER CHECK (char_count >= 0),          -- N (FR-10, FR-29)
  complexity             complexity_level,                         -- K_cx đã chốt
  estimated_price_min    NUMERIC(14,0) CHECK (estimated_price_min >= 0),   -- FR-10 khoảng giá
  estimated_price_max    NUMERIC(14,0) CHECK (estimated_price_max >= 0),
  total_amount           NUMERIC(14,0) CHECK (total_amount >= 0),  -- G theo báo giá đã duyệt
  deposit_pct            NUMERIC(5,2) CHECK (deposit_pct > 0 AND deposit_pct <= 100),
  deposit_amount         NUMERIC(14,0) CHECK (deposit_amount >= 0), -- D
  customer_note          TEXT,
  terms_accepted_at      TIMESTAMPTZ,                              -- FR-11
  assigned_staff_id      BIGINT REFERENCES accounts(id),          -- FR-12
  assigned_by            BIGINT REFERENCES accounts(id),          -- Manager gán (UC-47) hoặc tự nhận
  reject_reason          reject_reason,                            -- FR-13
  reject_note            TEXT,
  info_request_note      TEXT,                                     -- NEED_INFO
  -- FR-52 / BR-25: chính sách riêng tư (chi tiết lưu audit_logs)
  privacy_policy_version VARCHAR(20),
  privacy_accepted_at    TIMESTAMPTZ,
  privacy_declined_at    TIMESTAMPTZ,
  keep_stroke_set        BOOLEAN NOT NULL DEFAULT FALSE,           -- BR-23: khách đồng ý giữ bộ nét
  -- ETA (FR-26, BR-15, BR-16); eta_postponed_days do trigger tính, không nhận từ client
  eta                    DATE,
  eta_postponed_days     INTEGER NOT NULL DEFAULT 0 CHECK (eta_postponed_days >= 0),
  free_rewrite_used      BOOLEAN NOT NULL DEFAULT FALSE,           -- BR-13: 1 lần viết lại miễn phí
  -- Giao hàng (FR-21..23)
  delivery_method        delivery_method,
  delivery_address       JSONB,                                    -- snapshot địa chỉ lúc chọn
  pickup_slot_start      TIMESTAMPTZ,                              -- FR-23 hẹn khung giờ nhận
  pickup_slot_end        TIMESTAMPTZ,
  -- Mốc thời gian
  last_saved_at          TIMESTAMPTZ NOT NULL DEFAULT now(),       -- FR-55 lưu nháp gần nhất
  submitted_at           TIMESTAMPTZ,
  confirmed_at           TIMESTAMPTZ,
  accepted_product_at    TIMESTAMPTZ,                              -- nghiệm thu (FR-28)
  received_confirmed_at  TIMESTAMPTZ,                              -- khách xác nhận đã nhận
  completed_at           TIMESTAMPTZ,
  cancelled_at           TIMESTAMPTZ,
  cancel_reason          TEXT,
  inputs_purged_at       TIMESTAMPTZ,                              -- BR-23: đã xoá ảnh sau 90 ngày
  created_at             TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at             TIMESTAMPTZ NOT NULL DEFAULT now(),
  -- 0002: tự nghiệm thu sau 7 ngày + nhắc nghiệm thu
  awaiting_acceptance_at TIMESTAMPTZ,
  acceptance_reminded_at TIMESTAMPTZ,
  -- 0004: dịch vụ vận chuyển khách đã chọn (phí, ngày giao dự kiến)
  shipping_carrier       carrier,
  shipping_service_code  VARCHAR(30),
  shipping_eta           TIMESTAMPTZ,
  CONSTRAINT fk_orders_ink_of_pen FOREIGN KEY (ink_color_id, pen_type_id) REFERENCES ink_colors (id, pen_type_id),
  CONSTRAINT chk_orders_estimate CHECK (
    estimated_price_min IS NULL OR estimated_price_max IS NULL OR estimated_price_min <= estimated_price_max),
  CONSTRAINT chk_orders_pickup_slot CHECK (pickup_slot_end IS NULL OR pickup_slot_end > pickup_slot_start),
  CONSTRAINT chk_orders_reject CHECK (order_status <> 'REJECTED' OR reject_reason IS NOT NULL),
  CONSTRAINT chk_orders_staff_after_accept CHECK (                                                   -- FR-12
    order_status IN ('DRAFT','SUBMITTED','NEED_INFO','REJECTED','CANCELLED') OR assigned_staff_id IS NOT NULL),
  CONSTRAINT chk_orders_privacy_before_quote CHECK (                                                 -- BR-25
    order_status NOT IN ('QUOTED','AWAITING_DEPOSIT','CONFIRMED','AWAITING_ACCEPTANCE',
                         'AWAITING_FINAL_PAYMENT','READY_TO_DELIVER','DELIVERING','COMPLETED')
    OR privacy_accepted_at IS NOT NULL),
  CONSTRAINT chk_orders_materials_after_submit CHECK (
    order_status IN ('DRAFT','CANCELLED') OR workshop_suggest_materials
    OR (paper_type_id IS NOT NULL AND pen_type_id IS NOT NULL AND ink_color_id IS NOT NULL)),
  CONSTRAINT chk_orders_shipping_service CHECK ((shipping_carrier IS NULL) = (shipping_service_code IS NULL))
);
CREATE INDEX ix_orders_customer ON orders (customer_id, created_at DESC);
CREATE INDEX ix_orders_drafts ON orders (customer_id, last_saved_at DESC) WHERE order_status = 'DRAFT';   -- FR-56
CREATE INDEX ix_orders_status ON orders (order_status, production_status);
CREATE INDEX ix_orders_staff ON orders (assigned_staff_id) WHERE assigned_staff_id IS NOT NULL;
CREATE INDEX ix_orders_eta ON orders (eta) WHERE order_status NOT IN ('COMPLETED','CANCELLED','REJECTED');

-- #6 HandwritingStyle (FR-36, FR-42): bộ nét học từ chữ của một người (OT-2)
CREATE TABLE handwriting_styles (
  id                     BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  owner_id               BIGINT NOT NULL REFERENCES accounts(id),   -- khách sở hữu bộ nét
  source_order_id        BIGINT REFERENCES orders(id) ON DELETE SET NULL,
  name                   VARCHAR(150) NOT NULL,
  glyph_set_uri          TEXT,                                       -- bộ glyph đã học
  coverage_pct           NUMERIC(5,2) CHECK (coverage_pct BETWEEN 0 AND 100),
  status                 style_status NOT NULL DEFAULT 'PENDING_REVIEW',
  right_to_use_confirmed BOOLEAN NOT NULL DEFAULT FALSE,             -- FR-07 / BR-23
  keep_consent           BOOLEAN NOT NULL DEFAULT FALSE,             -- BR-23: giữ lại sau 90 ngày
  approved_by            BIGINT REFERENCES accounts(id),             -- Manager duyệt (FR-42)
  approved_at            TIMESTAMPTZ,
  delete_after           TIMESTAMPTZ,                                -- hạn xoá nếu không đồng ý giữ
  created_at             TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at             TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX ix_styles_owner ON handwriting_styles (owner_id);

-- #4 OrderInput (FR-06..08, FR-33, FR-55, FR-56): mỗi đơn có nhiều dòng input
CREATE TABLE order_inputs (
  id                   BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  order_id             BIGINT NOT NULL REFERENCES orders(id) ON DELETE CASCADE,
  kind                 order_input_kind NOT NULL,
  sort_order           SMALLINT NOT NULL DEFAULT 0,
  -- Ảnh (ORIGINAL_IMAGE, HANDWRITING_SAMPLE). BR-04: jpg/png/pdf ≤ 20 MB, ≤ 10 ảnh/trang mỗi đơn
  file_url             TEXT,
  mime_type            VARCHAR(50) CHECK (mime_type IN ('image/jpeg','image/png','application/pdf')),
  file_size_bytes      BIGINT CHECK (file_size_bytes > 0 AND file_size_bytes <= 20971520),
  rotation_deg         SMALLINT DEFAULT 0 CHECK (rotation_deg IN (0, 90, 180, 270)),
  crop_box             JSONB,                                  -- {"x","y","w","h"}
  quality_result       JSONB,                                  -- FR-33: {"sharpness","brightness","contrast","warning"}
  is_quality_warning   BOOLEAN NOT NULL DEFAULT FALSE,
  -- Nội dung chữ (TEXT_CONTENT)
  text_content         TEXT,
  template_id          BIGINT REFERENCES templates(id),
  handwriting_style_id BIGINT REFERENCES handwriting_styles(id),
  font_size_mm         NUMERIC(5,2) CHECK (font_size_mm > 0),
  alignment            VARCHAR(10) CHECK (alignment IN ('LEFT','CENTER','RIGHT','JUSTIFY')),
  layout               JSONB,                                  -- bố cục trang + kiểu chữ theo đoạn (cỡ, nghiêng, gạch chân, gạch ngang, giãn dòng)
  -- Canvas (CANVAS): toạ độ, thứ tự nét, áp lực bút (Pointer Events)
  canvas_data          JSONB,
  deleted_at           TIMESTAMPTZ,                            -- BR-23 xoá sau 90 ngày
  created_at           TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at           TIMESTAMPTZ NOT NULL DEFAULT now(),
  CONSTRAINT chk_input_payload CHECK (
    (kind IN ('ORIGINAL_IMAGE','HANDWRITING_SAMPLE') AND (file_url IS NOT NULL OR deleted_at IS NOT NULL)) OR
    (kind = 'TEXT_CONTENT') OR
    (kind = 'CANVAS' AND (canvas_data IS NOT NULL OR deleted_at IS NOT NULL)))
);
CREATE INDEX ix_order_inputs_order ON order_inputs (order_id, kind, sort_order);

-- #7 Sketch (FR-14, FR-34, FR-35): phác thảo có phiên bản
CREATE TABLE sketches (
  id                    BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  order_id              BIGINT NOT NULL REFERENCES orders(id) ON DELETE CASCADE,
  version               INTEGER NOT NULL CHECK (version >= 1),
  created_by            BIGINT NOT NULL REFERENCES accounts(id),
  trajectory_uri        TEXT NOT NULL,              -- danh sách nét (x, y, pen) theo toạ độ giấy
  preview_url           TEXT,                       -- ảnh PNG kỹ thuật
  similarity_score      NUMERIC(5,2) CHECK (similarity_score BETWEEN 0 AND 100),   -- stroke IoU (OT-1, NFR-02)
  suggested_complexity  complexity_level,
  estimated_writing_sec INTEGER CHECK (estimated_writing_sec >= 0),
  total_stroke_mm       NUMERIC(12,2) CHECK (total_stroke_mm >= 0),
  pen_lift_count        INTEGER CHECK (pen_lift_count >= 0),
  approach_note         TEXT,                       -- cách làm, vật tư đề xuất (UC-25)
  content_hash          CHAR(64),                   -- SHA-256 của phác thảo (FR-38)
  is_final              BOOLEAN NOT NULL DEFAULT FALSE,   -- bản gửi khách / dùng sản xuất
  created_at            TIMESTAMPTZ NOT NULL DEFAULT now(),
  image_urls            TEXT[] NOT NULL DEFAULT '{}',     -- 0009: ảnh JPEG cho khách, mỗi trang một đường dẫn storage
  UNIQUE (order_id, version)
);
CREATE UNIQUE INDEX ux_sketches_one_final ON sketches (order_id) WHERE is_final;

-- #8 Quotation (FR-15, FR-29, FR-31, FR-32)
CREATE TABLE quotations (
  id                    BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  order_id              BIGINT NOT NULL REFERENCES orders(id) ON DELETE CASCADE,
  version               INTEGER NOT NULL CHECK (version >= 1),
  sketch_id             BIGINT NOT NULL REFERENCES sketches(id),       -- BR-22: phải có phác thảo
  pricing_config_id     BIGINT NOT NULL REFERENCES pricing_configs(id),
  created_by            BIGINT NOT NULL REFERENCES accounts(id),
  status                quotation_status NOT NULL DEFAULT 'DRAFT',
  -- Dòng chi tiết; khi "để xưởng gợi ý" có thể chứa 2–3 phương án vật tư:
  -- [{"option":1,"paper_type_id","pen_type_id","ink_color_id","item","calc","amount"}]
  line_items            JSONB NOT NULL CHECK (jsonb_typeof(line_items) = 'array'),
  chosen_option         SMALLINT,
  char_count            INTEGER NOT NULL CHECK (char_count >= 0),
  quantity              INTEGER NOT NULL CHECK (quantity >= 1),
  complexity            complexity_level NOT NULL,
  computed_total        NUMERIC(14,0) NOT NULL CHECK (computed_total >= 0),   -- G từ Pricing Engine
  adjusted_total        NUMERIC(14,0) CHECK (adjusted_total >= 0),            -- FR-31
  adjustment_pct        NUMERIC(6,2) GENERATED ALWAYS AS (
                          CASE WHEN adjusted_total IS NULL OR computed_total = 0 THEN NULL
                               ELSE round((adjusted_total - computed_total) * 100.0 / computed_total, 2) END) STORED,
  adjustment_reason     TEXT,
  adjustment_status     adjustment_status NOT NULL DEFAULT 'NONE',
  approved_by           BIGINT REFERENCES accounts(id),                       -- Manager duyệt vượt ±15%
  approved_at           TIMESTAMPTZ,
  final_total           NUMERIC(14,0) GENERATED ALWAYS AS (COALESCE(adjusted_total, computed_total)) STORED,
  min_deposit_pct       NUMERIC(5,2) NOT NULL CHECK (min_deposit_pct > 0 AND min_deposit_pct <= 100),
  price_snapshot        JSONB NOT NULL,                                       -- toàn bộ tham số giá lúc lập (BR-08)
  eta                   DATE,                                                 -- FR-15
  file_url              TEXT,                                                 -- PDF có logo xưởng
  sent_at               TIMESTAMPTZ,
  valid_until           TIMESTAMPTZ,                                          -- 7 ngày từ lúc gửi (BR-08)
  customer_responded_at TIMESTAMPTZ,
  customer_note         TEXT,
  created_at            TIMESTAMPTZ NOT NULL DEFAULT now(),
  UNIQUE (order_id, version),
  CONSTRAINT chk_quote_adjust_reason CHECK (adjusted_total IS NULL OR adjustment_reason IS NOT NULL),
  CONSTRAINT chk_quote_sent_validity CHECK (sent_at IS NULL OR valid_until > sent_at)
);
CREATE INDEX ix_quotations_order ON quotations (order_id, version DESC);
CREATE INDEX ix_quotations_expiring ON quotations (valid_until) WHERE status = 'SENT';
CREATE INDEX ix_quotations_pending_approval ON quotations (created_at) WHERE adjustment_status = 'PENDING_MANAGER';
-- 0002: mỗi đơn chỉ một báo giá đang sống
CREATE UNIQUE INDEX ux_quotations_one_live ON quotations (order_id) WHERE status IN ('DRAFT','PENDING_APPROVAL','SENT');

-- #9 Payment (FR-17..20)
CREATE TABLE payments (
  id              BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  order_id        BIGINT NOT NULL REFERENCES orders(id),
  type            payment_type NOT NULL,
  amount          NUMERIC(14,0) NOT NULL CHECK (amount > 0),
  deposit_pct     NUMERIC(5,2) CHECK (deposit_pct > 0 AND deposit_pct <= 100),
  gateway         payment_gateway NOT NULL,
  gateway_txn_id  VARCHAR(100),                     -- idempotency webhook (NFR-06)
  status          payment_status NOT NULL DEFAULT 'PENDING',
  refund_of_id    BIGINT REFERENCES payments(id),   -- hoàn tiền tham chiếu giao dịch gốc
  refund_reason   TEXT,
  confirmed_by    BIGINT REFERENCES accounts(id),   -- Staff xác nhận / đối soát (UC-28)
  confirmed_at    TIMESTAMPTZ,
  invoice_url     TEXT,
  gateway_payload JSONB,                            -- webhook đã xác thực chữ ký; không lưu thẻ (NFR-09)
  paid_at         TIMESTAMPTZ,
  created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
  CONSTRAINT chk_payment_deposit_pct CHECK (type = 'DEPOSIT' OR deposit_pct IS NULL),
  CONSTRAINT chk_payment_refund_ref CHECK ((type = 'REFUND') = (refund_of_id IS NOT NULL))
);
CREATE UNIQUE INDEX ux_payments_gateway_txn ON payments (gateway, gateway_txn_id) WHERE gateway_txn_id IS NOT NULL;
CREATE INDEX ix_payments_order ON payments (order_id, created_at);
-- 0002: mỗi loại thanh toán chỉ thành công một lần cho một đơn
CREATE UNIQUE INDEX ux_payments_one_success_per_type ON payments (order_id, type)
  WHERE status = 'SUCCESS' AND type IN ('DEPOSIT','FINAL','SHIPPING');

-- #10 Shipment (FR-21..23). Nhận tại xưởng không tạo vận đơn (orders.delivery_method = PICKUP).
CREATE TABLE shipments (
  id                 BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  order_id           BIGINT NOT NULL REFERENCES orders(id),
  carrier            carrier NOT NULL,
  service_code       VARCHAR(30),
  waybill_code       VARCHAR(60),
  fee                NUMERIC(14,0) NOT NULL CHECK (fee >= 0),    -- F_ship
  is_fallback_fee    BOOLEAN NOT NULL DEFAULT FALSE,             -- API lỗi → bảng phí dự phòng
  package_type       VARCHAR(20) CHECK (package_type IN ('FLAT_BOX_A5','FLAT_BOX_A4','TUBE')),
  weight_g           INTEGER CHECK (weight_g > 0),
  to_address         JSONB NOT NULL,                             -- địa chỉ nhận (tỉnh -> phường/xã)
  status             shipment_status NOT NULL DEFAULT 'CREATED',
  carrier_status_raw VARCHAR(60),                                -- trạng thái gốc của hãng
  label_url          TEXT,
  created_by         BIGINT REFERENCES accounts(id),
  picked_up_at       TIMESTAMPTZ,
  delivered_at       TIMESTAMPTZ,
  created_at         TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at         TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE UNIQUE INDEX ux_shipments_waybill ON shipments (carrier, waybill_code) WHERE waybill_code IS NOT NULL;
CREATE INDEX ix_shipments_order ON shipments (order_id);

-- #11 Message (FR-16). 0006: kind TEXT | ORDER_CARD (thẻ đơn hàng không có chữ lẫn ảnh)
CREATE TABLE messages (
  id          BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  order_id    BIGINT NOT NULL REFERENCES orders(id) ON DELETE CASCADE,
  sender_id   BIGINT NOT NULL REFERENCES accounts(id),
  body        TEXT,
  attachments JSONB NOT NULL DEFAULT '[]'::jsonb,   -- ảnh đính kèm [{"url","mime"}]
  read_at     TIMESTAMPTZ,
  created_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
  kind        VARCHAR(20) NOT NULL DEFAULT 'TEXT',
  CONSTRAINT chk_messages_kind CHECK (kind IN ('TEXT', 'ORDER_CARD')),
  CONSTRAINT chk_message_not_empty CHECK (kind = 'ORDER_CARD' OR body IS NOT NULL OR jsonb_array_length(attachments) > 0)
);
CREATE INDEX ix_messages_order ON messages (order_id, created_at);
CREATE INDEX ix_messages_unread ON messages (order_id) WHERE read_at IS NULL;

-- #12 StatusHistory (FR-24..26). Trigger trên orders tự ghi; FK job_id thêm ở mục 5 sau khi có production_jobs.
CREATE TABLE status_histories (
  id          BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  order_id    BIGINT NOT NULL REFERENCES orders(id) ON DELETE CASCADE,
  job_id      BIGINT,
  state_type  state_type NOT NULL,
  from_status VARCHAR(30),
  to_status   VARCHAR(30),
  old_eta     DATE,
  new_eta     DATE,
  reason      TEXT,
  actor_id    BIGINT REFERENCES accounts(id),        -- NULL = hệ thống / tác vụ định kỳ
  created_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
  CONSTRAINT chk_history_payload CHECK (
    (state_type = 'ETA' AND new_eta IS NOT NULL AND reason IS NOT NULL) OR   -- BR-16: dời ETA phải có lý do
    (state_type <> 'ETA' AND to_status IS NOT NULL))
);
CREATE INDEX ix_status_histories_order ON status_histories (order_id, created_at);

-- =====================================================================================================================
-- 5. SẢN XUẤT
-- =====================================================================================================================
-- #17 Robot (FR-39). 0008: phiên bản controller/firmware/SDK/agent, trạng thái kết nối, chế độ chạy gần nhất
CREATE TABLE robots (
  id                       BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  code                     VARCHAR(30) NOT NULL UNIQUE,
  robot_type               VARCHAR(50) NOT NULL DEFAULT 'FAIRINO_FR3',
  station                  VARCHAR(50),                            -- trạm / bàn làm việc
  status                   robot_status NOT NULL DEFAULT 'AVAILABLE',
  is_simulated             BOOLEAN NOT NULL DEFAULT FALSE,         -- robot mô phỏng cho demo (LI-03)
  supported_pen_categories pen_category[],                         -- BR-18: robot phù hợp vật liệu
  note                     TEXT,
  created_at               TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at               TIMESTAMPTZ NOT NULL DEFAULT now(),
  controller_version       VARCHAR(60),
  firmware_version         VARCHAR(80),
  sdk_version              VARCHAR(60),
  agent_version            VARCHAR(30),
  connection_state         VARCHAR(10) NOT NULL DEFAULT 'UNKNOWN',
  last_seen_at             TIMESTAMPTZ,
  last_mode                VARCHAR(10),
  CONSTRAINT chk_robots_connection_state CHECK (connection_state IN ('ONLINE', 'OFFLINE', 'UNKNOWN')),
  CONSTRAINT chk_robots_last_mode CHECK (last_mode IS NULL OR last_mode IN ('MOCK', 'SIM', 'REAL'))
);

-- #18 ProductionJob (FR-37, FR-38, FR-40, FR-43, FR-45, FR-46)
CREATE TABLE production_jobs (
  id                     BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  order_id               BIGINT NOT NULL REFERENCES orders(id),
  sketch_id              BIGINT NOT NULL REFERENCES sketches(id),
  robot_id               BIGINT NOT NULL REFERENCES robots(id),
  technician_id          BIGINT NOT NULL REFERENCES accounts(id),
  scheduled_by           BIGINT NOT NULL REFERENCES accounts(id),    -- Manager
  status                 job_status NOT NULL DEFAULT 'SCHEDULED',
  is_rewrite             BOOLEAN NOT NULL DEFAULT FALSE,
  slot_start             TIMESTAMPTZ NOT NULL,
  slot_end               TIMESTAMPTZ NOT NULL,
  -- FR-40: thời lượng = thời gian viết × Q + chuẩn bị 15' + chụp ảnh 5'
  estimated_duration_min INTEGER NOT NULL CHECK (estimated_duration_min > 0),
  package_uri            TEXT,                       -- gói job (quỹ đạo, PenProfile, thông số giấy/bút, ảnh phác thảo)
  package_hash           CHAR(64),                   -- SHA-256 phác thảo đã duyệt (FR-38)
  packaged_at            TIMESTAMPTZ,
  downloaded_at          TIMESTAMPTZ,
  simulation_passed      BOOLEAN,                    -- FR-45: chặn chạy khi còn lỗi khả thi
  simulation_report      JSONB,
  progress_pct           NUMERIC(5,2) DEFAULT 0 CHECK (progress_pct BETWEEN 0 AND 100),
  started_at             TIMESTAMPTZ,
  finished_at            TIMESTAMPTZ,
  created_at             TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at             TIMESTAMPTZ NOT NULL DEFAULT now(),
  CONSTRAINT chk_job_slot CHECK (slot_end > slot_start),
  CONSTRAINT chk_job_run_requires_sim CHECK (
    status NOT IN ('WRITING','PAUSED','WRITTEN','PHOTO_UPLOADED','DONE') OR simulation_passed IS TRUE),
  -- BR-18: mỗi robot tối đa 1 job sống tại một thời điểm
  CONSTRAINT ex_job_robot_overlap EXCLUDE USING gist (
    robot_id WITH =, tstzrange(slot_start, slot_end) WITH &&)
    WHERE (status IN ('SCHEDULED','PREPARING','WRITING','PAUSED')),
  -- 0007: một kỹ thuật viên không giữ hai job sống trùng giờ (khung liền nhau vẫn được, tstzrange nửa mở)
  CONSTRAINT ex_job_technician_overlap EXCLUDE USING gist (
    technician_id WITH =, tstzrange(slot_start, slot_end) WITH &&)
    WHERE (status IN ('SCHEDULED','PREPARING','WRITING','PAUSED'))
);
CREATE INDEX ix_jobs_order ON production_jobs (order_id);
CREATE INDEX ix_jobs_technician ON production_jobs (technician_id, slot_start);
CREATE INDEX ix_jobs_robot ON production_jobs (robot_id, slot_start);
CREATE UNIQUE INDEX ux_jobs_one_active_per_order ON production_jobs (order_id)
  WHERE status IN ('SCHEDULED','PREPARING','WRITING','PAUSED','WRITTEN');

ALTER TABLE status_histories
  ADD CONSTRAINT fk_status_histories_job FOREIGN KEY (job_id) REFERENCES production_jobs(id) ON DELETE SET NULL;

-- #22 Calibration (FR-44, BR-19)
CREATE TABLE calibrations (
  id                BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  job_id            BIGINT NOT NULL REFERENCES production_jobs(id) ON DELETE CASCADE,
  robot_id          BIGINT NOT NULL REFERENCES robots(id),
  technician_id     BIGINT NOT NULL REFERENCES accounts(id),
  paper_type_id     BIGINT REFERENCES paper_types(id),
  pen_type_id       BIGINT REFERENCES pen_types(id),
  checklist         JSONB,                         -- khung / giấy / bút
  force_zero_offset NUMERIC(8,4),                  -- trung bình 1 s khi bút trên không
  probe_points      JSONB NOT NULL,                -- P0, P1, P2 (+ lưới)
  frame_transform   JSONB,                         -- R, t (giấy → đế robot)
  height_map        JSONB,                         -- z_map
  force_curve       JSONB,                         -- đường cong Hall → lực
  is_valid          BOOLEAN NOT NULL DEFAULT TRUE,
  created_at        TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX ix_calibrations_job ON calibrations (job_id, created_at DESC);

-- #23 Incident (FR-48)
CREATE TABLE incidents (
  id                 BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  job_id             BIGINT REFERENCES production_jobs(id) ON DELETE SET NULL,
  robot_id           BIGINT REFERENCES robots(id),
  reported_by        BIGINT NOT NULL REFERENCES accounts(id),
  type               incident_type NOT NULL,
  description        TEXT NOT NULL,
  photo_urls         TEXT[] NOT NULL DEFAULT '{}',
  robot_status_after robot_status,                  -- robot chuyển BROKEN / MAINTENANCE nếu cần
  resolved_by        BIGINT REFERENCES accounts(id),
  resolved_at        TIMESTAMPTZ,
  resolution_note    TEXT,
  created_at         TIMESTAMPTZ NOT NULL DEFAULT now(),
  CONSTRAINT chk_incident_target CHECK (job_id IS NOT NULL OR robot_id IS NOT NULL)
);
CREATE INDEX ix_incidents_robot ON incidents (robot_id, created_at DESC);
CREATE INDEX ix_incidents_open ON incidents (created_at) WHERE resolved_at IS NULL;

-- #19 JobEvent (FR-47, FR-48)
CREATE TABLE job_events (
  id            BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  job_id        BIGINT NOT NULL REFERENCES production_jobs(id) ON DELETE CASCADE,
  event_type    job_event_type NOT NULL,
  actor_id      BIGINT REFERENCES accounts(id),    -- NULL = Robot Agent / thiết bị
  incident_id   BIGINT REFERENCES incidents(id),
  stroke_index  INTEGER,
  force_summary JSONB,                             -- {"f_mean","f_max","rms_err_pct","in_band_pct","samples"} (NFR-05)
  payload       JSONB,
  occurred_at   TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX ix_job_events_job ON job_events (job_id, occurred_at);

-- #20 ProductPhoto (FR-49, BR-21)
CREATE TABLE product_photos (
  id          BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  order_id    BIGINT NOT NULL REFERENCES orders(id) ON DELETE CASCADE,
  job_id      BIGINT NOT NULL REFERENCES production_jobs(id),
  uploaded_by BIGINT NOT NULL REFERENCES accounts(id),
  kind        photo_kind NOT NULL,
  url         TEXT NOT NULL,
  overlay_url TEXT,                                -- ảnh chồng với phác thảo
  qc_result   qc_result,
  qc_note     TEXT,
  deleted_at  TIMESTAMPTZ,                         -- BR-23
  created_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX ix_product_photos_job ON product_photos (job_id);
CREATE INDEX ix_product_photos_order ON product_photos (order_id);

-- Đánh giá chất lượng tự động (0011, Service G): ảnh tờ đã viết so với phác thảo đã duyệt. Chỉ mang tính tham khảo:
-- quyết định QC vẫn là product_photos.qc_result. metrics giữ số đo (mm) và ngưỡng đã dùng.
CREATE TABLE quality_evaluations (
  id           BIGSERIAL PRIMARY KEY,
  photo_id     BIGINT NOT NULL REFERENCES product_photos(id),
  job_id       BIGINT NOT NULL REFERENCES production_jobs(id),
  order_id     BIGINT NOT NULL REFERENCES orders(id),
  sketch_id    BIGINT REFERENCES sketches(id),
  page_no      SMALLINT NOT NULL DEFAULT 1 CHECK (page_no >= 1),
  method       VARCHAR(30) NOT NULL,
  verdict      VARCHAR(14) NOT NULL CHECK (verdict IN ('PASS', 'NEEDS_REVIEW', 'FAIL')),
  metrics      JSONB NOT NULL,
  overlay_path TEXT,
  created_by   BIGINT NOT NULL REFERENCES accounts(id),
  created_at   TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX ix_quality_evaluations_photo ON quality_evaluations (photo_id, created_at DESC);
CREATE INDEX ix_quality_evaluations_job ON quality_evaluations (job_id, created_at DESC);

-- =====================================================================================================================
-- 6. VẬN HÀNH ROBOT (0008, 0010, 0012, 0013)
-- =====================================================================================================================
-- Danh mục cảnh báo cố định. Mức: 1 xanh, 2 vàng, 3 cam (robot đã tự dừng), 4 đỏ (bấm E-Stop vật lý ngay).
CREATE TABLE alert_catalog (
  code          VARCHAR(40) PRIMARY KEY,
  level         SMALLINT NOT NULL CHECK (level BETWEEN 1 AND 4),
  title_vi      TEXT NOT NULL,
  action_vi     TEXT NOT NULL,
  estop_advised BOOLEAN NOT NULL DEFAULT FALSE,
  notify_roles  TEXT[] NOT NULL DEFAULT '{}',
  send_email    BOOLEAN NOT NULL DEFAULT FALSE,
  threshold     JSONB,
  is_active     BOOLEAN NOT NULL DEFAULT TRUE,
  updated_by    BIGINT REFERENCES accounts(id),
  updated_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
  CONSTRAINT chk_alert_level4_is_estop CHECK ((level = 4) = estop_advised)
);

-- Mỗi lần Robot Agent chạy một job (kể cả chạy khô và lần bị từ chối). Chạy REAL phải có người cho phép;
-- mỗi robot tối đa một lượt chạy đang mở.
CREATE TABLE robot_runs (
  id                BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  run_id            VARCHAR(40) NOT NULL UNIQUE,
  job_id            BIGINT NOT NULL REFERENCES production_jobs(id),
  robot_id          BIGINT NOT NULL REFERENCES robots(id),
  mode              VARCHAR(10) NOT NULL CHECK (mode IN ('MOCK', 'SIM', 'REAL')),
  dry_run           BOOLEAN NOT NULL DEFAULT FALSE,
  started_at        TIMESTAMPTZ NOT NULL DEFAULT now(),
  ended_at          TIMESTAMPTZ,
  result            VARCHAR(20) CHECK (result IN ('DONE', 'STOPPED', 'FAULT', 'UNKNOWN', 'DRY_RUN_DONE', 'REFUSED')),
  completed_strokes INTEGER NOT NULL DEFAULT 0 CHECK (completed_strokes >= 0),
  total_strokes     INTEGER NOT NULL DEFAULT 0 CHECK (total_strokes >= 0),
  plan_digest       VARCHAR(64),
  authorized_by     BIGINT REFERENCES accounts(id),
  authorized_at     TIMESTAMPTZ,
  agent_version     VARCHAR(30),
  robot_info        JSONB,
  summary           JSONB,
  created_by        BIGINT NOT NULL REFERENCES accounts(id),
  CONSTRAINT chk_run_real_authorized CHECK (mode <> 'REAL' OR authorized_by IS NOT NULL OR result IS NOT DISTINCT FROM 'REFUSED'),
  CONSTRAINT chk_run_ended CHECK (ended_at IS NULL OR ended_at >= started_at),
  CONSTRAINT chk_run_progress CHECK (total_strokes = 0 OR completed_strokes <= total_strokes)
);
CREATE INDEX ix_robot_runs_job ON robot_runs (job_id, started_at);
CREATE INDEX ix_robot_runs_robot ON robot_runs (robot_id, started_at DESC);
CREATE UNIQUE INDEX ux_robot_runs_one_open ON robot_runs (robot_id) WHERE ended_at IS NULL;

-- Cảnh báo đã phát. Tiêu đề / hành động chép từ danh mục lúc phát để đổi câu chữ sau này không sửa lịch sử.
-- Một cảnh báo OPEN cho mỗi (robot, mã, job): lặp lại thì tăng occurrences.
CREATE TABLE robot_alerts (
  id              BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  robot_id        BIGINT NOT NULL REFERENCES robots(id),
  job_id          BIGINT REFERENCES production_jobs(id),
  run_id          BIGINT REFERENCES robot_runs(id),
  code            VARCHAR(40) NOT NULL REFERENCES alert_catalog(code),
  level           SMALLINT NOT NULL CHECK (level BETWEEN 1 AND 4),
  title_vi        TEXT NOT NULL,
  action_vi       TEXT NOT NULL,
  estop_advised   BOOLEAN NOT NULL DEFAULT FALSE,
  details         JSONB,
  occurrences     INTEGER NOT NULL DEFAULT 1 CHECK (occurrences >= 1),
  raised_at       TIMESTAMPTZ NOT NULL DEFAULT now(),
  last_raised_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
  emailed_at      TIMESTAMPTZ,
  acknowledged_by BIGINT REFERENCES accounts(id),
  acknowledged_at TIMESTAMPTZ,
  resolved_by     BIGINT REFERENCES accounts(id),
  resolved_at     TIMESTAMPTZ,
  resolution_note TEXT,
  CONSTRAINT chk_alert_ack_pair CHECK ((acknowledged_by IS NULL) = (acknowledged_at IS NULL)),
  CONSTRAINT chk_alert_level4_is_estop CHECK ((level = 4) = estop_advised)
);
CREATE INDEX ix_robot_alerts_open ON robot_alerts (robot_id, level DESC, raised_at DESC) WHERE resolved_at IS NULL;
CREATE INDEX ix_robot_alerts_job ON robot_alerts (job_id, raised_at);
CREATE UNIQUE INDEX ux_robot_alerts_one_open ON robot_alerts (robot_id, code, COALESCE(job_id, 0)) WHERE resolved_at IS NULL;

-- Khoá của máy trạm Robot Agent (chỉ lưu SHA-256). MANAGER: khoá dài hạn do Manager cấp, mỗi robot một khoá còn hiệu lực.
-- SESSION (0012): khoá ngắn hạn cấp cho tài khoản kỹ thuật viên + một phiên bản app, gia hạn trước khi hết hạn.
CREATE TABLE robot_agents (
  id           BIGSERIAL PRIMARY KEY,
  robot_id     BIGINT NOT NULL REFERENCES robots(id),
  key_hash     CHAR(64) NOT NULL,
  key_prefix   VARCHAR(12) NOT NULL,
  created_by   BIGINT NOT NULL REFERENCES accounts(id),
  created_at   TIMESTAMPTZ NOT NULL DEFAULT now(),
  revoked_at   TIMESTAMPTZ,
  last_seen_at TIMESTAMPTZ,
  kind         VARCHAR(8) NOT NULL DEFAULT 'MANAGER',
  account_id   BIGINT REFERENCES accounts(id),
  instance_id  VARCHAR(64),
  expires_at   TIMESTAMPTZ,
  CONSTRAINT chk_robot_agents_kind CHECK (
    (kind = 'MANAGER' AND account_id IS NULL AND instance_id IS NULL)
    OR (kind = 'SESSION' AND account_id IS NOT NULL AND instance_id IS NOT NULL AND expires_at IS NOT NULL))
);
CREATE UNIQUE INDEX ux_robot_agents_key ON robot_agents (key_hash);
CREATE UNIQUE INDEX ux_robot_agents_manager_active ON robot_agents (robot_id) WHERE revoked_at IS NULL AND kind = 'MANAGER';
CREATE INDEX ix_robot_agents_session ON robot_agents (robot_id, expires_at) WHERE revoked_at IS NULL AND kind = 'SESSION';

-- Lệnh cho Robot Agent (agent tự kéo về). Không bao giờ chạy lại: PENDING -> DELIVERED; PENDING quá expires_at -> EXPIRED.
-- idempotency_key: yêu cầu gửi lại chỉ tạo một lệnh.
CREATE TABLE robot_commands (
  id              UUID PRIMARY KEY,
  robot_id        BIGINT NOT NULL REFERENCES robots(id),
  job_id          BIGINT REFERENCES production_jobs(id),
  kind            VARCHAR(20) NOT NULL,
  params          JSONB NOT NULL DEFAULT '{}'::jsonb,
  status          VARCHAR(10) NOT NULL DEFAULT 'PENDING',
  result          JSONB,
  error_code      VARCHAR(40),
  error_message   TEXT,
  idempotency_key VARCHAR(80),
  created_by      BIGINT NOT NULL REFERENCES accounts(id),
  created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
  expires_at      TIMESTAMPTZ NOT NULL,
  delivered_at    TIMESTAMPTZ,
  finished_at     TIMESTAMPTZ,
  CONSTRAINT chk_robot_command_kind CHECK (kind IN
    ('LOAD','PREFLIGHT','DRY_RUN','RUN','PAUSE','RESUME','STOP','PAPER_CHANGED','IDENTIFY','ALIGN_START')),
  CONSTRAINT chk_robot_command_status CHECK (status IN
    ('PENDING','DELIVERED','DONE','FAILED','EXPIRED','CANCELLED'))
);
CREATE INDEX ix_robot_commands_robot_status ON robot_commands (robot_id, status, created_at);
CREATE INDEX ix_robot_commands_job ON robot_commands (job_id, created_at DESC);
CREATE UNIQUE INDEX ux_robot_commands_idem ON robot_commands (created_by, idempotency_key) WHERE idempotency_key IS NOT NULL;

-- =====================================================================================================================
-- 7. NHẬT KÝ, THÔNG BÁO, ĐÁNH GIÁ, TRANG CHỦ
-- =====================================================================================================================
-- #24 AuditLog (FR-31, FR-51, FR-52)
CREATE TABLE audit_logs (
  id             BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  actor_id       BIGINT REFERENCES accounts(id),
  action         VARCHAR(60) NOT NULL,            -- vd ACCOUNT_LOCK, PRICE_ADJUST, PRIVACY_ACCEPT, PRIVACY_DECLINE
  entity_type    VARCHAR(40),
  entity_id      BIGINT,
  old_value      JSONB,
  new_value      JSONB,
  reason         TEXT,
  policy_version VARCHAR(20),                     -- FR-52: phiên bản chính sách riêng tư
  ip_address     INET,
  created_at     TIMESTAMPTZ NOT NULL DEFAULT now(),
  CONSTRAINT chk_audit_privacy CHECK (action NOT IN ('PRIVACY_ACCEPT','PRIVACY_DECLINE') OR policy_version IS NOT NULL)
);
CREATE INDEX ix_audit_logs_time ON audit_logs (created_at DESC);
CREATE INDEX ix_audit_logs_entity ON audit_logs (entity_type, entity_id);
CREATE INDEX ix_audit_logs_actor ON audit_logs (actor_id, created_at DESC);

-- #25 Notification (FR-27, FR-57)
CREATE TABLE notifications (
  id         BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  account_id BIGINT NOT NULL REFERENCES accounts(id) ON DELETE CASCADE,
  order_id   BIGINT REFERENCES orders(id) ON DELETE CASCADE,
  type       notification_type NOT NULL,
  msg_code   VARCHAR(10),                        -- MSG07, MSG10... (mục 5.3)
  title      VARCHAR(200) NOT NULL,
  body       TEXT NOT NULL,
  channel    notification_channel NOT NULL,
  is_read    BOOLEAN NOT NULL DEFAULT FALSE,
  read_at    TIMESTAMPTZ,
  sent_at    TIMESTAMPTZ,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  CONSTRAINT chk_notification_read CHECK (is_read = (read_at IS NOT NULL))
);
CREATE INDEX ix_notifications_unread ON notifications (account_id, created_at DESC) WHERE channel = 'IN_APP' AND NOT is_read;
CREATE INDEX ix_notifications_account ON notifications (account_id, created_at DESC);

-- #26 Review (FR-58): mỗi đơn một đánh giá
CREATE TABLE reviews (
  id          BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  order_id    BIGINT NOT NULL UNIQUE REFERENCES orders(id) ON DELETE CASCADE,
  customer_id BIGINT NOT NULL REFERENCES accounts(id),
  rating      SMALLINT NOT NULL CHECK (rating BETWEEN 1 AND 5),
  comment     TEXT,
  created_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- #27 ReviewPhoto (FR-58)
CREATE TABLE review_photos (
  id         BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  review_id  BIGINT NOT NULL REFERENCES reviews(id) ON DELETE CASCADE,
  url        TEXT NOT NULL,
  sort_order SMALLINT NOT NULL DEFAULT 0,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX ix_review_photos_review ON review_photos (review_id, sort_order);

-- #28 ShowcasePost (FR-54, FR-04)
CREATE TABLE showcase_posts (
  id          BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  image_url   TEXT NOT NULL,
  title       VARCHAR(200) NOT NULL,
  description TEXT,
  order_type  order_type,
  posted_by   BIGINT NOT NULL REFERENCES accounts(id),
  is_visible  BOOLEAN NOT NULL DEFAULT TRUE,
  sort_order  INTEGER NOT NULL DEFAULT 0,
  created_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX ix_showcase_visible ON showcase_posts (sort_order, created_at DESC) WHERE is_visible;

-- =====================================================================================================================
-- 8. HÀM VÀ TRIGGER
-- =====================================================================================================================
-- 8.1 updated_at tự động
CREATE FUNCTION fn_set_updated_at() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
  NEW.updated_at := now();
  RETURN NEW;
END $$;

CREATE TRIGGER trg_accounts_updated_at           BEFORE UPDATE ON accounts           FOR EACH ROW EXECUTE FUNCTION fn_set_updated_at();
CREATE TRIGGER trg_paper_types_updated_at        BEFORE UPDATE ON paper_types        FOR EACH ROW EXECUTE FUNCTION fn_set_updated_at();
CREATE TRIGGER trg_pen_types_updated_at          BEFORE UPDATE ON pen_types          FOR EACH ROW EXECUTE FUNCTION fn_set_updated_at();
CREATE TRIGGER trg_templates_updated_at          BEFORE UPDATE ON templates          FOR EACH ROW EXECUTE FUNCTION fn_set_updated_at();
CREATE TRIGGER trg_orders_updated_at             BEFORE UPDATE ON orders             FOR EACH ROW EXECUTE FUNCTION fn_set_updated_at();
CREATE TRIGGER trg_handwriting_styles_updated_at BEFORE UPDATE ON handwriting_styles FOR EACH ROW EXECUTE FUNCTION fn_set_updated_at();
CREATE TRIGGER trg_order_inputs_updated_at       BEFORE UPDATE ON order_inputs       FOR EACH ROW EXECUTE FUNCTION fn_set_updated_at();
CREATE TRIGGER trg_payments_updated_at           BEFORE UPDATE ON payments           FOR EACH ROW EXECUTE FUNCTION fn_set_updated_at();
CREATE TRIGGER trg_shipments_updated_at          BEFORE UPDATE ON shipments          FOR EACH ROW EXECUTE FUNCTION fn_set_updated_at();
CREATE TRIGGER trg_robots_updated_at             BEFORE UPDATE ON robots             FOR EACH ROW EXECUTE FUNCTION fn_set_updated_at();
CREATE TRIGGER trg_production_jobs_updated_at    BEFORE UPDATE ON production_jobs    FOR EACH ROW EXECUTE FUNCTION fn_set_updated_at();
CREATE TRIGGER trg_reviews_updated_at            BEFORE UPDATE ON reviews            FOR EACH ROW EXECUTE FUNCTION fn_set_updated_at();
CREATE TRIGGER trg_showcase_posts_updated_at     BEFORE UPDATE ON showcase_posts     FOR EACH ROW EXECUTE FUNCTION fn_set_updated_at();
CREATE TRIGGER trg_alert_catalog_updated_at      BEFORE UPDATE ON alert_catalog      FOR EACH ROW EXECUTE FUNCTION fn_set_updated_at();

-- 8.2 Người thao tác lấy từ biến phiên app.current_account_id
CREATE FUNCTION fn_current_actor() RETURNS bigint LANGUAGE sql STABLE AS $$
  SELECT NULLIF(current_setting('app.current_account_id', true), '')::bigint
$$;

-- 8.3 Máy trạng thái đơn hàng (FR-24, bảng 2.5.1) + sản xuất (FR-25, bảng 2.5.2) + đồng bộ (BR-17, bảng 2.5.3).
--     * eta_postponed_days do trigger tự cộng dồn khi ETA bị dời, không nhận từ client.
--     * REJECTED, COMPLETED, CANCELLED và FINISHED là trạng thái kết thúc.
--     * Đơn bị huỷ được đưa sản xuất về NOT_STARTED từ bất kỳ trạng thái nào; không huỷ được khi đã bắt đầu viết,
--       trừ khi ETA đã dời quá 7 ngày (BR-14 / BR-16).
--     * Tự ghi các mốc submitted_at, confirmed_at, awaiting_acceptance_at, completed_at, cancelled_at, last_saved_at (FR-55).
--     Thân hàm giữ nguyên văn như trên database đang chạy (migration 0002).
CREATE FUNCTION fn_order_state_guard() RETURNS trigger LANGUAGE plpgsql AS $$
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
END $$;

CREATE TRIGGER trg_orders_state_guard
  BEFORE INSERT OR UPDATE ON orders
  FOR EACH ROW EXECUTE FUNCTION fn_order_state_guard();

-- 8.4 Ghi status_histories tự động (FR-24..26, NFR-11)
CREATE FUNCTION fn_order_status_history() RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE
  v_actor  bigint := fn_current_actor();
  v_reason text   := NULLIF(current_setting('app.status_reason', true), '');
BEGIN
  IF TG_OP = 'INSERT' THEN
    INSERT INTO status_histories (order_id, state_type, from_status, to_status, actor_id)
    VALUES (NEW.id, 'ORDER', NULL, NEW.order_status::text, COALESCE(v_actor, NEW.customer_id));
    RETURN NEW;
  END IF;
  IF NEW.order_status IS DISTINCT FROM OLD.order_status THEN
    INSERT INTO status_histories (order_id, state_type, from_status, to_status, reason, actor_id)
    VALUES (NEW.id, 'ORDER', OLD.order_status::text, NEW.order_status::text, v_reason, v_actor);
  END IF;
  IF NEW.production_status IS DISTINCT FROM OLD.production_status THEN
    INSERT INTO status_histories (order_id, state_type, from_status, to_status, reason, actor_id)
    VALUES (NEW.id, 'PRODUCTION', OLD.production_status::text, NEW.production_status::text, v_reason, v_actor);
  END IF;
  IF NEW.eta IS DISTINCT FROM OLD.eta AND OLD.eta IS NOT NULL THEN
    IF v_reason IS NULL THEN
      RAISE EXCEPTION 'Dời ETA phải có lý do (BR-16): SET LOCAL app.status_reason' USING ERRCODE = 'P0409';
    END IF;
    INSERT INTO status_histories (order_id, state_type, old_eta, new_eta, reason, actor_id)
    VALUES (NEW.id, 'ETA', OLD.eta, NEW.eta, v_reason, v_actor);
  END IF;
  RETURN NEW;
END $$;

CREATE TRIGGER trg_orders_status_history
  AFTER INSERT OR UPDATE ON orders
  FOR EACH ROW EXECUTE FUNCTION fn_order_status_history();

-- 8.5 Chỉ đánh giá đơn COMPLETED của chính khách (FR-58, BR-02)
CREATE FUNCTION fn_review_guard() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
  IF NOT EXISTS (SELECT 1 FROM orders o
                 WHERE o.id = NEW.order_id AND o.customer_id = NEW.customer_id
                   AND o.order_status = 'COMPLETED') THEN
    RAISE EXCEPTION 'Chỉ đánh giá được đơn đã hoàn thành của chính mình' USING ERRCODE = 'P0409';
  END IF;
  RETURN NEW;
END $$;

CREATE TRIGGER trg_reviews_guard
  BEFORE INSERT OR UPDATE OF order_id, customer_id ON reviews
  FOR EACH ROW EXECUTE FUNCTION fn_review_guard();

-- 8.6 BR-21: chỉ PHOTO_UPLOADED khi job có ≥ 2 ảnh chưa xoá (toàn cảnh + cận cảnh) và tất cả QC đạt
CREATE FUNCTION fn_photo_uploaded_guard() RETURNS trigger LANGUAGE plpgsql AS $$
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
END $$;

CREATE TRIGGER trg_orders_photo_guard
  BEFORE UPDATE OF production_status ON orders
  FOR EACH ROW EXECUTE FUNCTION fn_photo_uploaded_guard();

-- =====================================================================================================================
-- 9. VIEW
-- =====================================================================================================================
-- Bản nháp của khách (FR-56)
CREATE VIEW v_customer_drafts AS
SELECT o.id, o.code, o.customer_id, o.order_type, o.quantity, o.paper_type_id, o.pen_type_id,
       o.ink_color_id, o.last_saved_at, count(i.id) AS input_count
FROM orders o LEFT JOIN order_inputs i ON i.order_id = o.id AND i.deleted_at IS NULL
WHERE o.order_status = 'DRAFT'
GROUP BY o.id;

-- Tổng số ngày dời ETA tính lại từ lịch sử (BR-16)
CREATE VIEW v_order_eta_postponement AS
SELECT order_id,
       sum(GREATEST(new_eta - old_eta, 0)) AS total_postponed_days,
       sum(GREATEST(new_eta - old_eta, 0)) > 7 AS can_cancel_full_refund
FROM status_histories
WHERE state_type = 'ETA' AND old_eta IS NOT NULL
GROUP BY order_id;

-- =====================================================================================================================
-- 10. ROW-LEVEL SECURITY
-- Bật trên mọi bảng, không có policy: chỉ chủ bảng (backend kết nối trực tiếp Postgres) đọc/ghi được.
-- =====================================================================================================================
ALTER TABLE alembic_version     ENABLE ROW LEVEL SECURITY;
ALTER TABLE roles               ENABLE ROW LEVEL SECURITY;
ALTER TABLE accounts            ENABLE ROW LEVEL SECURITY;
ALTER TABLE phone_otps          ENABLE ROW LEVEL SECURITY;
ALTER TABLE auth_sessions       ENABLE ROW LEVEL SECURITY;
ALTER TABLE system_settings     ENABLE ROW LEVEL SECURITY;
ALTER TABLE paper_types         ENABLE ROW LEVEL SECURITY;
ALTER TABLE pen_types           ENABLE ROW LEVEL SECURITY;
ALTER TABLE ink_colors          ENABLE ROW LEVEL SECURITY;
ALTER TABLE paper_pen_compats   ENABLE ROW LEVEL SECURITY;
ALTER TABLE templates           ENABLE ROW LEVEL SECURITY;
ALTER TABLE pricing_configs     ENABLE ROW LEVEL SECURITY;
ALTER TABLE orders              ENABLE ROW LEVEL SECURITY;
ALTER TABLE handwriting_styles  ENABLE ROW LEVEL SECURITY;
ALTER TABLE order_inputs        ENABLE ROW LEVEL SECURITY;
ALTER TABLE sketches            ENABLE ROW LEVEL SECURITY;
ALTER TABLE quotations          ENABLE ROW LEVEL SECURITY;
ALTER TABLE payments            ENABLE ROW LEVEL SECURITY;
ALTER TABLE shipments           ENABLE ROW LEVEL SECURITY;
ALTER TABLE messages            ENABLE ROW LEVEL SECURITY;
ALTER TABLE status_histories    ENABLE ROW LEVEL SECURITY;
ALTER TABLE robots              ENABLE ROW LEVEL SECURITY;
ALTER TABLE production_jobs     ENABLE ROW LEVEL SECURITY;
ALTER TABLE calibrations        ENABLE ROW LEVEL SECURITY;
ALTER TABLE incidents           ENABLE ROW LEVEL SECURITY;
ALTER TABLE job_events          ENABLE ROW LEVEL SECURITY;
ALTER TABLE product_photos      ENABLE ROW LEVEL SECURITY;
ALTER TABLE quality_evaluations ENABLE ROW LEVEL SECURITY;
ALTER TABLE alert_catalog       ENABLE ROW LEVEL SECURITY;
ALTER TABLE robot_runs          ENABLE ROW LEVEL SECURITY;
ALTER TABLE robot_alerts        ENABLE ROW LEVEL SECURITY;
ALTER TABLE robot_agents        ENABLE ROW LEVEL SECURITY;
ALTER TABLE robot_commands      ENABLE ROW LEVEL SECURITY;
ALTER TABLE audit_logs          ENABLE ROW LEVEL SECURITY;
ALTER TABLE notifications       ENABLE ROW LEVEL SECURITY;
ALTER TABLE reviews             ENABLE ROW LEVEL SECURITY;
ALTER TABLE review_photos       ENABLE ROW LEVEL SECURITY;
ALTER TABLE showcase_posts      ENABLE ROW LEVEL SECURITY;

-- =====================================================================================================================
-- 11. DỮ LIỆU THAM CHIẾU
-- =====================================================================================================================
-- Đánh dấu database đang ở revision 0013 để `alembic upgrade head` chỉ chạy các migration sau này
INSERT INTO alembic_version (version_num) VALUES ('0013');

-- 5 vai trò (FR-03)
INSERT INTO roles (id, code, name, description) VALUES
  (1, 'CUSTOMER',        'Customer',        'Khách hàng: đặt đơn, duyệt báo giá, thanh toán, nghiệm thu'),
  (2, 'STAFF',           'Staff',           'Nhân viên xưởng: tiếp nhận đơn, phác thảo, báo giá, giao hàng'),
  (3, 'TECHNICAL_STAFF', 'Technical Staff', 'Kỹ thuật viên: vận hành robot FR3 qua Flutter App'),
  (4, 'MANAGER',         'Manager',         'Quản lý xưởng: robot, vật liệu, giá, lập lịch'),
  (5, 'ADMIN',           'Admin',           'Quản trị hệ thống: tài khoản, tích hợp, tham số, audit log');

-- Một tài khoản mẫu cho mỗi vai trò. Mật khẩu chung: ChangeMe@123 (bcrypt) - ĐỔI NGAY khi triển khai thật.
INSERT INTO accounts (role_id, email, password_hash, full_name, phone, phone_verified_at) VALUES
  (5, 'admin@netviet.vn',     crypt('ChangeMe@123', gen_salt('bf', 10)), 'System Admin',     NULL,         NULL),
  (4, 'manager@netviet.vn',   crypt('ChangeMe@123', gen_salt('bf', 10)), 'Workshop Manager', NULL,         NULL),
  (2, 'staff@netviet.vn',     crypt('ChangeMe@123', gen_salt('bf', 10)), 'Order Staff',      NULL,         NULL),
  (3, 'tech@netviet.vn',      crypt('ChangeMe@123', gen_salt('bf', 10)), 'Technical Staff',  NULL,         NULL),
  (1, 'customer@example.com', crypt('ChangeMe@123', gen_salt('bf', 10)), 'Demo Customer',    '0900000000', now());
UPDATE accounts SET created_by = (SELECT id FROM accounts WHERE email = 'admin@netviet.vn')
 WHERE role_id IN (2, 3, 4);

-- Bảng giá phiên bản 1: K_cx, d(Q), p_min, ±15% theo report; u, W_min, S lấy từ ví dụ minh hoạ trong FR-29
-- (300 VND/ký tự, 50.000, 100.000). Manager chỉnh lại giá thật bằng cách tạo phiên bản mới.
INSERT INTO pricing_configs (version, is_active, u_ot1, u_ot2, u_ot3, w_min, s_ot1, s_ot2, s_ot3, note, created_by)
SELECT 1, TRUE, 300, 300, 300, 50000, 100000, 100000, 100000, 'Giá khởi tạo theo ví dụ minh hoạ FR-29', id
FROM accounts WHERE email = 'manager@netviet.vn';

-- Loại bút theo bảng lực mục 3.6.2 (giá trị khởi điểm, chốt sau thí nghiệm).
-- Độ rộng nét bút máy 0.6 mm và bút lông 2.0 mm là giả định (report không ghi).
INSERT INTO pen_types (code, name, category, stroke_width_mm, f_target_n, f_min_n, f_max_n, f_hard_n, v_max_mm_s) VALUES
  ('BALL07', 'Ballpoint 0.7 mm', 'BALLPOINT', 0.70, 1.00, 0.60, 1.40, 4.00, 40),
  ('GEL05',  'Gel pen 0.5 mm',   'GEL',       0.50, 0.60, 0.36, 0.84, 3.00, 30),
  ('FINE03', 'Fineliner 0.3 mm', 'FINELINER', 0.30, 0.40, 0.24, 0.56, 2.00, 25),
  ('FOUNT',  'Fountain pen',     'FOUNTAIN',  0.60, 0.30, 0.18, 0.42, 2.00, 20),
  ('BRUSH',  'Brush pen',        'BRUSH',     2.00, 0.80, 0.48, 1.12, 3.50, 15);

-- Tham số hệ thống mặc định (Admin chỉnh trên màn hình tham số)
INSERT INTO system_settings (key, value, description) VALUES
  ('quotation_valid_days',       '7'::jsonb,    'BR-08: hiệu lực báo giá (ngày)'),
  ('auto_accept_days',           '7'::jsonb,    'FR-28: tự nghiệm thu sau (ngày)'),
  ('accept_reminder_days',       '3'::jsonb,    'Nhắc nghiệm thu sau (ngày)'),
  ('eta_cancel_threshold_days',  '7'::jsonb,    'BR-16: dời ETA lũy kế vượt ngưỡng thì được huỷ hoàn 100%'),
  ('price_adjust_threshold_pct', '15'::jsonb,   'BR-09: ngưỡng điều chỉnh giá của Staff'),
  ('image_retention_days',       '90'::jsonb,   'BR-23: xoá ảnh sau (ngày)'),
  ('max_upload_mb',              '20'::jsonb,   'BR-04'),
  ('max_pages_per_order',        '10'::jsonb,   'BR-04'),
  ('max_paper_size',             '"A4"'::jsonb, 'BR-07'),
  ('fallback_shipping_fees',     '{"FLAT_BOX_A5": 25000, "FLAT_BOX_A4": 30000, "TUBE": 45000}'::jsonb,
                                 'FR-21: phí dự phòng khi API hãng lỗi (giá trị khởi tạo, Admin chỉnh)'),
  ('integrations_enabled',       '{"VNPAY": false, "MOMO": false, "GHN": false, "GHTK": false, "SMTP": false, "SMS": false}'::jsonb,
                                 'UC-49: bật/tắt tích hợp. Khoá API nằm ở secret store/env, không lưu DB.');

-- Danh mục cảnh báo robot. Mức 4 = khuyên bấm E-Stop vật lý ngay (và gửi e-mail).
INSERT INTO alert_catalog (code, level, title_vi, action_vi, estop_advised, notify_roles, send_email) VALUES
  ('STOP_NOT_EFFECTIVE', 4,
   'Đã gửi lệnh dừng nhưng đầu bút vẫn đang di chuyển.',
   'BẤM NÚT E-STOP NGAY. Phần mềm không thể tự dừng robot trong trường hợp này.',
   TRUE, ARRAY['TECHNICAL_STAFF', 'MANAGER'], TRUE),
  ('LINK_LOST_MOVING', 4,
   'Mất kết nối với robot khi robot đang chạy.',
   'Nếu robot còn chuyển động, BẤM NÚT E-STOP NGAY. Sau đó kiểm tra dây mạng và nguồn.',
   TRUE, ARRAY['TECHNICAL_STAFF', 'MANAGER'], TRUE),
  ('TRACKING_ERROR', 4,
   'Đầu bút lệch xa đường đã định.',
   'BẤM NÚT E-STOP NGAY. Không chạy lại cho tới khi xác định nguyên nhân.',
   TRUE, ARRAY['TECHNICAL_STAFF', 'MANAGER'], TRUE),
  ('CONTROLLER_SAFETY_FAULT', 4,
   'Robot báo lỗi an toàn hoặc va chạm trong lúc di chuyển.',
   'BẤM NÚT E-STOP NGAY nếu robot chưa đứng yên, rồi gọi Manager.',
   TRUE, ARRAY['TECHNICAL_STAFF', 'MANAGER'], TRUE),
  ('OVER_FORCE_STILL', 4,
   'Lực ép vẫn vượt giới hạn dù đã gửi lệnh dừng.',
   'BẤM NÚT E-STOP NGAY. Bút hoặc giấy có thể đang bị kẹt.',
   TRUE, ARRAY['TECHNICAL_STAFF', 'MANAGER'], TRUE),
  ('OVER_FORCE', 3,
   'Bút ép quá mạnh, robot đã tự dừng và nhấc bút.',
   'Kiểm tra bút và tờ giấy (cong, kẹt, sai độ cao). Sau đó chọn tiếp tục hoặc bỏ qua nét dở; không tự chạy lại từ đầu.',
   FALSE, ARRAY['TECHNICAL_STAFF', 'MANAGER'], FALSE),
  ('SENSOR_LOST', 3,
   'Mất tín hiệu cảm biến lực, robot đã dừng.',
   'Kiểm tra dây USB của gripper rồi chạy lại bước kiểm tra trước khi viết.',
   FALSE, ARRAY['TECHNICAL_STAFF', 'MANAGER'], FALSE),
  ('STROKE_LOST', 3,
   'Bút rời khỏi giấy khi đang viết, robot đã tạm dừng.',
   'Kiểm tra giấy có bị nhấc lên hoặc bút có hết mực không, rồi tiếp tục hoặc bỏ qua nét dở.',
   FALSE, ARRAY['TECHNICAL_STAFF'], FALSE),
  ('RUN_OUTCOME_UNKNOWN', 3,
   'Mất kết nối giữa chừng: chưa biết bản viết đã đến đâu.',
   'Nhìn tờ giấy, xác định nét nào đã viết xong, rồi chọn nét bắt đầu lại. Không tự chạy lại từ đầu.',
   FALSE, ARRAY['TECHNICAL_STAFF', 'MANAGER'], FALSE),
  ('STROKE_INTERRUPTED', 3,
   'Một nét đang viết dở khi dừng.',
   'Xem nét dở trên giấy rồi chọn viết lại nét đó hoặc bỏ qua.',
   FALSE, ARRAY['TECHNICAL_STAFF'], FALSE),
  ('BACKEND_LINK_LOST', 3,
   'Máy trạm mất kết nối tới hệ thống trong lúc đang viết: robot đã viết xong nét hiện tại, nhấc bút và tạm dừng.',
   'Kiểm tra mạng của máy trạm. Khi kết nối lại, chọn tiếp tục hoặc dừng job. Nếu thấy robot chuyển động bất thường, dùng nút dừng khẩn vật lý.',
   FALSE, ARRAY['TECHNICAL_STAFF', 'MANAGER'], FALSE),
  ('PREFLIGHT_REFUSED', 2,
   'Chưa chạy được vì bước kiểm tra trước khi chạy không đạt.',
   'Đọc lý do hiển thị và xử lý (hiệu chuẩn, gripper, vị trí bút). Robot không di chuyển.',
   FALSE, ARRAY['TECHNICAL_STAFF'], FALSE),
  ('CALIBRATION_OLD', 2,
   'Hiệu chuẩn đã cũ.',
   'Nên hiệu chuẩn lại mặt giấy trước khi viết tiếp.',
   FALSE, ARRAY['TECHNICAL_STAFF'], FALSE),
  ('FORCE_NEAR_LIMIT', 2,
   'Lực ép thường xuyên sát giới hạn.',
   'Kiểm tra bút, giấy và độ cao đặt bút.',
   FALSE, ARRAY['TECHNICAL_STAFF'], FALSE),
  ('DROPPED_FRAMES', 2,
   'Cảm biến lực mất nhiều gói tin.',
   'Kiểm tra dây USB của gripper.',
   FALSE, ARRAY['TECHNICAL_STAFF'], FALSE),
  ('AGENT_OFFLINE', 2,
   'Máy trạm điều khiển không báo về máy chủ.',
   'Kiểm tra máy trạm và mạng. Nếu robot đang chạy, đứng cạnh nút E-Stop.',
   FALSE, ARRAY['MANAGER'], FALSE),
  ('PAPER_CHANGE', 1,
   'Cần đặt tờ giấy mới cho trang kế tiếp.',
   'Đặt giấy mới, kẹp chặt rồi xác nhận để tiếp tục.',
   FALSE, ARRAY['TECHNICAL_STAFF'], FALSE);

-- =====================================================================================================================
-- 12. CHỈ TRÊN SUPABASE: role REST (anon, authenticated) không được chạm vào bảng; nơi khác tự bỏ qua
-- =====================================================================================================================
DO $$
BEGIN
  IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'anon') THEN
    REVOKE ALL ON ALL TABLES    IN SCHEMA public FROM anon, authenticated;
    REVOKE ALL ON ALL SEQUENCES IN SCHEMA public FROM anon, authenticated;
    REVOKE ALL ON ALL FUNCTIONS IN SCHEMA public FROM anon, authenticated;
    ALTER DEFAULT PRIVILEGES IN SCHEMA public REVOKE ALL ON TABLES    FROM anon, authenticated;
    ALTER DEFAULT PRIVILEGES IN SCHEMA public REVOKE ALL ON SEQUENCES FROM anon, authenticated;
    ALTER DEFAULT PRIVILEGES IN SCHEMA public REVOKE ALL ON FUNCTIONS FROM anon, authenticated;
  END IF;
END $$;

COMMIT;
