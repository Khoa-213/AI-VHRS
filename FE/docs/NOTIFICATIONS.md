# Thông báo theo từng role (FR-27, FR-57)

Tài liệu này liệt kê mỗi role nhận những thông báo nào, do việc gì kích hoạt, và hiện ở đâu. Nguồn: `BE/app/domain/notification_messages.py` (nội dung và loại) và các chỗ gọi `notifications.notify(...)` trong `BE/app/services/`. Chưa kiểm tra bằng cách chạy từng luồng, nên dùng bảng "Cách thử" ở cuối để xác nhận.

## Cách hoạt động chung

- Mỗi tài khoản có danh sách riêng, đọc qua `GET /me/notifications`. Chuông ở top bar (khách) và header xưởng (Staff, Manager, Technician, Admin) hiện badge số chưa đọc.
- Nội dung (`title`, `body`) do backend soạn bằng **tiếng Việt** và FE hiện nguyên văn, không dịch sang en/ja.
- Thông báo mới đến tức thời qua SSE (`GET /me/notifications/stream`). Bấm vào một thông báo là đánh dấu đã đọc, và mở trang đơn nếu có `order_id`.
- Chỉ các thông báo SRS đánh số **MSG07, MSG08, MSG10, MSG11, MSG12, MSG15** được gửi thêm **email**. Còn lại chỉ hiện trong chuông.
- Một số loại "gộp" (`collapse`): nếu người nhận còn một thông báo cùng loại của cùng đơn chưa đọc thì không tạo thêm. Hiện áp dụng cho tin nhắn mới (`MESSAGE`, `MESSAGE_UNCLAIMED`).
- Cột "Mở ra" là trang chuông dẫn tới khi bấm: khách mở `/orders/{id}/review`, Staff và Manager mở `/staff/review/{id}`. Technician và Admin chưa có trang đơn nên bấm chỉ đánh dấu đã đọc.

## Khách hàng (CUSTOMER)

| Mã | Loại (`type`) | Khi nào | Email |
|---|---|---|---|
| MSG07 | `ORDER_REJECTED` | Staff từ chối đơn, kèm lý do | Có |
| MSG08 | `QUOTATION_EXPIRED` | Báo giá hết hạn, đơn bị hủy | Có |
| MSG10 | `QUOTATION_AVAILABLE` | Đơn đã có phác thảo và báo giá | Có |
| MSG11 (`ETA_POSTPONED`) | `ETA_POSTPONED` | Ngày giao bị dời **muộn hơn** | Có |
| MSG12 | `PRODUCT_COMPLETED` | Sản phẩm xong, mời xem ảnh và nghiệm thu | Có |
| MSG15 | `DELIVERING` | Đơn đang được giao, kèm mã vận đơn | Có |
| `ETA_CHANGED` | `ETA_POSTPONED` | Staff đổi ngày giao **sớm hơn** | Không |
| `DEPOSIT_PAID` | `PAYMENT` | Xưởng nhận được tiền cọc | Không |
| `FINAL_PAID` | `PAYMENT` | Xưởng nhận thanh toán cuối | Không |
| `ORDER_CANCELLED` | `ORDER_STATUS_CHANGED` | Đơn đã hủy (kèm số tiền hoàn nếu có) | Không |
| `REFUND_REQUESTED` | `PAYMENT` | Yêu cầu hoàn tiền được tạo, xưởng đang xử lý | Không |
| `REFUND_SENT` | `PAYMENT` | Xưởng đã chuyển tiền hoàn | Không |
| `SHIPMENT_CREATED` | `DELIVERING` | Đơn đã có vận đơn, chờ hãng tới lấy | Không |
| `ORDER_COMPLETED` | `ORDER_STATUS_CHANGED` | Đơn hoàn tất | Không |
| `DEPOSIT_OVERDUE` | `ORDER_STATUS_CHANGED` | Đơn bị hủy vì quá hạn cọc (tác vụ nền) | Không |
| `ACCEPT_REMINDER` | `ORDER_STATUS_CHANGED` | Nhắc nghiệm thu sau 3 ngày, kèm giờ tự nghiệm thu | Không |
| `MESSAGE` | `NEW_MESSAGE` | Staff hoặc Manager nhắn tin trong đơn | Không |

Ai kích hoạt ngày giao bị dời (MSG11): Staff được giao đơn đổi tay, Manager xếp hoặc xếp lại lịch sản xuất làm giao muộn hơn, hoặc chính khách chọn dịch vụ vận chuyển giao muộn hơn ETA. Tổng số ngày dời vượt ngưỡng (mặc định 7) thì khách được hủy và hoàn 100%.

Chưa có thông báo riêng cho khách khi đơn tự nghiệm thu sau 7 ngày.

## Staff (STAFF)

Chỉ nhận về **đơn mình được giao** (`assigned_staff_id`). Tất cả chỉ hiện trong chuông, không có email.

| Mã | Loại | Khi nào |
|---|---|---|
| `MESSAGE` | `NEW_MESSAGE` | Khách nhắn tin trong đơn của mình |
| `REFUND_TO_PROCESS` | `PAYMENT` | Đơn đã hủy, cần chuyển hoàn tiền cho khách (làm ở `/staff/refunds`) |
| `ORDER_READY_TO_DELIVER` | `ORDER_STATUS_CHANGED` | Khách thanh toán đủ, đơn sẵn sàng giao |
| `PRODUCT_ACCEPTED` | `ORDER_STATUS_CHANGED` | Khách đã nghiệm thu |
| `PRODUCT_AUTO_ACCEPTED` | `ORDER_STATUS_CHANGED` | Đơn tự nghiệm thu vì khách không phản hồi |
| `REWRITE_REQUESTED` | `PRODUCTION_STATUS_CHANGED` | Khách yêu cầu viết lại, cần xếp lịch lại |
| `SHIPMENT_PROBLEM` | `SYSTEM` | Vận đơn gặp sự cố (giao không thành công, hoàn về, thất lạc, bị hủy) |

## Manager (MANAGER)

Tất cả chỉ hiện trong chuông, không có email. Các thông báo sản xuất đến Manager **đã xếp lịch job đó** (`job.scheduled_by`).

| Mã | Loại | Khi nào |
|---|---|---|
| `MESSAGE_UNCLAIMED` | `NEW_MESSAGE` | Khách nhắn ở đơn chưa có Staff phụ trách (báo cho **mọi** Manager đang hoạt động) |
| `REWRITE_REQUESTED` | `PRODUCTION_STATUS_CHANGED` | Khách yêu cầu viết lại đơn mà Manager đã xếp lịch |
| `QC_FAILED` | `PRODUCTION_STATUS_CHANGED` | Sản phẩm không đạt QC, cần xếp lịch viết lại |
| `JOB_SAFETY_STOP` | `SYSTEM` | Robot dừng an toàn (quá lực, dừng khẩn cấp, dừng an toàn) |
| `INCIDENT_REPORTED` | `SYSTEM` | Technician báo sự cố khi viết |

Manager không nhận `MESSAGE` hay các thông báo hoàn tiền của Staff. Cảnh báo robot (mức 1 đến 4) gửi theo danh mục `notify_roles` của từng cảnh báo, có thể gồm Manager và Staff; FE hiện chưa có màn cảnh báo robot cho Manager.

## Kỹ thuật viên (TECHNICAL_STAFF)

| Mã | Loại | Khi nào |
|---|---|---|
| `JOB_ASSIGNED` | `PRODUCTION_STATUS_CHANGED` | Được Manager giao viết đơn, kèm giờ bắt đầu |
| `JOB_CANCELLED` | `PRODUCTION_STATUS_CHANGED` | Đơn bị hủy nên job của mình cũng bị hủy |

Cảnh báo robot của Technician đi theo hệ thống cảnh báo riêng: chuông đỏ `RobotAlertBell` (poll `GET /technician/robot-status`) và banner E-Stop mức 4, không phải bảng thông báo này. Cảnh báo mức 4 còn được backend gửi email.

## Admin (ADMIN)

Không có thông báo nào được gửi cho Admin. Chuông vẫn hiện nhưng luôn trống.

## Cách thử nhanh

| Muốn thấy | Làm gì | Ai thấy |
|---|---|---|
| `MESSAGE` | Staff nhắn trong đơn | Khách |
| `MESSAGE` / `MESSAGE_UNCLAIMED` | Khách nhắn trong đơn đã có Staff / chưa có Staff | Staff được giao / mọi Manager |
| MSG10 | Staff gửi báo giá | Khách |
| `DEPOSIT_PAID` | Khách đặt cọc (MOCK) | Khách |
| `JOB_ASSIGNED` | Manager xếp lịch cho đơn đã cọc | Technician |
| `ORDER_CANCELLED`, `REFUND_REQUESTED`, `REFUND_TO_PROCESS` | Khách hoặc xưởng hủy đơn đã cọc | Khách, Staff được giao, Technician (`JOB_CANCELLED` nếu đã có job) |
| `REFUND_SENT` | Staff xác nhận đã chuyển ở `/staff/refunds` | Khách |
| MSG11 hoặc `ETA_CHANGED` | Staff đổi ETA muộn hơn hoặc sớm hơn | Khách |
| `ACCEPT_REMINDER`, `DEPOSIT_OVERDUE` | Admin chạy "Tác vụ nền" ở `/admin` (cần dữ liệu quá hạn) | Khách |

## Điểm cần lưu ý khi dùng

- Nội dung thông báo luôn là tiếng Việt, kể cả khi người dùng chọn tiếng Anh hoặc tiếng Nhật.
- Sự kiện SSE không được phát lại khi mất kết nối; FE tải lại danh sách mỗi lần nối lại.
- Backend hiện chỉ gửi theo bảng trên. Loại nào chưa có mã trong danh mục vẫn đến người nhận dưới dạng thông báo `SYSTEM` chung "Cập nhật đơn …".
