# Tài liệu gốc của dự án (source of truth về yêu cầu)

Thư mục này chứa **bản chép sang markdown** của các tài liệu đồ án gốc (PDF/Word không nằm trong repo). Agent phải đọc ở đây trước khi hỏi chủ dự án về
yêu cầu nghiệp vụ; chỉ hỏi khi tài liệu **không nói** hoặc **mâu thuẫn**. Tra nhanh: `grep -rn "BR-14" BE/docs/source`.

| File | Nguồn | Nội dung | Mức tin cậy |
|---|---|---|---|
| [03_report3_srs.md](03_report3_srs.md) | Report 3 – SRS (`REPORT (4).pdf`) | **Quan trọng nhất**: 5 actor, UC-01..52, FR-01..51, công thức giá, pipeline AI, IoT, NFR, **BR-01..24**, tham số mặc định, MSG01..15 | Yêu cầu chính thức (có override bên dưới) |
| [04_feature_entity_list_v2.md](04_feature_entity_list_v2.md) | Danh sách chức năng & entity bản 2 (`REPORT (5).pdf`) | Thêm FR-52..58, UC-53..59, 5 entity mới (29 bảng); tên chức năng theo luồng | Chính thức, bổ sung cho Report 3 |
| [01_report1_project_introduction.md](01_report1_project_introduction.md) | Report 1 (`REPORT (2).pdf`) | Bối cảnh, mô hình xưởng, actor, FE-01..15, **LI-01..12** (giới hạn) | Chính thức |
| [02_report2_project_management_plan.md](02_report2_project_management_plan.md) | Report 2 (`REPORT (3).pdf`) | WBS, rủi ro, quy trình, công nghệ, Gitflow | Tham khảo (RACI suy lại từ PDF vỡ cột) |
| [06_capstone_registration.md](06_capstone_registration.md) | Phiếu đăng ký đề tài (`FA26SE097_AI-VHRS_Phieudangky.pdf`) | MVP/Stretch, fallback mock, RQ1–RQ3, phương pháp đo | Tham khảo; **MVP hẹp hơn Report 1–3** |
| [05_legacy_ui_flow_3actor.md](05_legacy_ui_flow_3actor.md) | `REPORT (6).pdf` | Luồng UI cũ 3 actor (Operator) | **LỖI THỜI – không dùng làm yêu cầu** |

Không có trong repo (chưa từng được cung cấp): bảng trạng thái 2.5.1/2.5.2/2.5.3, nguyên văn **FR-52 / BR-25** (chính sách riêng tư), FR-53..58 chi tiết, ERD/diagram ảnh.
Cho tới khi có, nguồn thực tế là trigger DB `fn_order_state_guard` và baseline SQL.

## Thứ tự ưu tiên khi mâu thuẫn
1. Quyết định của chủ dự án đã ghi trong `PROJECT_STATUS.md` mục 5 và 8 (xem "Quyết định đã override" dưới đây).
2. Schema/trigger thật trong DB (`migrations/`) – nhiều luật đã nằm sẵn ở đó.
3. Report 3 (SRS) → bản 2 danh sách chức năng → Report 1 → Report 2 → Phiếu đăng ký.
4. `05_legacy_ui_flow_3actor.md` không bao giờ thắng.

## Quyết định đã override so với tài liệu gốc (không đảo ngược nếu chưa hỏi)
| Tài liệu gốc nói | Dự án đã chọn | Nơi ghi |
|---|---|---|
| Ma trận 3.1.3: Manager thao tác Order Review, Quotation Builder, Messages, Payments, Delivery | **Manager chỉ đọc đơn**; mọi lệnh ghi `/workshop/*` là **Staff only**; Manager vẫn nhắn tin để xử lý khiếu nại, vẫn duyệt giá vượt ngưỡng, phân công Staff | `PROJECT_STATUS.md` mục 5 |
| Ma trận 3.1.3: Admin "Xem" Order Detail và Production Dashboard | **Admin chỉ quản trị hệ thống**, không xem/sửa đơn, giá, sản xuất | mục 5 |
| BR-09: ±15% so với giá Pricing Engine tính | So với `computed_total` của chính báo giá đó (không phải giá ước tính lúc tạo đơn) | mục 5 |
| BR-09/BR-10: ngưỡng ±15% và p_min là tham số | Nguồn duy nhất: bảng `pricing_configs` (có phiên bản); khóa `system_settings.price_adjust_threshold_pct` không được đọc | mục 5 |
| LI-10: OT-2 là R&D | `system_settings.order_types_enabled` = chỉ OT-1, OT-3 | mục 5 |
| FR-36 (OT-2) học nét | Chưa làm; AI là cổ điển, không gọi dịch vụ ngoài | mục 5 |
| Cổng thanh toán VNPay/MoMo, GHN/GHTK thật | **MOCK** có nhãn `mode=MOCK` (phiếu đăng ký cho phép fallback mock) | mục 5 |
| Robot thật FR3 + Robot Agent + IoT | Thuộc phạm vi BE nhưng **chưa làm; chỉ làm khi chủ dự án yêu cầu rõ** (2026-10-18). Trước đó Technical Staff làm "web scope A": bản ghi/trạng thái, client báo kết quả lên | mục 3, 5 |

## Quyết định bổ sung của chủ dự án (2026-10-18, cho Phase 4)
| Vấn đề tài liệu không nói rõ | Quyết định |
|---|---|
| Viết lại lần 2 trở đi (BR-13 "tính phí theo báo giá mới") | **Chỉ hỗ trợ 1 lần miễn phí.** Lần 2 trả lỗi rõ ràng "liên hệ xưởng"; không đổi schema; tính phí viết lại để phase sau khi có chính sách giá. |
| Giao hàng thất bại/hoàn về (`shipment_status` FAILED/RETURNED) | **Giữ đơn ở `DELIVERING`**, Staff tạo lại vận đơn hoặc chuyển sang nhận tại xưởng; **không** đổi trigger. |
| Ai đưa đơn sang `COMPLETED` khi giao qua hãng | **Webhook hãng `DELIVERED` → `COMPLETED`** (FR-22). Khách bấm "xác nhận đã nhận" chỉ ghi `received_confirmed_at` và mở quyền đánh giá. Nhận tại xưởng: Staff xác nhận đã giao → `COMPLETED` (FR-23). |
| DB chạy test Phase 4 | **Tiếp tục Supabase thật** (như cũ), chạy lúc không có khách thật; tuân thủ `AI_PLAYBOOK.md` S07 và mục 8 (không chạy 2 phiên pytest cùng lúc, kiểm tra DB sạch `pytest_*` sau khi chạy). |

## Luật nghiệp vụ Phase 4–5 đã có đáp án trong tài liệu gốc
(để agent không phải hỏi lại; nguyên văn ở `03_report3_srs.md`)

- **Thanh toán cuối (FR-18, BR-11, LI-08)**: *một lần* thanh toán `(G − D) + F_ship`, ghi **2 dòng Payment** (`FINAL`, `SHIPPING`); tối đa 2 đợt thanh toán; không COD; phải trả trước khi giao/nhận tại xưởng. Nhận tại xưởng: `F_ship = 0`, **không** có dòng `SHIPPING`.
- **Giao hàng (FR-21..23, BR-12)**: gói suy ra từ khổ giấy + số bản: hộp phẳng A5/A4, ống cứng cho poster (`package_type` FLAT_BOX_A5/FLAT_BOX_A4/TUBE); phí dự phòng khi API lỗi, bảng phí dự phòng do **Admin** cấu hình (System Parameters); `is_fallback_fee`. Webhook hãng → `DELIVERING`/`COMPLETED`. Nhận tại xưởng: hẹn khung giờ, Staff xác nhận giao → `COMPLETED`, khách nhận bằng mã đơn + SĐT. Mọi báo giá ghi "Giá chưa bao gồm phí giao hàng".
- **Nghiệm thu / viết lại (FR-28, BR-13)**: khách nghiệm thu qua ≥ 2 ảnh; **viết lại miễn phí tối đa 1 lần** (lỗi do xưởng hoặc sai so với phác thảo đã duyệt; cột `free_rewrite_used`); lần sau **tính phí theo báo giá mới**. Tự nghiệm thu sau **7 ngày**, nhắc sau **3 ngày** (cột `awaiting_acceptance_at`, `acceptance_reminded_at`).
- **Huỷ + hoàn tiền (FR-19, BR-14, BR-16)**: chưa `SCHEDULED` → hoàn 100% cọc; đã xếp lịch nhưng chưa viết → hoàn 100% cọc **trừ phí setup** (`S_type`); đã bắt đầu viết → không huỷ, **trừ khi** ETA dời lũy kế > 7 ngày → huỷ + hoàn 100% số đã thanh toán. Staff xác nhận hoàn tiền; lưu `Payment(type=REFUND, refund_of_id)`.
- **ETA (FR-26, BR-15, BR-16)**: ETA = ngày cọc thành công + thời gian chờ theo lịch robot + thời gian giao ước tính của hãng; hiển thị từ lúc báo giá; Staff dời ETA bắt buộc có lý do + thông báo MSG11; trigger DB tự cộng `eta_postponed_days`.
- **Sản xuất (FR-43..49, BR-17..21)**: job chỉ chạy khi hiệu chuẩn (BR-19) + mô phỏng đạt (FR-45, ràng buộc `simulation_passed`); gói job có hash SHA-256 phác thảo đã duyệt (FR-38); hash sai → từ chối chạy (MSG14); quá lực (MSG13); sự cố → job `FAILED` → đơn `PENDING_SCHEDULE` (FR-48, UC-37); ≥ 2 ảnh (OVERALL + CLOSE_UP) + QC đạt trước `PHOTO_UPLOADED` (BR-21, trigger đã chặn); **trừ tồn kho khi job `WRITTEN`** (FR-41).
- **Thông báo (FR-27, FR-57)**: kênh `EMAIL` + `IN_APP`; mã MSG07, MSG08, MSG10, MSG11, MSG12, MSG15 là email+in-app (nội dung ở mục 5.3 của SRS); MSG13/MSG14 chỉ là alert trong app Flutter (không thuộc BE web). Trung tâm thông báo cho khách: đánh dấu đã đọc.
- **Scheduled jobs (SRS 3.1.4 #15)**: hủy báo giá hết hạn, nhắc nghiệm thu, tự nghiệm thu, xóa ảnh sau 90 ngày kể từ khi hoàn tất (BR-23, trừ khi khách đồng ý lưu bộ nét).
- **Đánh giá (FR-58, UC-20/59)**: khách đánh giá sau khi đơn hoàn thành; mỗi đơn 1 đánh giá (bảng `reviews`, `review_photos` đã có).

## Điểm tài liệu còn **không nói** hoặc mơ hồ (cần hỏi chủ dự án khi gặp)
1. Phí `S_type` bị trừ khi hoàn tiền (BR-14): lấy từ snapshot báo giá nào? (báo giá `APPROVED`).
2. *(đã chốt 2026-10-18, xem bảng trên)* viết lại lần 2 · giao thất bại · xác nhận nhận hàng.
5. Khách có huỷ được ở `AWAITING_ACCEPTANCE` không (SRS không nói; trigger không cho).
6. Bảng phí ship dự phòng, cân nặng gói, mức giảm "viết lại" – không có số liệu.
7. FR-52/BR-25 chính sách riêng tư: nguyên văn chưa có (hiện là bản nháp trong seed).
8. Giá trị mặc định của các tham số ở SRS 5.2 đã có; còn lại (thời gian chờ hãng, hao hụt vật tư khi trừ kho) chưa có.

## Quy ước cập nhật
- Tài liệu gốc đổi (SRS v3, thêm BR-25…) → cập nhật file tương ứng ở đây **và** ghi dòng vào `PROJECT_STATUS.md` mục 9.
- Không sửa nội dung gốc để cho khớp code; nếu code khác tài liệu, ghi vào bảng "override" ở trên kèm lý do và người quyết định.
