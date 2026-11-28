# 07 — Đánh giá mức độ sẵn sàng

Mã vấn đề tra ở `05_ISSUES_AND_RECOMMENDATIONS.md`.

## 1. Chấm điểm

Giữ nguyên trọng số tham chiếu. Thang 10. "Tin cậy" là độ chắc của chính điểm số, dựa trên việc đã chạy thật hay chỉ đọc code.

| Tiêu chí | Trọng số | Điểm | Tin cậy | Cơ sở | Hạn chế kéo điểm xuống | Để lên mức cao hơn |
|---|---:|---:|---|---|---|---|
| Business Logic Completeness | 20% | 7,0 | Cao | Đủ luồng chính và phần lớn luồng phụ (huỷ sau cọc, hoàn tiền, viết lại, hết hạn, ETA); luật nằm ở hàm thuần và trigger | Trạng thái không có lối ra (CO-01, CO-02); nhân sự vắng làm kẹt việc (SD-01, TP-06); hoàn tiền một người tự xác nhận (PP-03) | Sửa CO-01, SD-01, TP-06; chốt quy trình CO-02 |
| End-to-End Workflow | 20% | 6,5 | Trung bình | Bước 1–8 và 12–15 có code, nối web, 1.091 test đạt trên DB cục bộ | Bước 9–11 chưa chạy trọn với BE + agent + robot thật; nhiều bước dựa vào mock và thao tác tay | Tập trọn luồng trên máy trạm thật (DM-02) |
| AI & Handwriting Intelligence | 10% | 6,5 | Cao | Pipeline thị giác tự cài đặt, có benchmark; LLM bị kiểm soát bằng hàm + đề xuất + hash | Số đo trên ảnh tổng hợp; "độ giống" dễ hiểu sai; OT-2 không học; web tự áp dụng đề xuất | Tập giữ lại ảnh thật (AI-08); sửa AI-01, AI-03 |
| Robotics & Production | 15% | 4,0 | Trung bình | Thiết kế an toàn phần mềm tốt; 183 test agent đạt trên mô phỏng | Chưa viết xong một trang; vòng hở; cảm biến lực chưa nối; 4 mục P0 về an toàn | Một lần viết trọn trang có bằng chứng; sửa TP-01, TP-02, RB-02 |
| — Chất lượng bản viết vật lý | (trong mục trên) | **Not Verified** | — | Không có bản viết hoàn chỉnh nào để đo | — | Đo bằng Service G + thước (DM-04) |
| Data Integrity & Consistency | 10% | 8,0 | Cao | 139 CHECK, 139 khoá ngoại, 2 EXCLUDE, 20 trigger; hash + chữ ký xuyên suốt; webhook idempotent | Nhật ký sửa / xoá được (SR-02); trạng thái job chỉ kiểm ở Python | Trigger chống sửa nhật ký |
| Security & Authorization | 10% | 6,5 | Cao | RBAC + phân quyền theo bản ghi phủ kín, có test ma trận quyền; thu hồi phiên tức thì; không lộ secret trong mã nguồn | Thanh toán thử tự xác nhận (PP-01); chiếm tài khoản qua Google (SR-01); khoá agent (TP-06); agent mở ra LAN (RB-04) | Sửa bốn mục trên |
| Reliability & Error Recovery | 5% | 5,0 | Trung bình | Lệnh robot bền trong DB; tác vụ nền có khoá; agent ghi tiến độ từng nét | Một tiến trình, trạng thái trong RAM, không `lock_timeout`, phát hiện agent mất kết nối chỉ khi có người xem, chưa có sao lưu | AR-02, AR-03, TP-08, SR-06 |
| Maintainability & Architecture | 5% | 7,0 | Cao | Phân tầng rõ, 1.286 test hai gói, tài liệu dày | Test chạy trên DB thật (AR-01); tài liệu lệch code; vài module lớn; không có CI | Chuyển test sang DB cục bộ + CI |
| Demo Readiness | 5% | 5,5 | Trung bình | Luồng web demo được; nhãn MOCK hiển thị rõ | Phần robot chưa chứng minh; chưa chốt kênh kỹ thuật viên; tài liệu mâu thuẫn | DM-01..04 |
| **Tổng có trọng số** | 100% | **6,3** | | | | |

Cách tính: 0,2×7,0 + 0,2×6,5 + 0,1×6,5 + 0,15×4,0 + 0,1×8,0 + 0,1×6,5 + 0,05×5,0 + 0,05×7,0 + 0,05×5,5 = 6,28.

Điểm tổng không bù được điều kiện chặn. Các mục về an toàn robot, sai tiền và sai quyền dưới đây chặn mức sẵn sàng tương ứng bất kể điểm.

## 2. Ba mức sẵn sàng

### Academic Demo Ready — **Conditionally Ready**

Đủ khi đạt cả ba điều kiện:
1. Có một lần robot viết trọn trang (trực tiếp hoặc video quay liên tục kèm log), hoặc công khai với hội đồng rằng phần viết là mô phỏng.
2. Sửa TP-01, TP-02, TP-03, RB-06 trước mọi lần chạy robot thật tiếp theo.
3. Lời trình bày khớp với thực tế: OT-2, con số "độ giống", vòng hở, cảm biến lực (AI-08, AI-09, DM-03).

### Enterprise Pilot Ready — **Not Ready**

Điều kiện chặn:

| Chặn | Mã | Lý do |
|---|---|---|
| An toàn robot | TP-01, TP-02, RB-02, RB-04 | Hệ thống có thể coi job đã dừng khi tay máy còn chạy; chạy lại được ngay sau E-Stop; độ sâu Z không có sàn cứng; bật REAL được từ máy khác trong LAN |
| Sai tiền | PP-01 | Đơn được xác nhận không cần tiền thật |
| Chưa chứng minh sản phẩm | RB-01, DM-04 | Chưa có bản viết hoàn chỉnh và chưa có số đo |
| Vận hành | SD-01, TP-06, CO-02 | Nhân sự vắng hoặc khách im lặng làm đơn kẹt không lối ra |
| Dữ liệu | AR-01, SR-07 | Test chạy trên DB thật; secret đã lộ chưa xoay |

Cần thêm cho một xưởng thật: quy trình hiệu chuẩn đo bằng số (độ cứng lò xo, TCP, 9 điểm dò), biên bản thử E-Stop vật lý, cấu hình phát hiện va chạm của bộ điều khiển, quy trình sao lưu, hoàn tiền có đối soát, hãng vận chuyển thật.

### Production Ready — **Not Ready**

Ngoài các mục trên: chạy một tiến trình với trạng thái trong RAM; không có giám sát, cảnh báo hay mã request; chưa đo tải; chưa có chính sách lưu giữ dữ liệu chạy thật; MoMo và GHN chưa chạy trọn với hệ thống thật; chưa có giấy phép để dùng cổng thanh toán ở chế độ live.

## 3. Trả lời trực tiếp

**Ngày mai demo trước hội đồng doanh nghiệp thì đã sẵn sàng chưa?**
Phần web: có, với thanh toán và vận chuyển ở chế độ MOCK có nhãn. Phần robot: chưa. Chưa có lần viết trọn trang nào, và chuỗi BE + agent + robot với code hiện tại chưa chạy lần nào. Demo ngày mai chỉ an toàn nếu phần robot là mô phỏng hoặc video và nói rõ điều đó.

**Hội đồng yêu cầu một luồng ngoài kịch bản thì sao?**
Đáp ứng được: huỷ đơn ở các bước trước cọc, huỷ sau cọc có hoàn tiền, yêu cầu chỉnh báo giá, viết lại một lần, báo giá hết hạn, hai người cùng nhận một đơn, callback thanh toán trùng.
Không đáp ứng được: huỷ đơn đang `ACCEPTED`; khách không trả phần còn lại; giao hàng thất bại; viết lại lần hai; kỹ thuật viên vắng giữa job; đặt đơn OT-2; yêu cầu robot viết một nội dung bất kỳ ngay tại chỗ.

**Nhiều khách và nhân viên dùng cùng lúc thì rủi ro gì?**
- Vài lượt chat AI hoặc vài ảnh OT-1 cùng lúc có thể chiếm hết 5 kết nối database và làm đứng cả API (AI-02, AR-04).
- Webhook thanh toán chặn tiến trình duy nhất trong lúc xử lý (AR-02).
- Hàng đợi của Staff tải toàn bộ đơn mỗi lần mở (SD-08).
- Giới hạn tần suất tính theo IP trong RAM; nếu Render đưa IP dùng chung thì giới hạn đăng nhập thành giới hạn toàn hệ thống.
- Tính đúng đắn dữ liệu khi đồng thời thì tốt: có test hai yêu cầu cùng lúc cho cọc, thanh toán cuối, xếp lịch, gửi đơn.

**Triển khai thử ở một xưởng thật còn thiếu gì?**
Xem bảng điều kiện chặn của mức Pilot. Ngắn gọn: robot viết được trọn sản phẩm một cách lặp lại; bốn sửa an toàn; thanh toán thật; quy trình cho đơn kẹt và nhân sự vắng; số đo hiệu chuẩn; sao lưu.

**Bắt buộc sửa trước buổi bảo vệ?**
TP-01, TP-02, TP-03, RB-02, RB-06 (trước khi chạy robot thật), DM-01, DM-02, DM-03, AI-08, AI-09, AI-10, PP-01 (ít nhất là đặt cấu hình tường minh), AR-03, SR-07. Nên sửa thêm vì rẻ: CO-01, SD-05, TP-09, AI-05, AR-02.

**Giải thích được là giới hạn hiện tại hoặc hướng phát triển?**
- Điều khiển vòng hở, lực bằng lò xo thụ động; cảm biến Hall là bước tiếp theo (RB-08).
- OT-2 là R&D, chưa mở.
- Tốc độ viết chậm do MoveL từng đoạn; hướng tiếp là chuyển động có trộn đoạn.
- Hoàn tiền chuyển khoản tay vì payOS không có API hoàn; VNPay / MoMo live cần giấy phép kinh doanh.
- Hãng vận chuyển ở chế độ thử.
- Viết lại chỉ một lần miễn phí.
- Một tiến trình, chưa mở rộng ngang.
- Không kiểm va chạm bằng phần mềm; dựa vào bộ điều khiển và E-Stop.
- Service G chưa hiệu chuẩn, chỉ tham khảo.

## 4. Cập nhật sau khi sửa (2026-11-28)

Điểm dưới đây dựa trên code đã sửa và test trên Postgres cục bộ. Chưa có gì được kiểm trên Supabase, Render hay robot thật, nên độ tin cậy của phần tăng điểm là trung bình.

| Tiêu chí | Trước | Sau | Lý do đổi |
|---|---:|---:|---|
| Business Logic Completeness | 7,0 | 8,0 | Có lối ra cho `ACCEPTED`, đơn kẹt sau sản xuất, nhân sự bị khoá; "viết xong" cần bằng chứng |
| End-to-End Workflow | 6,5 | 6,5 | Không đổi: chuỗi BE + agent + robot vẫn chưa chạy trọn |
| AI & Handwriting Intelligence | 6,5 | 7,0 | Trợ lý không còn đổi thứ không hoàn tác được mà không hỏi; hết revision mồ côi; nhãn số đo đúng nghĩa |
| Robotics & Production | 4,0 | 4,5 | Thêm sàn Z cứng, chặn sau cảnh báo đỏ, tự gửi STOP. Vẫn chưa viết xong một trang, và code mới chưa chạy trên robot |
| Data Integrity & Consistency | 8,0 | 8,0 | Sửa hook sau commit; nhật ký vẫn sửa / xoá được |
| Security & Authorization | 6,5 | 7,5 | Cờ thanh toán thử, chiếm tài khoản qua Google, khoá agent, phát lại lượt chat |
| Reliability & Error Recovery | 5,0 | 6,0 | Hết deadlock 30 giây, có `lock_timeout`, webhook không chặn tiến trình, có log lỗi |
| Maintainability & Architecture | 7,0 | 7,0 | Thêm 55 test BE và 14 test agent; test vẫn chạy trên DB thật theo luật dự án |
| Demo Readiness | 5,5 | 5,5 | Không đổi cho tới khi tập trọn luồng |
| **Tổng có trọng số** | **6,3** | **6,8** | |

Ba kết luận không đổi: Academic Demo **Conditionally Ready**, Enterprise Pilot **Not Ready**, Production **Not Ready**.

Điều kiện chặn mức Pilot còn lại:
- RB-01, DM-01, DM-04: robot chưa viết xong một trang, chưa có bằng chứng và số đo.
- RB-04: bật REAL được từ máy khác trong LAN (chủ dự án để sau).
- TP-04: kết quả mô phỏng do máy trạm báo vẫn được tin khi `MOTION_VALIDATION_REQUIRED` chưa bật.
- Mọi sửa đổi về an toàn robot ở đợt này mới kiểm trên mô phỏng.
- SR-07: secret đã lộ chưa xoay.
