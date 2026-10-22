-- =====================================================================================================================
-- AI-VHRS (Xuong Net Viet) - full database script for PostgreSQL 15+ (Supabase uses 17).
-- Revision 0006 (alembic head), generated 2026-10-22 by scripts/build_database_script.py. DO NOT EDIT BY HAND:
-- change the database with an Alembic migration, then rebuild this file.
--
-- What it contains
--   1. the schema: extension, enum types, tables, constraints, indexes, functions, triggers, row-level security (all of the
--      baseline schema and every migration up to 0006);
--   2. the `alembic_version` row, so the application's migrations see this database as already at 0006;
--   3. reference data: the 5 roles, the demo accounts (password ChangeMe@123: CHANGE IT before any real use), the first price list,
--      the pen types, and the default system settings.
-- It does NOT contain the catalogue and policy text that `scripts/seed_workshop_data.py` loads (papers, inks, templates, the
-- privacy policy, which order types are enabled): run that script afterwards for a working demo.
--
-- How to run (an EMPTY database):   psql "$DATABASE_URL" -v ON_ERROR_STOP=1 -f database/AI-VHRS_database_full.sql
-- On Supabase: run it in the SQL editor of an empty project (the `anon`/`authenticated` lock-down at the end applies there).
-- =====================================================================================================================

-- =====================================================================================================================
-- 1. Schema (pg_dump --schema-only of the migrated database)
-- =====================================================================================================================
--
-- PostgreSQL database dump
--

-- Dumped from database version 16.15 (Debian 16.15-1.pgdg13+2)
-- Dumped by pg_dump version 16.15 (Debian 16.15-1.pgdg13+2)

SET statement_timeout = 0;
SET lock_timeout = 0;
SET idle_in_transaction_session_timeout = 0;
SET client_encoding = 'UTF8';
SET standard_conforming_strings = on;
SELECT pg_catalog.set_config('search_path', '', false);
SET check_function_bodies = false;
SET xmloption = content;
SET client_min_messages = warning;
SET row_security = off;

--
-- Name: btree_gist; Type: EXTENSION; Schema: -; Owner: -
--

CREATE EXTENSION IF NOT EXISTS btree_gist WITH SCHEMA public;

--
-- Name: EXTENSION btree_gist; Type: COMMENT; Schema: -; Owner: -
--

COMMENT ON EXTENSION btree_gist IS 'support for indexing common datatypes in GiST';

--
-- Name: pgcrypto; Type: EXTENSION; Schema: -; Owner: -
--

CREATE EXTENSION IF NOT EXISTS pgcrypto WITH SCHEMA public;

--
-- Name: EXTENSION pgcrypto; Type: COMMENT; Schema: -; Owner: -
--

COMMENT ON EXTENSION pgcrypto IS 'cryptographic functions';

--
-- Name: account_status; Type: TYPE; Schema: public; Owner: -
--

CREATE TYPE public.account_status AS ENUM (
    'ACTIVE',
    'LOCKED',
    'DISABLED'
);

--
-- Name: adjustment_status; Type: TYPE; Schema: public; Owner: -
--

CREATE TYPE public.adjustment_status AS ENUM (
    'NONE',
    'WITHIN_THRESHOLD',
    'PENDING_MANAGER',
    'APPROVED',
    'REJECTED'
);

--
-- Name: carrier; Type: TYPE; Schema: public; Owner: -
--

CREATE TYPE public.carrier AS ENUM (
    'GHN',
    'GHTK'
);

--
-- Name: complexity_level; Type: TYPE; Schema: public; Owner: -
--

CREATE TYPE public.complexity_level AS ENUM (
    'SIMPLE',
    'MEDIUM',
    'COMPLEX'
);

--
-- Name: delivery_method; Type: TYPE; Schema: public; Owner: -
--

CREATE TYPE public.delivery_method AS ENUM (
    'DELIVERY',
    'PICKUP'
);

--
-- Name: incident_type; Type: TYPE; Schema: public; Owner: -
--

CREATE TYPE public.incident_type AS ENUM (
    'ROBOT',
    'MATERIAL',
    'FORCE_MODULE',
    'OTHER'
);

--
-- Name: job_event_type; Type: TYPE; Schema: public; Owner: -
--

CREATE TYPE public.job_event_type AS ENUM (
    'DOWNLOADED',
    'HASH_MISMATCH',
    'CALIBRATED',
    'SIMULATED',
    'START',
    'PROGRESS',
    'PAUSE',
    'RESUME',
    'ESTOP',
    'OVER_FORCE',
    'STROKE_LOST',
    'SENSOR_LOST',
    'INCIDENT',
    'WRITTEN',
    'FORCE_SUMMARY'
);

--
-- Name: job_status; Type: TYPE; Schema: public; Owner: -
--

CREATE TYPE public.job_status AS ENUM (
    'SCHEDULED',
    'PREPARING',
    'WRITING',
    'PAUSED',
    'WRITTEN',
    'PHOTO_UPLOADED',
    'DONE',
    'FAILED',
    'REWRITE_REQUIRED',
    'CANCELLED'
);

--
-- Name: notification_channel; Type: TYPE; Schema: public; Owner: -
--

CREATE TYPE public.notification_channel AS ENUM (
    'EMAIL',
    'IN_APP'
);

--
-- Name: notification_type; Type: TYPE; Schema: public; Owner: -
--

CREATE TYPE public.notification_type AS ENUM (
    'ORDER_ACCEPTED',
    'ORDER_REJECTED',
    'NEED_INFO',
    'ORDER_STATUS_CHANGED',
    'PRODUCTION_STATUS_CHANGED',
    'SKETCH_READY',
    'QUOTATION_AVAILABLE',
    'QUOTATION_EXPIRED',
    'ETA_POSTPONED',
    'NEW_MESSAGE',
    'PRODUCT_COMPLETED',
    'DELIVERING',
    'PAYMENT',
    'SYSTEM'
);

--
-- Name: order_input_kind; Type: TYPE; Schema: public; Owner: -
--

CREATE TYPE public.order_input_kind AS ENUM (
    'ORIGINAL_IMAGE',
    'HANDWRITING_SAMPLE',
    'TEXT_CONTENT',
    'CANVAS'
);

--
-- Name: order_status; Type: TYPE; Schema: public; Owner: -
--

CREATE TYPE public.order_status AS ENUM (
    'DRAFT',
    'SUBMITTED',
    'NEED_INFO',
    'REJECTED',
    'ACCEPTED',
    'AWAITING_PRIVACY',
    'QUOTED',
    'AWAITING_DEPOSIT',
    'CONFIRMED',
    'AWAITING_ACCEPTANCE',
    'AWAITING_FINAL_PAYMENT',
    'READY_TO_DELIVER',
    'DELIVERING',
    'COMPLETED',
    'CANCELLED'
);

--
-- Name: order_type; Type: TYPE; Schema: public; Owner: -
--

CREATE TYPE public.order_type AS ENUM (
    'OT1_COPY_RESTORE',
    'OT2_LEARNED_STYLE',
    'OT3_TEMPLATE'
);

--
-- Name: paper_size; Type: TYPE; Schema: public; Owner: -
--

CREATE TYPE public.paper_size AS ENUM (
    'A6',
    'A5',
    'A4'
);

--
-- Name: paper_surface; Type: TYPE; Schema: public; Owner: -
--

CREATE TYPE public.paper_surface AS ENUM (
    'PLAIN',
    'ART',
    'GLOSSY',
    'COATED',
    'CARD',
    'OTHER'
);

--
-- Name: payment_gateway; Type: TYPE; Schema: public; Owner: -
--

CREATE TYPE public.payment_gateway AS ENUM (
    'VNPAY',
    'MOMO',
    'PAYOS'
);

--
-- Name: payment_status; Type: TYPE; Schema: public; Owner: -
--

CREATE TYPE public.payment_status AS ENUM (
    'PENDING',
    'SUCCESS',
    'FAILED',
    'CANCELLED'
);

--
-- Name: payment_type; Type: TYPE; Schema: public; Owner: -
--

CREATE TYPE public.payment_type AS ENUM (
    'DEPOSIT',
    'FINAL',
    'SHIPPING',
    'REFUND'
);

--
-- Name: pen_category; Type: TYPE; Schema: public; Owner: -
--

CREATE TYPE public.pen_category AS ENUM (
    'BALLPOINT',
    'GEL',
    'FINELINER',
    'FOUNTAIN',
    'BRUSH',
    'MARKER'
);

--
-- Name: photo_kind; Type: TYPE; Schema: public; Owner: -
--

CREATE TYPE public.photo_kind AS ENUM (
    'OVERALL',
    'CLOSE_UP',
    'OTHER'
);

--
-- Name: production_status; Type: TYPE; Schema: public; Owner: -
--

CREATE TYPE public.production_status AS ENUM (
    'NOT_STARTED',
    'PENDING_SCHEDULE',
    'SCHEDULED',
    'PREPARING',
    'WRITING',
    'PAUSED',
    'FAILED',
    'WRITTEN',
    'PHOTO_UPLOADED',
    'REWRITE_REQUIRED',
    'FINISHED'
);

--
-- Name: qc_result; Type: TYPE; Schema: public; Owner: -
--

CREATE TYPE public.qc_result AS ENUM (
    'PASS',
    'FAIL'
);

--
-- Name: quotation_status; Type: TYPE; Schema: public; Owner: -
--

CREATE TYPE public.quotation_status AS ENUM (
    'DRAFT',
    'PENDING_APPROVAL',
    'SENT',
    'APPROVED',
    'CHANGES_REQUESTED',
    'EXPIRED',
    'CANCELLED',
    'SUPERSEDED'
);

--
-- Name: reject_reason; Type: TYPE; Schema: public; Owner: -
--

CREATE TYPE public.reject_reason AS ENUM (
    'TOO_OLD',
    'DAMAGED',
    'MISSING_CONTENT',
    'PROHIBITED_CONTENT',
    'OTHER'
);

--
-- Name: robot_status; Type: TYPE; Schema: public; Owner: -
--

CREATE TYPE public.robot_status AS ENUM (
    'AVAILABLE',
    'BUSY',
    'MAINTENANCE',
    'BROKEN'
);

--
-- Name: shipment_status; Type: TYPE; Schema: public; Owner: -
--

CREATE TYPE public.shipment_status AS ENUM (
    'CREATED',
    'PICKED_UP',
    'DELIVERING',
    'DELIVERED',
    'FAILED',
    'RETURNED',
    'CANCELLED'
);

--
-- Name: state_type; Type: TYPE; Schema: public; Owner: -
--

CREATE TYPE public.state_type AS ENUM (
    'ORDER',
    'PRODUCTION',
    'ETA'
);

--
-- Name: style_status; Type: TYPE; Schema: public; Owner: -
--

CREATE TYPE public.style_status AS ENUM (
    'PENDING_REVIEW',
    'APPROVED',
    'REJECTED',
    'DELETED'
);

--
-- Name: template_kind; Type: TYPE; Schema: public; Owner: -
--

CREATE TYPE public.template_kind AS ENUM (
    'TYPOGRAPHY',
    'CALLIGRAPHY',
    'SINGLE_LINE_FONT'
);

--
-- Name: fn_current_actor(); Type: FUNCTION; Schema: public; Owner: -
--

CREATE FUNCTION public.fn_current_actor() RETURNS bigint
    LANGUAGE sql STABLE
    AS $$
  SELECT NULLIF(current_setting('app.current_account_id', true), '')::bigint
$$;

--
-- Name: fn_order_state_guard(); Type: FUNCTION; Schema: public; Owner: -
--

CREATE FUNCTION public.fn_order_state_guard() RETURNS trigger
    LANGUAGE plpgsql
    AS $$
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

--
-- Name: fn_order_status_history(); Type: FUNCTION; Schema: public; Owner: -
--

CREATE FUNCTION public.fn_order_status_history() RETURNS trigger
    LANGUAGE plpgsql
    AS $$
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

--
-- Name: fn_photo_uploaded_guard(); Type: FUNCTION; Schema: public; Owner: -
--

CREATE FUNCTION public.fn_photo_uploaded_guard() RETURNS trigger
    LANGUAGE plpgsql
    AS $$
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

--
-- Name: fn_review_guard(); Type: FUNCTION; Schema: public; Owner: -
--

CREATE FUNCTION public.fn_review_guard() RETURNS trigger
    LANGUAGE plpgsql
    AS $$
BEGIN
  IF NOT EXISTS (SELECT 1 FROM orders o
                 WHERE o.id = NEW.order_id AND o.customer_id = NEW.customer_id
                   AND o.order_status = 'COMPLETED') THEN
    RAISE EXCEPTION 'Chỉ đánh giá được đơn đã hoàn thành của chính mình' USING ERRCODE = 'P0409';
  END IF;
  RETURN NEW;
END $$;

--
-- Name: fn_set_updated_at(); Type: FUNCTION; Schema: public; Owner: -
--

CREATE FUNCTION public.fn_set_updated_at() RETURNS trigger
    LANGUAGE plpgsql
    AS $$
BEGIN
  NEW.updated_at := now();
  RETURN NEW;
END $$;

SET default_tablespace = '';

SET default_table_access_method = heap;

--
-- Name: accounts; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.accounts (
    id bigint NOT NULL,
    role_id smallint NOT NULL,
    email character varying(255) NOT NULL,
    password_hash character varying(255) NOT NULL,
    full_name character varying(150) NOT NULL,
    phone character varying(20),
    phone_verified_at timestamp with time zone,
    status public.account_status DEFAULT 'ACTIVE'::public.account_status NOT NULL,
    failed_login_count smallint DEFAULT 0 NOT NULL,
    locked_until timestamp with time zone,
    addresses jsonb DEFAULT '[]'::jsonb NOT NULL,
    created_by bigint,
    last_login_at timestamp with time zone,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL,
    CONSTRAINT accounts_addresses_check CHECK ((jsonb_typeof(addresses) = 'array'::text)),
    CONSTRAINT chk_accounts_failed_login CHECK ((failed_login_count >= 0))
);

--
-- Name: accounts_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

ALTER TABLE public.accounts ALTER COLUMN id ADD GENERATED ALWAYS AS IDENTITY (
    SEQUENCE NAME public.accounts_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1
);

--
-- Name: alembic_version; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.alembic_version (
    version_num character varying(32) NOT NULL
);

--
-- Name: audit_logs; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.audit_logs (
    id bigint NOT NULL,
    actor_id bigint,
    action character varying(60) NOT NULL,
    entity_type character varying(40),
    entity_id bigint,
    old_value jsonb,
    new_value jsonb,
    reason text,
    policy_version character varying(20),
    ip_address inet,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    CONSTRAINT chk_audit_privacy CHECK ((((action)::text <> ALL ((ARRAY['PRIVACY_ACCEPT'::character varying, 'PRIVACY_DECLINE'::character varying])::text[])) OR (policy_version IS NOT NULL)))
);

--
-- Name: audit_logs_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

ALTER TABLE public.audit_logs ALTER COLUMN id ADD GENERATED ALWAYS AS IDENTITY (
    SEQUENCE NAME public.audit_logs_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1
);

--
-- Name: auth_sessions; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.auth_sessions (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    account_id bigint NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    expires_at timestamp with time zone NOT NULL,
    revoked_at timestamp with time zone,
    ip_address inet,
    user_agent character varying(255),
    CONSTRAINT chk_auth_sessions_expiry CHECK ((expires_at > created_at))
);

--
-- Name: calibrations; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.calibrations (
    id bigint NOT NULL,
    job_id bigint NOT NULL,
    robot_id bigint NOT NULL,
    technician_id bigint NOT NULL,
    paper_type_id bigint,
    pen_type_id bigint,
    checklist jsonb,
    force_zero_offset numeric(8,4),
    probe_points jsonb NOT NULL,
    frame_transform jsonb,
    height_map jsonb,
    force_curve jsonb,
    is_valid boolean DEFAULT true NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL
);

--
-- Name: calibrations_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

ALTER TABLE public.calibrations ALTER COLUMN id ADD GENERATED ALWAYS AS IDENTITY (
    SEQUENCE NAME public.calibrations_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1
);

--
-- Name: handwriting_styles; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.handwriting_styles (
    id bigint NOT NULL,
    owner_id bigint NOT NULL,
    source_order_id bigint,
    name character varying(150) NOT NULL,
    glyph_set_uri text,
    coverage_pct numeric(5,2),
    status public.style_status DEFAULT 'PENDING_REVIEW'::public.style_status NOT NULL,
    right_to_use_confirmed boolean DEFAULT false NOT NULL,
    keep_consent boolean DEFAULT false NOT NULL,
    approved_by bigint,
    approved_at timestamp with time zone,
    delete_after timestamp with time zone,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL,
    CONSTRAINT handwriting_styles_coverage_pct_check CHECK (((coverage_pct >= (0)::numeric) AND (coverage_pct <= (100)::numeric)))
);

--
-- Name: handwriting_styles_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

ALTER TABLE public.handwriting_styles ALTER COLUMN id ADD GENERATED ALWAYS AS IDENTITY (
    SEQUENCE NAME public.handwriting_styles_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1
);

--
-- Name: incidents; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.incidents (
    id bigint NOT NULL,
    job_id bigint,
    robot_id bigint,
    reported_by bigint NOT NULL,
    type public.incident_type NOT NULL,
    description text NOT NULL,
    photo_urls text[] DEFAULT '{}'::text[] NOT NULL,
    robot_status_after public.robot_status,
    resolved_by bigint,
    resolved_at timestamp with time zone,
    resolution_note text,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    CONSTRAINT chk_incident_target CHECK (((job_id IS NOT NULL) OR (robot_id IS NOT NULL)))
);

--
-- Name: incidents_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

ALTER TABLE public.incidents ALTER COLUMN id ADD GENERATED ALWAYS AS IDENTITY (
    SEQUENCE NAME public.incidents_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1
);

--
-- Name: ink_colors; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.ink_colors (
    id bigint NOT NULL,
    pen_type_id bigint NOT NULL,
    name character varying(60) NOT NULL,
    hex_code character(7),
    unit_price numeric(14,0) DEFAULT 0 NOT NULL,
    stock_qty integer DEFAULT 0 NOT NULL,
    is_active boolean DEFAULT true NOT NULL,
    CONSTRAINT ink_colors_hex_code_check CHECK ((hex_code ~ '^#[0-9A-Fa-f]{6}$'::text)),
    CONSTRAINT ink_colors_stock_qty_check CHECK ((stock_qty >= 0)),
    CONSTRAINT ink_colors_unit_price_check CHECK ((unit_price >= (0)::numeric))
);

--
-- Name: ink_colors_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

ALTER TABLE public.ink_colors ALTER COLUMN id ADD GENERATED ALWAYS AS IDENTITY (
    SEQUENCE NAME public.ink_colors_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1
);

--
-- Name: job_events; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.job_events (
    id bigint NOT NULL,
    job_id bigint NOT NULL,
    event_type public.job_event_type NOT NULL,
    actor_id bigint,
    incident_id bigint,
    stroke_index integer,
    force_summary jsonb,
    payload jsonb,
    occurred_at timestamp with time zone DEFAULT now() NOT NULL
);

--
-- Name: job_events_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

ALTER TABLE public.job_events ALTER COLUMN id ADD GENERATED ALWAYS AS IDENTITY (
    SEQUENCE NAME public.job_events_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1
);

--
-- Name: messages; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.messages (
    id bigint NOT NULL,
    order_id bigint NOT NULL,
    sender_id bigint NOT NULL,
    body text,
    attachments jsonb DEFAULT '[]'::jsonb NOT NULL,
    read_at timestamp with time zone,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    kind character varying(20) DEFAULT 'TEXT'::character varying NOT NULL,
    CONSTRAINT chk_message_not_empty CHECK ((((kind)::text = 'ORDER_CARD'::text) OR (body IS NOT NULL) OR (jsonb_array_length(attachments) > 0))),
    CONSTRAINT chk_messages_kind CHECK (((kind)::text = ANY ((ARRAY['TEXT'::character varying, 'ORDER_CARD'::character varying])::text[])))
);

--
-- Name: messages_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

ALTER TABLE public.messages ALTER COLUMN id ADD GENERATED ALWAYS AS IDENTITY (
    SEQUENCE NAME public.messages_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1
);

--
-- Name: notifications; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.notifications (
    id bigint NOT NULL,
    account_id bigint NOT NULL,
    order_id bigint,
    type public.notification_type NOT NULL,
    msg_code character varying(10),
    title character varying(200) NOT NULL,
    body text NOT NULL,
    channel public.notification_channel NOT NULL,
    is_read boolean DEFAULT false NOT NULL,
    read_at timestamp with time zone,
    sent_at timestamp with time zone,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    CONSTRAINT chk_notification_read CHECK ((is_read = (read_at IS NOT NULL)))
);

--
-- Name: notifications_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

ALTER TABLE public.notifications ALTER COLUMN id ADD GENERATED ALWAYS AS IDENTITY (
    SEQUENCE NAME public.notifications_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1
);

--
-- Name: order_inputs; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.order_inputs (
    id bigint NOT NULL,
    order_id bigint NOT NULL,
    kind public.order_input_kind NOT NULL,
    sort_order smallint DEFAULT 0 NOT NULL,
    file_url text,
    mime_type character varying(50),
    file_size_bytes bigint,
    rotation_deg smallint DEFAULT 0,
    crop_box jsonb,
    quality_result jsonb,
    is_quality_warning boolean DEFAULT false NOT NULL,
    text_content text,
    template_id bigint,
    handwriting_style_id bigint,
    font_size_mm numeric(5,2),
    alignment character varying(10),
    layout jsonb,
    canvas_data jsonb,
    deleted_at timestamp with time zone,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL,
    CONSTRAINT chk_input_payload CHECK ((((kind = ANY (ARRAY['ORIGINAL_IMAGE'::public.order_input_kind, 'HANDWRITING_SAMPLE'::public.order_input_kind])) AND ((file_url IS NOT NULL) OR (deleted_at IS NOT NULL))) OR (kind = 'TEXT_CONTENT'::public.order_input_kind) OR ((kind = 'CANVAS'::public.order_input_kind) AND ((canvas_data IS NOT NULL) OR (deleted_at IS NOT NULL))))),
    CONSTRAINT order_inputs_alignment_check CHECK (((alignment)::text = ANY ((ARRAY['LEFT'::character varying, 'CENTER'::character varying, 'RIGHT'::character varying, 'JUSTIFY'::character varying])::text[]))),
    CONSTRAINT order_inputs_file_size_bytes_check CHECK (((file_size_bytes > 0) AND (file_size_bytes <= 20971520))),
    CONSTRAINT order_inputs_font_size_mm_check CHECK ((font_size_mm > (0)::numeric)),
    CONSTRAINT order_inputs_mime_type_check CHECK (((mime_type)::text = ANY ((ARRAY['image/jpeg'::character varying, 'image/png'::character varying, 'application/pdf'::character varying])::text[]))),
    CONSTRAINT order_inputs_rotation_deg_check CHECK ((rotation_deg = ANY (ARRAY[0, 90, 180, 270])))
);

--
-- Name: order_inputs_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

ALTER TABLE public.order_inputs ALTER COLUMN id ADD GENERATED ALWAYS AS IDENTITY (
    SEQUENCE NAME public.order_inputs_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1
);

--
-- Name: orders; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.orders (
    id bigint NOT NULL,
    code character varying(20) NOT NULL,
    customer_id bigint NOT NULL,
    order_type public.order_type NOT NULL,
    order_status public.order_status DEFAULT 'DRAFT'::public.order_status NOT NULL,
    production_status public.production_status DEFAULT 'NOT_STARTED'::public.production_status NOT NULL,
    paper_type_id bigint,
    pen_type_id bigint,
    ink_color_id bigint,
    workshop_suggest_materials boolean DEFAULT false NOT NULL,
    quantity integer DEFAULT 1 NOT NULL,
    char_count integer,
    complexity public.complexity_level,
    estimated_price_min numeric(14,0),
    estimated_price_max numeric(14,0),
    total_amount numeric(14,0),
    deposit_pct numeric(5,2),
    deposit_amount numeric(14,0),
    customer_note text,
    terms_accepted_at timestamp with time zone,
    assigned_staff_id bigint,
    assigned_by bigint,
    reject_reason public.reject_reason,
    reject_note text,
    info_request_note text,
    privacy_policy_version character varying(20),
    privacy_accepted_at timestamp with time zone,
    privacy_declined_at timestamp with time zone,
    keep_stroke_set boolean DEFAULT false NOT NULL,
    eta date,
    eta_postponed_days integer DEFAULT 0 NOT NULL,
    free_rewrite_used boolean DEFAULT false NOT NULL,
    delivery_method public.delivery_method,
    delivery_address jsonb,
    pickup_slot_start timestamp with time zone,
    pickup_slot_end timestamp with time zone,
    last_saved_at timestamp with time zone DEFAULT now() NOT NULL,
    submitted_at timestamp with time zone,
    confirmed_at timestamp with time zone,
    accepted_product_at timestamp with time zone,
    received_confirmed_at timestamp with time zone,
    completed_at timestamp with time zone,
    cancelled_at timestamp with time zone,
    cancel_reason text,
    inputs_purged_at timestamp with time zone,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL,
    awaiting_acceptance_at timestamp with time zone,
    acceptance_reminded_at timestamp with time zone,
    shipping_carrier public.carrier,
    shipping_service_code character varying(30),
    shipping_eta timestamp with time zone,
    CONSTRAINT chk_orders_estimate CHECK (((estimated_price_min IS NULL) OR (estimated_price_max IS NULL) OR (estimated_price_min <= estimated_price_max))),
    CONSTRAINT chk_orders_materials_after_submit CHECK (((order_status = ANY (ARRAY['DRAFT'::public.order_status, 'CANCELLED'::public.order_status])) OR workshop_suggest_materials OR ((paper_type_id IS NOT NULL) AND (pen_type_id IS NOT NULL) AND (ink_color_id IS NOT NULL)))),
    CONSTRAINT chk_orders_pickup_slot CHECK (((pickup_slot_end IS NULL) OR (pickup_slot_end > pickup_slot_start))),
    CONSTRAINT chk_orders_privacy_before_quote CHECK (((order_status <> ALL (ARRAY['QUOTED'::public.order_status, 'AWAITING_DEPOSIT'::public.order_status, 'CONFIRMED'::public.order_status, 'AWAITING_ACCEPTANCE'::public.order_status, 'AWAITING_FINAL_PAYMENT'::public.order_status, 'READY_TO_DELIVER'::public.order_status, 'DELIVERING'::public.order_status, 'COMPLETED'::public.order_status])) OR (privacy_accepted_at IS NOT NULL))),
    CONSTRAINT chk_orders_reject CHECK (((order_status <> 'REJECTED'::public.order_status) OR (reject_reason IS NOT NULL))),
    CONSTRAINT chk_orders_shipping_service CHECK (((shipping_carrier IS NULL) = (shipping_service_code IS NULL))),
    CONSTRAINT chk_orders_staff_after_accept CHECK (((order_status = ANY (ARRAY['DRAFT'::public.order_status, 'SUBMITTED'::public.order_status, 'NEED_INFO'::public.order_status, 'REJECTED'::public.order_status, 'CANCELLED'::public.order_status])) OR (assigned_staff_id IS NOT NULL))),
    CONSTRAINT orders_char_count_check CHECK ((char_count >= 0)),
    CONSTRAINT orders_deposit_amount_check CHECK ((deposit_amount >= (0)::numeric)),
    CONSTRAINT orders_deposit_pct_check CHECK (((deposit_pct > (0)::numeric) AND (deposit_pct <= (100)::numeric))),
    CONSTRAINT orders_estimated_price_max_check CHECK ((estimated_price_max >= (0)::numeric)),
    CONSTRAINT orders_estimated_price_min_check CHECK ((estimated_price_min >= (0)::numeric)),
    CONSTRAINT orders_eta_postponed_days_check CHECK ((eta_postponed_days >= 0)),
    CONSTRAINT orders_quantity_check CHECK ((quantity >= 1)),
    CONSTRAINT orders_total_amount_check CHECK ((total_amount >= (0)::numeric))
);

--
-- Name: orders_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

ALTER TABLE public.orders ALTER COLUMN id ADD GENERATED ALWAYS AS IDENTITY (
    SEQUENCE NAME public.orders_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1
);

--
-- Name: paper_pen_compats; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.paper_pen_compats (
    paper_type_id bigint NOT NULL,
    pen_type_id bigint NOT NULL,
    is_compatible boolean NOT NULL,
    note character varying(255),
    updated_by bigint,
    updated_at timestamp with time zone DEFAULT now() NOT NULL
);

--
-- Name: paper_types; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.paper_types (
    id bigint NOT NULL,
    code character varying(30) NOT NULL,
    name character varying(120) NOT NULL,
    gsm smallint NOT NULL,
    surface public.paper_surface NOT NULL,
    size public.paper_size NOT NULL,
    unit_price numeric(14,0) NOT NULL,
    stock_qty integer DEFAULT 0 NOT NULL,
    is_active boolean DEFAULT true NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL,
    CONSTRAINT paper_types_gsm_check CHECK ((gsm > 0)),
    CONSTRAINT paper_types_stock_qty_check CHECK ((stock_qty >= 0)),
    CONSTRAINT paper_types_unit_price_check CHECK ((unit_price >= (0)::numeric))
);

--
-- Name: paper_types_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

ALTER TABLE public.paper_types ALTER COLUMN id ADD GENERATED ALWAYS AS IDENTITY (
    SEQUENCE NAME public.paper_types_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1
);

--
-- Name: payments; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.payments (
    id bigint NOT NULL,
    order_id bigint NOT NULL,
    type public.payment_type NOT NULL,
    amount numeric(14,0) NOT NULL,
    deposit_pct numeric(5,2),
    gateway public.payment_gateway NOT NULL,
    gateway_txn_id character varying(100),
    status public.payment_status DEFAULT 'PENDING'::public.payment_status NOT NULL,
    refund_of_id bigint,
    refund_reason text,
    confirmed_by bigint,
    confirmed_at timestamp with time zone,
    invoice_url text,
    gateway_payload jsonb,
    paid_at timestamp with time zone,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL,
    CONSTRAINT chk_payment_deposit_pct CHECK (((type = 'DEPOSIT'::public.payment_type) OR (deposit_pct IS NULL))),
    CONSTRAINT chk_payment_refund_ref CHECK (((type = 'REFUND'::public.payment_type) = (refund_of_id IS NOT NULL))),
    CONSTRAINT payments_amount_check CHECK ((amount > (0)::numeric)),
    CONSTRAINT payments_deposit_pct_check CHECK (((deposit_pct > (0)::numeric) AND (deposit_pct <= (100)::numeric)))
);

--
-- Name: payments_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

ALTER TABLE public.payments ALTER COLUMN id ADD GENERATED ALWAYS AS IDENTITY (
    SEQUENCE NAME public.payments_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1
);

--
-- Name: pen_types; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.pen_types (
    id bigint NOT NULL,
    code character varying(30) NOT NULL,
    name character varying(120) NOT NULL,
    category public.pen_category NOT NULL,
    stroke_width_mm numeric(4,2) NOT NULL,
    f_target_n numeric(4,2) DEFAULT 1.0 NOT NULL,
    f_min_n numeric(4,2) NOT NULL,
    f_max_n numeric(4,2) NOT NULL,
    f_hard_n numeric(4,2) NOT NULL,
    v_max_mm_s numeric(5,1) NOT NULL,
    surcharge numeric(14,0) DEFAULT 0 NOT NULL,
    stock_qty integer DEFAULT 0 NOT NULL,
    is_active boolean DEFAULT true NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL,
    CONSTRAINT chk_pen_force_band CHECK (((f_min_n > (0)::numeric) AND (f_min_n < f_target_n) AND (f_target_n < f_max_n) AND (f_max_n < f_hard_n))),
    CONSTRAINT pen_types_f_target_n_check CHECK (((f_target_n >= 0.3) AND (f_target_n <= 2.0))),
    CONSTRAINT pen_types_stock_qty_check CHECK ((stock_qty >= 0)),
    CONSTRAINT pen_types_stroke_width_mm_check CHECK ((stroke_width_mm > (0)::numeric)),
    CONSTRAINT pen_types_surcharge_check CHECK ((surcharge >= (0)::numeric)),
    CONSTRAINT pen_types_v_max_mm_s_check CHECK ((v_max_mm_s > (0)::numeric))
);

--
-- Name: pen_types_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

ALTER TABLE public.pen_types ALTER COLUMN id ADD GENERATED ALWAYS AS IDENTITY (
    SEQUENCE NAME public.pen_types_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1
);

--
-- Name: phone_otps; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.phone_otps (
    id bigint NOT NULL,
    account_id bigint NOT NULL,
    phone character varying(20) NOT NULL,
    otp_hash character varying(255) NOT NULL,
    expires_at timestamp with time zone NOT NULL,
    attempt_count smallint DEFAULT 0 NOT NULL,
    max_attempts smallint DEFAULT 5 NOT NULL,
    used_at timestamp with time zone,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    CONSTRAINT chk_otp_attempts CHECK (((attempt_count >= 0) AND (attempt_count <= max_attempts))),
    CONSTRAINT chk_otp_expiry CHECK ((expires_at > created_at))
);

--
-- Name: phone_otps_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

ALTER TABLE public.phone_otps ALTER COLUMN id ADD GENERATED ALWAYS AS IDENTITY (
    SEQUENCE NAME public.phone_otps_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1
);

--
-- Name: pricing_configs; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.pricing_configs (
    id bigint NOT NULL,
    version integer NOT NULL,
    is_active boolean DEFAULT false NOT NULL,
    u_ot1 numeric(14,0) NOT NULL,
    u_ot2 numeric(14,0) NOT NULL,
    u_ot3 numeric(14,0) NOT NULL,
    w_min numeric(14,0) NOT NULL,
    s_ot1 numeric(14,0) NOT NULL,
    s_ot2 numeric(14,0) NOT NULL,
    s_ot3 numeric(14,0) NOT NULL,
    k_simple numeric(4,2) DEFAULT 1.0 NOT NULL,
    k_medium numeric(4,2) DEFAULT 1.3 NOT NULL,
    k_complex numeric(4,2) DEFAULT 1.6 NOT NULL,
    discount_tiers jsonb DEFAULT '[{"pct": 5, "min_qty": 10}, {"pct": 10, "min_qty": 50}, {"pct": 15, "min_qty": 100}]'::jsonb NOT NULL,
    p_min_pct numeric(5,2) DEFAULT 50 NOT NULL,
    adjust_threshold_pct numeric(5,2) DEFAULT 15 NOT NULL,
    canvas_mm_per_char numeric(6,2) DEFAULT 40 NOT NULL,
    note text,
    created_by bigint,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    CONSTRAINT chk_pricing_k CHECK (((k_simple > (0)::numeric) AND (k_simple <= k_medium) AND (k_medium <= k_complex))),
    CONSTRAINT chk_pricing_tiers CHECK ((jsonb_typeof(discount_tiers) = 'array'::text)),
    CONSTRAINT pricing_configs_adjust_threshold_pct_check CHECK ((adjust_threshold_pct >= (0)::numeric)),
    CONSTRAINT pricing_configs_p_min_pct_check CHECK (((p_min_pct > (0)::numeric) AND (p_min_pct <= (100)::numeric))),
    CONSTRAINT pricing_configs_s_ot1_check CHECK ((s_ot1 >= (0)::numeric)),
    CONSTRAINT pricing_configs_s_ot2_check CHECK ((s_ot2 >= (0)::numeric)),
    CONSTRAINT pricing_configs_s_ot3_check CHECK ((s_ot3 >= (0)::numeric)),
    CONSTRAINT pricing_configs_u_ot1_check CHECK ((u_ot1 >= (0)::numeric)),
    CONSTRAINT pricing_configs_u_ot2_check CHECK ((u_ot2 >= (0)::numeric)),
    CONSTRAINT pricing_configs_u_ot3_check CHECK ((u_ot3 >= (0)::numeric)),
    CONSTRAINT pricing_configs_w_min_check CHECK ((w_min >= (0)::numeric))
);

--
-- Name: pricing_configs_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

ALTER TABLE public.pricing_configs ALTER COLUMN id ADD GENERATED ALWAYS AS IDENTITY (
    SEQUENCE NAME public.pricing_configs_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1
);

--
-- Name: product_photos; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.product_photos (
    id bigint NOT NULL,
    order_id bigint NOT NULL,
    job_id bigint NOT NULL,
    uploaded_by bigint NOT NULL,
    kind public.photo_kind NOT NULL,
    url text NOT NULL,
    overlay_url text,
    qc_result public.qc_result,
    qc_note text,
    deleted_at timestamp with time zone,
    created_at timestamp with time zone DEFAULT now() NOT NULL
);

--
-- Name: product_photos_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

ALTER TABLE public.product_photos ALTER COLUMN id ADD GENERATED ALWAYS AS IDENTITY (
    SEQUENCE NAME public.product_photos_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1
);

--
-- Name: production_jobs; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.production_jobs (
    id bigint NOT NULL,
    order_id bigint NOT NULL,
    sketch_id bigint NOT NULL,
    robot_id bigint NOT NULL,
    technician_id bigint NOT NULL,
    scheduled_by bigint NOT NULL,
    status public.job_status DEFAULT 'SCHEDULED'::public.job_status NOT NULL,
    is_rewrite boolean DEFAULT false NOT NULL,
    slot_start timestamp with time zone NOT NULL,
    slot_end timestamp with time zone NOT NULL,
    estimated_duration_min integer NOT NULL,
    package_uri text,
    package_hash character(64),
    packaged_at timestamp with time zone,
    downloaded_at timestamp with time zone,
    simulation_passed boolean,
    simulation_report jsonb,
    progress_pct numeric(5,2) DEFAULT 0,
    started_at timestamp with time zone,
    finished_at timestamp with time zone,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL,
    CONSTRAINT chk_job_run_requires_sim CHECK (((status <> ALL (ARRAY['WRITING'::public.job_status, 'PAUSED'::public.job_status, 'WRITTEN'::public.job_status, 'PHOTO_UPLOADED'::public.job_status, 'DONE'::public.job_status])) OR (simulation_passed IS TRUE))),
    CONSTRAINT chk_job_slot CHECK ((slot_end > slot_start)),
    CONSTRAINT production_jobs_estimated_duration_min_check CHECK ((estimated_duration_min > 0)),
    CONSTRAINT production_jobs_progress_pct_check CHECK (((progress_pct >= (0)::numeric) AND (progress_pct <= (100)::numeric)))
);

--
-- Name: production_jobs_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

ALTER TABLE public.production_jobs ALTER COLUMN id ADD GENERATED ALWAYS AS IDENTITY (
    SEQUENCE NAME public.production_jobs_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1
);

--
-- Name: quotations; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.quotations (
    id bigint NOT NULL,
    order_id bigint NOT NULL,
    version integer NOT NULL,
    sketch_id bigint NOT NULL,
    pricing_config_id bigint NOT NULL,
    created_by bigint NOT NULL,
    status public.quotation_status DEFAULT 'DRAFT'::public.quotation_status NOT NULL,
    line_items jsonb NOT NULL,
    chosen_option smallint,
    char_count integer NOT NULL,
    quantity integer NOT NULL,
    complexity public.complexity_level NOT NULL,
    computed_total numeric(14,0) NOT NULL,
    adjusted_total numeric(14,0),
    adjustment_pct numeric(6,2) GENERATED ALWAYS AS (
CASE
    WHEN ((adjusted_total IS NULL) OR (computed_total = (0)::numeric)) THEN NULL::numeric
    ELSE round((((adjusted_total - computed_total) * 100.0) / computed_total), 2)
END) STORED,
    adjustment_reason text,
    adjustment_status public.adjustment_status DEFAULT 'NONE'::public.adjustment_status NOT NULL,
    approved_by bigint,
    approved_at timestamp with time zone,
    final_total numeric(14,0) GENERATED ALWAYS AS (COALESCE(adjusted_total, computed_total)) STORED,
    min_deposit_pct numeric(5,2) NOT NULL,
    price_snapshot jsonb NOT NULL,
    eta date,
    file_url text,
    sent_at timestamp with time zone,
    valid_until timestamp with time zone,
    customer_responded_at timestamp with time zone,
    customer_note text,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    CONSTRAINT chk_quote_adjust_reason CHECK (((adjusted_total IS NULL) OR (adjustment_reason IS NOT NULL))),
    CONSTRAINT chk_quote_sent_validity CHECK (((sent_at IS NULL) OR (valid_until > sent_at))),
    CONSTRAINT quotations_adjusted_total_check CHECK ((adjusted_total >= (0)::numeric)),
    CONSTRAINT quotations_char_count_check CHECK ((char_count >= 0)),
    CONSTRAINT quotations_computed_total_check CHECK ((computed_total >= (0)::numeric)),
    CONSTRAINT quotations_line_items_check CHECK ((jsonb_typeof(line_items) = 'array'::text)),
    CONSTRAINT quotations_min_deposit_pct_check CHECK (((min_deposit_pct > (0)::numeric) AND (min_deposit_pct <= (100)::numeric))),
    CONSTRAINT quotations_quantity_check CHECK ((quantity >= 1)),
    CONSTRAINT quotations_version_check CHECK ((version >= 1))
);

--
-- Name: quotations_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

ALTER TABLE public.quotations ALTER COLUMN id ADD GENERATED ALWAYS AS IDENTITY (
    SEQUENCE NAME public.quotations_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1
);

--
-- Name: review_photos; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.review_photos (
    id bigint NOT NULL,
    review_id bigint NOT NULL,
    url text NOT NULL,
    sort_order smallint DEFAULT 0 NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL
);

--
-- Name: review_photos_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

ALTER TABLE public.review_photos ALTER COLUMN id ADD GENERATED ALWAYS AS IDENTITY (
    SEQUENCE NAME public.review_photos_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1
);

--
-- Name: reviews; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.reviews (
    id bigint NOT NULL,
    order_id bigint NOT NULL,
    customer_id bigint NOT NULL,
    rating smallint NOT NULL,
    comment text,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL,
    CONSTRAINT reviews_rating_check CHECK (((rating >= 1) AND (rating <= 5)))
);

--
-- Name: reviews_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

ALTER TABLE public.reviews ALTER COLUMN id ADD GENERATED ALWAYS AS IDENTITY (
    SEQUENCE NAME public.reviews_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1
);

--
-- Name: robots; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.robots (
    id bigint NOT NULL,
    code character varying(30) NOT NULL,
    robot_type character varying(50) DEFAULT 'FAIRINO_FR3'::character varying NOT NULL,
    station character varying(50),
    status public.robot_status DEFAULT 'AVAILABLE'::public.robot_status NOT NULL,
    is_simulated boolean DEFAULT false NOT NULL,
    supported_pen_categories public.pen_category[],
    note text,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL
);

--
-- Name: robots_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

ALTER TABLE public.robots ALTER COLUMN id ADD GENERATED ALWAYS AS IDENTITY (
    SEQUENCE NAME public.robots_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1
);

--
-- Name: roles; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.roles (
    id smallint NOT NULL,
    code character varying(30) NOT NULL,
    name character varying(100) NOT NULL,
    description text
);

--
-- Name: shipments; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.shipments (
    id bigint NOT NULL,
    order_id bigint NOT NULL,
    carrier public.carrier NOT NULL,
    service_code character varying(30),
    waybill_code character varying(60),
    fee numeric(14,0) NOT NULL,
    is_fallback_fee boolean DEFAULT false NOT NULL,
    package_type character varying(20),
    weight_g integer,
    to_address jsonb NOT NULL,
    status public.shipment_status DEFAULT 'CREATED'::public.shipment_status NOT NULL,
    carrier_status_raw character varying(60),
    label_url text,
    created_by bigint,
    picked_up_at timestamp with time zone,
    delivered_at timestamp with time zone,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL,
    CONSTRAINT shipments_fee_check CHECK ((fee >= (0)::numeric)),
    CONSTRAINT shipments_package_type_check CHECK (((package_type)::text = ANY ((ARRAY['FLAT_BOX_A5'::character varying, 'FLAT_BOX_A4'::character varying, 'TUBE'::character varying])::text[]))),
    CONSTRAINT shipments_weight_g_check CHECK ((weight_g > 0))
);

--
-- Name: shipments_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

ALTER TABLE public.shipments ALTER COLUMN id ADD GENERATED ALWAYS AS IDENTITY (
    SEQUENCE NAME public.shipments_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1
);

--
-- Name: showcase_posts; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.showcase_posts (
    id bigint NOT NULL,
    image_url text NOT NULL,
    title character varying(200) NOT NULL,
    description text,
    order_type public.order_type,
    posted_by bigint NOT NULL,
    is_visible boolean DEFAULT true NOT NULL,
    sort_order integer DEFAULT 0 NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL
);

--
-- Name: showcase_posts_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

ALTER TABLE public.showcase_posts ALTER COLUMN id ADD GENERATED ALWAYS AS IDENTITY (
    SEQUENCE NAME public.showcase_posts_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1
);

--
-- Name: sketches; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.sketches (
    id bigint NOT NULL,
    order_id bigint NOT NULL,
    version integer NOT NULL,
    created_by bigint NOT NULL,
    trajectory_uri text NOT NULL,
    preview_url text,
    similarity_score numeric(5,2),
    suggested_complexity public.complexity_level,
    estimated_writing_sec integer,
    total_stroke_mm numeric(12,2),
    pen_lift_count integer,
    approach_note text,
    content_hash character(64),
    is_final boolean DEFAULT false NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    CONSTRAINT sketches_estimated_writing_sec_check CHECK ((estimated_writing_sec >= 0)),
    CONSTRAINT sketches_pen_lift_count_check CHECK ((pen_lift_count >= 0)),
    CONSTRAINT sketches_similarity_score_check CHECK (((similarity_score >= (0)::numeric) AND (similarity_score <= (100)::numeric))),
    CONSTRAINT sketches_total_stroke_mm_check CHECK ((total_stroke_mm >= (0)::numeric)),
    CONSTRAINT sketches_version_check CHECK ((version >= 1))
);

--
-- Name: sketches_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

ALTER TABLE public.sketches ALTER COLUMN id ADD GENERATED ALWAYS AS IDENTITY (
    SEQUENCE NAME public.sketches_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1
);

--
-- Name: status_histories; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.status_histories (
    id bigint NOT NULL,
    order_id bigint NOT NULL,
    job_id bigint,
    state_type public.state_type NOT NULL,
    from_status character varying(30),
    to_status character varying(30),
    old_eta date,
    new_eta date,
    reason text,
    actor_id bigint,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    CONSTRAINT chk_history_payload CHECK ((((state_type = 'ETA'::public.state_type) AND (new_eta IS NOT NULL) AND (reason IS NOT NULL)) OR ((state_type <> 'ETA'::public.state_type) AND (to_status IS NOT NULL))))
);

--
-- Name: status_histories_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

ALTER TABLE public.status_histories ALTER COLUMN id ADD GENERATED ALWAYS AS IDENTITY (
    SEQUENCE NAME public.status_histories_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1
);

--
-- Name: system_settings; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.system_settings (
    key character varying(60) NOT NULL,
    value jsonb NOT NULL,
    description text,
    updated_by bigint,
    updated_at timestamp with time zone DEFAULT now() NOT NULL
);

--
-- Name: templates; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.templates (
    id bigint NOT NULL,
    code character varying(40) NOT NULL,
    name character varying(150) NOT NULL,
    kind public.template_kind NOT NULL,
    font_uri text NOT NULL,
    preview_url text,
    is_active boolean DEFAULT true NOT NULL,
    created_by bigint,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL
);

--
-- Name: templates_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

ALTER TABLE public.templates ALTER COLUMN id ADD GENERATED ALWAYS AS IDENTITY (
    SEQUENCE NAME public.templates_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1
);

--
-- Name: v_customer_drafts; Type: VIEW; Schema: public; Owner: -
--

CREATE VIEW public.v_customer_drafts AS
SELECT
    NULL::bigint AS id,
    NULL::character varying(20) AS code,
    NULL::bigint AS customer_id,
    NULL::public.order_type AS order_type,
    NULL::integer AS quantity,
    NULL::bigint AS paper_type_id,
    NULL::bigint AS pen_type_id,
    NULL::bigint AS ink_color_id,
    NULL::timestamp with time zone AS last_saved_at,
    NULL::bigint AS input_count;

--
-- Name: v_order_eta_postponement; Type: VIEW; Schema: public; Owner: -
--

CREATE VIEW public.v_order_eta_postponement AS
 SELECT order_id,
    sum(GREATEST((new_eta - old_eta), 0)) AS total_postponed_days,
    (sum(GREATEST((new_eta - old_eta), 0)) > 7) AS can_cancel_full_refund
   FROM public.status_histories
  WHERE ((state_type = 'ETA'::public.state_type) AND (old_eta IS NOT NULL))
  GROUP BY order_id;

--
-- Name: accounts accounts_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.accounts
    ADD CONSTRAINT accounts_pkey PRIMARY KEY (id);

--
-- Name: alembic_version alembic_version_pkc; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.alembic_version
    ADD CONSTRAINT alembic_version_pkc PRIMARY KEY (version_num);

--
-- Name: audit_logs audit_logs_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.audit_logs
    ADD CONSTRAINT audit_logs_pkey PRIMARY KEY (id);

--
-- Name: auth_sessions auth_sessions_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.auth_sessions
    ADD CONSTRAINT auth_sessions_pkey PRIMARY KEY (id);

--
-- Name: calibrations calibrations_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.calibrations
    ADD CONSTRAINT calibrations_pkey PRIMARY KEY (id);

--
-- Name: production_jobs ex_job_robot_overlap; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.production_jobs
    ADD CONSTRAINT ex_job_robot_overlap EXCLUDE USING gist (robot_id WITH =, tstzrange(slot_start, slot_end) WITH &&) WHERE ((status = ANY (ARRAY['SCHEDULED'::public.job_status, 'PREPARING'::public.job_status, 'WRITING'::public.job_status, 'PAUSED'::public.job_status])));

--
-- Name: handwriting_styles handwriting_styles_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.handwriting_styles
    ADD CONSTRAINT handwriting_styles_pkey PRIMARY KEY (id);

--
-- Name: incidents incidents_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.incidents
    ADD CONSTRAINT incidents_pkey PRIMARY KEY (id);

--
-- Name: ink_colors ink_colors_id_pen_type_id_key; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.ink_colors
    ADD CONSTRAINT ink_colors_id_pen_type_id_key UNIQUE (id, pen_type_id);

--
-- Name: ink_colors ink_colors_pen_type_id_name_key; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.ink_colors
    ADD CONSTRAINT ink_colors_pen_type_id_name_key UNIQUE (pen_type_id, name);

--
-- Name: ink_colors ink_colors_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.ink_colors
    ADD CONSTRAINT ink_colors_pkey PRIMARY KEY (id);

--
-- Name: job_events job_events_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.job_events
    ADD CONSTRAINT job_events_pkey PRIMARY KEY (id);

--
-- Name: messages messages_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.messages
    ADD CONSTRAINT messages_pkey PRIMARY KEY (id);

--
-- Name: notifications notifications_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.notifications
    ADD CONSTRAINT notifications_pkey PRIMARY KEY (id);

--
-- Name: order_inputs order_inputs_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.order_inputs
    ADD CONSTRAINT order_inputs_pkey PRIMARY KEY (id);

--
-- Name: orders orders_code_key; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.orders
    ADD CONSTRAINT orders_code_key UNIQUE (code);

--
-- Name: orders orders_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.orders
    ADD CONSTRAINT orders_pkey PRIMARY KEY (id);

--
-- Name: paper_pen_compats paper_pen_compats_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.paper_pen_compats
    ADD CONSTRAINT paper_pen_compats_pkey PRIMARY KEY (paper_type_id, pen_type_id);

--
-- Name: paper_types paper_types_code_key; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.paper_types
    ADD CONSTRAINT paper_types_code_key UNIQUE (code);

--
-- Name: paper_types paper_types_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.paper_types
    ADD CONSTRAINT paper_types_pkey PRIMARY KEY (id);

--
-- Name: payments payments_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.payments
    ADD CONSTRAINT payments_pkey PRIMARY KEY (id);

--
-- Name: pen_types pen_types_code_key; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.pen_types
    ADD CONSTRAINT pen_types_code_key UNIQUE (code);

--
-- Name: pen_types pen_types_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.pen_types
    ADD CONSTRAINT pen_types_pkey PRIMARY KEY (id);

--
-- Name: phone_otps phone_otps_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.phone_otps
    ADD CONSTRAINT phone_otps_pkey PRIMARY KEY (id);

--
-- Name: pricing_configs pricing_configs_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.pricing_configs
    ADD CONSTRAINT pricing_configs_pkey PRIMARY KEY (id);

--
-- Name: pricing_configs pricing_configs_version_key; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.pricing_configs
    ADD CONSTRAINT pricing_configs_version_key UNIQUE (version);

--
-- Name: product_photos product_photos_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.product_photos
    ADD CONSTRAINT product_photos_pkey PRIMARY KEY (id);

--
-- Name: production_jobs production_jobs_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.production_jobs
    ADD CONSTRAINT production_jobs_pkey PRIMARY KEY (id);

--
-- Name: quotations quotations_order_id_version_key; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.quotations
    ADD CONSTRAINT quotations_order_id_version_key UNIQUE (order_id, version);

--
-- Name: quotations quotations_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.quotations
    ADD CONSTRAINT quotations_pkey PRIMARY KEY (id);

--
-- Name: review_photos review_photos_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.review_photos
    ADD CONSTRAINT review_photos_pkey PRIMARY KEY (id);

--
-- Name: reviews reviews_order_id_key; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.reviews
    ADD CONSTRAINT reviews_order_id_key UNIQUE (order_id);

--
-- Name: reviews reviews_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.reviews
    ADD CONSTRAINT reviews_pkey PRIMARY KEY (id);

--
-- Name: robots robots_code_key; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.robots
    ADD CONSTRAINT robots_code_key UNIQUE (code);

--
-- Name: robots robots_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.robots
    ADD CONSTRAINT robots_pkey PRIMARY KEY (id);

--
-- Name: roles roles_code_key; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.roles
    ADD CONSTRAINT roles_code_key UNIQUE (code);

--
-- Name: roles roles_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.roles
    ADD CONSTRAINT roles_pkey PRIMARY KEY (id);

--
-- Name: shipments shipments_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.shipments
    ADD CONSTRAINT shipments_pkey PRIMARY KEY (id);

--
-- Name: showcase_posts showcase_posts_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.showcase_posts
    ADD CONSTRAINT showcase_posts_pkey PRIMARY KEY (id);

--
-- Name: sketches sketches_order_id_version_key; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.sketches
    ADD CONSTRAINT sketches_order_id_version_key UNIQUE (order_id, version);

--
-- Name: sketches sketches_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.sketches
    ADD CONSTRAINT sketches_pkey PRIMARY KEY (id);

--
-- Name: status_histories status_histories_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.status_histories
    ADD CONSTRAINT status_histories_pkey PRIMARY KEY (id);

--
-- Name: system_settings system_settings_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.system_settings
    ADD CONSTRAINT system_settings_pkey PRIMARY KEY (key);

--
-- Name: templates templates_code_key; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.templates
    ADD CONSTRAINT templates_code_key UNIQUE (code);

--
-- Name: templates templates_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.templates
    ADD CONSTRAINT templates_pkey PRIMARY KEY (id);

--
-- Name: ix_accounts_role; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_accounts_role ON public.accounts USING btree (role_id);

--
-- Name: ix_audit_logs_actor; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_audit_logs_actor ON public.audit_logs USING btree (actor_id, created_at DESC);

--
-- Name: ix_audit_logs_entity; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_audit_logs_entity ON public.audit_logs USING btree (entity_type, entity_id);

--
-- Name: ix_audit_logs_time; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_audit_logs_time ON public.audit_logs USING btree (created_at DESC);

--
-- Name: ix_auth_sessions_account; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_auth_sessions_account ON public.auth_sessions USING btree (account_id) WHERE (revoked_at IS NULL);

--
-- Name: ix_auth_sessions_expiry; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_auth_sessions_expiry ON public.auth_sessions USING btree (expires_at);

--
-- Name: ix_calibrations_job; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_calibrations_job ON public.calibrations USING btree (job_id, created_at DESC);

--
-- Name: ix_incidents_open; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_incidents_open ON public.incidents USING btree (created_at) WHERE (resolved_at IS NULL);

--
-- Name: ix_incidents_robot; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_incidents_robot ON public.incidents USING btree (robot_id, created_at DESC);

--
-- Name: ix_job_events_job; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_job_events_job ON public.job_events USING btree (job_id, occurred_at);

--
-- Name: ix_jobs_order; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_jobs_order ON public.production_jobs USING btree (order_id);

--
-- Name: ix_jobs_robot; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_jobs_robot ON public.production_jobs USING btree (robot_id, slot_start);

--
-- Name: ix_jobs_technician; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_jobs_technician ON public.production_jobs USING btree (technician_id, slot_start);

--
-- Name: ix_messages_order; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_messages_order ON public.messages USING btree (order_id, created_at);

--
-- Name: ix_messages_unread; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_messages_unread ON public.messages USING btree (order_id) WHERE (read_at IS NULL);

--
-- Name: ix_notifications_account; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_notifications_account ON public.notifications USING btree (account_id, created_at DESC);

--
-- Name: ix_notifications_unread; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_notifications_unread ON public.notifications USING btree (account_id, created_at DESC) WHERE ((channel = 'IN_APP'::public.notification_channel) AND (NOT is_read));

--
-- Name: ix_order_inputs_order; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_order_inputs_order ON public.order_inputs USING btree (order_id, kind, sort_order);

--
-- Name: ix_orders_customer; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_orders_customer ON public.orders USING btree (customer_id, created_at DESC);

--
-- Name: ix_orders_drafts; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_orders_drafts ON public.orders USING btree (customer_id, last_saved_at DESC) WHERE (order_status = 'DRAFT'::public.order_status);

--
-- Name: ix_orders_eta; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_orders_eta ON public.orders USING btree (eta) WHERE (order_status <> ALL (ARRAY['COMPLETED'::public.order_status, 'CANCELLED'::public.order_status, 'REJECTED'::public.order_status]));

--
-- Name: ix_orders_staff; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_orders_staff ON public.orders USING btree (assigned_staff_id) WHERE (assigned_staff_id IS NOT NULL);

--
-- Name: ix_orders_status; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_orders_status ON public.orders USING btree (order_status, production_status);

--
-- Name: ix_payments_order; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_payments_order ON public.payments USING btree (order_id, created_at);

--
-- Name: ix_phone_otps_lookup; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_phone_otps_lookup ON public.phone_otps USING btree (phone, created_at DESC) WHERE (used_at IS NULL);

--
-- Name: ix_product_photos_job; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_product_photos_job ON public.product_photos USING btree (job_id);

--
-- Name: ix_product_photos_order; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_product_photos_order ON public.product_photos USING btree (order_id);

--
-- Name: ix_quotations_expiring; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_quotations_expiring ON public.quotations USING btree (valid_until) WHERE (status = 'SENT'::public.quotation_status);

--
-- Name: ix_quotations_order; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_quotations_order ON public.quotations USING btree (order_id, version DESC);

--
-- Name: ix_quotations_pending_approval; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_quotations_pending_approval ON public.quotations USING btree (created_at) WHERE (adjustment_status = 'PENDING_MANAGER'::public.adjustment_status);

--
-- Name: ix_review_photos_review; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_review_photos_review ON public.review_photos USING btree (review_id, sort_order);

--
-- Name: ix_shipments_order; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_shipments_order ON public.shipments USING btree (order_id);

--
-- Name: ix_showcase_visible; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_showcase_visible ON public.showcase_posts USING btree (sort_order, created_at DESC) WHERE is_visible;

--
-- Name: ix_status_histories_order; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_status_histories_order ON public.status_histories USING btree (order_id, created_at);

--
-- Name: ix_styles_owner; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_styles_owner ON public.handwriting_styles USING btree (owner_id);

--
-- Name: ux_accounts_email; Type: INDEX; Schema: public; Owner: -
--

CREATE UNIQUE INDEX ux_accounts_email ON public.accounts USING btree (lower((email)::text));

--
-- Name: ux_accounts_verified_phone; Type: INDEX; Schema: public; Owner: -
--

CREATE UNIQUE INDEX ux_accounts_verified_phone ON public.accounts USING btree (phone) WHERE (phone_verified_at IS NOT NULL);

--
-- Name: ux_jobs_one_active_per_order; Type: INDEX; Schema: public; Owner: -
--

CREATE UNIQUE INDEX ux_jobs_one_active_per_order ON public.production_jobs USING btree (order_id) WHERE (status = ANY (ARRAY['SCHEDULED'::public.job_status, 'PREPARING'::public.job_status, 'WRITING'::public.job_status, 'PAUSED'::public.job_status, 'WRITTEN'::public.job_status]));

--
-- Name: ux_payments_gateway_txn; Type: INDEX; Schema: public; Owner: -
--

CREATE UNIQUE INDEX ux_payments_gateway_txn ON public.payments USING btree (gateway, gateway_txn_id) WHERE (gateway_txn_id IS NOT NULL);

--
-- Name: ux_payments_one_success_per_type; Type: INDEX; Schema: public; Owner: -
--

CREATE UNIQUE INDEX ux_payments_one_success_per_type ON public.payments USING btree (order_id, type) WHERE ((status = 'SUCCESS'::public.payment_status) AND (type = ANY (ARRAY['DEPOSIT'::public.payment_type, 'FINAL'::public.payment_type, 'SHIPPING'::public.payment_type])));

--
-- Name: ux_pricing_configs_one_active; Type: INDEX; Schema: public; Owner: -
--

CREATE UNIQUE INDEX ux_pricing_configs_one_active ON public.pricing_configs USING btree (is_active) WHERE is_active;

--
-- Name: ux_quotations_one_live; Type: INDEX; Schema: public; Owner: -
--

CREATE UNIQUE INDEX ux_quotations_one_live ON public.quotations USING btree (order_id) WHERE (status = ANY (ARRAY['DRAFT'::public.quotation_status, 'PENDING_APPROVAL'::public.quotation_status, 'SENT'::public.quotation_status]));

--
-- Name: ux_shipments_waybill; Type: INDEX; Schema: public; Owner: -
--

CREATE UNIQUE INDEX ux_shipments_waybill ON public.shipments USING btree (carrier, waybill_code) WHERE (waybill_code IS NOT NULL);

--
-- Name: ux_sketches_one_final; Type: INDEX; Schema: public; Owner: -
--

CREATE UNIQUE INDEX ux_sketches_one_final ON public.sketches USING btree (order_id) WHERE is_final;

--
-- Name: v_customer_drafts _RETURN; Type: RULE; Schema: public; Owner: -
--

CREATE OR REPLACE VIEW public.v_customer_drafts AS
 SELECT o.id,
    o.code,
    o.customer_id,
    o.order_type,
    o.quantity,
    o.paper_type_id,
    o.pen_type_id,
    o.ink_color_id,
    o.last_saved_at,
    count(i.id) AS input_count
   FROM (public.orders o
     LEFT JOIN public.order_inputs i ON (((i.order_id = o.id) AND (i.deleted_at IS NULL))))
  WHERE (o.order_status = 'DRAFT'::public.order_status)
  GROUP BY o.id;

--
-- Name: accounts trg_accounts_updated_at; Type: TRIGGER; Schema: public; Owner: -
--

CREATE TRIGGER trg_accounts_updated_at BEFORE UPDATE ON public.accounts FOR EACH ROW EXECUTE FUNCTION public.fn_set_updated_at();

--
-- Name: handwriting_styles trg_handwriting_styles_updated_at; Type: TRIGGER; Schema: public; Owner: -
--

CREATE TRIGGER trg_handwriting_styles_updated_at BEFORE UPDATE ON public.handwriting_styles FOR EACH ROW EXECUTE FUNCTION public.fn_set_updated_at();

--
-- Name: order_inputs trg_order_inputs_updated_at; Type: TRIGGER; Schema: public; Owner: -
--

CREATE TRIGGER trg_order_inputs_updated_at BEFORE UPDATE ON public.order_inputs FOR EACH ROW EXECUTE FUNCTION public.fn_set_updated_at();

--
-- Name: orders trg_orders_photo_guard; Type: TRIGGER; Schema: public; Owner: -
--

CREATE TRIGGER trg_orders_photo_guard BEFORE UPDATE OF production_status ON public.orders FOR EACH ROW EXECUTE FUNCTION public.fn_photo_uploaded_guard();

--
-- Name: orders trg_orders_state_guard; Type: TRIGGER; Schema: public; Owner: -
--

CREATE TRIGGER trg_orders_state_guard BEFORE INSERT OR UPDATE ON public.orders FOR EACH ROW EXECUTE FUNCTION public.fn_order_state_guard();

--
-- Name: orders trg_orders_status_history; Type: TRIGGER; Schema: public; Owner: -
--

CREATE TRIGGER trg_orders_status_history AFTER INSERT OR UPDATE ON public.orders FOR EACH ROW EXECUTE FUNCTION public.fn_order_status_history();

--
-- Name: orders trg_orders_updated_at; Type: TRIGGER; Schema: public; Owner: -
--

CREATE TRIGGER trg_orders_updated_at BEFORE UPDATE ON public.orders FOR EACH ROW EXECUTE FUNCTION public.fn_set_updated_at();

--
-- Name: paper_types trg_paper_types_updated_at; Type: TRIGGER; Schema: public; Owner: -
--

CREATE TRIGGER trg_paper_types_updated_at BEFORE UPDATE ON public.paper_types FOR EACH ROW EXECUTE FUNCTION public.fn_set_updated_at();

--
-- Name: payments trg_payments_updated_at; Type: TRIGGER; Schema: public; Owner: -
--

CREATE TRIGGER trg_payments_updated_at BEFORE UPDATE ON public.payments FOR EACH ROW EXECUTE FUNCTION public.fn_set_updated_at();

--
-- Name: pen_types trg_pen_types_updated_at; Type: TRIGGER; Schema: public; Owner: -
--

CREATE TRIGGER trg_pen_types_updated_at BEFORE UPDATE ON public.pen_types FOR EACH ROW EXECUTE FUNCTION public.fn_set_updated_at();

--
-- Name: production_jobs trg_production_jobs_updated_at; Type: TRIGGER; Schema: public; Owner: -
--

CREATE TRIGGER trg_production_jobs_updated_at BEFORE UPDATE ON public.production_jobs FOR EACH ROW EXECUTE FUNCTION public.fn_set_updated_at();

--
-- Name: reviews trg_reviews_guard; Type: TRIGGER; Schema: public; Owner: -
--

CREATE TRIGGER trg_reviews_guard BEFORE INSERT OR UPDATE OF order_id, customer_id ON public.reviews FOR EACH ROW EXECUTE FUNCTION public.fn_review_guard();

--
-- Name: reviews trg_reviews_updated_at; Type: TRIGGER; Schema: public; Owner: -
--

CREATE TRIGGER trg_reviews_updated_at BEFORE UPDATE ON public.reviews FOR EACH ROW EXECUTE FUNCTION public.fn_set_updated_at();

--
-- Name: robots trg_robots_updated_at; Type: TRIGGER; Schema: public; Owner: -
--

CREATE TRIGGER trg_robots_updated_at BEFORE UPDATE ON public.robots FOR EACH ROW EXECUTE FUNCTION public.fn_set_updated_at();

--
-- Name: shipments trg_shipments_updated_at; Type: TRIGGER; Schema: public; Owner: -
--

CREATE TRIGGER trg_shipments_updated_at BEFORE UPDATE ON public.shipments FOR EACH ROW EXECUTE FUNCTION public.fn_set_updated_at();

--
-- Name: showcase_posts trg_showcase_posts_updated_at; Type: TRIGGER; Schema: public; Owner: -
--

CREATE TRIGGER trg_showcase_posts_updated_at BEFORE UPDATE ON public.showcase_posts FOR EACH ROW EXECUTE FUNCTION public.fn_set_updated_at();

--
-- Name: templates trg_templates_updated_at; Type: TRIGGER; Schema: public; Owner: -
--

CREATE TRIGGER trg_templates_updated_at BEFORE UPDATE ON public.templates FOR EACH ROW EXECUTE FUNCTION public.fn_set_updated_at();

--
-- Name: accounts accounts_created_by_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.accounts
    ADD CONSTRAINT accounts_created_by_fkey FOREIGN KEY (created_by) REFERENCES public.accounts(id);

--
-- Name: accounts accounts_role_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.accounts
    ADD CONSTRAINT accounts_role_id_fkey FOREIGN KEY (role_id) REFERENCES public.roles(id);

--
-- Name: audit_logs audit_logs_actor_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.audit_logs
    ADD CONSTRAINT audit_logs_actor_id_fkey FOREIGN KEY (actor_id) REFERENCES public.accounts(id);

--
-- Name: auth_sessions auth_sessions_account_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.auth_sessions
    ADD CONSTRAINT auth_sessions_account_id_fkey FOREIGN KEY (account_id) REFERENCES public.accounts(id) ON DELETE CASCADE;

--
-- Name: calibrations calibrations_job_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.calibrations
    ADD CONSTRAINT calibrations_job_id_fkey FOREIGN KEY (job_id) REFERENCES public.production_jobs(id) ON DELETE CASCADE;

--
-- Name: calibrations calibrations_paper_type_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.calibrations
    ADD CONSTRAINT calibrations_paper_type_id_fkey FOREIGN KEY (paper_type_id) REFERENCES public.paper_types(id);

--
-- Name: calibrations calibrations_pen_type_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.calibrations
    ADD CONSTRAINT calibrations_pen_type_id_fkey FOREIGN KEY (pen_type_id) REFERENCES public.pen_types(id);

--
-- Name: calibrations calibrations_robot_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.calibrations
    ADD CONSTRAINT calibrations_robot_id_fkey FOREIGN KEY (robot_id) REFERENCES public.robots(id);

--
-- Name: calibrations calibrations_technician_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.calibrations
    ADD CONSTRAINT calibrations_technician_id_fkey FOREIGN KEY (technician_id) REFERENCES public.accounts(id);

--
-- Name: orders fk_orders_ink_of_pen; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.orders
    ADD CONSTRAINT fk_orders_ink_of_pen FOREIGN KEY (ink_color_id, pen_type_id) REFERENCES public.ink_colors(id, pen_type_id);

--
-- Name: status_histories fk_status_histories_job; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.status_histories
    ADD CONSTRAINT fk_status_histories_job FOREIGN KEY (job_id) REFERENCES public.production_jobs(id) ON DELETE SET NULL;

--
-- Name: handwriting_styles handwriting_styles_approved_by_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.handwriting_styles
    ADD CONSTRAINT handwriting_styles_approved_by_fkey FOREIGN KEY (approved_by) REFERENCES public.accounts(id);

--
-- Name: handwriting_styles handwriting_styles_owner_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.handwriting_styles
    ADD CONSTRAINT handwriting_styles_owner_id_fkey FOREIGN KEY (owner_id) REFERENCES public.accounts(id);

--
-- Name: handwriting_styles handwriting_styles_source_order_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.handwriting_styles
    ADD CONSTRAINT handwriting_styles_source_order_id_fkey FOREIGN KEY (source_order_id) REFERENCES public.orders(id) ON DELETE SET NULL;

--
-- Name: incidents incidents_job_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.incidents
    ADD CONSTRAINT incidents_job_id_fkey FOREIGN KEY (job_id) REFERENCES public.production_jobs(id) ON DELETE SET NULL;

--
-- Name: incidents incidents_reported_by_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.incidents
    ADD CONSTRAINT incidents_reported_by_fkey FOREIGN KEY (reported_by) REFERENCES public.accounts(id);

--
-- Name: incidents incidents_resolved_by_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.incidents
    ADD CONSTRAINT incidents_resolved_by_fkey FOREIGN KEY (resolved_by) REFERENCES public.accounts(id);

--
-- Name: incidents incidents_robot_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.incidents
    ADD CONSTRAINT incidents_robot_id_fkey FOREIGN KEY (robot_id) REFERENCES public.robots(id);

--
-- Name: ink_colors ink_colors_pen_type_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.ink_colors
    ADD CONSTRAINT ink_colors_pen_type_id_fkey FOREIGN KEY (pen_type_id) REFERENCES public.pen_types(id) ON DELETE CASCADE;

--
-- Name: job_events job_events_actor_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.job_events
    ADD CONSTRAINT job_events_actor_id_fkey FOREIGN KEY (actor_id) REFERENCES public.accounts(id);

--
-- Name: job_events job_events_incident_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.job_events
    ADD CONSTRAINT job_events_incident_id_fkey FOREIGN KEY (incident_id) REFERENCES public.incidents(id);

--
-- Name: job_events job_events_job_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.job_events
    ADD CONSTRAINT job_events_job_id_fkey FOREIGN KEY (job_id) REFERENCES public.production_jobs(id) ON DELETE CASCADE;

--
-- Name: messages messages_order_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.messages
    ADD CONSTRAINT messages_order_id_fkey FOREIGN KEY (order_id) REFERENCES public.orders(id) ON DELETE CASCADE;

--
-- Name: messages messages_sender_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.messages
    ADD CONSTRAINT messages_sender_id_fkey FOREIGN KEY (sender_id) REFERENCES public.accounts(id);

--
-- Name: notifications notifications_account_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.notifications
    ADD CONSTRAINT notifications_account_id_fkey FOREIGN KEY (account_id) REFERENCES public.accounts(id) ON DELETE CASCADE;

--
-- Name: notifications notifications_order_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.notifications
    ADD CONSTRAINT notifications_order_id_fkey FOREIGN KEY (order_id) REFERENCES public.orders(id) ON DELETE CASCADE;

--
-- Name: order_inputs order_inputs_handwriting_style_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.order_inputs
    ADD CONSTRAINT order_inputs_handwriting_style_id_fkey FOREIGN KEY (handwriting_style_id) REFERENCES public.handwriting_styles(id);

--
-- Name: order_inputs order_inputs_order_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.order_inputs
    ADD CONSTRAINT order_inputs_order_id_fkey FOREIGN KEY (order_id) REFERENCES public.orders(id) ON DELETE CASCADE;

--
-- Name: order_inputs order_inputs_template_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.order_inputs
    ADD CONSTRAINT order_inputs_template_id_fkey FOREIGN KEY (template_id) REFERENCES public.templates(id);

--
-- Name: orders orders_assigned_by_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.orders
    ADD CONSTRAINT orders_assigned_by_fkey FOREIGN KEY (assigned_by) REFERENCES public.accounts(id);

--
-- Name: orders orders_assigned_staff_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.orders
    ADD CONSTRAINT orders_assigned_staff_id_fkey FOREIGN KEY (assigned_staff_id) REFERENCES public.accounts(id);

--
-- Name: orders orders_customer_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.orders
    ADD CONSTRAINT orders_customer_id_fkey FOREIGN KEY (customer_id) REFERENCES public.accounts(id);

--
-- Name: orders orders_paper_type_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.orders
    ADD CONSTRAINT orders_paper_type_id_fkey FOREIGN KEY (paper_type_id) REFERENCES public.paper_types(id);

--
-- Name: orders orders_pen_type_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.orders
    ADD CONSTRAINT orders_pen_type_id_fkey FOREIGN KEY (pen_type_id) REFERENCES public.pen_types(id);

--
-- Name: paper_pen_compats paper_pen_compats_paper_type_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.paper_pen_compats
    ADD CONSTRAINT paper_pen_compats_paper_type_id_fkey FOREIGN KEY (paper_type_id) REFERENCES public.paper_types(id) ON DELETE CASCADE;

--
-- Name: paper_pen_compats paper_pen_compats_pen_type_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.paper_pen_compats
    ADD CONSTRAINT paper_pen_compats_pen_type_id_fkey FOREIGN KEY (pen_type_id) REFERENCES public.pen_types(id) ON DELETE CASCADE;

--
-- Name: paper_pen_compats paper_pen_compats_updated_by_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.paper_pen_compats
    ADD CONSTRAINT paper_pen_compats_updated_by_fkey FOREIGN KEY (updated_by) REFERENCES public.accounts(id);

--
-- Name: payments payments_confirmed_by_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.payments
    ADD CONSTRAINT payments_confirmed_by_fkey FOREIGN KEY (confirmed_by) REFERENCES public.accounts(id);

--
-- Name: payments payments_order_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.payments
    ADD CONSTRAINT payments_order_id_fkey FOREIGN KEY (order_id) REFERENCES public.orders(id);

--
-- Name: payments payments_refund_of_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.payments
    ADD CONSTRAINT payments_refund_of_id_fkey FOREIGN KEY (refund_of_id) REFERENCES public.payments(id);

--
-- Name: phone_otps phone_otps_account_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.phone_otps
    ADD CONSTRAINT phone_otps_account_id_fkey FOREIGN KEY (account_id) REFERENCES public.accounts(id) ON DELETE CASCADE;

--
-- Name: pricing_configs pricing_configs_created_by_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.pricing_configs
    ADD CONSTRAINT pricing_configs_created_by_fkey FOREIGN KEY (created_by) REFERENCES public.accounts(id);

--
-- Name: product_photos product_photos_job_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.product_photos
    ADD CONSTRAINT product_photos_job_id_fkey FOREIGN KEY (job_id) REFERENCES public.production_jobs(id);

--
-- Name: product_photos product_photos_order_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.product_photos
    ADD CONSTRAINT product_photos_order_id_fkey FOREIGN KEY (order_id) REFERENCES public.orders(id) ON DELETE CASCADE;

--
-- Name: product_photos product_photos_uploaded_by_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.product_photos
    ADD CONSTRAINT product_photos_uploaded_by_fkey FOREIGN KEY (uploaded_by) REFERENCES public.accounts(id);

--
-- Name: production_jobs production_jobs_order_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.production_jobs
    ADD CONSTRAINT production_jobs_order_id_fkey FOREIGN KEY (order_id) REFERENCES public.orders(id);

--
-- Name: production_jobs production_jobs_robot_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.production_jobs
    ADD CONSTRAINT production_jobs_robot_id_fkey FOREIGN KEY (robot_id) REFERENCES public.robots(id);

--
-- Name: production_jobs production_jobs_scheduled_by_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.production_jobs
    ADD CONSTRAINT production_jobs_scheduled_by_fkey FOREIGN KEY (scheduled_by) REFERENCES public.accounts(id);

--
-- Name: production_jobs production_jobs_sketch_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.production_jobs
    ADD CONSTRAINT production_jobs_sketch_id_fkey FOREIGN KEY (sketch_id) REFERENCES public.sketches(id);

--
-- Name: production_jobs production_jobs_technician_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.production_jobs
    ADD CONSTRAINT production_jobs_technician_id_fkey FOREIGN KEY (technician_id) REFERENCES public.accounts(id);

--
-- Name: quotations quotations_approved_by_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.quotations
    ADD CONSTRAINT quotations_approved_by_fkey FOREIGN KEY (approved_by) REFERENCES public.accounts(id);

--
-- Name: quotations quotations_created_by_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.quotations
    ADD CONSTRAINT quotations_created_by_fkey FOREIGN KEY (created_by) REFERENCES public.accounts(id);

--
-- Name: quotations quotations_order_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.quotations
    ADD CONSTRAINT quotations_order_id_fkey FOREIGN KEY (order_id) REFERENCES public.orders(id) ON DELETE CASCADE;

--
-- Name: quotations quotations_pricing_config_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.quotations
    ADD CONSTRAINT quotations_pricing_config_id_fkey FOREIGN KEY (pricing_config_id) REFERENCES public.pricing_configs(id);

--
-- Name: quotations quotations_sketch_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.quotations
    ADD CONSTRAINT quotations_sketch_id_fkey FOREIGN KEY (sketch_id) REFERENCES public.sketches(id);

--
-- Name: review_photos review_photos_review_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.review_photos
    ADD CONSTRAINT review_photos_review_id_fkey FOREIGN KEY (review_id) REFERENCES public.reviews(id) ON DELETE CASCADE;

--
-- Name: reviews reviews_customer_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.reviews
    ADD CONSTRAINT reviews_customer_id_fkey FOREIGN KEY (customer_id) REFERENCES public.accounts(id);

--
-- Name: reviews reviews_order_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.reviews
    ADD CONSTRAINT reviews_order_id_fkey FOREIGN KEY (order_id) REFERENCES public.orders(id) ON DELETE CASCADE;

--
-- Name: shipments shipments_created_by_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.shipments
    ADD CONSTRAINT shipments_created_by_fkey FOREIGN KEY (created_by) REFERENCES public.accounts(id);

--
-- Name: shipments shipments_order_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.shipments
    ADD CONSTRAINT shipments_order_id_fkey FOREIGN KEY (order_id) REFERENCES public.orders(id);

--
-- Name: showcase_posts showcase_posts_posted_by_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.showcase_posts
    ADD CONSTRAINT showcase_posts_posted_by_fkey FOREIGN KEY (posted_by) REFERENCES public.accounts(id);

--
-- Name: sketches sketches_created_by_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.sketches
    ADD CONSTRAINT sketches_created_by_fkey FOREIGN KEY (created_by) REFERENCES public.accounts(id);

--
-- Name: sketches sketches_order_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.sketches
    ADD CONSTRAINT sketches_order_id_fkey FOREIGN KEY (order_id) REFERENCES public.orders(id) ON DELETE CASCADE;

--
-- Name: status_histories status_histories_actor_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.status_histories
    ADD CONSTRAINT status_histories_actor_id_fkey FOREIGN KEY (actor_id) REFERENCES public.accounts(id);

--
-- Name: status_histories status_histories_order_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.status_histories
    ADD CONSTRAINT status_histories_order_id_fkey FOREIGN KEY (order_id) REFERENCES public.orders(id) ON DELETE CASCADE;

--
-- Name: system_settings system_settings_updated_by_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.system_settings
    ADD CONSTRAINT system_settings_updated_by_fkey FOREIGN KEY (updated_by) REFERENCES public.accounts(id);

--
-- Name: templates templates_created_by_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.templates
    ADD CONSTRAINT templates_created_by_fkey FOREIGN KEY (created_by) REFERENCES public.accounts(id);

--
-- Name: accounts; Type: ROW SECURITY; Schema: public; Owner: -
--

ALTER TABLE public.accounts ENABLE ROW LEVEL SECURITY;

--
-- Name: alembic_version; Type: ROW SECURITY; Schema: public; Owner: -
--

ALTER TABLE public.alembic_version ENABLE ROW LEVEL SECURITY;

--
-- Name: audit_logs; Type: ROW SECURITY; Schema: public; Owner: -
--

ALTER TABLE public.audit_logs ENABLE ROW LEVEL SECURITY;

--
-- Name: auth_sessions; Type: ROW SECURITY; Schema: public; Owner: -
--

ALTER TABLE public.auth_sessions ENABLE ROW LEVEL SECURITY;

--
-- Name: calibrations; Type: ROW SECURITY; Schema: public; Owner: -
--

ALTER TABLE public.calibrations ENABLE ROW LEVEL SECURITY;

--
-- Name: handwriting_styles; Type: ROW SECURITY; Schema: public; Owner: -
--

ALTER TABLE public.handwriting_styles ENABLE ROW LEVEL SECURITY;

--
-- Name: incidents; Type: ROW SECURITY; Schema: public; Owner: -
--

ALTER TABLE public.incidents ENABLE ROW LEVEL SECURITY;

--
-- Name: ink_colors; Type: ROW SECURITY; Schema: public; Owner: -
--

ALTER TABLE public.ink_colors ENABLE ROW LEVEL SECURITY;

--
-- Name: job_events; Type: ROW SECURITY; Schema: public; Owner: -
--

ALTER TABLE public.job_events ENABLE ROW LEVEL SECURITY;

--
-- Name: messages; Type: ROW SECURITY; Schema: public; Owner: -
--

ALTER TABLE public.messages ENABLE ROW LEVEL SECURITY;

--
-- Name: notifications; Type: ROW SECURITY; Schema: public; Owner: -
--

ALTER TABLE public.notifications ENABLE ROW LEVEL SECURITY;

--
-- Name: order_inputs; Type: ROW SECURITY; Schema: public; Owner: -
--

ALTER TABLE public.order_inputs ENABLE ROW LEVEL SECURITY;

--
-- Name: orders; Type: ROW SECURITY; Schema: public; Owner: -
--

ALTER TABLE public.orders ENABLE ROW LEVEL SECURITY;

--
-- Name: paper_pen_compats; Type: ROW SECURITY; Schema: public; Owner: -
--

ALTER TABLE public.paper_pen_compats ENABLE ROW LEVEL SECURITY;

--
-- Name: paper_types; Type: ROW SECURITY; Schema: public; Owner: -
--

ALTER TABLE public.paper_types ENABLE ROW LEVEL SECURITY;

--
-- Name: payments; Type: ROW SECURITY; Schema: public; Owner: -
--

ALTER TABLE public.payments ENABLE ROW LEVEL SECURITY;

--
-- Name: pen_types; Type: ROW SECURITY; Schema: public; Owner: -
--

ALTER TABLE public.pen_types ENABLE ROW LEVEL SECURITY;

--
-- Name: phone_otps; Type: ROW SECURITY; Schema: public; Owner: -
--

ALTER TABLE public.phone_otps ENABLE ROW LEVEL SECURITY;

--
-- Name: pricing_configs; Type: ROW SECURITY; Schema: public; Owner: -
--

ALTER TABLE public.pricing_configs ENABLE ROW LEVEL SECURITY;

--
-- Name: product_photos; Type: ROW SECURITY; Schema: public; Owner: -
--

ALTER TABLE public.product_photos ENABLE ROW LEVEL SECURITY;

--
-- Name: production_jobs; Type: ROW SECURITY; Schema: public; Owner: -
--

ALTER TABLE public.production_jobs ENABLE ROW LEVEL SECURITY;

--
-- Name: quotations; Type: ROW SECURITY; Schema: public; Owner: -
--

ALTER TABLE public.quotations ENABLE ROW LEVEL SECURITY;

--
-- Name: review_photos; Type: ROW SECURITY; Schema: public; Owner: -
--

ALTER TABLE public.review_photos ENABLE ROW LEVEL SECURITY;

--
-- Name: reviews; Type: ROW SECURITY; Schema: public; Owner: -
--

ALTER TABLE public.reviews ENABLE ROW LEVEL SECURITY;

--
-- Name: robots; Type: ROW SECURITY; Schema: public; Owner: -
--

ALTER TABLE public.robots ENABLE ROW LEVEL SECURITY;

--
-- Name: roles; Type: ROW SECURITY; Schema: public; Owner: -
--

ALTER TABLE public.roles ENABLE ROW LEVEL SECURITY;

--
-- Name: shipments; Type: ROW SECURITY; Schema: public; Owner: -
--

ALTER TABLE public.shipments ENABLE ROW LEVEL SECURITY;

--
-- Name: showcase_posts; Type: ROW SECURITY; Schema: public; Owner: -
--

ALTER TABLE public.showcase_posts ENABLE ROW LEVEL SECURITY;

--
-- Name: sketches; Type: ROW SECURITY; Schema: public; Owner: -
--

ALTER TABLE public.sketches ENABLE ROW LEVEL SECURITY;

--
-- Name: status_histories; Type: ROW SECURITY; Schema: public; Owner: -
--

ALTER TABLE public.status_histories ENABLE ROW LEVEL SECURITY;

--
-- Name: system_settings; Type: ROW SECURITY; Schema: public; Owner: -
--

ALTER TABLE public.system_settings ENABLE ROW LEVEL SECURITY;

--
-- Name: templates; Type: ROW SECURITY; Schema: public; Owner: -
--

ALTER TABLE public.templates ENABLE ROW LEVEL SECURITY;

--
-- PostgreSQL database dump complete
--


-- pg_dump empties the search_path; the data below uses plain table names.
SET search_path TO public;

-- =====================================================================================================================
-- 2. Migration marker
-- =====================================================================================================================
INSERT INTO alembic_version (version_num) VALUES ('0006');

-- =====================================================================================================================
-- 3. Reference data (roles, demo accounts, first price list, pen types) - from the baseline script, section 9
-- =====================================================================================================================
BEGIN;
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

-- Default system settings (migration 0002)
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
ON CONFLICT (key) DO NOTHING;
COMMIT;

-- =====================================================================================================================
-- 4. Supabase only: the REST roles must not reach the tables (the API talks to Postgres directly). Skipped elsewhere.
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
