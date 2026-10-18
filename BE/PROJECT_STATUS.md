# AI-VHRS Backend – Trạng thái dự án (đọc file này ĐẦU TIÊN)

> **Quy tắc bắt buộc cho mọi AI/người làm tiếp:** sau MỖI lần code xong (hoặc đổi quyết định) phải cập nhật file này
> ngay trong cùng lượt làm việc: mục 1 (trạng thái), mục 3 (bảng phase), mục 6 (test), mục 9 (changelog) và các mục khác nếu có
> thay đổi. Quy trình đầy đủ ở `AI_PLAYBOOK.md`. Hướng dẫn cho FE ở `docs/FE_API_GUIDE.md` (cũng phải cập nhật khi API đổi).

> **Tài liệu yêu cầu gốc** (Report 1–3 SRS, danh sách FR/entity bản 2, phiếu đăng ký) nằm ở `docs/source/` – đọc `docs/source/README.md` trước khi hỏi chủ dự án về nghiệp vụ.

## 1. Đang ở đâu

| Mục | Giá trị |
|---|---|
| Cập nhật lần cuối | 2026-10-16 (Phase 3 code xong, **295 test pass trên Supabase**, seed Phase 3 đã áp dụng) |
| Phase hiện tại | **Phase 3 – Cọc & Manager vận hành**: code xong, toàn bộ suite pass; **chưa commit** (chờ chủ dự án review) |
| Đã commit | Phase 1 (khách đặt đơn), Phase 2 (xưởng tiếp nhận → báo giá) – commit `e7d0fbf` trên `origin/BE` và đã vào `main` |
| Phase kế tiếp | Phase 4 – Sản xuất (web scope A), nghiệm thu, thanh toán cuối, giao hàng, thông báo |
| Nhánh làm việc | `BE` (nhánh chính là `main`) |
| Việc chờ chủ dự án | review + commit Phase 3 → rồi mới bắt đầu Phase 4 (xem mục 10) |

Dự án: backend của **AI-VHRS – Xưởng Nét Việt** (đồ án): khách đặt viết/sao chép chữ viết tay tiếng Việt, xưởng làm phác thảo bằng AI,
báo giá, thu cọc, xếp lịch cho robot cánh tay Fairino FR3 viết lên giấy. **Chỉ làm BE** (`/BE`); không đụng `FE/`, `Mobile/`.

## 2. Chạy dự án

```bash
cd BE && source .venv/bin/activate          # venv có sẵn: BE/.venv (Python 3.14 local, Dockerfile dùng 3.11)
python -m uvicorn app.main:app --reload --port 8000        # PHẢI chạy trong thư mục BE (không phải thư mục gốc repo)
python -m pytest -q                         # chạy trên DB trong BE/.env (Supabase thật). Toàn bộ suite ~20+ phút
python scripts/seed_workshop_data.py --dry-run             # xem seed sẽ ghi gì; bỏ --dry-run để ghi (idempotent)
```
`BE/.env` (đã `.gitignore`, **không bao giờ in/commit**): `DATABASE_URL` (Supabase session pooler), `JWT_SECRET`, `SUPABASE_URL`,
`SUPABASE_SERVICE_KEY`, `STORAGE_BUCKET=order-inputs`. Thiếu `.env` → hỏi chủ dự án, không giả lập. Swagger: `/docs`.
Tài khoản demo trên Supabase: `customer@example.com`, `khach@example.com`, `staff@netviet.vn`, `manager@netviet.vn`, `tech@netviet.vn`, `admin@netviet.vn`
(mật khẩu do chủ dự án giữ; **đổi trước khi deploy công khai**).

## 3. Bảng phase

| Phase | Nội dung | Trạng thái |
|---|---|---|
| 0 | Auth (session server-side), tài khoản, Admin tài khoản + audit log | ✅ xong, đã commit |
| 1 | Khách: danh mục, giá ước tính, tạo/sửa/gửi đơn, upload ảnh (Supabase Storage), huỷ đơn SUBMITTED/NEED_INFO | ✅ xong, đã commit |
| 2 | Staff/Manager: hàng đợi, nhận/phân công, tiếp nhận/từ chối/yêu cầu bổ sung, **phác thảo AI thật (OT-1, OT-3)**, báo giá (Pricing Engine, ±ngưỡng, Manager duyệt, PDF, hết hạn 7 ngày), chính sách riêng tư, chat, seed dữ liệu thật | ✅ xong, đã commit (`e7d0fbf`) |
| **3** | Khách duyệt báo giá + chọn % cọc, **cọc qua cổng MOCK + webhook ký HMAC idempotent**, khách huỷ khi chưa cọc; Manager: giấy/bút/mực/tồn kho/tương thích, mẫu chữ, duyệt bộ nét, robot, **bảng giá có phiên bản** (gồm ngưỡng BR-09 & % cọc tối thiểu), **lập lịch sản xuất** (gợi ý, xếp, đổi, gỡ, xếp lại khi FAILED) | ✅ code xong + test pass (295/295 toàn suite), **chưa commit** |
| 4 | Technical Staff (web scope A: xem/tải gói job + hash, Calibration dạng bản ghi, JobEvent, Incident, ảnh sản phẩm + QC ≥2 ảnh BR-21, trừ kho khi WRITTEN), nghiệm thu / viết lại ≤1 lần free (BR-13), thanh toán cuối + giao hàng (carrier MOCK), ETA & dời ETA (BR-15/16), **huỷ sau cọc + hoàn tiền (BR-14/16)**, notification center + email, xử lý khoản `needs_refund` | ⬜ chưa làm |
| 5 | Admin (tích hợp, `system_settings`, dashboard hệ thống), báo cáo Manager, **scheduled jobs** (hết hạn báo giá chủ động, nhắc/tự nghiệm thu, xoá ảnh 90 ngày BR-23, huỷ cọc quá hạn), OTP SMS, showcase, review | ⬜ chưa làm |

## 4. Bản đồ code (`BE/app`)

```
api/v1/*        route mỏng: auth, me, catalog, pricing, orders, customer_quotes, messages, payments,
                workshop (Staff+Manager), manager (phân công, duyệt giá), manager_ops (vật tư/giá/robot), scheduling, admin
api/*schemas.py Pydantic in/out (tách khỏi ORM): schemas, order_schemas, staff_schemas, ops_schemas
services/       nghiệp vụ: orders, pricing(thuần), quotations, payments, manager_catalog, scheduling, staff_orders, sketches,
                messages, notifications(hook, chưa gửi), audit, workshop_access(phân quyền bản ghi), stroke_ai/ (AI thật)
domain/         luật thuần (không DB): quotation_rules, payment_rules, pricing_config_rules, scheduling_rules
repositories/   truy cập dữ liệu (không nghiệp vụ): accounts, catalog, orders, workshop, ops
models/         ORM ánh xạ bảng có sẵn: account, catalog, order, sketch, ops   (schema do SQL migration sở hữu)
integrations/   storage (Supabase Storage + InMemoryStorage cho test), payment_gateway (MOCK), mailer (console)
core/           config, security, errors (envelope lỗi), ratelimit
migrations/     sql/AI-VHRS_database_postgresql.sql (baseline) + versions/0001..0003 (Alembic)
scripts/seed_workshop_data.py   seed dữ liệu thật lên Supabase (idempotent)
tests/          conftest.py (dọn dữ liệu tiền tố pytest_) + test_* (xem mục 6)
```
Luồng một request: `api` → `services` → `repositories` → `models`. **Trạng thái đơn do trigger DB `fn_order_state_guard` quyết định**
(service chỉ UPDATE; sai → lỗi `P0409` → HTTP 409 `STATE_CONFLICT`); không nhân đôi luật chuyển trạng thái ở Python.
Trạng thái báo giá/job **không** có trigger: do service kiểm tra.

## 5. Quyết định kiến trúc đã chốt (không đổi nếu chưa hỏi chủ dự án)

- Python 3.11 (3.14 local) · FastAPI · SQLAlchemy 2 · Alembic · PostgreSQL (Supabase) · Pydantic v2 · JWT + session server-side · httpx · OpenCV headless · Hershey-Fonts · fpdf2.
- Lỗi: `{"error":{"code","message","details"}}`; phân trang `{items,total,page,page_size}`.
- Phân quyền bản ghi: đơn của người khác → **404**; sai vai trò → **403**. Staff thấy đơn được giao + pool `SUBMITTED` chưa ai nhận (chỉ đọc tới khi nhận); Manager thấy mọi đơn không phải `DRAFT`.
- **Manager không xử lý đơn như Staff** (chủ dự án chọn 2026-10-17): Manager chỉ **đọc** mọi đơn, phân công Staff, duyệt/từ chối giá vượt ngưỡng, quản vật tư/mẫu chữ/robot/bảng giá/ngưỡng %, lập lịch; mọi lệnh ghi trong `/workshop/*` (accept, reject, phác thảo, báo giá, điều chỉnh, gửi) là **STAFF only**; Manager **được** nhắn tin với khách trong chat để xử lý khiếu nại; Manager không tự duyệt giá của chính mình. Ma trận quyền toàn API được test tự động ở `tests/test_permission_matrix.py`.
- **Admin chỉ quản trị hệ thống** (tài khoản, tích hợp, tham số, audit); **không** xem/sửa đơn, giá, sản xuất (override Report 3). Manager lo đơn/sản xuất/giá/vật tư.
- **Không kết nối robot thật** (không SDK Fairino, serial, lệnh chuyển động). Cổng thanh toán/vận chuyển là **MOCK** có nhãn `mode=MOCK`; mô phỏng không bao giờ được báo như thao tác thật.
- AI là thật nhưng **cổ điển, không gọi dịch vụ ngoài**: OT-1 (CV: thinning Zhang-Suen, đồ thị nét…), OT-3 (font một nét Hershey + ghép dấu tiếng Việt NFD). OT-2 không sinh tự động (R&D).
- Loại đơn khách được đặt: `system_settings.order_types_enabled` = `["OT1_COPY_RESTORE","OT3_TEMPLATE"]` (OT-2 tắt).
- Nguồn ngưỡng điều chỉnh giá (BR-09) và % cọc tối thiểu (BR-10): **`pricing_configs`** (có phiên bản, mỗi báo giá giữ snapshot). Khoá `system_settings.price_adjust_threshold_pct` (migration 0002) **không được code đọc**.
- BR-09 so giá Staff nhập với giá hệ thống tính (`computed_total`) của chính báo giá đó, **không** so với giá ước tính lúc khách tạo đơn (chủ dự án chọn phương án A, 2026-10-17).
- **Chốt 2026-10-18 cho Phase 4** (chi tiết `docs/source/README.md`): viết lại chỉ 1 lần miễn phí (lần 2 → lỗi "liên hệ xưởng", không đổi schema); giao thất bại/hoàn → giữ đơn `DELIVERING`, không đổi trigger; webhook hãng `DELIVERED` → `COMPLETED`, khách xác nhận nhận hàng chỉ ghi `received_confirmed_at`; test tiếp tục trên Supabase thật.
- Mọi mã lỗi nghiệp vụ nằm trong `AppError(...)`; danh sách để FE đối chiếu: `grep -rhoE 'AppError\([0-9]{3}, "[A-Z_0-9]+"' app | sort -u`.

## 6. Test

Chạy trên **Supabase thật**, chỉ tạo/xoá dữ liệu tiền tố `pytest_` (xem `tests/conftest.py::_cleanup`); tạm gỡ `order_types_enabled` trong lúc chạy rồi khôi phục.
**Không chạy hai phiên pytest cùng lúc** (chúng dọn dữ liệu của nhau).

| File | Nội dung | Cần DB |
|---|---|---|
| `test_pricing.py`, `test_quotation_rules.py`, `test_phase3_rules.py`, `test_stroke_ai.py`, `test_handwriting_image.py`, `test_security.py` | luật thuần, AI, bảo mật | không |
| `test_api_accounts.py`, `test_api_orders*.py`, `test_db_state_guard.py`, `test_hardening.py` | Phase 0–1, trigger | có |
| `test_api_workshop.py` | Phase 2 (xưởng, phác thảo, báo giá, riêng tư, chat) | có |
| `test_permission_matrix.py` | ma trận quyền: mọi route × 5 vai trò, token/đăng xuất | có |
| `test_api_payments.py` | Phase 3: duyệt báo giá, cọc MOCK, webhook, huỷ | có |
| `test_api_manager_ops.py` | Phase 3: vật tư, tồn kho, mẫu chữ, bộ nét, robot, bảng giá | có |
| `test_api_scheduling.py` | Phase 3: lịch sản xuất, xung đột, đổi/gỡ, FAILED | có |
| `test_storage_live.py` | Supabase Storage thật | có + service key |

**Kết quả gần nhất (ghi lại sau mỗi lần chạy toàn bộ):**
- 2026-10-18 (sau đổi `GOOGLE_CLIENT` + thêm `docs/source`): toàn bộ suite **323 passed, 0 failed, 0 skipped** trong 33 phút 40 giây trên Supabase thật (Python 3.14); `test_storage_live` chạy thật (không còn skip). Sau chạy: DB không còn `pytest_*`, bảng giá thật còn đúng 1 bản active, `order_types_enabled` = `[OT1_COPY_RESTORE, OT3_TEMPLATE]`. Chậm nhất: `test_permission_matrix` (~188 s). Lưu ý: `test_api_google_login` chạy nhánh "đã cấu hình client id" vì `.env` có `GOOGLE_CLIENT`; vẫn **chưa thử với token Google thật**.
- 2026-10-16 (Phase 2, trước Phase 3): toàn bộ suite **219 passed** trên Supabase (Python 3.14).
- 2026-10-17 (sau phân quyền, Google, vật tư): toàn bộ suite 314 passed + 1 failed (test cũ dùng Manager để từ chối đơn, đã sửa) + 1 error (bước dọn cuối, xem bài học trong `AI_PLAYBOOK.md` 8, đã sửa); sau đó chạy lại `test_api_materials/google_login/permission_matrix/workshop/payments/manager_ops`: **119 passed** (111 + 8). **Chưa chạy lại toàn bộ suite sau các sửa này.** Cần: Google thật chưa thử (đã có `GOOGLE_CLIENT_ID` trong `.env`, chưa kiểm tra bằng token thật).
- 2026-10-16 (sau Phase 3): **toàn bộ suite 295 passed** trong 28 phút 35 giây trên Supabase (Python 3.14). Sau chạy: DB không còn `pytest_*`, bảng giá thật (version 1) active, `order_types_enabled` đã khôi phục.
- Chưa từng chạy: FE nối API thật, OT-1 trên chữ viết tay thật (không có benchmark), Python 3.11 cho code Phase 3.

## 7. Dữ liệu trên Supabase (đã có)

- Schema: Alembic `0003` (baseline SQL + `0002_fixes` + `0003_auth_sessions`). **Phase 2 và 3 không thêm migration.** Mọi đổi schema cần chủ dự án duyệt.
- Đã seed (kể cả phần Phase 3, chạy lại không ghi thêm) bằng `scripts/seed_workshop_data.py`: 7 loại giấy, 11 màu mực, 4 mẫu font Hershey, 35 dòng tương thích giấy–bút (BR-06), giá/tồn bút khởi điểm, 1 robot `FR3-01`, settings `order_types_enabled`, `privacy_policy` v1.0, `working_hours`, `schedule_params`.
- Có sẵn `pricing_configs` version 1 (đang áp dụng; ngưỡng 15%, cọc tối thiểu 50%) và 6 tài khoản demo.
- Còn 1 đơn nháp mồ côi `VHRS-D40BD099` của `customer@example.com` (không phải do test): **hỏi chủ dự án trước khi xoá**.

## 8. Giả định / việc chưa kiểm chứng (cần chủ dự án hoặc xưởng xác nhận)

1. Giá giấy/bút/mực và tồn kho trong seed là **giá trị khởi điểm do AI chọn** (SRS chỉ có số minh hoạ): Manager phải nhập số thật (có API).
2. Nội dung `privacy_policy` là **bản nháp** suy ra từ BR-23/24, NFR-09/12; chưa có nguyên văn BR-25.
3. Độ chính xác OT-1 trên chữ viết tay thật chưa đo (NFR-02 cần bộ ảnh benchmark); ~82% IoU chỉ trên ảnh tổng hợp. Thứ tự/chiều nét là heuristic; hằng số ước tính thời gian viết và ngưỡng K_cx là giả định.
4. Giờ làm việc xưởng mặc định T2–T7 08:00–17:00 UTC+7; chuẩn bị 15', chụp ảnh 5', ETA = ngày viết xong + 2 ngày; robot `FR3-01` hỗ trợ mọi loại bút (BR-18 chưa có bảng loại robot thật).
5. Từ chối chính sách riêng tư = **huỷ đơn**. Khách huỷ được khi `QUOTED`/`AWAITING_DEPOSIT` (chưa trả tiền); sau cọc chưa huỷ online được.
6. Báo giá nhiều phương án vật tư **không** điều chỉnh giá được; báo giá thiếu logo xưởng (chỉ header chữ; đặt `app/assets/logo.png` để in logo).
7. Hết hạn báo giá chạy **lười** (khi có người đọc đơn); scheduler chủ động ở Phase 5. Cọc quá hạn chưa tự huỷ đơn (Phase 5).
8. Thông báo (MSG07/08/10, `DEPOSIT_PAID`, `JOB_ASSIGNED`) mới chỉ ghi log qua hook `services/notifications.notify()`; gửi thật ở Phase 4. Mã `DEPOSIT_PAID`/`JOB_ASSIGNED` do AI đặt tên vì chưa có bảng mã MSG đầy đủ.
9. Webhook MOCK ký bằng khoá dẫn xuất từ `JWT_SECRET`; cổng thật sẽ có khoá riêng (Phase 5 – tích hợp).
10. Đường REWRITE_REQUIRED của lập lịch có code (`is_rewrite`) nhưng **chưa có test đầu-cuối** (cần luồng nghiệm thu của Phase 4).

## 9. Changelog (mới nhất trước)

- **2026-10-18 – Tài liệu gốc vào repo** (chưa commit): thêm `docs/source/` (chép markdown từ Report 1, 2, 3/SRS, danh sách chức năng & entity bản 2, phiếu đăng ký đề tài, và bản UI 3-actor đã đánh dấu lỗi thời) + `README.md` chỉ mục, bảng quyết định đã override, luật Phase 4–5 đã có đáp án và các điểm tài liệu còn mơ hồ; cập nhật `CLAUDE.md`, `AI_PLAYBOOK.md` mục 0.
- **2026-10-18 – Biến môi trường Google**: `GOOGLE_CLIENT` là tên chính (khớp Render), `GOOGLE_CLIENT_ID` vẫn được đọc (`core/config.py` dùng `AliasChoices`); cập nhật `.env.example`, `DEPLOY.md`, `FE_API_GUIDE.md`. Đã chạy lại toàn bộ suite trên Supabase sau thay đổi này: 323 passed (xem mục 6).

- **2026-10-17 – Chọn vật tư**: `GET /catalog/suggest-materials?paper_type_id=` (bút tương thích + mực, công khai); "để xưởng chọn" giữ nguyên lựa chọn của khách, Staff chỉ điền phần thiếu và vẫn theo luật tương thích (`MATERIAL_LOCKED_BY_CUSTOMER`); `GET /workshop/orders/{id}/material-suggestions` liệt kê tổ hợp còn đề xuất được; `MaterialOptionIn` các trường đều tuỳ chọn. Không đổi schema, không thêm cảnh báo chất lượng. Tương thích giấy–bút–mực là **bảng quy tắc do con người thiết lập** (không có AI nhận diện): seed ban đầu theo BR-06, Manager chỉnh qua `/manager/compatibility`.
- **2026-10-17 – Đăng nhập Google**: `POST /auth/google {id_token}` (`integrations/google_auth.py` xác minh qua Google tokeninfo: aud/iss/exp/email_verified; `AuthService.login_google`). **Không đổi schema**: khớp tài khoản theo email đã xác minh, chỉ khách hàng (email nội bộ → 403 `GOOGLE_NOT_ALLOWED`), tạo `CUSTOMER` mới nếu chưa có. Cần env `GOOGLE_CLIENT_ID` (Web client từ Google Cloud Console); chưa có thì endpoint trả 503. Test: luật xác minh trên verifier thật với transport giả lập, logic tài khoản trên DB thật; **chưa thử với token Google thật**.
- **2026-10-17 – Phân quyền Manager/Staff** (chưa commit): mọi lệnh ghi `/workshop/*` chỉ STAFF; chat dành cho Customer+Staff+Manager (Manager nhắn để xử lý khiếu nại); bỏ nhánh "Manager tự duyệt giá" trong `QuotationService.adjust`; thêm `tests/test_permission_matrix.py` (quét mọi route × 5 vai trò, route mới thiếu quy tắc thì fail); cập nhật test Phase 2 và `docs/FE_API_GUIDE.md`.
- **2026-10-16 – Phase 3** (chưa commit): thêm `models/ops.py`, `services/{payments,manager_catalog,scheduling}.py`, `domain/{payment_rules,pricing_config_rules,scheduling_rules}.py`, `integrations/payment_gateway.py`, `repositories/ops.py`, `api/v1/{payments,manager_ops,scheduling}.py`, `api/ops_schemas.py`; mở rộng `orders.cancel` (QUOTED/AWAITING_DEPOSIT), `customer_quotes.py` (approve), `workshop.py` (payments/jobs chỉ đọc), seed (robot + 2 settings), `conftest` (dọn payments/jobs/robots/pricing/styles). Sửa 3 lỗi phát hiện qua test: (a) hết hạn báo giá bị rollback khi API trả 409 → `expire_and_persist`; (b) audit `PAYMENT_MISMATCH` bị rollback → commit trước khi raise; (c) cảnh báo Pydantic `OptionSummary`. Thêm `PROJECT_STATUS.md`, `AI_PLAYBOOK.md`, `CLAUDE.md`, `docs/FE_API_GUIDE.md`.
- **2026-10-16 – Phase 2** (commit `e7d0fbf`): xưởng + AI + báo giá + riêng tư + chat + seed.
- Trước đó: Phase 0–1 (auth, tài khoản, đặt đơn, upload).

## 10. Việc kế tiếp (thứ tự)

1. Chủ dự án review + commit Phase 3 (AI **không** tự commit/push).
2. Khi bắt đầu Phase 4: đọc `AI_PLAYBOOK.md`, trình bày kế hoạch (phạm vi FR/UC, endpoint, entity, file đổi, test, giả định), **chờ "duyệt"**, rồi code. Ưu tiên: Technical Staff (job/gói job/JobEvent/Incident/ảnh+QC), nghiệm thu & viết lại, thanh toán cuối + giao hàng MOCK, huỷ sau cọc + hoàn tiền (kể cả xử lý `needs_refund`), ETA/dời ETA, notification center + email.
3. Việc tồn của chủ dự án: **xoay (rotate) `service_role` key Supabase** (từng bị dán vào chat), xác nhận đơn mồ côi, duyệt chính sách riêng tư, nhập giá/tồn thật, gửi lại Report 3 EN bản mới + BR-25 nếu muốn đối chiếu, đổi mật khẩu demo trước khi deploy.
4. Chỗ nợ kỹ thuật nhỏ: `conftest.py` còn vài `SyntaxWarning` (`'\_'`) từ trước; FE cần poll vì chưa có thông báo đẩy.
