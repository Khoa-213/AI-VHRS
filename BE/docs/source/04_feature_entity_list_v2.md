# Danh sách chức năng và entity AI-VHRS (bản 2)

> Chép lại từ PDF `REPORT (5).pdf`. Nguồn gốc theo PDF: "Report 3 (SRS) bản EN theo phiếu mới, có đủ FR-01..FR-52 và UC-01..UC-53. Bản này thêm 6 chức năng mới
> (đánh dấu **[MỚI]**, mã đề xuất UC-54..59, FR-53..58). Report 3 chưa được sửa."
> Đây là nguồn duy nhất trong repo cho tên của **FR-52, FR-53..58, UC-53..59**. Baseline SQL (`migrations/sql/AI-VHRS_database_postgresql.sql`) đã dựng 29 bảng theo danh sách này.

## Phần A. Chức năng theo luồng

### 1. Tài khoản và phân quyền
- Đăng ký tài khoản khách hàng (UC-05, FR-01)
- Đăng nhập web và Flutter App (UC-01, FR-01) · Đăng xuất (UC-02, FR-01)
- Khôi phục mật khẩu qua email (UC-03, FR-01)
- **[MỚI]** Khôi phục tài khoản bằng số điện thoại: nhập SĐT đã đăng ký, nhận OTP qua SMS, đặt lại mật khẩu (UC-54, FR-53)
- Quản lý hồ sơ và nhiều địa chỉ giao hàng (UC-04, FR-02)
- Phân quyền theo 5 vai trò (FR-03)

### 2. Khách tìm hiểu dịch vụ
- Xem các loại dịch vụ, thư viện mẫu chữ, sản phẩm mẫu, bảng giá tham khảo (UC-06, FR-04)
- Xem trước mẫu chữ với nội dung tự gõ (UC-06, FR-04)
- **[MỚI]** Staff đăng ảnh sản phẩm mẫu lên trang chủ (tiêu đề, mô tả, loại đơn; ẩn/hiện) (UC-55, FR-54)

### 3. Khách tạo đơn
- Tạo đơn và chọn 1 trong 3 loại (UC-07, FR-05)
- **[MỚI]** Lưu bản nháp: lưu văn bản, ảnh và các tùy chọn đã chọn (loại đơn, vật liệu, số lượng) ở bất kỳ bước nào (UC-56, FR-55)
- **[MỚI]** Xem danh sách bản nháp, tiếp tục thiết kế từ bản nháp, hoặc xoá bản nháp (UC-57, FR-56)
- Sao chép–Phục hồi: tải ảnh bản gốc, xoay, cắt (UC-08, FR-06) · Kiểm tra chất lượng ảnh và tiền xử lý (UC-08, FR-33)
- Sáng tạo theo nét đã học: tải mẫu chữ hoặc chọn bộ nét đã lưu, nhập nội dung (UC-09, FR-07)
- Viết theo mẫu: chọn mẫu, nhập nội dung, vẽ canvas (UC-10, FR-08)
- Chọn vật liệu giấy → bút → mực, hoặc để xưởng gợi ý (UC-11, FR-09)
- Xem giá ước tính tức thì (UC-12, FR-10, FR-29) · Gửi đơn cho xưởng (UC-13, FR-11)

### 4. Staff tiếp nhận đơn
- Xem hàng đợi đơn mới/được giao (UC-23, FR-12) · Manager gán Staff cho đơn (UC-47, FR-12)
- Duyệt, từ chối hoặc yêu cầu bổ sung thông tin (UC-24, FR-13) · Khách bổ sung ảnh/thông tin (UC-14, FR-13)
- Nhắn tin giữa khách và Staff trong đơn (UC-27, FR-16)

### 5. Làm phác thảo
- Staff chạy AI tạo phác thảo, sửa nét, lưu phiên bản (UC-25, FR-14)
- Dựng lại nét từ ảnh cho đơn Sao chép–Phục hồi (UC-25, FR-34) · Sinh nét từ mẫu/font cho đơn Viết theo mẫu (UC-25, FR-35)
- Học nét chữ và sinh nội dung mới cho đơn Sáng tạo (UC-09, UC-25, FR-36)

### 6. Chính sách riêng tư
- Khách chấp nhận hoặc từ chối chính sách riêng tư **trước khi xem phác thảo và báo giá** (UC-53, FR-52)

### 7. Báo giá
- Staff tạo báo giá dạng bảng và PDF, gửi khách (UC-26, FR-15) · Tính giá theo công thức (UC-26, FR-29)
- Điều chỉnh giá trong ±15%, vượt ngưỡng chờ Manager duyệt (UC-26, UC-44, FR-31)
- Lưu snapshot giá và xuất file báo giá (UC-26, FR-32)
- Khách xem phác thảo và báo giá, duyệt hoặc yêu cầu sửa (UC-15, FR-15)

### 8. Đặt cọc
- Khách chọn % cọc ≥ mức tối thiểu và thanh toán qua cổng (UC-16, FR-17)

### 9. Lập lịch sản xuất
- Manager xếp lịch: hệ thống gợi ý robot và khung giờ, Manager quyết định (UC-41, FR-40)
- Lập quỹ đạo cho tay FR3 (UC-32, UC-34, FR-37) · Đóng gói job kèm hash (UC-32, FR-38)

### 10. Sản xuất tại xưởng (Flutter App)
- Xem job được giao (UC-31, FR-43) · Tải gói job và kiểm hash (UC-32, FR-43)
- Chuẩn bị robot và hiệu chuẩn mặt giấy, lực (UC-33, FR-44) · Mô phỏng quỹ đạo trước khi chạy (UC-34, FR-45)
- Chạy viết qua Robot Agent (UC-35, FR-46) · Điều khiển lực bút bằng thiết bị IoT (UC-33, UC-35, FR-47)
- Giám sát, tạm dừng, dừng khẩn cấp (UC-36, FR-48) · Báo cáo sự cố (UC-37, FR-48)
- Chụp ảnh sản phẩm và kiểm tra chất lượng (UC-38, FR-49) · Cập nhật trạng thái sản xuất (UC-39, FR-49, FR-25)

### 11. Theo dõi đơn
- Khách theo dõi trạng thái đơn, trạng thái sản xuất và ETA (UC-17)
- Máy trạng thái đơn hàng (FR-24) · Máy trạng thái sản xuất và đồng bộ 2 trạng thái (UC-39, FR-25)
- Tính ETA và dời ETA có lý do (UC-30, FR-26) · Thông báo email và trong ứng dụng (FR-27)
- **[MỚI]** Trung tâm thông báo cho khách: báo khi Staff chấp nhận/từ chối đơn, đổi trạng thái đơn, có phác thảo, báo giá, dời ETA, tin nhắn mới; đánh dấu đã đọc (UC-58, FR-57)

### 12. Nghiệm thu
- Khách nghiệm thu qua ảnh sản phẩm hoặc yêu cầu viết lại (UC-18, FR-28)

### 13. Thanh toán cuối và giao hàng
- Tính phí ship qua API hãng vận chuyển (UC-19, FR-21) · Thanh toán phần còn lại và phí ship (UC-19, FR-18)
- Tạo vận đơn và theo dõi giao hàng (UC-29, FR-22) · Nhận hàng tại xưởng (UC-19, UC-29, FR-23)
- Khách xác nhận đã nhận hàng (UC-20, FR-28)
- **[MỚI]** Khách đánh giá sau khi đơn hoàn thành: chấm sao, viết nhận xét, tải ảnh (UC-59, FR-58)

### 14. Huỷ đơn và thanh toán
- Huỷ đơn và hoàn tiền theo chính sách (UC-21, FR-19)
- Staff xác nhận thanh toán và hoàn tiền (UC-28, FR-19, FR-20)
- Xem lịch sử thanh toán và hoá đơn (UC-22, FR-20)

### 15. Quản lý xưởng (Manager)
- Quản lý robot và loại robot (UC-40, FR-39) · Vật liệu và bảng tương thích giấy–bút (UC-42, FR-41)
- Mẫu chữ và bộ nét đã học (UC-43, FR-42) · Bảng giá và % cọc tối thiểu (UC-44, FR-30)
- Dashboard sản xuất (UC-45, FR-50) · Báo cáo doanh thu, sản lượng, hiệu suất robot (UC-46, FR-50)

### 16. Quản trị hệ thống (Admin)
- Quản lý tài khoản và vai trò (UC-48, FR-51) · Cấu hình tích hợp thanh toán, vận chuyển, email (UC-49, FR-51)
- Tham số hệ thống (UC-50, FR-51) · Nhật ký hoạt động (UC-51, FR-51) · Dashboard hệ thống (UC-52, FR-50, FR-51)

## Phần B. Entity (24 có sẵn + 5 mới = 29)

| # | Entity | Mô tả | Chức năng |
|---|---|---|---|
| 1 | Role | 5 vai trò | FR-03, FR-51 |
| 2 | Account | Tài khoản mọi vai trò, trạng thái, địa chỉ; **thêm số điện thoại đã xác minh** | FR-01, FR-02, FR-51, FR-53 |
| 3 | Order | Loại đơn, order_status, production_status, vật liệu, số lượng, ETA, Staff phụ trách; **DRAFT dùng cho bản nháp, thêm thời điểm lưu gần nhất** | FR-05, FR-11..13, FR-19, FR-24..26, FR-28, FR-52, FR-55, FR-56 |
| 4 | OrderInput | Ảnh gốc, nội dung chữ, canvas, mẫu/bộ nét đã chọn (cũng lưu nội dung bản nháp) | FR-06..08, FR-33, FR-55, FR-56 |
| 5 | Template | Mẫu typography, calligraphy, font một nét | FR-04, FR-42 |
| 6 | HandwritingStyle | Bộ nét chữ đã học của một người (OT-2) | FR-36, FR-42 |
| 7 | Sketch | Phác thảo có phiên bản: quỹ đạo, ảnh xem trước, độ giống, thời gian viết | FR-14, FR-34, FR-35 |
| 8 | Quotation | Báo giá: dòng chi tiết, tổng, % cọc tối thiểu, hiệu lực, snapshot giá, file | FR-15, FR-29, FR-31, FR-32 |
| 9 | Payment | Giao dịch cọc, phần còn lại, phí ship, hoàn tiền | FR-17, FR-18, FR-20 |
| 10 | Shipment | Vận đơn: hãng, mã, phí, trạng thái | FR-21, FR-22, FR-23 |
| 11 | Message | Tin nhắn khách ↔ Staff trong đơn | FR-16 |
| 12 | StatusHistory | Lịch sử chuyển trạng thái, ETA cũ/mới, lý do | FR-24, FR-25, FR-26 |
| 13 | PaperType | Giấy: gsm, bề mặt, khổ, đơn giá, tồn kho | FR-41, FR-09 |
| 14 | PenType | Bút: độ rộng nét, dải lực, phụ phí | FR-41, FR-09 |
| 15 | InkColor | Màu mực theo bút | FR-41, FR-09 |
| 16 | PaperPenCompat | Ma trận tương thích giấy × bút | FR-41, FR-09 |
| 17 | Robot | Mã, loại, trạm, trạng thái | FR-39 |
| 18 | ProductionJob | Đơn, robot, kỹ thuật viên, khung giờ, gói job, hash | FR-37, FR-38, FR-40, FR-43, FR-45, FR-46 |
| 19 | JobEvent | Sự kiện job: bắt đầu, tạm dừng, sự cố, tóm tắt lực | FR-47, FR-48 |
| 20 | ProductPhoto | Ảnh sản phẩm thật và kết quả QC | FR-49 |
| 21 | PricingConfig | Tham số giá có phiên bản | FR-30 |
| 22 | Calibration | Kết quả hiệu chuẩn mặt giấy và lực, gắn với job | FR-44 |
| 23 | Incident | Sự cố robot/vật tư | FR-48 |
| 24 | AuditLog | Log thao tác quản trị và chấp nhận/từ chối chính sách riêng tư | FR-51, FR-52, FR-31 |
| 25 | **Notification [MỚI]** | Thông báo: tài khoản nhận, đơn liên quan, loại (chấp nhận/từ chối, đổi trạng thái, báo giá, ETA, tin nhắn), nội dung, kênh (email/in-app), đã đọc, thời gian | FR-27, FR-57 |
| 26 | **Review [MỚI]** | Đánh giá của khách cho một đơn đã hoàn thành: số sao, nhận xét, thời gian (mỗi đơn 1 đánh giá) | FR-58 |
| 27 | **ReviewPhoto [MỚI]** | Ảnh khách tải lên kèm đánh giá | FR-58 |
| 28 | **ShowcasePost [MỚI]** | Ảnh sản phẩm mẫu Staff đăng lên trang chủ: ảnh, tiêu đề, mô tả, loại đơn, người đăng, ẩn/hiện, thứ tự | FR-54, FR-04 |
| 29 | **PhoneOtp [MỚI]** | OTP khôi phục tài khoản qua SMS: số điện thoại, mã (đã băm), hết hạn, số lần thử, đã dùng | FR-53 |

Ghi chú của bản gốc:
- Bản nháp không cần entity mới: report đã có trạng thái DRAFT của Order (FR-05) và OrderInput lưu nội dung; chỉ cần cho phép lưu và mở lại đơn DRAFT.
- Khôi phục bằng số điện thoại cần thêm một nhà cung cấp SMS vào phần cấu hình tích hợp của Admin (UC-49).
