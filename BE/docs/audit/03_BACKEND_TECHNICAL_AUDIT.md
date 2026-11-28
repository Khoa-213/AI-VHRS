# 03 — Kiến trúc, database, bảo mật, độ tin cậy

Đường dẫn tính từ `BE/`. Mã vấn đề tra ở `05_ISSUES_AND_RECOMMENDATIONS.md`.

## 1. Kiến trúc

FastAPI + SQLAlchemy 2 + PostgreSQL (Supabase) + Pydantic v2, một tiến trình uvicorn trên Render. Bốn tầng: `api/v1` (route mỏng) → `services` (nghiệp vụ) → `repositories` → `models`; luật thuần không cần DB nằm ở `domain/`. Cổng ngoài nằm ở `integrations/` sau các adapter có chế độ mock / sandbox / live.

Đánh giá: phân tầng rõ và được tuân thủ. Kiến trúc này đủ cho quy mô một xưởng; không cần microservices hay message broker.

| Tiêu chí | Nhận xét |
|---|---|
| Phân tách trách nhiệm | Tốt. Route không chứa nghiệp vụ; luật tiền, hoàn tiền, lịch, ảnh là hàm thuần có test riêng |
| Phụ thuộc | Hợp lý. `robot_agent` dùng lại `app/services/motion` và `core/production_signing` để hai bên tính cùng một kết quả |
| Module quá lớn | `sketch_geometry.py` 900 dòng, `quotations.py` 627, `services/studio.py` 617, `stroke_ai/recovery.py` 581 |
| Code chết | Nhánh Manager trong `staff_orders._intake_order`; `RobotStatus.BUSY`; `ForceTable` ở agent; `FE/src/services/robot.ts`; trợ lý studio cũ (`ai/tools.py`) |
| API không client nào gọi | Showcase, 8 route `/styles`, ảnh và hồ sơ vật tư, so sánh phác thảo, sửa nét phía server, vùng phục dựng, lệnh robot phía Manager (xem AR-07) |
| Cấu hình cứng | Ít. Ngoại lệ: giờ nhận hàng chép cứng ở FE; cổng 20003/20004 ở agent |

## 2. Database

Số liệu từ `database/AI-VHRS_database_full.sql` (đang ở revision 0032, khớp với kết quả `alembic upgrade head` tôi chạy trên DB trống): 139 CHECK, 139 khoá ngoại, 18 chỉ mục duy nhất (đa số theo điều kiện), 2 ràng buộc EXCLUDE, 20 trigger, RLS bật trên mọi bảng.

Điểm tốt:
- Tiền dùng `numeric(14,0)` và `Decimal`, bước 100 đồng.
- Mỗi quy tắc "chỉ một" đều có chỉ mục: một báo giá sống mỗi đơn, một bản final, một thanh toán thành công mỗi loại, một job đang chạy mỗi đơn, một lần chạy mở mỗi robot, một gói sản xuất hiệu lực.
- Chống trùng lịch bằng `EXCLUDE USING gist`, không chỉ bằng kiểm tra trong Python.
- Trạng thái đơn do trigger quyết định, lịch sử trạng thái ghi bằng trigger.

Điểm yếu:
- Trạng thái báo giá, job, lệnh robot chỉ kiểm trong Python.
- `audit_logs` không có trigger chống sửa / xoá; `sketch_approvals` và `production_snapshots` chỉ chặn `UPDATE`, khoá ngoại vẫn `ON DELETE CASCADE` (SR-02).
- Migration `0001` là no-op trên Supabase vì schema gốc được áp tay; `target_metadata=None` nên không có công cụ nào phát hiện lệch giữa ORM và database (AR-06).
- Hai file SQL để nộp: `AI-VHRS_database_full.sql` (0032) và `AI-VHRS_database.sql` (0013, không do script sinh). `PROJECT_STATUS.md` mục 2 còn ghi file tổng ở revision 0017.

## 3. Giao dịch, đồng thời, idempotency

- Một phiên DB mỗi request, commit khi thành công (`db/session.py:27-36`). Pool 3 + 2.
- Thứ tự khoá cố định: đơn rồi thanh toán. Xếp lịch có savepoint và thử lại một lần khi deadlock.
- Email và SSE chỉ gửi sau commit.
- Idempotency: webhook thanh toán theo `(gateway, gateway_txn_id)`; lệnh robot theo `(created_by, idempotency_key)`; lượt chat AI theo `client_ref`; áp dụng đề xuất AI hai lần trả kết quả cũ.

Vấn đề:
- Gọi HTTP ra ngoài khi đang giữ khoá dòng: tạo / huỷ link payOS, đọc file từ Storage (timeout 60 giây), gọi LLM (tới 30 giây mỗi lần, nhiều lần mỗi lượt). Với pool 5 kết nối, vài request chậm là API đứng (AR-04, AI-02).
- Bốn webhook khai báo `async def` nhưng chạy SQLAlchemy đồng bộ, tức chặn vòng lặp sự kiện của tiến trình duy nhất; không có `lock_timeout` hay `statement_timeout` (AR-02).
- Xử lý ảnh bằng OpenCV và dựng PDF chạy đồng bộ trong request (AR-04).

## 4. Xác thực và phân quyền

| Phần | Hiện trạng |
|---|---|
| Mật khẩu | bcrypt 10 vòng; tối thiểu 8 ký tự có chữ và số; sai 5 lần khoá 15 phút |
| Token | JWT HS256, access 30 phút, refresh 7 ngày, gắn phiên phía server |
| Thu hồi | Mỗi request đọc lại tài khoản + phiên, nên khoá, đăng xuất, đổi vai trò có hiệu lực ngay; vai trò trong token không được tin |
| Vai trò | `require_roles()` trên từng endpoint; `test_every_route_has_a_permission_rule` bảo đảm không route nào thiếu luật |
| Theo bản ghi | Khách: `get_owned`. Xưởng: `WorkshopAccess`. Kỹ thuật viên: `job.technician_id`. Sai chủ trả 404 |
| Webhook | Chữ ký HMAC của từng cổng, so sánh bằng `compare_digest` |
| Agent | Khoá `vhrs_ak_…`, chỉ lưu SHA-256 |

Lỗ hổng tìm thấy:
- Đăng ký không xác minh email + đăng nhập Google khớp theo email: kẻ xấu đăng ký trước email của nạn nhân, sau đó vẫn giữ được mật khẩu và phiên khi nạn nhân vào bằng Google (`services/auth.py:89-108`, SR-01).
- Khoá agent vẫn hành động thay kỹ thuật viên đã bị khoá (`api/deps.py:35-44`, TP-06).
- Phát lại lượt chat AI chạy trước khi kiểm chủ đơn (`services/ai/assistant.py:315-318`, AI-05).
- Thanh toán MOCK tự xác nhận (PP-01).
- `JWT_SECRET` không có kiểm độ dài, và là gốc dẫn xuất cho HMAC của OTP, webhook mock và vé xem 3D (SR-04).
- Quên mật khẩu trả lời nhanh hơn khi email không tồn tại, vì gửi mail đồng bộ trong request (SR-03).

## 5. Tải file và dữ liệu cá nhân

- Server tự đặt tên file bằng UUID, kiểm tiền tố đường dẫn, đọc loại file từ nội dung, bucket riêng tư + link ký có hạn. Ảnh danh mục ở bucket công khai tách riêng.
- Kích thước chỉ kiểm sau khi file đã lên Storage. `cv2.imdecode` chạy trước mọi giới hạn số điểm ảnh: một PNG nén tốt có thể giải nén thành hàng GB RAM (AI-11).
- Xoá ảnh khách sau 90 ngày chỉ chạy thật khi `photo_purge_enabled=true` và tác vụ nền được bật. Bản chép chữ từ ảnh (`htr_readings`) và nội dung trong đề xuất AI không có tác vụ xoá (AI-07, SR-06).
- Không tìm thấy secret nào trong cây mã nguồn hay lịch sử git theo các mẫu thường gặp; `.env` chưa từng được commit. `PROJECT_STATUS.md` ghi còn treo việc "xoay mật khẩu DB và các secret đã lộ trong chat" (SR-07).

## 6. Nhật ký, lỗi, quan sát

- 97 mã hành động qua `audit.record`, gồm thay đổi giá, tồn kho, phân công, lệnh robot, đề xuất AI.
- Thiếu: đăng nhập thành công / thất bại, đăng xuất, đổi mật khẩu; Staff nhận đơn.
- Không có `logging.basicConfig` / `dictConfig` ở đâu, nên `log.info` không được in. Không có mã request, Sentry hay số đo.
- Không có handler cho `Exception`: lỗi 500 trả chữ thô, không có header CORS, nên web hiểu thành lỗi CORS (AR-05).

## 7. Dịch vụ ngoài: timeout, thử lại, dự phòng

| Dịch vụ | Timeout | Thử lại / dự phòng |
|---|---|---|
| LLM | 30 giây mỗi lần gọi | Chuyển hãng khác, chạy lại cả lượt; không thử lại cùng hãng; không có hạn tổng cho lượt |
| Đọc chữ từ ảnh | 90 giây | Gemini rồi Claude |
| payOS / VNPay / MoMo | 15 giây | `refresh` hỏi lại cổng khi IPN trễ |
| GHN | 15 giây | Bảng phí dự phòng khi tắt tích hợp |
| Storage | 60 giây | Không |
| SMTP | 10 giây | Tác vụ nền gửi lại mail lỗi |
| SMS | 10 giây | Không |

## 8. Triển khai

- `render.yaml`: Docker, một worker, chạy bằng người dùng không phải root, `alembic upgrade head` trước khi deploy, kiểm sức khoẻ ở `/api/v1/health`.
- `render.yaml` không khai `PAYMENT_MODE`, `BACKGROUND_JOBS_ENABLED`, `MOTION_VALIDATION_REQUIRED`, `PRODUCTION_SIGNING_KEY`, SMTP. Mặc định trong code của ba biến đầu là `mock`, `false`, `false` (AR-03).
- Giới hạn tần suất, SSE, khung hình robot sống, cache khoá agent đều nằm trong RAM của một tiến trình. Chạy hai tiến trình sẽ hỏng; mỗi lần deploy làm mất khung hình và ngắt SSE.
- Swagger đang bật ở production.
- Không có mục sao lưu / khôi phục trong `DEPLOY.md`; rollback migration không tự động.

## 9. Kiểm thử

- BE: 89 file, 1.099 test. Bao phủ tốt các luồng tiền, trạng thái, phân quyền, đồng thời (có test hai request cùng lúc cho cọc, thanh toán cuối, xếp lịch, gửi đơn).
- `robot_agent`: 187 test với SDK giả, không cần phần cứng.
- Không có test end-to-end qua trình duyệt cho luồng chính; không có CI.
- Vấn đề lớn nhất: quy trình của dự án yêu cầu chạy test trên Supabase thật. `tests/conftest.py:49-147` xoá theo mẫu trên hơn 30 bảng; `:192-209` xoá `system_settings.order_types_enabled` suốt phiên rồi mới chèn lại (AR-01). Đợt audit này chứng minh bộ test chạy đạt trên Postgres cục bộ trong 3 phút 40 giây, nên không còn lý do kỹ thuật để chạy trên DB thật.
