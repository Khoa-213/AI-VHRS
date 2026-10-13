-- =====================================================================
-- AI-VHRS (Xưởng Nét Việt) - Database schema cho PostgreSQL 14+
-- Nguồn: REPORT_3_EN_theo-phieu-moi.docx (FR-01..FR-52, UC-01..UC-53,
--        BR-01..BR-25, bảng trạng thái 2.5.1/2.5.2/2.5.3) và danh sách
--        29 entity bản 2 (thêm FR-53..FR-58, UC-54..UC-59).
-- Đã chạy thử trên PostgreSQL 16.
--
-- Cách dùng:
--   CREATE DATABASE ai_vhrs ENCODING 'UTF8' TEMPLATE template0;
--   \c ai_vhrs
--   \i AI-VHRS_database_postgresql.sql
--
-- Quy ước:
--   * Tên bảng số nhiều, snake_case ("order" là từ khoá nên dùng orders).
--   * Khoá chính BIGINT IDENTITY (roles dùng SMALLINT).
--   * Tiền VND lưu NUMERIC(14,0) (làm tròn 100 VND ở tầng ứng dụng, mục 5.2).
--   * Thời gian TIMESTAMPTZ; múi giờ hiển thị Asia/Ho_Chi_Minh.
--   * File (ảnh, PDF, gói job) lưu ở object storage, DB chỉ giữ URL/URI.
--   * Người thực hiện thao tác truyền vào qua:
--       SET LOCAL app.current_account_id = '<id>';
--       SET LOCAL app.status_reason      = '<lý do>';   (tuỳ chọn)
--     Trigger dùng 2 biến này để ghi status_histories.
--
-- Chỗ report không nói rõ (mặc định đã chọn, ghi [GIẢ ĐỊNH] tại chỗ):
--   * Nhiều địa chỉ giao hàng (FR-02) lưu JSONB trong accounts vì danh sách
--     29 entity không có bảng Address.
--   * Loại robot (FR-39) là cột robot_type của robots, không có bảng riêng.
--   * Cấu hình tích hợp (UC-49, gồm nhà cung cấp SMS) và tham số hệ thống
--     (UC-50) không có entity trong 29 bảng nên KHÔNG tạo bảng; nên lưu ở
--     file cấu hình/secret store. Mọi thay đổi vẫn ghi audit_logs.
--   * Token khôi phục mật khẩu qua email (FR-01) dùng link ký (JWT) có hạn,
--     không cần bảng.
--   * Bảng trạng thái 2.5 lấy theo SRS v2 (bản mà Report 3 tham chiếu),
--     cộng AWAITING_PRIVACY (FR-52/BR-25).
--
-- LƯU Ý (repo): đây là baseline gốc, giữ nguyên. Các bản vá sau đó nằm trong
--   migrations/versions (0002 sửa guard/RLS/system_settings, 0003 auth_sessions).
--   Dùng `alembic upgrade head` để dựng DB mới: revision 0001 tự chạy file này.
-- =====================================================================

BEGIN;

CREATE EXTENSION IF NOT EXISTS pgcrypto;    -- crypt()/gen_salt() cho seed mật khẩu
CREATE EXTENSION IF NOT EXISTS btree_gist;  -- ràng buộc EXCLUDE 1 robot 1 job (BR-18)

-- ---------------------------------------------------------------------
-- 1. ENUM
-- ---------------------------------------------------------------------
CREATE TYPE account_status AS ENUM ('ACTIVE', 'LOCKED', 'DISABLED');

-- BR-03: OT-1 Sao chép–Phục hồi, OT-2 Sáng tạo theo nét đã học, OT-3 Viết theo mẫu
CREATE TYPE order_type AS ENUM ('OT1_COPY_RESTORE', 'OT2_LEARNED_STYLE', 'OT3_TEMPLATE');

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

-- FR-13: lý do từ chối chọn từ danh sách
CREATE TYPE reject_reason AS ENUM ('TOO_OLD', 'DAMAGED', 'MISSING_CONTENT', 'PROHIBITED_CONTENT', 'OTHER');

CREATE TYPE complexity_level AS ENUM ('SIMPLE', 'MEDIUM', 'COMPLEX');      -- K_cx 1.0/1.3/1.6
CREATE TYPE paper_size AS ENUM ('A6', 'A5', 'A4');                         -- BR-07: tối đa A4 [GIẢ ĐỊNH A6/A5/A4]
CREATE TYPE delivery_method AS ENUM ('DELIVERY', 'PICKUP');                -- FR-21/FR-23

CREATE TYPE order_input_kind AS ENUM (
  'ORIGINAL_IMAGE',      -- OT-1: ảnh/pdf bản gốc (FR-06)
  'HANDWRITING_SAMPLE',  -- OT-2: ảnh mẫu chữ (FR-07)
  'TEXT_CONTENT',        -- OT-2/OT-3: nội dung chữ + mẫu/bộ nét đã chọn
  'CANVAS');             -- OT-3: hình vẽ canvas (FR-08)

CREATE TYPE template_kind AS ENUM ('TYPOGRAPHY', 'CALLIGRAPHY', 'SINGLE_LINE_FONT');
CREATE TYPE style_status AS ENUM ('PENDING_REVIEW', 'APPROVED', 'REJECTED', 'DELETED');

CREATE TYPE quotation_status AS ENUM (
  'DRAFT', 'PENDING_APPROVAL', 'SENT', 'APPROVED', 'CHANGES_REQUESTED',
  'EXPIRED', 'CANCELLED', 'SUPERSEDED');
CREATE TYPE adjustment_status AS ENUM ('NONE', 'WITHIN_THRESHOLD', 'PENDING_MANAGER', 'APPROVED', 'REJECTED');

CREATE TYPE payment_type AS ENUM ('DEPOSIT', 'FINAL', 'SHIPPING', 'REFUND');
CREATE TYPE payment_status AS ENUM ('PENDING', 'SUCCESS', 'FAILED', 'CANCELLED');
CREATE TYPE payment_gateway AS ENUM ('VNPAY', 'MOMO');

CREATE TYPE carrier AS ENUM ('GHN', 'GHTK');
CREATE TYPE shipment_status AS ENUM ('CREATED', 'PICKED_UP', 'DELIVERING', 'DELIVERED', 'FAILED', 'RETURNED', 'CANCELLED');

CREATE TYPE state_type AS ENUM ('ORDER', 'PRODUCTION', 'ETA');

CREATE TYPE paper_surface AS ENUM ('PLAIN', 'ART', 'GLOSSY', 'COATED', 'CARD', 'OTHER');
CREATE TYPE pen_category AS ENUM ('BALLPOINT', 'GEL', 'FINELINER', 'FOUNTAIN', 'BRUSH', 'MARKER');

CREATE TYPE robot_status AS ENUM ('AVAILABLE', 'BUSY', 'MAINTENANCE', 'BROKEN');   -- FR-39

-- Trạng thái riêng của 1 job (1 đơn có thể có nhiều job khi viết lại/đổi robot)
CREATE TYPE job_status AS ENUM (
  'SCHEDULED', 'PREPARING', 'WRITING', 'PAUSED', 'WRITTEN', 'PHOTO_UPLOADED',
  'DONE', 'FAILED', 'REWRITE_REQUIRED', 'CANCELLED');

CREATE TYPE job_event_type AS ENUM (
  'DOWNLOADED', 'HASH_MISMATCH', 'CALIBRATED', 'SIMULATED', 'START', 'PROGRESS',
  'PAUSE', 'RESUME', 'ESTOP', 'OVER_FORCE', 'STROKE_LOST', 'SENSOR_LOST',
  'INCIDENT', 'WRITTEN', 'FORCE_SUMMARY');

CREATE TYPE incident_type AS ENUM ('ROBOT', 'MATERIAL', 'FORCE_MODULE', 'OTHER');
CREATE TYPE photo_kind AS ENUM ('OVERALL', 'CLOSE_UP', 'OTHER');           -- BR-21
CREATE TYPE qc_result AS ENUM ('PASS', 'FAIL');

CREATE TYPE notification_type AS ENUM (
  'ORDER_ACCEPTED', 'ORDER_REJECTED', 'NEED_INFO', 'ORDER_STATUS_CHANGED',
  'PRODUCTION_STATUS_CHANGED', 'SKETCH_READY', 'QUOTATION_AVAILABLE',
  'QUOTATION_EXPIRED', 'ETA_POSTPONED', 'NEW_MESSAGE', 'PRODUCT_COMPLETED',
  'DELIVERING', 'PAYMENT', 'SYSTEM');
CREATE TYPE notification_channel AS ENUM ('EMAIL', 'IN_APP');

-- ---------------------------------------------------------------------
-- 2. TÀI KHOẢN
-- ---------------------------------------------------------------------
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
  password_hash      VARCHAR(255) NOT NULL,                 -- bcrypt/argon2
  full_name          VARCHAR(150) NOT NULL,
  phone              VARCHAR(20),
  phone_verified_at  TIMESTAMPTZ,                           -- FR-53: SĐT đã xác minh
  status             account_status NOT NULL DEFAULT 'ACTIVE',
  failed_login_count SMALLINT NOT NULL DEFAULT 0,           -- FR-01: khoá tạm sau 5 lần sai
  locked_until       TIMESTAMPTZ,
  -- [GIẢ ĐỊNH] FR-02 nhiều địa chỉ: mảng JSON
  -- [{"label","receiver","phone","street","province_code","district_code","ward_code","is_default"}]
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
  max_attempts  SMALLINT NOT NULL DEFAULT 5,                -- [GIẢ ĐỊNH] 5 lần
  used_at       TIMESTAMPTZ,
  created_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
  CONSTRAINT chk_otp_attempts CHECK (attempt_count BETWEEN 0 AND max_attempts),
  CONSTRAINT chk_otp_expiry CHECK (expires_at > created_at)
);
CREATE INDEX ix_phone_otps_lookup ON phone_otps (phone, created_at DESC) WHERE used_at IS NULL;

-- ---------------------------------------------------------------------
-- 3. DANH MỤC: VẬT LIỆU, MẪU CHỮ, BẢNG GIÁ
-- ---------------------------------------------------------------------
-- #13 PaperType (FR-41, FR-09)
CREATE TABLE paper_types (
  id          BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  code        VARCHAR(30) NOT NULL UNIQUE,
  name        VARCHAR(120) NOT NULL,
  gsm         SMALLINT NOT NULL CHECK (gsm > 0),
  surface     paper_surface NOT NULL,
  size        paper_size NOT NULL,                          -- BR-07: tối đa A4
  unit_price  NUMERIC(14,0) NOT NULL CHECK (unit_price >= 0),   -- P_paper(type, size)
  stock_qty   INTEGER NOT NULL DEFAULT 0 CHECK (stock_qty >= 0), -- trừ khi job WRITTEN (FR-41)
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
  surcharge       NUMERIC(14,0) NOT NULL DEFAULT 0 CHECK (surcharge >= 0),  -- P_pen
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
  unit_price  NUMERIC(14,0) NOT NULL DEFAULT 0 CHECK (unit_price >= 0),  -- P_ink
  stock_qty   INTEGER NOT NULL DEFAULT 0 CHECK (stock_qty >= 0),
  is_active   BOOLEAN NOT NULL DEFAULT TRUE,
  UNIQUE (pen_type_id, name),
  UNIQUE (id, pen_type_id)               -- để orders kiểm tra mực thuộc đúng bút
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
  font_uri    TEXT NOT NULL,                 -- file font một nét JSON
  preview_url TEXT,
  is_active   BOOLEAN NOT NULL DEFAULT TRUE, -- FR-42: active/inactive
  created_by  BIGINT REFERENCES accounts(id),
  created_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- #21 PricingConfig (FR-30): mỗi lần lưu tạo 1 phiên bản mới
CREATE TABLE pricing_configs (
  id                 BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  version            INTEGER NOT NULL UNIQUE,
  is_active          BOOLEAN NOT NULL DEFAULT FALSE,
  u_ot1              NUMERIC(14,0) NOT NULL CHECK (u_ot1 >= 0),   -- VND/ký tự theo loại đơn
  u_ot2              NUMERIC(14,0) NOT NULL CHECK (u_ot2 >= 0),
  u_ot3              NUMERIC(14,0) NOT NULL CHECK (u_ot3 >= 0),
  w_min              NUMERIC(14,0) NOT NULL CHECK (w_min >= 0),   -- công viết tối thiểu / bản
  s_ot1              NUMERIC(14,0) NOT NULL CHECK (s_ot1 >= 0),   -- phí setup theo loại đơn
  s_ot2              NUMERIC(14,0) NOT NULL CHECK (s_ot2 >= 0),
  s_ot3              NUMERIC(14,0) NOT NULL CHECK (s_ot3 >= 0),
  k_simple           NUMERIC(4,2) NOT NULL DEFAULT 1.0,
  k_medium           NUMERIC(4,2) NOT NULL DEFAULT 1.3,
  k_complex          NUMERIC(4,2) NOT NULL DEFAULT 1.6,
  -- d(Q): [{"min_qty":10,"pct":5},{"min_qty":50,"pct":10},{"min_qty":100,"pct":15}]
  discount_tiers     JSONB NOT NULL DEFAULT '[{"min_qty":10,"pct":5},{"min_qty":50,"pct":10},{"min_qty":100,"pct":15}]'::jsonb,
  p_min_pct          NUMERIC(5,2) NOT NULL DEFAULT 50 CHECK (p_min_pct > 0 AND p_min_pct <= 100),  -- BR-10
  adjust_threshold_pct NUMERIC(5,2) NOT NULL DEFAULT 15 CHECK (adjust_threshold_pct >= 0),       -- BR-09
  canvas_mm_per_char NUMERIC(6,2) NOT NULL DEFAULT 40,   -- FR-29: N = tổng độ dài nét / 40 mm
  note               TEXT,
  created_by         BIGINT REFERENCES accounts(id),
  created_at         TIMESTAMPTZ NOT NULL DEFAULT now(),
  CONSTRAINT chk_pricing_k CHECK (k_simple > 0 AND k_simple <= k_medium AND k_medium <= k_complex),
  CONSTRAINT chk_pricing_tiers CHECK (jsonb_typeof(discount_tiers) = 'array')
);
CREATE UNIQUE INDEX ux_pricing_configs_one_active ON pricing_configs (is_active) WHERE is_active;

-- ---------------------------------------------------------------------
-- 4. ĐƠN HÀNG
-- ---------------------------------------------------------------------
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
  workshop_suggest_materials BOOLEAN NOT NULL DEFAULT FALSE,     -- UC-11 "để xưởng gợi ý"
  quantity               INTEGER NOT NULL DEFAULT 1 CHECK (quantity >= 1),
  char_count             INTEGER CHECK (char_count >= 0),          -- N (FR-10, FR-29)
  complexity             complexity_level,                         -- K_cx đã chốt
  estimated_price_min    NUMERIC(14,0) CHECK (estimated_price_min >= 0),  -- FR-10 khoảng giá
  estimated_price_max    NUMERIC(14,0) CHECK (estimated_price_max >= 0),
  total_amount           NUMERIC(14,0) CHECK (total_amount >= 0),  -- G theo báo giá đã duyệt
  deposit_pct            NUMERIC(5,2) CHECK (deposit_pct > 0 AND deposit_pct <= 100),
  deposit_amount         NUMERIC(14,0) CHECK (deposit_amount >= 0), -- D
  customer_note          TEXT,
  terms_accepted_at      TIMESTAMPTZ,                              -- FR-11 kiểm tra điều khoản
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
  -- ETA (FR-26, BR-15, BR-16)
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
  received_confirmed_at  TIMESTAMPTZ,                              -- khách xác nhận nhận hàng
  completed_at           TIMESTAMPTZ,
  cancelled_at           TIMESTAMPTZ,
  cancel_reason          TEXT,
  inputs_purged_at       TIMESTAMPTZ,                              -- BR-23: đã xoá ảnh sau 90 ngày
  created_at             TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at             TIMESTAMPTZ NOT NULL DEFAULT now(),
  CONSTRAINT fk_orders_ink_of_pen FOREIGN KEY (ink_color_id, pen_type_id) REFERENCES ink_colors (id, pen_type_id),
  CONSTRAINT chk_orders_estimate CHECK (estimated_price_min IS NULL OR estimated_price_max IS NULL OR estimated_price_min <= estimated_price_max),
  CONSTRAINT chk_orders_pickup_slot CHECK (pickup_slot_end IS NULL OR pickup_slot_end > pickup_slot_start),
  CONSTRAINT chk_orders_reject CHECK (order_status <> 'REJECTED' OR reject_reason IS NOT NULL),
  CONSTRAINT chk_orders_staff_after_accept CHECK (
    order_status IN ('DRAFT','SUBMITTED','NEED_INFO','REJECTED','CANCELLED') OR assigned_staff_id IS NOT NULL),  -- FR-12
  CONSTRAINT chk_orders_privacy_before_quote CHECK (
    order_status NOT IN ('QUOTED','AWAITING_DEPOSIT','CONFIRMED','AWAITING_ACCEPTANCE',
                         'AWAITING_FINAL_PAYMENT','READY_TO_DELIVER','DELIVERING','COMPLETED')
    OR privacy_accepted_at IS NOT NULL),                                                                -- BR-25
  CONSTRAINT chk_orders_materials_after_submit CHECK (
    order_status IN ('DRAFT','CANCELLED') OR workshop_suggest_materials
    OR (paper_type_id IS NOT NULL AND pen_type_id IS NOT NULL AND ink_color_id IS NOT NULL))
);
CREATE INDEX ix_orders_customer ON orders (customer_id, created_at DESC);
CREATE INDEX ix_orders_drafts ON orders (customer_id, last_saved_at DESC) WHERE order_status = 'DRAFT';  -- FR-56
CREATE INDEX ix_orders_status ON orders (order_status, production_status);
CREATE INDEX ix_orders_staff ON orders (assigned_staff_id) WHERE assigned_staff_id IS NOT NULL;
CREATE INDEX ix_orders_eta ON orders (eta) WHERE order_status NOT IN ('COMPLETED','CANCELLED','REJECTED');

-- #6 HandwritingStyle (FR-36, FR-42): bộ nét học từ chữ của 1 người (OT-2)
CREATE TABLE handwriting_styles (
  id                 BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  owner_id           BIGINT NOT NULL REFERENCES accounts(id),   -- khách sở hữu bộ nét
  source_order_id    BIGINT REFERENCES orders(id) ON DELETE SET NULL,
  name               VARCHAR(150) NOT NULL,
  glyph_set_uri      TEXT,                                       -- bộ glyph đã học
  coverage_pct       NUMERIC(5,2) CHECK (coverage_pct BETWEEN 0 AND 100),
  status             style_status NOT NULL DEFAULT 'PENDING_REVIEW',
  right_to_use_confirmed BOOLEAN NOT NULL DEFAULT FALSE,         -- FR-07/BR-23
  keep_consent       BOOLEAN NOT NULL DEFAULT FALSE,             -- BR-23: giữ lại sau 90 ngày
  approved_by        BIGINT REFERENCES accounts(id),             -- Manager duyệt (FR-42)
  approved_at        TIMESTAMPTZ,
  delete_after       TIMESTAMPTZ,                                -- hạn xoá nếu không đồng ý giữ
  created_at         TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at         TIMESTAMPTZ NOT NULL DEFAULT now()
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
  -- Nội dung (TEXT_CONTENT)
  text_content         TEXT,
  template_id          BIGINT REFERENCES templates(id),
  handwriting_style_id BIGINT REFERENCES handwriting_styles(id),
  font_size_mm         NUMERIC(5,2) CHECK (font_size_mm > 0),
  alignment            VARCHAR(10) CHECK (alignment IN ('LEFT','CENTER','RIGHT','JUSTIFY')),
  layout               JSONB,                                  -- bố cục trang
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
  preview_url           TEXT,
  similarity_score      NUMERIC(5,2) CHECK (similarity_score BETWEEN 0 AND 100),  -- stroke IoU (OT-1, NFR-02)
  suggested_complexity  complexity_level,
  estimated_writing_sec INTEGER CHECK (estimated_writing_sec >= 0),
  total_stroke_mm       NUMERIC(12,2) CHECK (total_stroke_mm >= 0),
  pen_lift_count        INTEGER CHECK (pen_lift_count >= 0),
  approach_note         TEXT,                       -- cách làm, vật tư đề xuất (UC-25)
  content_hash          CHAR(64),                   -- SHA-256 của phác thảo (FR-38)
  is_final              BOOLEAN NOT NULL DEFAULT FALSE,  -- bản gửi khách / dùng sản xuất
  created_at            TIMESTAMPTZ NOT NULL DEFAULT now(),
  UNIQUE (order_id, version)
);
CREATE UNIQUE INDEX ux_sketches_one_final ON sketches (order_id) WHERE is_final;

-- #8 Quotation (FR-15, FR-29, FR-31, FR-32)
CREATE TABLE quotations (
  id                 BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  order_id           BIGINT NOT NULL REFERENCES orders(id) ON DELETE CASCADE,
  version            INTEGER NOT NULL CHECK (version >= 1),
  sketch_id          BIGINT NOT NULL REFERENCES sketches(id),    -- BR-22: phải có phác thảo
  pricing_config_id  BIGINT NOT NULL REFERENCES pricing_configs(id),
  created_by         BIGINT NOT NULL REFERENCES accounts(id),
  status             quotation_status NOT NULL DEFAULT 'DRAFT',
  -- Dòng chi tiết; khi "để xưởng gợi ý" có thể chứa 2–3 phương án vật tư:
  -- [{"option":1,"paper_type_id","pen_type_id","ink_color_id","item","calc","amount"}]
  line_items         JSONB NOT NULL CHECK (jsonb_typeof(line_items) = 'array'),
  chosen_option      SMALLINT,
  char_count         INTEGER NOT NULL CHECK (char_count >= 0),
  quantity           INTEGER NOT NULL CHECK (quantity >= 1),
  complexity         complexity_level NOT NULL,
  computed_total     NUMERIC(14,0) NOT NULL CHECK (computed_total >= 0),   -- G từ Pricing Engine
  adjusted_total     NUMERIC(14,0) CHECK (adjusted_total >= 0),            -- FR-31
  adjustment_pct     NUMERIC(6,2) GENERATED ALWAYS AS (
                       CASE WHEN adjusted_total IS NULL OR computed_total = 0 THEN NULL
                            ELSE round((adjusted_total - computed_total) * 100.0 / computed_total, 2) END) STORED,
  adjustment_reason  TEXT,
  adjustment_status  adjustment_status NOT NULL DEFAULT 'NONE',
  approved_by        BIGINT REFERENCES accounts(id),             -- Manager duyệt vượt ±15%
  approved_at        TIMESTAMPTZ,
  final_total        NUMERIC(14,0) GENERATED ALWAYS AS (COALESCE(adjusted_total, computed_total)) STORED,
  min_deposit_pct    NUMERIC(5,2) NOT NULL CHECK (min_deposit_pct > 0 AND min_deposit_pct <= 100),
  price_snapshot     JSONB NOT NULL,                             -- toàn bộ tham số giá lúc lập (BR-08)
  eta                DATE,                                       -- FR-15: ETA hiển thị trong báo giá
  file_url           TEXT,                                       -- PDF có logo xưởng
  sent_at            TIMESTAMPTZ,
  valid_until        TIMESTAMPTZ,                                -- 7 ngày từ lúc gửi (BR-08)
  customer_responded_at TIMESTAMPTZ,
  customer_note      TEXT,
  created_at         TIMESTAMPTZ NOT NULL DEFAULT now(),
  UNIQUE (order_id, version),
  CONSTRAINT chk_quote_adjust_reason CHECK (adjusted_total IS NULL OR adjustment_reason IS NOT NULL),
  CONSTRAINT chk_quote_sent_validity CHECK (sent_at IS NULL OR valid_until > sent_at)
);
CREATE INDEX ix_quotations_order ON quotations (order_id, version DESC);
CREATE INDEX ix_quotations_expiring ON quotations (valid_until) WHERE status = 'SENT';
CREATE INDEX ix_quotations_pending_approval ON quotations (created_at) WHERE adjustment_status = 'PENDING_MANAGER';

-- #9 Payment (FR-17, FR-18, FR-19, FR-20)
CREATE TABLE payments (
  id                BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  order_id          BIGINT NOT NULL REFERENCES orders(id),
  type              payment_type NOT NULL,
  amount            NUMERIC(14,0) NOT NULL CHECK (amount > 0),
  deposit_pct       NUMERIC(5,2) CHECK (deposit_pct > 0 AND deposit_pct <= 100),
  gateway           payment_gateway NOT NULL,
  gateway_txn_id    VARCHAR(100),                     -- idempotency webhook (NFR-06)
  status            payment_status NOT NULL DEFAULT 'PENDING',
  refund_of_id      BIGINT REFERENCES payments(id),   -- hoàn tiền tham chiếu giao dịch gốc
  refund_reason     TEXT,
  confirmed_by      BIGINT REFERENCES accounts(id),   -- Staff xác nhận/đối soát (UC-28)
  confirmed_at      TIMESTAMPTZ,
  invoice_url       TEXT,
  gateway_payload   JSONB,                            -- webhook đã xác thực chữ ký; không lưu thẻ (NFR-09)
  paid_at           TIMESTAMPTZ,
  created_at        TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at        TIMESTAMPTZ NOT NULL DEFAULT now(),
  CONSTRAINT chk_payment_deposit_pct CHECK (type = 'DEPOSIT' OR deposit_pct IS NULL),
  CONSTRAINT chk_payment_refund_ref CHECK ((type = 'REFUND') = (refund_of_id IS NOT NULL))
);
CREATE UNIQUE INDEX ux_payments_gateway_txn ON payments (gateway, gateway_txn_id) WHERE gateway_txn_id IS NOT NULL;
CREATE INDEX ix_payments_order ON payments (order_id, created_at);

-- #10 Shipment (FR-21, FR-22, FR-23). Nhận tại xưởng không tạo vận đơn (orders.delivery_method = PICKUP).
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
  to_address         JSONB NOT NULL,                             -- mã tỉnh/huyện/xã theo hãng
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

-- #11 Message (FR-16)
CREATE TABLE messages (
  id          BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  order_id    BIGINT NOT NULL REFERENCES orders(id) ON DELETE CASCADE,
  sender_id   BIGINT NOT NULL REFERENCES accounts(id),
  body        TEXT,
  attachments JSONB NOT NULL DEFAULT '[]'::jsonb,   -- ảnh đính kèm [{"url","mime"}]
  read_at     TIMESTAMPTZ,
  created_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
  CONSTRAINT chk_message_not_empty CHECK (body IS NOT NULL OR jsonb_array_length(attachments) > 0)
);
CREATE INDEX ix_messages_order ON messages (order_id, created_at);

-- #12 StatusHistory (FR-24, FR-25, FR-26)
CREATE TABLE status_histories (
  id          BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  order_id    BIGINT NOT NULL REFERENCES orders(id) ON DELETE CASCADE,
  job_id      BIGINT,                                -- FK thêm sau khi tạo production_jobs
  state_type  state_type NOT NULL,
  from_status VARCHAR(30),
  to_status   VARCHAR(30),
  old_eta     DATE,
  new_eta     DATE,
  reason      TEXT,
  actor_id    BIGINT REFERENCES accounts(id),        -- NULL = hệ thống/scheduled job
  created_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
  CONSTRAINT chk_history_payload CHECK (
    (state_type = 'ETA' AND new_eta IS NOT NULL AND reason IS NOT NULL) OR     -- BR-16: dời ETA phải có lý do
    (state_type <> 'ETA' AND to_status IS NOT NULL))
);
CREATE INDEX ix_status_histories_order ON status_histories (order_id, created_at);

-- ---------------------------------------------------------------------
-- 5. SẢN XUẤT
-- ---------------------------------------------------------------------
-- #17 Robot (FR-39)
CREATE TABLE robots (
  id           BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  code         VARCHAR(30) NOT NULL UNIQUE,
  robot_type   VARCHAR(50) NOT NULL DEFAULT 'FAIRINO_FR3',  -- [GIẢ ĐỊNH] loại robot là cột, không có bảng riêng
  station      VARCHAR(50),                                -- trạm/bàn làm việc
  status       robot_status NOT NULL DEFAULT 'AVAILABLE',
  is_simulated BOOLEAN NOT NULL DEFAULT FALSE,             -- robot mô phỏng cho demo (LI-03)
  supported_pen_categories pen_category[],                 -- BR-18: loại robot phù hợp vật liệu [GIẢ ĐỊNH]
  note         TEXT,
  created_at   TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at   TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- #18 ProductionJob (FR-37, FR-38, FR-40, FR-43, FR-45, FR-46)
CREATE TABLE production_jobs (
  id                    BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  order_id              BIGINT NOT NULL REFERENCES orders(id),
  sketch_id             BIGINT NOT NULL REFERENCES sketches(id),
  robot_id              BIGINT NOT NULL REFERENCES robots(id),
  technician_id         BIGINT NOT NULL REFERENCES accounts(id),
  scheduled_by          BIGINT NOT NULL REFERENCES accounts(id),    -- Manager
  status                job_status NOT NULL DEFAULT 'SCHEDULED',
  is_rewrite            BOOLEAN NOT NULL DEFAULT FALSE,
  slot_start            TIMESTAMPTZ NOT NULL,
  slot_end              TIMESTAMPTZ NOT NULL,
  -- FR-40: thời lượng = thời gian viết × Q + chuẩn bị 15' + chụp ảnh 5'
  estimated_duration_min INTEGER NOT NULL CHECK (estimated_duration_min > 0),
  package_uri           TEXT,                       -- gói job (quỹ đạo, PenProfile, thông số giấy/bút, ảnh phác thảo)
  package_hash          CHAR(64),                   -- SHA-256 phác thảo đã duyệt (FR-38)
  packaged_at           TIMESTAMPTZ,
  downloaded_at         TIMESTAMPTZ,
  simulation_passed     BOOLEAN,                    -- FR-45: chặn chạy khi còn lỗi khả thi
  simulation_report     JSONB,
  progress_pct          NUMERIC(5,2) DEFAULT 0 CHECK (progress_pct BETWEEN 0 AND 100),
  started_at            TIMESTAMPTZ,
  finished_at           TIMESTAMPTZ,
  created_at            TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at            TIMESTAMPTZ NOT NULL DEFAULT now(),
  CONSTRAINT chk_job_slot CHECK (slot_end > slot_start),
  CONSTRAINT chk_job_run_requires_sim CHECK (
    status NOT IN ('WRITING','PAUSED','WRITTEN','PHOTO_UPLOADED','DONE') OR simulation_passed IS TRUE),
  -- BR-18: mỗi robot tối đa 1 job tại một thời điểm
  CONSTRAINT ex_job_robot_overlap EXCLUDE USING gist (
    robot_id WITH =, tstzrange(slot_start, slot_end) WITH &&)
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
  id                 BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  job_id             BIGINT NOT NULL REFERENCES production_jobs(id) ON DELETE CASCADE,
  robot_id           BIGINT NOT NULL REFERENCES robots(id),
  technician_id      BIGINT NOT NULL REFERENCES accounts(id),
  paper_type_id      BIGINT REFERENCES paper_types(id),
  pen_type_id        BIGINT REFERENCES pen_types(id),
  checklist          JSONB,                         -- khung/giấy/bút
  force_zero_offset  NUMERIC(8,4),                  -- trung bình 1 s khi bút trên không
  probe_points       JSONB NOT NULL,                -- P0, P1, P2 (+ lưới)
  frame_transform    JSONB,                         -- R, t (giấy → đế robot)
  height_map         JSONB,                         -- z_map
  force_curve        JSONB,                         -- đường cong Hall → lực (đối chiếu cân chuẩn)
  is_valid           BOOLEAN NOT NULL DEFAULT TRUE,
  created_at         TIMESTAMPTZ NOT NULL DEFAULT now()
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
  robot_status_after robot_status,                  -- robot chuyển BROKEN/MAINTENANCE nếu cần
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
  actor_id      BIGINT REFERENCES accounts(id),    -- NULL = Robot Agent / thiết bị IoT
  incident_id   BIGINT REFERENCES incidents(id),
  stroke_index  INTEGER,
  -- Tóm tắt lực: {"f_mean","f_max","rms_err_pct","in_band_pct","samples"} (NFR-05)
  force_summary JSONB,
  payload       JSONB,
  occurred_at   TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX ix_job_events_job ON job_events (job_id, occurred_at);

-- #20 ProductPhoto (FR-49, BR-21)
CREATE TABLE product_photos (
  id           BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  order_id     BIGINT NOT NULL REFERENCES orders(id) ON DELETE CASCADE,
  job_id       BIGINT NOT NULL REFERENCES production_jobs(id),
  uploaded_by  BIGINT NOT NULL REFERENCES accounts(id),
  kind         photo_kind NOT NULL,
  url          TEXT NOT NULL,
  overlay_url  TEXT,                                -- ảnh chồng với phác thảo
  qc_result    qc_result,
  qc_note      TEXT,
  deleted_at   TIMESTAMPTZ,                         -- BR-23
  created_at   TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX ix_product_photos_job ON product_photos (job_id);
CREATE INDEX ix_product_photos_order ON product_photos (order_id);

-- ---------------------------------------------------------------------
-- 6. HỆ THỐNG, THÔNG BÁO, ĐÁNH GIÁ, TRANG CHỦ
-- ---------------------------------------------------------------------
-- #24 AuditLog (FR-51, FR-52, FR-31)
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
  id           BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  account_id   BIGINT NOT NULL REFERENCES accounts(id) ON DELETE CASCADE,
  order_id     BIGINT REFERENCES orders(id) ON DELETE CASCADE,
  type         notification_type NOT NULL,
  msg_code     VARCHAR(10),                        -- MSG07, MSG10... (mục 5.3)
  title        VARCHAR(200) NOT NULL,
  body         TEXT NOT NULL,
  channel      notification_channel NOT NULL,
  is_read      BOOLEAN NOT NULL DEFAULT FALSE,
  read_at      TIMESTAMPTZ,
  sent_at      TIMESTAMPTZ,
  created_at   TIMESTAMPTZ NOT NULL DEFAULT now(),
  CONSTRAINT chk_notification_read CHECK (is_read = (read_at IS NOT NULL))
);
CREATE INDEX ix_notifications_unread ON notifications (account_id, created_at DESC) WHERE channel = 'IN_APP' AND NOT is_read;
CREATE INDEX ix_notifications_account ON notifications (account_id, created_at DESC);

-- #26 Review (FR-58): mỗi đơn 1 đánh giá
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

-- ---------------------------------------------------------------------
-- 7. TRIGGER
-- ---------------------------------------------------------------------
-- 7.1 updated_at tự động
CREATE OR REPLACE FUNCTION fn_set_updated_at() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
  NEW.updated_at := now();
  RETURN NEW;
END $$;

DO $$
DECLARE t text;
BEGIN
  FOREACH t IN ARRAY ARRAY['accounts','paper_types','pen_types','templates','orders','handwriting_styles',
                           'order_inputs','payments','shipments','robots','production_jobs','reviews','showcase_posts']
  LOOP
    EXECUTE format('CREATE TRIGGER trg_%1$s_updated_at BEFORE UPDATE ON %1$I
                    FOR EACH ROW EXECUTE FUNCTION fn_set_updated_at()', t);
  END LOOP;
END $$;

-- 7.2 Lấy người thao tác từ biến phiên
CREATE OR REPLACE FUNCTION fn_current_actor() RETURNS bigint LANGUAGE sql STABLE AS $$
  SELECT NULLIF(current_setting('app.current_account_id', true), '')::bigint
$$;

-- 7.3 Máy trạng thái đơn hàng (FR-24, bảng 2.5.1) + sản xuất (FR-25, bảng 2.5.2)
--     + ràng buộc đồng bộ (BR-17, bảng 2.5.3). Vi phạm → lỗi SQLSTATE 'P0409'
--     (API trả 409).
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
      ELSE FALSE                    -- REJECTED, COMPLETED, CANCELLED là trạng thái kết thúc
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
      ELSE FALSE              -- FINISHED
    END;
    -- Huỷ đơn khi đã xếp lịch/chuẩn bị: sản xuất quay về trạng thái chờ (job bị huỷ, robot giải phóng)
    IF NOT p_ok AND NEW.order_status = 'CANCELLED'
       AND OLD.production_status IN ('PENDING_SCHEDULE','SCHEDULED','PREPARING')
       AND NEW.production_status = 'NOT_STARTED' THEN
      p_ok := TRUE;
    END IF;
    IF NOT p_ok THEN
      RAISE EXCEPTION 'Chuyển trạng thái sản xuất không hợp lệ: % -> %', OLD.production_status, NEW.production_status
        USING ERRCODE = 'P0409';
    END IF;
  END IF;

  -- BR-17 / bảng 2.5.3
  IF NEW.production_status <> 'NOT_STARTED' AND NEW.order_status NOT IN
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
  -- BR-14 / BR-16: không huỷ khi đã bắt đầu viết, trừ khi dời ETA > 7 ngày
  IF NEW.order_status = 'CANCELLED' AND OLD.order_status = 'CONFIRMED'
     AND OLD.production_status IN ('WRITING','PAUSED','WRITTEN','PHOTO_UPLOADED','REWRITE_REQUIRED','FAILED')
     AND NEW.eta_postponed_days <= 7 THEN
    RAISE EXCEPTION 'Không thể huỷ đơn đã bắt đầu viết (BR-14)' USING ERRCODE = 'P0409';
  END IF;

  -- Mốc thời gian
  IF NEW.order_status IS DISTINCT FROM OLD.order_status THEN
    CASE NEW.order_status
      WHEN 'SUBMITTED' THEN NEW.submitted_at := COALESCE(NEW.submitted_at, now());
      WHEN 'CONFIRMED' THEN NEW.confirmed_at := COALESCE(NEW.confirmed_at, now());
      WHEN 'COMPLETED' THEN NEW.completed_at := now();
      WHEN 'CANCELLED' THEN NEW.cancelled_at := now();
      ELSE NULL;
    END CASE;
  END IF;
  IF OLD.order_status = 'DRAFT' AND NEW.order_status = 'DRAFT' THEN
    NEW.last_saved_at := now();                               -- FR-55
  END IF;
  RETURN NEW;
END $$;

CREATE TRIGGER trg_orders_state_guard
  BEFORE INSERT OR UPDATE ON orders
  FOR EACH ROW EXECUTE FUNCTION fn_order_state_guard();

-- 7.4 Ghi StatusHistory tự động (FR-24, FR-25, FR-26, NFR-11)
CREATE OR REPLACE FUNCTION fn_order_status_history() RETURNS trigger LANGUAGE plpgsql AS $$
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

-- 7.5 Đánh giá chỉ cho đơn COMPLETED của chính khách (FR-58, BR-02)
CREATE OR REPLACE FUNCTION fn_review_guard() RETURNS trigger LANGUAGE plpgsql AS $$
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

-- 7.6 BR-21: chỉ PHOTO_UPLOADED khi job có ≥ 2 ảnh (toàn cảnh + cận cảnh) và QC đạt
CREATE OR REPLACE FUNCTION fn_photo_uploaded_guard() RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE v_job bigint;
BEGIN
  IF NEW.production_status = 'PHOTO_UPLOADED' AND OLD.production_status IS DISTINCT FROM 'PHOTO_UPLOADED' THEN
    SELECT id INTO v_job FROM production_jobs
     WHERE order_id = NEW.id AND status IN ('WRITTEN','PHOTO_UPLOADED')
     ORDER BY created_at DESC LIMIT 1;
    IF v_job IS NULL
       OR (SELECT count(*) FROM product_photos WHERE job_id = v_job AND deleted_at IS NULL) < 2
       OR NOT EXISTS (SELECT 1 FROM product_photos WHERE job_id = v_job AND kind = 'OVERALL')
       OR NOT EXISTS (SELECT 1 FROM product_photos WHERE job_id = v_job AND kind = 'CLOSE_UP')
       OR EXISTS (SELECT 1 FROM product_photos WHERE job_id = v_job AND qc_result IS DISTINCT FROM 'PASS') THEN
      RAISE EXCEPTION 'Cần ≥ 2 ảnh (toàn cảnh + cận cảnh) và QC đạt trước PHOTO_UPLOADED (BR-21)' USING ERRCODE = 'P0409';
    END IF;
  END IF;
  RETURN NEW;
END $$;

CREATE TRIGGER trg_orders_photo_guard
  BEFORE UPDATE OF production_status ON orders
  FOR EACH ROW EXECUTE FUNCTION fn_photo_uploaded_guard();

-- ---------------------------------------------------------------------
-- 8. VIEW tiện dùng
-- ---------------------------------------------------------------------
-- Bản nháp của khách (FR-56)
CREATE VIEW v_customer_drafts AS
SELECT o.id, o.code, o.customer_id, o.order_type, o.quantity, o.paper_type_id, o.pen_type_id,
       o.ink_color_id, o.last_saved_at, count(i.id) AS input_count
FROM orders o LEFT JOIN order_inputs i ON i.order_id = o.id AND i.deleted_at IS NULL
WHERE o.order_status = 'DRAFT'
GROUP BY o.id;

-- Tổng ngày dời ETA được tính lại từ lịch sử (BR-16)
CREATE VIEW v_order_eta_postponement AS
SELECT order_id,
       sum(GREATEST(new_eta - old_eta, 0)) AS total_postponed_days,
       sum(GREATEST(new_eta - old_eta, 0)) > 7 AS can_cancel_full_refund
FROM status_histories
WHERE state_type = 'ETA' AND old_eta IS NOT NULL
GROUP BY order_id;

-- ---------------------------------------------------------------------
-- 9. SEED
-- ---------------------------------------------------------------------
-- 5 vai trò (FR-03)
INSERT INTO roles (id, code, name, description) VALUES
  (1, 'CUSTOMER',        'Customer',        'Khách hàng: đặt đơn, duyệt báo giá, thanh toán, nghiệm thu'),
  (2, 'STAFF',           'Staff',           'Nhân viên xưởng: tiếp nhận đơn, phác thảo, báo giá, giao hàng'),
  (3, 'TECHNICAL_STAFF', 'Technical Staff', 'Kỹ thuật viên: vận hành robot FR3 qua Flutter App'),
  (4, 'MANAGER',         'Manager',         'Quản lý xưởng: robot, vật liệu, giá, lập lịch'),
  (5, 'ADMIN',           'Admin',           'Quản trị hệ thống: tài khoản, tích hợp, tham số, audit log');

-- 1 tài khoản mẫu cho mỗi vai trò. Mật khẩu chung: ChangeMe@123 (bcrypt) - ĐỔI NGAY khi triển khai.
INSERT INTO accounts (role_id, email, password_hash, full_name, phone, phone_verified_at) VALUES
  (5, 'admin@netviet.vn',     crypt('ChangeMe@123', gen_salt('bf', 10)), 'System Admin',       NULL, NULL),
  (4, 'manager@netviet.vn',   crypt('ChangeMe@123', gen_salt('bf', 10)), 'Workshop Manager',   NULL, NULL),
  (2, 'staff@netviet.vn',     crypt('ChangeMe@123', gen_salt('bf', 10)), 'Order Staff',        NULL, NULL),
  (3, 'tech@netviet.vn',      crypt('ChangeMe@123', gen_salt('bf', 10)), 'Technical Staff',    NULL, NULL),
  (1, 'customer@example.com', crypt('ChangeMe@123', gen_salt('bf', 10)), 'Demo Customer', '0900000000', now());
UPDATE accounts SET created_by = (SELECT id FROM accounts WHERE email = 'admin@netviet.vn')
 WHERE role_id IN (2, 3, 4);

-- Bảng giá phiên bản 1: K_cx, d(Q), p_min, ±15% theo report; u, W_min, S lấy từ ví dụ minh hoạ
-- trong FR-29 (300 VND/ký tự, 50.000, 100.000) - Manager chỉnh lại giá thật.
INSERT INTO pricing_configs (version, is_active, u_ot1, u_ot2, u_ot3, w_min, s_ot1, s_ot2, s_ot3, note, created_by)
SELECT 1, TRUE, 300, 300, 300, 50000, 100000, 100000, 100000,
       'Giá khởi tạo theo ví dụ minh hoạ FR-29', id
FROM accounts WHERE email = 'manager@netviet.vn';

-- Loại bút theo bảng lực mục 3.6.2 (giá trị khởi điểm, chốt sau thí nghiệm)
INSERT INTO pen_types (code, name, category, stroke_width_mm, f_target_n, f_min_n, f_max_n, f_hard_n, v_max_mm_s) VALUES
  ('BALL07',  'Ballpoint 0.7 mm', 'BALLPOINT', 0.70, 1.00, 0.60, 1.40, 4.00, 40),
  ('GEL05',   'Gel pen 0.5 mm',   'GEL',       0.50, 0.60, 0.36, 0.84, 3.00, 30),
  ('FINE03',  'Fineliner 0.3 mm', 'FINELINER', 0.30, 0.40, 0.24, 0.56, 2.00, 25),
  ('FOUNT',   'Fountain pen',     'FOUNTAIN',  0.60, 0.30, 0.18, 0.42, 2.00, 20),
  ('BRUSH',   'Brush pen',        'BRUSH',     2.00, 0.80, 0.48, 1.12, 3.50, 15);
-- [GIẢ ĐỊNH] độ rộng nét bút máy 0.6 mm và bút lông 2.0 mm (report không ghi).

COMMIT;
