# AI Playbook – cách làm việc trên dự án AI-VHRS (BE)

> Dành cho **mọi AI agent** (và người dùng Claude trên máy khác) tham gia dự án. Đây là bộ "kỹ năng" đã được kiểm chứng trong
> các phase trước: bám theo để làm nhanh, ít lỗi, không lan man. **Có kỹ năng/bài học mới thì bổ sung thẳng vào file này
> (mục 8) trong cùng lượt làm việc.** Trạng thái dự án nằm ở `PROJECT_STATUS.md`; hợp đồng API cho FE ở `docs/FE_API_GUIDE.md`.

## 0. Bắt đầu mỗi phiên (5 phút, bắt buộc)

1. Đọc `PROJECT_STATUS.md` (đang ở phase nào, việc chờ ai, giả định chưa xác nhận) và file này.
2. `git status`, `git log --oneline -10`, nhánh hiện tại (làm trên nhánh `BE`).
3. Có `BE/.env` chưa? (không in nội dung). Thiếu → xin chủ dự án, **không** giả lập dữ liệu.
4. Cần luật nghiệp vụ/ý nghĩa mã BR/FR/UC/MSG/LI? Đọc `docs/source/README.md` (bản chép Report 1–3 + danh sách FR bản 2, kèm bảng "đã override" và "điểm còn mơ hồ") và `grep -rn "BR-xx" docs/source` **trước khi hỏi chủ dự án**.
5. Muốn biết code đang có gì: đọc `PROJECT_STATUS.md` mục 4 rồi mở đúng file; không quét cả repo.
6. Nếu yêu cầu của người dùng mâu thuẫn với file này hoặc `PROJECT_STATUS.md` mục 5 (quyết định đã chốt) → nêu rõ mâu thuẫn và hỏi, đừng âm thầm đổi.

## 1. Luật không thương lượng

- Giao tiếp **tiếng Việt**, giữ thuật ngữ kỹ thuật tiếng Anh. Báo cáo trung thực: cái gì **đã chạy**, cái gì **chưa chạy**, cái gì **không chắc**.
- **Chỉ làm `BE/`.** Không sửa `FE/`, `Mobile/`, root repo (trừ khi được yêu cầu rõ).
- **Kết nối robot thật (SDK Fairino, Robot Agent, serial/IoT) thuộc phạm vi BE nhưng CHƯA làm: chỉ làm khi chủ dự án yêu cầu rõ.** Mặc định chừa lại, làm các luồng tương tác với web app trước. Trong lúc chưa kết nối: không gọi SDK/serial/lệnh chuyển động, kết quả mô phỏng và dữ liệu lực/tiến độ do client báo lên (hoặc nhập thủ công) và BE chỉ ghi nhận. Cổng thanh toán/vận chuyển dùng adapter **MOCK** có `mode=MOCK`; không bao giờ trình bày mô phỏng như thao tác thật.
- **Dữ liệu phải thật**: dữ liệu mẫu seed thẳng vào Supabase bằng script idempotent; không hard-code dữ liệu giả trong code. AI là AI thật (xem `services/stroke_ai/`), không giả vờ.
- Admin = quản trị hệ thống (không đụng đơn/giá/sản xuất); Manager = đơn/sản xuất/giá/vật tư.
- **Không đổi schema/migration, không chạy lệnh DB phá huỷ khi chưa được duyệt.** Cần đổi → nêu giới hạn hiện tại, SQL đề xuất, ảnh hưởng, cách rollback.
- **Không commit/push khi chưa được yêu cầu.** Không `git push --force` lên nhánh dùng chung (`main`, `BE`) – làm hỏng người khác; hệ thống cũng sẽ chặn. **Không thêm dòng `Co-Authored-By: Claude`** (hay chữ ký AI) vào commit/PR: chủ dự án không muốn "claude" xuất hiện là contributor.
- **Không in/commit secret** (`.env`, `service_role` key, mật khẩu). Nếu người dùng dán secret vào chat: ghi vào `.env`, đừng nhắc lại, và nhắc họ xoay key.
- Không xoá/đổi tên chức năng hay field đang chạy; ưu tiên mở rộng; không đổi stack; không refactor ngoài phạm vi.

## 2. Quy trình mỗi phase / tính năng

`READ → AUDIT → COMPARE → PROPOSE → ASK → CONFIRM → CODE → TEST → REVIEW → REPORT → CẬP NHẬT TÀI LIỆU`

1. **Trước khi code phase mới:** trình bày kế hoạch (phạm vi FR/UC/BR, endpoint, entity, file sẽ đổi, test, tiêu chí hoàn thành, giả định) và **chờ chủ dự án "duyệt"**. Khi người dùng đã giao toàn quyền trong phạm vi một phase ("cứ làm cái hợp lý") thì làm theo mặc định khuyến nghị nhưng **ghi rõ mọi giả định**.
2. Gặp mơ hồ: dừng phần bị ảnh hưởng và hỏi bằng 2 phương án + khuyến nghị + tác động. Đừng im lặng quyết định chuyện lớn.
3. **Định nghĩa "xong"** (tất cả phải đạt, xem skill S06–S07): code chạy · test mới viết · **test chạy trên Supabase thật và pass** · toàn bộ suite không hồi quy · tài liệu cập nhật (S14) · báo cáo trung thực (S15).
4. Chạy test nặng ở **nền** (`run_in_background`), không poll; làm việc khác không đụng DB trong lúc chờ.

## 3. Bộ kỹ năng (skill cards)

### S01 · DB là nguồn sự thật – đọc schema và trigger trước khi code
Đọc `migrations/sql/AI-VHRS_database_postgresql.sql` + `versions/0002_fixes.py` (trigger `fn_order_state_guard` bản mới nhất ở 0002) **trước** khi viết service. Nhiều luật đã nằm trong DB (CHECK, EXCLUDE, unique index một phần, trigger). Đừng tái cài đặt; hãy dựa vào đó và viết test chứng minh DB chặn.
*Ví dụ:* `ex_job_robot_overlap` (không trùng lịch robot), `ux_payments_one_success_per_type`, `chk_orders_privacy_before_quote`.

### S02 · Đổi trạng thái đơn = UPDATE + `set_actor`, để trigger phán
Service chỉ gán `order.order_status = ...`, `session.flush()`; lỗi `P0409` tự thành 409 `STATE_CONFLICT`. **Gọi `set_actor(session, account_id, reason)` ngay trước mỗi UPDATE đổi trạng thái** (GUC chỉ sống trong 1 transaction: gọi lại sau mỗi `commit`). Trigger có ràng buộc ghép (ví dụ cọc thành công phải đổi `order_status=CONFIRMED` **và** `production_status=PENDING_SCHEDULE` trong cùng một UPDATE). Ghi đè cùng trạng thái là no-op nên phải tự chặn bằng 409. Trạng thái báo giá/job không có trigger → service tự kiểm tra và có test.

### S03 · Lỗi làm rollback cả request – cái cần giữ phải `commit` trước khi `raise`
`get_session` rollback khi có exception. Việc đáng giữ dù request thất bại (đánh dấu báo giá hết hạn, audit `PAYMENT_MISMATCH`) phải `session.commit()` rồi mới `raise AppError`. Đã dính 2 lần (Phase 3). Sau `commit`, khoá `FOR UPDATE` và `set_actor` đều mất: lấy lại nếu còn ghi tiếp.

### S04 · Phân quyền: token → vai trò → ma trận, và 403 vs 404
**Mọi route phải có quy tắc trong `tests/test_permission_matrix.py::RULES`** (route mới không khai báo sẽ làm test đỏ). Vai trò luôn lấy từ DB theo token, không tin claim trong token. Manager chỉ đọc đơn/duyệt giá/quản trị xưởng; ghi trên đơn là của Staff. Sau khi thêm/đổi endpoint: cập nhật RULES + bảng quyền trong `docs/FE_API_GUIDE.md`.

Sai vai trò → 403 (`require_roles`). Đúng vai trò nhưng bản ghi không phải của mình → **404** (không lộ tồn tại). Staff: `WorkshopAccess.order(...)`; khách: `get_owned`. Mọi endpoint mới phải có test cho: 401, 403 (4 vai trò còn lại), 404 (người khác), thành công.

### S05 · Tiền, số thập phân, JSON
Tiền = VND số nguyên, làm tròn 100đ; **cọc làm tròn LÊN** (`payment_rules.resolve_deposit`). API trả Decimal dạng chuỗi. `Decimal`/`Enum` **không** tự serialize vào JSONB (audit, `discount_tiers`): đổi sang `str`/`.value`/số trước (`manager_catalog._plain`). Pricing Engine là hàm thuần (`services/pricing.py`) – đừng tính giá ở chỗ khác.

### S06 · Kiểm chứng trên Supabase thật (bắt buộc sau khi code xong)
```bash
cd BE && source .venv/bin/activate
python -m pytest tests/test_<file>.py -q -p no:cacheprovider      # file mới trước
python -m pytest -q -p no:cacheprovider                           # rồi TOÀN BỘ suite (≥15 phút → chạy nền)
```
Test chạy bằng `TestClient` nhưng nói chuyện với DB Supabase thật, trigger thật, AI thật, PDF thật; chỉ Storage dùng `InMemoryStorage` (trừ `test_storage_live.py`). Sau khi chạy: kiểm tra DB **không còn** bản ghi `pytest_*` và cấu hình thật (bảng giá active, `order_types_enabled`) còn nguyên. Ngoài test, thử vài lệnh gọi API thật qua Swagger/`TestClient` bằng tài khoản demo khi đổi hành vi quan trọng. Nếu **không chạy được** (thiếu `.env`, mất mạng) phải nói rõ là chưa kiểm chứng, không viết "đã pass".

### S07 · Thiết kế test trên DB dùng chung
- Mọi dữ liệu test mang tiền tố `pytest_` (email `pytest_*@example.com`, mã `pytest_*`) để `conftest._cleanup` xoá. **Thêm bảng mới ⇒ cập nhật `_cleanup`.** Bảng tham chiếu `orders` **không cascade** (ví dụ `payments`, `production_jobs`) phải xoá **trước** `orders`; robot/pricing test xoá sau job.
- Test nào đổi cấu hình toàn cục (bảng giá active, `system_settings`) phải có fixture **khôi phục** (xem `pricing_guard`); `_cleanup` còn tự kích hoạt lại phiên bản thật.
- **Không chạy 2 phiên pytest song song** trên cùng DB (cleanup đầu/cuối phiên xoá dữ liệu của nhau).
- Mỗi test tạo robot/kỹ thuật viên riêng để không đụng robot/người thật và không xung đột nhau.
- Mỗi tính năng cần: unit (luật thuần) + API + phân quyền + chuyển trạng thái + validation + idempotency/đồng thời (dùng nhiều `TestClient` trong `ThreadPoolExecutor`).
- Giả lập thời gian bằng cách sửa cột trong DB (ví dụ `valid_until` về quá khứ), không `sleep`.
- Test mô phỏng bước của phase sau (Technical Staff…) bằng `UPDATE` hợp lệ trực tiếp vào DB, ghi chú rõ lý do.

### S08 · Adapter tích hợp có nhãn MOCK
Cổng ngoài (thanh toán, vận chuyển, email, SMS) đi qua một "port" trong `integrations/` + adapter MOCK. Mọi output mang `mode="MOCK"`; kết quả tới hệ thống **qua cùng đường như bản thật** (ví dụ webhook ký HMAC, idempotent theo `(gateway, gateway_txn_id)`; nút mock chỉ phát lại webhook ấy). Khi thêm cổng thật: chỉ thêm adapter + khoá riêng, không đổi nghiệp vụ.

### S09 · Audit và thông báo
Mọi thay đổi quan trọng gọi `services.audit.record(actor_id, action, entity_type, entity_id, old, new, reason, ip)`; `actor_id=None` cho hệ thống. Thông báo gọi `services.notifications.notify(...)` (hiện chỉ log; Phase 4 gửi thật) – giữ nguyên chữ ký để sau không phải sửa chỗ gọi.

### S10 · Lớp ORM và Pydantic – các bẫy đã gặp
- Cột Postgres `ENUM` phải khai bằng `ENUM(..., name=..., create_type=False)` trong ORM (psycopg3 không tự ép `varchar` → enum khi INSERT/UPDATE).
- Cột `GENERATED` (`quotations.final_total`, `adjustment_pct`): khai `FetchedValue`, **không bao giờ set**, `refresh()` sau khi ghi.
- PATCH: `model_dump(exclude_unset=True)` vẫn chứa giá trị `null` người dùng gửi; quy ước dự án: **`null` = không đổi** (`_apply` bỏ qua `None`). Muốn xoá chuỗi → gửi `""`.
- Gán `out.options = [dict…]` sau `model_validate` gây `PydanticSerializationUnexpectedValue`: dựng đúng model con.
- Python 3.11 (Docker) vs 3.14 (local): method tên `list` che builtin trong annotation → dùng `from __future__ import annotations`.
- FastAPI `Query(alias="status")` cho tham số trùng tên builtin/biến.

### S11 · Seed dữ liệu thật
`scripts/seed_workshop_data.py`: `ON CONFLICT DO NOTHING`, có `--dry-run` (rollback), chạy 2 lần không ghi gì thêm, không ghi đè thứ Manager đã sửa. Thêm dữ liệu khởi điểm → ghi giả định ở đầu script **và** mục 8 của `PROJECT_STATUS.md`.

### S12 · Git hygiene
Chỉ commit khi được yêu cầu; commit thông điệp tiếng Anh `feat:/fix:/docs:` mô tả phạm vi, **không** thêm trailer AI. Không `git add -A` bừa (tránh `.env`, `.vscode/`). Không viết lại lịch sử đã đẩy lên `origin`; nếu lỡ lệnh `--force` cần thiết thì tạo nhánh backup trước, dùng `--force-with-lease=<ref>:<sha>` và hỏi chủ dự án. Mọi thay đổi trên GitHub phải **không bắt đồng đội chạy thêm lệnh**: nếu lỡ làm thì khôi phục về đúng SHA cũ.

### S13 · Hỏi người dùng đúng lúc
Hỏi khi: đổi schema, thiếu secret/tài liệu nguồn, quy tắc nghiệp vụ mơ hồ ảnh hưởng tiền/trạng thái, hành động không thể hoàn tác. **Không** hỏi khi có mặc định hợp lý: chọn, làm, và ghi vào danh sách giả định. Câu hỏi gồm 2 phương án + khuyến nghị + tác động.

### S14 · Đồng bộ tài liệu sau mỗi thay đổi (không được quên)
Sau khi code xong, cập nhật **trong cùng lượt**:
1. `PROJECT_STATUS.md`: mục 1 (trạng thái/ngày), 3 (bảng phase), 6 (kết quả test thật), 7 (dữ liệu DB nếu đổi), 8 (giả định mới), 9 (changelog), 10 (việc kế tiếp).
2. `docs/FE_API_GUIDE.md` nếu endpoint/field/luồng/mã lỗi đổi (FE đọc file này). Swagger: mỗi endpoint phải có `summary` tiếng Việt kèm mã FR/UC.
3. `README.md` (kiến trúc/lệnh chạy) nếu có đổi.
4. File này nếu rút ra kỹ năng/bài học mới (mục 8).
5. Bộ nhớ riêng của AI (nếu có) chỉ ghi điều **không** suy ra được từ repo.

### S15 · Mẫu báo cáo cuối phase (trung thực)
Yêu cầu đã làm · file tạo/sửa · test đã chạy + kết quả (số passed/failed, môi trường) · test **chưa** chạy · giới hạn · việc tồn · giả định cần xác nhận · việc người dùng cần làm. Không nói "hoàn hảo/không lỗi"; nói "đã kiểm chứng X bằng Y".

### S16 · Môi trường và công cụ
- Chạy lệnh trong `BE/` (uvicorn, pytest, alembic, seed). Từ thư mục gốc repo sẽ lỗi `No module named 'app'`.
- venv: `BE/.venv` (Linux: `source .venv/bin/activate`; Windows: `.venv/Scripts/python.exe`). Python 3.14 local, 3.11 khi deploy: tránh cú pháp/thư viện chỉ có ở bản mới.
- Heredoc có dấu nháy trên Windows/Git Bash dễ lỗi: dùng công cụ ghi file thay vì `cat <<`.
- Test nặng (Tokyo pooler, ~1 giây/lệnh gọi) → chạy nền, kiên nhẫn; đừng chạy lại cả suite vì một lỗi nhỏ: sửa rồi chạy riêng test đó, cuối cùng mới chạy toàn bộ.
- Xem route thật: `python -c "from app.main import app; print(sorted(app.openapi()['paths']))"` (không cần DB).

### S17 · Khi test fail
Đọc lỗi → xác định là **lỗi code** hay **lỗi test** (sai giả định). Lỗi code: sửa gốc, thêm test chặn tái diễn, ghi vào mục 8 nếu là bài học. Không "sửa" bằng cách nới lỏng assert; không xoá test. Test xung đột dữ liệu thật → dừng và hỏi.

## 4. Checklist trước khi nói "xong"

- [ ] Kế hoạch đã được duyệt (hoặc có uỷ quyền rõ ràng) và giả định đã ghi.
- [ ] Không đụng `FE/`, `Mobile/`, secret, schema (hoặc đã được duyệt).
- [ ] Endpoint mới có `summary` + mã lỗi `responses`; schema Pydantic tách khỏi ORM.
- [ ] Test: unit + API + phân quyền + trạng thái + validation (+ đồng thời nếu có tiền/trạng thái).
- [ ] Chạy trên Supabase thật: file mới pass, **toàn bộ suite pass**, DB sạch `pytest_*`, cấu hình thật nguyên vẹn.
- [ ] `PROJECT_STATUS.md`, `docs/FE_API_GUIDE.md`, README cập nhật.
- [ ] Báo cáo: đã chạy / chưa chạy / giả định / việc người dùng cần làm. Chưa commit nếu chưa được yêu cầu.

## 5. Bản đồ nhanh "muốn làm X thì sửa ở đâu"

| Muốn | Đụng vào |
|---|---|
| Thêm endpoint | `api/v1/<nhóm>.py` (route mỏng) + `api/*schemas.py` + `services/<nhóm>.py` + đăng ký trong `main.py` (và `TAGS`) |
| Luật nghiệp vụ thuần | `domain/*.py` (+ `tests/test_*rules.py`, không cần DB) |
| Truy vấn mới | `repositories/*.py` |
| Cột/bảng mới đã có trong DB | `models/*.py` (ORM chỉ ánh xạ; **không** tạo schema ở đây) |
| Dữ liệu khởi điểm | `scripts/seed_workshop_data.py` |
| Cổng ngoài | `integrations/` (port + adapter MOCK) |
| Thông báo | `services/notifications.py` (hook) |
| Test | `tests/test_api_*.py`; dọn dữ liệu ở `tests/conftest.py::_cleanup` |

## 6. Các luồng cốt lõi để nhớ

`DRAFT → SUBMITTED → ACCEPTED → (phác thảo → báo giá → gửi) → AWAITING_PRIVACY → QUOTED → AWAITING_DEPOSIT → CONFIRMED (+PENDING_SCHEDULE) → SCHEDULED → … (Phase 4) …`
Chi tiết, sơ đồ và endpoint từng bước: `docs/FE_API_GUIDE.md` mục 4–7.

## 7. Điều AI thường làm sai ở dự án này (tránh)

1. Quên cập nhật `PROJECT_STATUS.md`/`FE_API_GUIDE.md` sau khi code → người sau mất phương hướng.
2. Chạy lệnh ở thư mục sai (gốc repo thay vì `BE/`).
3. Tự commit/push, thêm trailer Co-Authored-By, `--force` lên nhánh chung.
4. Báo "pass" khi mới chạy test không-DB hoặc mới chạy một phần.
5. Thêm bảng/cột tham chiếu `orders` mà quên cập nhật `_cleanup` → test sau lỗi FK, rác DB thật.
6. Raise lỗi sau khi đã đổi dữ liệu cần giữ (S03).
7. Hard-code dữ liệu mẫu trong code thay vì seed (S11).
8. Mô phỏng thanh toán/robot mà không gắn nhãn `MOCK`.

## 8. Nhật ký kỹ năng & bài học bổ sung (thêm vào cuối, mới nhất ở dưới)

> Mẫu: `### YYYY-MM-DD · Tên ngắn` — **Bối cảnh** (chuyện gì xảy ra) · **Cách làm đúng** · **Lệnh/đoạn code mẫu nếu có**. Nếu đủ quan trọng thì nâng lên thành skill card ở mục 3.

### 2026-10-17 · Test trên DB dùng chung làm lộ dữ liệu test cho người dùng thật
**Bối cảnh:** danh mục test (giấy/bút/mẫu chữ `pytest_*`) công khai trong lúc suite chạy; một khách thật đặt đơn bằng bút test; bước dọn cuối vi phạm khoá ngoại và **cả `_cleanup` bị huỷ** (để lại 303 tài khoản + hàng trăm đơn test). Ngoài ra chạy 2 phiên pytest chồng nhau làm mất setting `order_types_enabled` và làm đỏ 25 test. **Cách làm đúng:** (1) không bao giờ chạy hai pytest cùng lúc, kể cả một lệnh `-k` nhỏ (fixture session autouse vẫn dọn DB); (2) `_cleanup` đổi tên + tắt (`orphan_…`) mọi mục danh mục test còn được đơn thật tham chiếu thay vì xoá; (3) khuyến nghị dùng **dự án Supabase riêng cho test**; (4) sau mỗi lần chạy kiểm tra DB: không còn `pytest_*`, `order_types_enabled` còn đủ.

### 2026-10-16 · Hết hạn báo giá bị rollback (Phase 3)
**Bối cảnh:** `expire_if_overdue` đổi báo giá sang `EXPIRED` rồi API trả 409; rollback của request xoá mất việc hết hạn. **Cách làm đúng:** `expire_and_persist` (commit rồi mới raise); xem S03.

### 2026-10-16 · Audit bảo mật bị mất khi trả 422 (Phase 3)
**Bối cảnh:** `PAYMENT_MISMATCH` (số tiền/mã đơn sai trong webhook đã ký) được ghi audit rồi raise → mất. **Cách làm đúng:** `session.commit()` trước `raise` cho mọi audit về sự kiện đáng ngờ.

### 2026-10-16 · Test thanh toán/lập lịch cần dọn bảng không cascade
**Bối cảnh:** `payments`, `production_jobs` tham chiếu `orders` không `ON DELETE CASCADE` → xoá đơn test lỗi FK. **Cách làm đúng:** xoá chúng trước trong `_cleanup`, rồi robot/pricing test (S07).

### 2026-10-16 · Đổi bảng giá trong test phải trả lại bản thật
**Bối cảnh:** `POST /manager/pricing-config` tắt phiên bản thật, bật phiên bản mới. **Cách làm đúng:** fixture `pricing_guard` + `_cleanup` xoá phiên bản do tài khoản test tạo và bật lại phiên bản lớn nhất còn lại.

### 2026-10-16 · Git: không viết lại lịch sử chung
**Bối cảnh:** muốn gỡ dòng `Co-Authored-By` khỏi commit đã vào `main`. **Cách làm đúng:** đánh giá ảnh hưởng đồng đội trước; nếu chỉ lỡ đẩy `--force` lên `BE`, khôi phục lại đúng SHA cũ bằng `--force-with-lease=BE:<sha mới>` để không ai phải chạy thêm lệnh; chủ dự án quyết định có viết lại `main` hay không.

### 2026-10-18 · Bảng mới tham chiếu robot/tài khoản mà không cascade (Phase 4a)
**Bối cảnh:** `incidents` tham chiếu `robots` và `accounts` không `ON DELETE CASCADE` (còn `calibrations`, `job_events` thì cascade theo job); `job_events.incident_id` lại trỏ ngược tới `incidents`. Xoá robot/tài khoản test mà không xoá `incidents` trước sẽ vi phạm khoá ngoại và huỷ cả `_cleanup`. **Cách làm đúng:** thứ tự dọn là jobs (kéo theo `job_events`, `calibrations`) → `incidents` (theo `reported_by` hoặc robot test, kèm audit `entity_type='incident'`) → robots → accounts. Thêm bảng mới ⇒ đọc `ON DELETE` của nó trước khi sửa `_cleanup` (S07).

### 2026-10-18 · Kiểm tra test có thật sự bắt lỗi (kiểm tra đột biến, rẻ)
**Bối cảnh:** bộ test mới pass ngay lần đầu; pass ngay không chứng minh test có giá trị. **Cách làm đúng:** với luật quan trọng (ở đây BR-19), tạm bỏ một dòng bảo vệ trong code (ví dụ `sed -i`), chạy đúng test liên quan, thấy nó **đỏ**, rồi khôi phục (`cp` bản sao lưu) và kiểm tra bằng `grep` rằng dòng bảo vệ đã về. Không để code đột biến lại trong working tree.

### 2026-10-18 · Ngắt pytest bằng SIGINT, không SIGKILL
**Bối cảnh:** phải dừng suite đang chạy trên Supabase thật. **Cách làm đúng:** gửi `kill -INT` tới tiến trình `python -m pytest` thật (không phải shell bọc ngoài: `pgrep -f "^\.venv/bin/python -m pytest"`), để fixture cuối phiên chạy `_cleanup` và trả `order_types_enabled`; sau đó kiểm tra DB không còn `pytest_*`, bảng giá thật còn đúng 1 bản active, `order_types_enabled` còn đủ.

### 2026-10-18 · Codespace dừng giữa lúc chạy test ⇒ DB dùng chung bị bỏ dở
**Bối cảnh:** phiên làm việc kết thúc khi suite đang chạy trên Supabase. Dọn dẹp cuối phiên không chạy: còn 167 tài khoản + 60 đơn + 51 mục danh mục `pytest_*`, và **`system_settings.order_types_enabled` bị mất** (suite xoá nó lúc chạy), nghĩa là khách thật có thể đặt loại đơn R&D OT-2 đang bị tắt. Log nằm trong thư mục tạm cũng mất theo. **Cách làm đúng:** (1) việc đầu tiên của phiên mới, trước mọi việc khác, nếu nghi suite từng bị cắt ngang: chạy `.venv/bin/python scripts/recover_after_interrupted_tests.py` (khôi phục setting + `_cleanup`, in số liệu kiểm tra); (2) không báo "test đã chạy xong" khi chỉ có tiến trình nền "đã dừng"; (3) chỉ bắt đầu một lần chạy dài khi biết người dùng còn ở đó, và nói rõ rủi ro này.

### 2026-10-18 · Dữ liệu test còn sót làm lệch test khác trong cùng một phiên (robot cho gợi ý lịch)
**Bối cảnh:** `test_queue_suggestion_and_schedule_validation` pass khi chạy riêng nhưng đỏ ở đúng ~31% mỗi lần chạy cả suite (`assert 188 in [46, 179, 180, 181, 182]`). Gợi ý lịch của Manager chỉ trả tối đa 5 robot (`MAX_SUGGESTIONS`), cùng giờ rảnh thì xếp theo id nhỏ; fixture `robot` để robot test `AVAILABLE` tới hết phiên (dữ liệu test chỉ xoá lúc bắt đầu/kết thúc phiên), và các test Phase 4b thêm đủ robot rảnh để robot của test này bị cắt. **Cách làm đúng:** (1) fixture tạo dữ liệu "dùng chung toàn cục" (robot, giấy, bút...) phải trả về trạng thái trung tính sau mỗi test (`yield` + `update ... status='MAINTENANCE'`), không chờ `_cleanup`; (2) test phụ thuộc vào "tập hợp toàn bộ X trong DB" dễ vỡ khi thêm test ở file khác — thêm test mới thì chạy cả suite; (3) khi chạy cả suite để tìm lỗi lẻ, **lưu toàn bộ log vào file** (`-v --tb=long > file`), đừng `| tail -40`: traceback nằm cuối phiên và chỉ cần một lần chạy để biết nguyên nhân.

### 2026-10-22 · Vận đơn/incidents không cascade; mã vận đơn trong fake phải duy nhất (Phase 4c-2)
**Bối cảnh:** `shipments` tham chiếu `orders` không `ON DELETE CASCADE`; fake GHN trả cùng một mã vận đơn ở nhiều test làm vỡ unique `(carrier, waybill_code)` (lỗi chung `409 CONFLICT`, khó đoán nguyên nhân). **Cách làm đúng:** `_cleanup` xoá `shipments` (và audit `entity_type='shipment'`) **trước** payments/orders/robots/accounts; fake của hãng nhận tham số mã và test dùng uuid riêng cho mỗi lần.

### 2026-10-22 · Cổng thật mở thêm cửa: đóng cửa webhook mô phỏng
**Bối cảnh:** webhook thanh toán mô phỏng không cần chữ ký hợp lệ của cổng thật; để mở khi `PAYMENT_MODE=sandbox|live` thì ai biết mã giao dịch cũng "trả tiền" được. **Cách làm đúng:** khi thêm adapter thật, rà mọi đường vào MOCK và tắt chúng ở chế độ thật (`MOCK_WEBHOOK_DISABLED`, `mock-event` chỉ cho vận đơn MOCK), kèm test. Callback "tiền về" cho giao dịch đã huỷ không được xác nhận đơn: ghi `needs_refund` + `PAYMENT_ORPHAN` và vẫn trả cổng "đã nhận".

### 2026-10-22 · Adapter chưa chạy với bên thật phải tự nói thẳng
**Bối cảnh:** tài liệu VNPay/MoMo/GHN/GHTK không truy cập được lúc viết; test chỉ chứng minh adapter nhất quán với chính nó (HTTP giả `MockTransport`). **Cách làm đúng:** mỗi adapter có ghi chú "VERIFICATION STATUS" liệt kê điều phải xác nhận ở lần chạy sandbox đầu; báo cáo cuối phase ghi rõ "chưa chạy với bên thật"; mặc định giữ mock.

### 2026-10-22 · Chạy nhanh bằng Postgres Docker cục bộ
**Bối cảnh:** Supabase ở Tokyo ~1 s/truy vấn, suite ~70 phút và Codespace tự tắt sau 30 phút im lặng. **Cách làm đúng:** vòng lặp sửa-chạy dùng Postgres Docker cục bộ (chạy migration lên đó, đặt `DATABASE_URL`/`JWT_SECRET` trong môi trường, không sửa `.env`): 476 test trong ~2m20s. Vẫn chạy toàn suite trên Supabase khi chủ dự án ở lại, trước khi báo "đã kiểm chứng" (S06).

### 2026-10-22 · Mọi phiên pytest đều dọn `pytest_*`, kể cả test thuần; cổng thật chặn IP nước ngoài
**Bối cảnh:** khi đang giữ một đơn `pytest_` sống để chủ dự án trả tiền thật qua VNPay sandbox, tôi chạy thêm một lệnh pytest (test thuần, không DB): fixture `_cleanup` của `conftest.py` vẫn chạy và xoá đơn đang dùng, làm mất giao dịch giữa chừng. Ngoài ra `sandbox.vnpayment.vn/merchant_webapi` (API truy vấn) `ConnectTimeout` từ Codespace và Render dù trang thanh toán và IPN vẫn chạy. **Cách làm đúng:** (1) khi cần giữ dữ liệu `pytest_` sống cho thử nghiệm tương tác, không chạy bất kỳ phiên pytest nào khác cho tới khi xong; (2) thử cổng thật bằng một test tạm in `pay_url` rồi chờ DB đổi trạng thái (quy trình ở `PROJECT_STATUS.md` 10.0), xoá file tạm sau đó; (3) đừng giả định BE gọi ra được API của cổng từ nước ngoài: coi IPN là đường chính, truy vấn ngược là dự phòng, và hỏi nhà cung cấp về whitelist IP; (4) mọi lỗi gọi cổng phải ghi log nguyên nhân (đã có trong `vnpay.py`, `momo.py`).
