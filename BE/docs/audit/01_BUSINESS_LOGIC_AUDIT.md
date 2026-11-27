# 01 — Rà soát nghiệp vụ theo actor và module

Mã vấn đề (CO-, SD-, PP-, TP-, AI-, RB-, AR-, SR-, DM-) tra ở `05_ISSUES_AND_RECOMMENDATIONS.md`.

## 1. Bài toán và actor

Hệ thống nhận yêu cầu viết tay tiếng Việt (chép lại từ ảnh thư cũ, hoặc viết nội dung mới theo mẫu chữ), dựng bản phác thảo dạng đường nét, báo giá, thu cọc, rồi cho cánh tay robot FAIRINO FR3 viết lên giấy bằng bút thật.

| Actor | Kênh | Trách nhiệm theo code |
|---|---|---|
| Customer | Web | Tạo đơn, dùng trợ lý AI, duyệt báo giá, đặt cọc, nghiệm thu, thanh toán cuối, chọn giao / nhận, huỷ, đánh giá |
| Staff | Web | Nhận đơn, dựng và chốt phác thảo, báo giá, chat, vận đơn, bàn giao, xác nhận hoàn tiền |
| Technical Staff | Màn máy trạm của Robot Agent, DesktopApp | Job của mình: gói job, hiệu chuẩn, mô phỏng, lệnh robot, ảnh + QC |
| Manager | Web | Đọc mọi đơn, phân công, duyệt giá vượt ngưỡng, vật tư, bảng giá, xếp lịch, robot, báo cáo |
| Admin | Web | Tài khoản nội bộ, tham số hệ thống, tích hợp, nhật ký, tác vụ nền |
| Robot Agent | Máy trạm | Kéo lệnh từ BE, điều khiển FR3, báo trạng thái và cảnh báo |
| Hệ thống ngoài | Webhook | payOS, VNPay, MoMo, GHN; LLM (Claude, GPT, Gemini) |

## 2. Từng actor

### Customer

Làm được và được kiểm soát đúng:
- Chỉ sửa đơn khi `DRAFT` hoặc `NEED_INFO` (`services/orders.py:33`), có khoá dòng.
- Chỉ thấy đơn của mình; đơn người khác trả 404 qua `OrderRepository.get_owned`.
- Duyệt báo giá ghi lại phiên bản phác thảo, hash, ảnh đã xem và IP (`services/payments.py:84-96`).
- Bấm hai lần ở submit, duyệt, đặt cọc, huỷ không tạo bản ghi trùng: `start_deposit` dùng lại giao dịch đang mở cùng ý định (`services/payments.py:136-138`).

Thiếu hoặc lệch:
- Không huỷ được khi đơn ở `ACCEPTED`, kể cả ngay sau khi tự yêu cầu chỉnh báo giá (CO-01).
- Không chọn được % cọc trên web dù BE cho phép từ mức tối thiểu tới 100 (CO-04).
- Sản phẩm viết lại vẫn lỗi thì không còn kênh nào trong hệ thống ngoài chat (CO-03).
- Tự xác nhận được thanh toán khi cổng ở chế độ MOCK (PP-01).
- Không rút được đồng ý chat AI trên web dù BE có `DELETE /me/assistant/consent`.

### Staff

Kiểm soát đúng:
- Hai Staff cùng nhận một đơn: `UPDATE … WHERE assigned_staff_id IS NULL AND status='SUBMITTED'`, người thua nhận `409 ALREADY_ASSIGNED` (`repositories/orders.py:91-96`).
- Chỉ sửa phác thảo khi đơn `ACCEPTED`, luôn tạo phiên bản mới, chỉ sửa trên phiên bản mới nhất (`services/sketches.py:50-54, 270-274`).
- Giá đã gửi khách thì không sửa được; vượt ngưỡng điều chỉnh phải có Manager duyệt.

Thiếu hoặc lệch:
- Đã tiếp nhận rồi mới thấy không làm được thì không có cách đóng đơn (CO-01).
- Tự chuyển khoản hoàn tiền và tự xác nhận, mã tham chiếu là chữ tự do, tạo sai không huỷ được (PP-03).
- Đơn "phục dựng trung thành" có thể tới khách với nét Staff vẽ thêm mà không có nhãn cảnh báo (SD-02).
- Nhận đơn và tự nhận khi tiếp nhận không ghi nhật ký; Manager phân công không gửi thông báo.

### Technical Staff

Kiểm soát đúng:
- Job của người khác trả 404; mọi thao tác khoá dòng job và đơn (`services/technician.py:71-75`).
- Không bắt đầu viết được nếu hash phác thảo khác gói đã tải, chữ ký gói sai, chưa hiệu chuẩn, hoặc mô phỏng chưa đạt.
- Cần ít nhất 2 ảnh (toàn cảnh + cận cảnh) đều QC đạt mới nộp được; database kiểm lại bằng trigger `fn_photo_uploaded_guard`.

Thiếu hoặc lệch:
- Bấm "bắt đầu" rồi "kết thúc" liền nhau là hợp lệ, không cần robot chạy (TP-05).
- Kết quả mô phỏng do chính máy trạm báo lên và mặc định được tin (TP-04).
- Báo sự cố không dừng robot (TP-01).
- Gửi lại lệnh chạy được ngay sau cảnh báo đỏ (TP-02).

### Manager

Quyền đúng với quyết định của chủ dự án ngày 2026-10-17: chỉ đọc đơn, không thao tác như Staff. Ma trận quyền được test tự động (`tests/test_permission_matrix.py`).

Thiếu hoặc lệch:
- Không tiếp quản được job đã bắt đầu khi kỹ thuật viên vắng (TP-06).
- Không xác nhận hoàn tiền thay Staff, không đổi ngày giao dự kiến thay Staff (`services/refunds.py:249`, `services/eta.py:123`).
- Được gửi RESUME từ xa dù ghi chú trong code nói "không bao giờ cho robot chạy" (TP-03).
- Nhánh code "Manager tiếp nhận đơn" trong `staff_orders._intake_order` không bao giờ chạy vì endpoint chỉ cho Staff.

### Admin

Chỉ `/admin/*`. Khoá hoặc đổi vai trò tài khoản không kiểm việc đang mở của người đó (SD-01), không thu hồi khoá agent của họ (TP-06).

### Robot Agent

Khoá agent chỉ lưu SHA-256, không tạo được lệnh robot. Nhưng mở được gần hết `/technician/*` với danh nghĩa kỹ thuật viên đang có job trên robot đó, kể cả khi tài khoản ấy đã bị khoá (TP-06, SR-05).

## 3. Trùng lặp và bỏ sót giữa các actor

| Câu hỏi | Kết quả |
|---|---|
| Actor nào có quyền vượt trách nhiệm? | Manager RESUME từ xa (TP-03); khoá agent phủ rộng (SR-05) |
| Bước nào cần actor khác xác nhận nhưng bị bỏ qua? | Hoàn tiền (PP-03); kết quả mô phỏng (TP-04); "viết xong" (TP-05); đóng cảnh báo đỏ trước khi chạy lại (TP-02) |
| Actor không làm việc thì hệ thống kẹt ở đâu? | Staff vắng: đơn `ACCEPTED`, hoàn tiền, ETA. Kỹ thuật viên vắng: job `PREPARING` / `WRITING` / `PAUSED`. Khách im lặng: `AWAITING_FINAL_PAYMENT`, `READY_TO_DELIVER` |
| Có cơ chế chuyển giao? | Có cho đơn (`PUT /manager/orders/{id}/assignment`) và job chưa bắt đầu (xếp lại lịch). Không có cho job đã bắt đầu, và không tự động khi khoá tài khoản |
| Thời hạn tự động nào đang có? | Báo giá 7 ngày, cọc 3 ngày, nghiệm thu 7 ngày. Cả ba chỉ chạy khi `BACKGROUND_JOBS_ENABLED=true` (AR-03) |

## 4. Theo module

### A. Customer & Order

Đủ: đăng ký, đăng nhập (mật khẩu, Google, OTP điện thoại), tạo đơn 2 loại đang mở, upload ảnh, canvas vẽ tay, chọn vật tư có kiểm tương thích, giá ước tính, theo dõi, huỷ, nghiệm thu, đánh giá.

Lưu ý nghiệp vụ: hệ thống không có bước "xác nhận bản phác thảo cuối" tách riêng. Duyệt báo giá + đặt cọc chính là xác nhận phác thảo, và bản được khoá là bản khách đã xem lúc duyệt. Đây là quyết định có chủ ý và hợp lý, cần mô tả đúng như vậy khi trình bày.

### B. Staff Operations

Đủ: hàng đợi, nhận đơn, từ chối, yêu cầu bổ sung, phác thảo AI hoặc tải tay, sửa nét, sửa theo vùng, so sánh phiên bản, chốt bản final, báo giá, gửi PDF, chat.

Web chưa dùng các endpoint BE đã có: sửa nét phía server (`sketches/{v}/edit`), vùng phục dựng, so sánh phiên bản. Staff sửa nét trên web rồi gửi cả bản bằng `PATCH`.

### C. Technical Staff & Production

Đủ ở BE và agent: gói job có chữ ký, hiệu chuẩn 3 điểm, kiểm chuyển động phía server, lệnh bền có hạn, lần chạy, sự kiện, sự cố, cảnh báo 4 mức, ảnh + QC, đo chất lượng (tham khảo).

Chưa có: trạng thái robot `BUSY` tự động (không dòng code nào gán), quét nền phát hiện agent mất kết nối, trừ kho cho giấy hỏng khi job thất bại.

### D. Manager & System Operations

Đủ: nhân sự (qua Admin), đơn (đọc), vật tư và tồn kho có nhật ký, bảng giá có phiên bản, lịch có ràng buộc chống trùng ở database, robot, báo cáo doanh thu / sản lượng xuất Excel và PDF, nhật ký thao tác.

Chưa có: chi phí vật tư theo đơn, công suất theo robot theo thời gian thực (suy ra từ lịch, không từ lần chạy thật).

## 5. Đặc tả so với code

| ID | Tài liệu nói | Code làm | Khuyến nghị |
|---|---|---|---|
| DOC-01 | SRS: loadcell + HX711, vòng điều khiển lực | Lò xo + cảm biến Hall, chỉ giám sát; lần chạy thật dùng chế độ không cảm biến | Sửa SRS, nêu là giới hạn |
| DOC-02 | Phiếu đăng ký: OT-2 "học nét chữ" | Tắt; cắt và ghép glyph từ phiếu mẫu | Gọi đúng tên, ghi là R&D |
| DOC-03 | `PROJECT_STATUS.md`: "AI cổ điển, không gọi dịch vụ ngoài" | Trợ lý chat và đọc chữ gọi Claude / GPT / Gemini | Sửa tài liệu, tách hai loại AI khi trình bày |
| DOC-04 | SRS: kỹ thuật viên dùng Flutter Desktop | Quyết định 2026-11-26: màn máy trạm của Robot Agent | Chốt một kênh chính trước demo |
| DOC-05 | SRS 3.1.3: Manager thao tác đơn, Admin xem đơn | Manager chỉ đọc, Admin không thấy đơn | Sửa ma trận trong SRS |
| DOC-06 | BR-13: viết lại lần sau tính phí | Lần hai bị từ chối | Xem CO-03 |
| DOC-07 | UC-41: gán job cho robot + kỹ thuật viên | Robot cố định theo kỹ thuật viên, kỹ thuật viên tự chọn | Sửa UC-41 |
| DOC-08 | FR-19: gọi API hoàn tiền của cổng | Chuyển khoản tay | Ghi là phương án dự phòng |
| DOC-11 | Luồng tham chiếu có bước "xác nhận phác thảo cuối" sau cọc | Duyệt báo giá là xác nhận | Mô tả lại luồng |
| DOC-12 | `HANDOFF.md` mục 4–5, `FE_API_GUIDE.md` mục 0, README gốc | Đã lỗi thời | Cập nhật hoặc ghi "lỗi thời" |
| DOC-13 | NFR-02..05 hứa số đo (IoU ≥ 80%, lệch ≤ 0,5 mm, lực) | Chưa có số đo hợp lệ trên robot | Xem AI-08, DM-04 |
| DOC-14 | Phiếu đăng ký yêu cầu an toàn | Đã bỏ xác nhận "có người cạnh E-Stop" khi bật REAL (2026-11-26) | Xem RB-04 |
