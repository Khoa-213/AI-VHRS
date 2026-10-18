# [LỖI THỜI] Mô tả luồng giao diện theo mô hình 3 actor (Customer / Operator / Super Admin)

> Chép lại từ PDF `REPORT (6).pdf`. **KHÔNG dùng làm yêu cầu.** Tài liệu này mô tả một phiên bản cũ của dự án (3 actor, thanh toán 100% **trước** khi vào hàng đợi,
> trạng thái đơn kiểu Awaiting Payment/Paid/Approved/Rejected/Writing/Done, "Operator" gộp duyệt + thực thi). Phạm vi hiện hành là mô hình xưởng 5 actor ở Report 1–3
> (đặt cọc theo %, báo giá, double state). Giữ lại để agent biết **vì sao** có thể gặp các thuật ngữ cũ (Operator, Project, Awaiting Payment…) và **không nhầm** với yêu cầu hiện hành.
> Một vài ý vẫn đúng và còn dùng: 3 hình thức nhập liệu (Text+Font, Canvas, Upload ảnh), thanh trượt xoay/crop/ngưỡng tương phản, xem trước hoạt ảnh quỹ đạo, E-Stop ≤ 1 s, mô phỏng trước khi chạy.

## 1. Phân hệ Khách hàng (Customer Portal)
Giao diện trực quan, nhẹ, dễ thao tác trên trình duyệt; mô hình 3 actor (Customer/Operator/Super Admin) và 3 hình thức nhập liệu.

- **Luồng 1 Đăng ký & Đăng nhập**: email + mật khẩu; quản lý hồ sơ, đăng xuất. UC: UC-01 Register, UC-02 Login, UC-24 Logout, UC-27 Manage Profile.
- **Luồng 2 Workspace**: tạo dự án mới, chọn khổ giấy (A4, A5, thiệp chúc mừng) và loại bút (bút bi, bút máy) từ danh mục Super Admin cấu hình; Project Dashboard xem lại dự án. UC-03 Create Project, UC-25 View Project Dashboard.
- **Luồng 3 Nhập liệu & Thiết kế** (chọn đúng 1 trong 3 phương thức cho mỗi yêu cầu, không kết hợp):
  - *Text + Font*: gõ văn bản, chọn style/font single-line; hệ thống tự vector hóa, không qua AI phục dựng.
  - *Vẽ tự do trên Canvas*: chuột/stylus, Pointer Events API ghi tọa độ, thứ tự nét, điểm nhấc bút, giới hạn trong khổ giấy.
  - *Upload & Reconstruct*: ảnh chụp/scan chữ viết tay cũ (jpg/png), chữ của một người, đoạn ngắn, nền tương phản; slider xoay/crop/ngưỡng tương phản; AI skeletonization, vector hóa, xử lý dấu thanh/dấu phụ; không cam kết 100%, đánh giá bằng chỉ số độ giống.
  - *Preview*: cả 3 phương thức hiển thị hoạt ảnh quỹ đạo trước khi gửi, cho phép xử lý lại. UC-04..07.
- **Luồng 4 Báo giá & Gửi yêu cầu**: báo giá ước tính theo khổ giấy, loại bút, độ phức tạp quỹ đạo; ghi chú cho Operator; Submit → trạng thái "Awaiting Payment" (quỹ đạo đóng gói JSON). UC-28, UC-08.
- **Luồng 5 Thanh toán**: VNPay/Momo, không lưu thẻ; thành công → "Paid" và vào hàng đợi Operator; thất bại/hủy → giữ "Awaiting Payment" để thử lại; **Operator từ chối đơn đã thanh toán → hoàn 100% giá trị đơn tự động**. UC-29.
- **Luồng 6 Theo dõi & Nhận kết quả**: trạng thái Awaiting Payment/Paid/Approved/Rejected/Writing/Done, thông báo khi đổi; xem/tải kết quả (ảnh/video bản viết thật); lịch sử thanh toán. UC-09, UC-10, UC-30.

## 2. Phân hệ Nhân viên Vận hành (Operator Dashboard)
Control Center cho Operator — toàn quyền xử lý đơn (gộp duyệt + thực thi).

- **Luồng 7**: đăng nhập/đăng xuất/hồ sơ dùng chung cho cả 3 actor.
- **Luồng 8 Hàng đợi**: chỉ gồm yêu cầu "Paid"; xem trước quỹ đạo để đánh giá khả thi trong không gian làm việc robot; duyệt/từ chối kèm lý do (từ chối → "Rejected", hoàn 100% nếu đã thanh toán). UC-11, UC-12, UC-13.
- **Luồng 9 Cấu hình phiên viết & sinh quỹ đạo**: Operator cấu hình loại bút, khổ giấy thực tế, điểm gốc "home". Motion Generation Service (tự động): ánh xạ 2D → Cartesian space của robot, thiết lập trục Z (độ tỳ/áp lực), nội suy spline; SDK robot (Fairino/lerobot) có sẵn IK và giới hạn khớp. UC-14.
- **Luồng 10 Mô phỏng & Thực thi**: "Simulate" (2D/3D, kiểm va chạm, soft limits, singularity); kẹp giấy, lắp bút, set home; ra lệnh từ Web Dashboard xuống Robot Control Service (Python + SDK); giám sát thời gian thực, **E-Stop trên UI, robot dừng ≤ 1 s**; ghi nhận kết quả kèm ảnh/video → "Done" hoặc "Failed". UC-15..18.
- **Luồng 11 Lịch sử phiên viết**: lịch sử và thống kê phiên viết đã xử lý. UC-26.

## Đối chiếu nhanh với mô hình hiện hành
| Tài liệu cũ | Hiện hành (Report 1–3) |
|---|---|
| 3 actor: Customer, Operator, Super Admin | 5 actor: Customer, Staff, Technical Staff, Manager, Admin |
| Thanh toán đủ một lần trước khi vào hàng đợi | Cọc ≥ p_min (mặc định 50%) sau khi duyệt báo giá; phần còn lại + ship khi nghiệm thu |
| Hoàn 100% khi Operator từ chối | Từ chối đơn trước khi có thanh toán; hoàn tiền theo BR-14/BR-16 |
| Trạng thái Awaiting Payment/Paid/Approved/Rejected/Writing/Done | 2 trạng thái độc lập: `order_status` + `production_status` |
| Project / Project Dashboard | Order, My Orders |
| Operator tự chạy robot từ Web Dashboard | Technical Staff chạy qua Flutter Desktop App + Robot Agent cục bộ |
