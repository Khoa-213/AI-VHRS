# AI-VHRS — Tổng quan kết quả audit (2026-11-27)

Phạm vi: nhánh `BE` tại commit `691f361`. Backend `BE/` (34.341 dòng, 33 router, 272 endpoint, 32 migration), `robot_agent/` (8.413 dòng), phần `FE/` và `DesktopApp/` cần để xác minh API, và tài liệu trong `BE/docs/`.

Đợt audit này không sửa code, không đổi schema, không commit. Không lệnh nào được gửi tới robot, cổng thanh toán hay Supabase thật.

> **Cập nhật 2026-11-28.** Nội dung dưới đây là kết quả audit trước khi sửa. Sau đó chủ dự án đã duyệt và phần lớn mục P0 / P1 về phần mềm đã được sửa (BE 1.149 test đạt trên Postgres cục bộ, agent 197). Xem trạng thái từng vấn đề và các thay đổi hành vi ở `09_APPROVAL_AND_IMPLEMENTATION_PLAN.md` mục 6, điểm cập nhật ở `07_ENTERPRISE_READINESS_ASSESSMENT.md` mục 4 (6,3 → 6,8; ba kết luận sẵn sàng không đổi). Chưa commit, chưa chạy trên Supabase, chưa chạy robot thật.

## 1. Kết luận

AI-VHRS là một hệ thống thật, không phải khung code: luồng đơn hàng từ tạo đơn tới giao hàng đã có đủ code ở BE và đã nối vào web, có 1.094 test tự động và ràng buộc ở mức database. Phần phần mềm đủ vững để bảo vệ đồ án.

Điểm yếu nằm ở đầu ra vật lý: **robot thật chưa từng viết xong một trang**. Bằng chứng duy nhất là một dòng changelog ngày 2026-10-25 (chạy nhấc bút 45/45 nét, viết thật 2 nét đầu). Mọi phần sau đó (gói ký, nút REAL trên máy trạm, giao robot cho kỹ thuật viên) chưa chạy trên robot.

| Mức sẵn sàng | Kết luận | Lý do chính |
|---|---|---|
| Academic Demo Ready | **Conditionally Ready** | Luồng web chạy được; phần robot phải có một lần viết trọn trang hoặc công khai là mô phỏng + video |
| Enterprise Pilot Ready | **Not Ready** | 4 điều kiện chặn: an toàn robot (TP-01, TP-02, RB-02), thanh toán tự xác nhận (PP-01), robot chưa viết xong trang (RB-01) |
| Production Ready | **Not Ready** | Thêm: một tiến trình duy nhất, test chạy trên DB thật, chưa có backup/khôi phục, chưa có số đo chất lượng |

Điểm tổng theo trọng số tham chiếu: **6,3 / 10** (chi tiết ở `07_ENTERPRISE_READINESS_ASSESSMENT.md`). Điểm này không bù được các điều kiện chặn ở trên.

## 2. Đã kiểm chứng bằng chạy thật trong đợt audit

Mọi lệnh chạy trên Postgres 18 tạm ở máy cục bộ, biến môi trường ghi đè để không chạm Supabase, payOS, Google hay LLM.

| Việc | Kết quả |
|---|---|
| `alembic upgrade head` trên DB trống | Lên `0032` sạch, 56 bảng |
| `scripts/seed_workshop_data.py` | Chạy được, idempotent |
| Bộ test BE (1.099 test) | **1.091 passed, 5 skipped, 3 failed** trong 3 phút 40 giây |
| 3 test hỏng | Đều ở `tests/test_catalog_media.py`, do tôi để trống `SUPABASE_URL` nên `core/media.py:public_url` trả `None`. Không phải lỗi logic |
| Bộ test `robot_agent` (187 test, SDK giả, không phần cứng) | **183 passed, 3 skipped, 1 treo vô hạn** trên macOS (RB-11) |
| FE `tsc -b`, `i18n:check`, `oxlint` | Đạt; lint có 4 cảnh báo |

Chưa kiểm chứng được: robot thật, cổng thanh toán thật, GHN thật, LLM thật, cấu hình trên Render, DesktopApp (máy không có Flutter).

## 3. Luồng nghiệp vụ

| Luồng | Trạng thái |
|---|---|
| Tạo đơn OT-1 / OT-3, trợ lý AI, phác thảo làm việc | Hoàn chỉnh, nối API thật |
| Staff nhận đơn, phác thảo chính thức, báo giá, Manager duyệt giá | Hoàn chỉnh |
| Khách duyệt báo giá, đặt cọc, khoá gói sản xuất có chữ ký | Hoàn chỉnh; cổng mặc định là MOCK |
| Manager xếp lịch, giao robot cho kỹ thuật viên | Hoàn chỉnh |
| Kỹ thuật viên: gói job, hiệu chuẩn, mô phỏng, lệnh robot | Có code và test ở BE và agent; chỉ làm được trên màn máy trạm hoặc DesktopApp; chưa chạy trọn với BE + agent + robot thật |
| Robot viết | Chưa từng xong một trang (RB-01) |
| Ảnh + QC, nghiệm thu, viết lại 1 lần | Hoàn chỉnh |
| Thanh toán cuối, giao hàng / nhận tại xưởng | Hoàn chỉnh trên web; hãng vận chuyển MOCK |
| Huỷ sau cọc, hoàn tiền | Hoàn chỉnh; hoàn tiền là chuyển khoản tay |
| OT-2 "học nét chữ" | Tắt với khách; thực chất là cắt và ghép lại glyph từ phiếu mẫu, không có mô hình học |
| Lối ra cho đơn kẹt (ACCEPTED, chờ thanh toán cuối, giao thất bại) | Chưa có (CO-01, CO-02) |

## 4. Tám vấn đề nghiêm trọng nhất

| ID | Vấn đề | Hậu quả |
|---|---|---|
| RB-01 | Robot thật chưa viết xong một trang; chế độ MoveL chạy khoảng 1 mm/s | Demo chính chưa được chứng minh |
| TP-01 | Báo sự cố, huỷ đơn hay đặt robot BROKEN không gửi lệnh dừng và không đóng lần chạy | Hệ thống ghi job đã hỏng trong khi cánh tay vẫn chạy |
| TP-02 | Cảnh báo đỏ chưa đóng không chặn lệnh RUN / RESUME | Quy tắc "chỉ Manager đóng cảnh báo E-Stop" không có tác dụng thật |
| RB-02 | Độ sâu Z chỉ dựa vào 3 điểm dò tay (sai số luôn bằng 0), không có sàn Z cứng, chạy không cảm biến lực | Gõ sai vài mm thì bút ép xuống bàn |
| PP-01 | Ở chế độ MOCK khách tự bấm "thanh toán thành công"; ở sandbox trả bằng thẻ test | Đơn được xác nhận và robot viết mà xưởng không nhận tiền |
| TP-05 | Job thành "đã viết xong" mà không cần lần chạy robot nào kết thúc | Trừ kho, khách có thể nhận sản phẩm robot chưa viết |
| AI-08, AI-09 | "Độ giống 98%" là nét so với mực hệ thống tự lọc; OT-2 không học gì | Nói sai trước hội đồng sẽ bị bắt lỗi |
| AR-01 | Bộ test chạy thẳng trên Supabase thật và xoá tham số `order_types_enabled` trong lúc chạy | Khách thật đặt được OT-2 trong khoảng đó; rủi ro mất dữ liệu thật |

Bảng đầy đủ (74 mục: 6 P0, 29 P1, 31 P2, 8 P3) ở `05_ISSUES_AND_RECOMMENDATIONS.md`.

## 5. Việc bắt buộc trước buổi bảo vệ

1. Chạy trọn một lần viết thật trên FR3 với nội dung demo, quay video liên tục, giữ `run-*.jsonl` và `progress.json`. Nếu không kịp: demo bằng mô phỏng và nói rõ.
2. Sửa TP-01, TP-02, TP-03, RB-06 trước khi chạy robot thật lần nữa.
3. Đặt tường minh trên Render: `PAYMENT_MODE`, `BACKGROUND_JOBS_ENABLED`, `MOTION_VALIDATION_REQUIRED`; quyết định PP-01.
4. Thống nhất cách gọi OT-2 và con số "độ giống" trong slide, báo cáo và README.
5. Sửa các tài liệu mâu thuẫn nhau về "robot thật đã chạy hay chưa", loadcell, "AI không gọi dịch vụ ngoài".
6. Chốt kênh làm việc của kỹ thuật viên cho buổi demo và tập trọn kịch bản ít nhất hai lần.
7. Xoay mật khẩu DB Supabase và các secret đã lộ trong chat (việc còn treo ở `PROJECT_STATUS.md` mục 1).

## 6. Cần chủ dự án cung cấp

- Giá trị thật trên Render của `PAYMENT_MODE`, `BACKGROUND_JOBS_ENABLED`, `MOTION_VALIDATION_REQUIRED`, `ENABLE_DOCS`, `htr_enabled`, gói dịch vụ (starter hay free).
- File `agent.json` đang dùng ở máy trạm (ẩn secret): `host`, `require_signed_packages`, giá trị watchdog.
- Log gốc của buổi chạy robot 2026-10-25, nếu còn.
- Gripper cuối cùng có cảm biến Hall + ESP32 hay chỉ lò xo.
- Quyền chạy robot thật có người vận hành, nếu muốn tôi hỗ trợ kiểm chứng.

## 7. Bản đồ tài liệu

| File | Nội dung |
|---|---|
| `01_BUSINESS_LOGIC_AUDIT.md` | Actor, quyền hạn, nghiệp vụ theo module |
| `02_WORKFLOW_AND_STATE_MACHINE_AUDIT.md` | Máy trạng thái, truy vết end-to-end, tình huống biên |
| `03_BACKEND_TECHNICAL_AUDIT.md` | Kiến trúc, database, bảo mật, độ tin cậy |
| `04_AI_ROBOTICS_AUDIT.md` | Trợ lý AI, xử lý nét chữ, robot, mức kiểm chứng |
| `05_ISSUES_AND_RECOMMENDATIONS.md` | Bảng vấn đề + phụ lục bằng chứng |
| `06_ALGORITHMS_AND_TECHNICAL_HIGHLIGHTS.md` | Thuật toán thật sự dùng, điểm nổi bật |
| `07_ENTERPRISE_READINESS_ASSESSMENT.md` | Chấm điểm, ba mức sẵn sàng |
| `08_DEMO_AND_DEFENSE_STRATEGY.md` | Kịch bản demo, 24 câu hỏi phản biện |
| `09_APPROVAL_AND_IMPLEMENTATION_PLAN.md` | Phương án cần duyệt, kế hoạch thực hiện |

## 8. Cách audit và giới hạn

Tám nhóm phân tích chỉ-đọc chạy song song theo khu vực, sau đó tôi đọc lại code cho mọi mục P0 và phần lớn mục P1 (đánh dấu "đã kiểm tra chéo" ở phụ lục của file 05). Các mục còn lại dựa trên một lượt đọc, ghi rõ mức tin cậy.

Chưa đọc: thân các file test, `api/v1/{verify,locations,reports}.py`, `services/{admin_system,certificates,material_profiles}.py`, `robot_agent/vhrs_agent/session_key.py`, phần lớn `DesktopApp/lib`, migration 0002–0032 từng file (chỉ xem kết quả trong SQL tổng), chưa đối chiếu schema request/response giữa FE và BE.
