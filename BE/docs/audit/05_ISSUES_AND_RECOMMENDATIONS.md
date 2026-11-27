# 05 — Bảng vấn đề và đề xuất chỉnh sửa

75 mục, chia 9 nhóm (74 mục của đợt audit + AR-08 phát hiện khi sửa). Bằng chứng theo ID ở Phụ lục cuối file.

**Loại:** Bug = lỗi đã xác minh trên code · Xung đột = logic nghiệp vụ mâu thuẫn · Thiếu luồng · Bảo mật · Nợ KT = nợ kỹ thuật · Cần kiểm chứng = rủi ro phải chạy thật mới kết luận · Cải tiến = không phải lỗi hiện tại.

**Ưu tiên:** P0 an toàn / sai tiền / sai quyền / hỏng demo chính · P1 đúng đắn nghiệp vụ · P2 nên sửa để ổn định · P3 để sau.
**Công sức:** XS < 1 giờ · S nửa ngày · M 1–2 ngày · L 3–5 ngày · XL nhiều module.

## Tổng hợp

| Nhóm | P0 | P1 | P2 | P3 |
|---|---:|---:|---:|---:|
| 1. Customer & Order (CO) | 0 | 2 | 3 | 1 |
| 2. Staff & Design (SD) | 0 | 2 | 6 | 1 |
| 3. Pricing & Payment (PP) | 1 | 0 | 3 | 2 |
| 4. Technical Staff & Production (TP) | 2 | 5 | 3 | 0 |
| 5. AI & Handwriting (AI) | 0 | 7 | 4 | 1 |
| 6. Robotics & IoT (RB) | 2 | 5 | 3 | 1 |
| 7. Database & Architecture (AR) | 0 | 4 | 3 | 1 |
| 8. Security & Reliability (SR) | 0 | 2 | 5 | 1 |
| 9. Demo Readiness (DM) | 1 | 3 | 1 | 0 |
| **Tổng** | **6** | **30** | **31** | **8** |

## 1. Customer & Order

| ID | Loại | Vấn đề hiện tại | Hậu quả thực tế | Đề xuất | Ưu tiên | Công |
|---|---|---|---|---|---|---|
| CO-01 | Thiếu luồng | Đơn `ACCEPTED` không ai huỷ được và không có thời hạn | Xưởng nhận đơn rồi mới thấy không làm được, hoặc khách vừa yêu cầu chỉnh báo giá muốn rút: đơn treo vô hạn | Thêm `ACCEPTED` vào danh sách khách huỷ được; thêm endpoint Staff huỷ kèm lý do (trigger đã cho phép) | P1 | S |
| CO-02 | Thiếu luồng | Không có lối ra cho `AWAITING_FINAL_PAYMENT`, `READY_TO_DELIVER`, và `DELIVERING` khi giao thất bại | Khách không trả phần còn lại hoặc không đến lấy: đơn mở mãi, hàng nằm kho, số liệu doanh thu sai dần. Giao thất bại chỉ tạo lại vận đơn được | Tối thiểu: tác vụ nhắc + hạn thanh toán cuối, báo Manager. Đầy đủ: đổi sang nhận tại xưởng khi giao thất bại, Manager đóng đơn + hoàn tiền | P1 | M–L |
| CO-03 | Xung đột | BR-13 ghi viết lại lần sau tính phí; code từ chối lần hai | Sản phẩm viết lại vẫn lỗi thì khách chỉ còn nghiệm thu hoặc chờ tự nghiệm thu rồi bị đòi thanh toán | Sửa BR-13 theo code + cho Manager mở thêm một lượt có ghi nhật ký; hoặc làm viết lại có phí | P2 | S–M |
| CO-04 | Xung đột | Web cố định % cọc (ép tối thiểu 50) dù BE cho chọn | Lệch UC-16; bảng giá đặt cọc tối thiểu 30% thì khách vẫn phải cọc 50% | Ô chọn % trong khoảng BE cho phép | P2 | S |
| CO-05 | Thiếu luồng | Sản phẩm mẫu và đánh giá công khai: BE xong, web chưa dùng | Trang chủ chỉ có ảnh tĩnh | Khối trên trang chủ + màn quản lý showcase | P2 | M |
| CO-06 | Nợ KT | Giờ nhận tại xưởng chép cứng ở web | Admin đổi giờ làm việc thì khách chọn giờ bị từ chối | Endpoint đọc `working_hours` | P3 | S |

## 2. Staff & Design Workflow

| ID | Loại | Vấn đề hiện tại | Hậu quả thực tế | Đề xuất | Ưu tiên | Công |
|---|---|---|---|---|---|---|
| SD-01 | Thiếu luồng | Khoá hoặc đổi vai trò Staff không kiểm đơn đang giữ | Đơn, hoàn tiền, ngày giao dự kiến của người đó đứng yên; tin nhắn khách chỉ báo cho tài khoản đã khoá | Khi khoá / đổi vai trò: trả danh sách việc đang mở và chặn cho tới khi phân công lại, hoặc tự trả đơn về hàng đợi và báo Manager | P1 | S |
| SD-02 | Xung đột | Cam kết "phục dựng trung thành, không có nét suy đoán" lách được: tải quỹ đạo tay không có vùng nào; sửa nét không hạ nhãn `ORIGINAL` | Khách nhận và robot viết nét do Staff thêm hoặc biến dạng mà không được cảnh báo | Với OT-1 trung thành: từ chối chốt bản tải tay không có vùng, hoặc gắn cờ hiển thị cho khách; sửa nét hạ nhãn vùng xuống `RESTORED` | P1 | S |
| SD-03 | Bug | Trạng thái "đã đọc" của chat dùng chung một cột; web chỉ lấy 100 tin cũ nhất | Manager mở chat là tin thành "đã đọc" với Staff phụ trách; tin thứ 101 không hiện | Bảng đã đọc theo từng người (hoặc trước mắt chỉ khách và Staff phụ trách được đánh dấu); web dùng `latest=true` | P2 | S |
| SD-04 | Cần kiểm chứng | Tiếp nhận đơn có thể bỏ bản phác thảo khách đã chỉnh mà không báo; lỗi Storage làm hỏng cả bước tiếp nhận | Staff vẽ lại bằng AI thành bản khác bản khách đã làm | Bắt mọi lỗi trong savepoint; trả cảnh báo; cho gọi lại | P2 | S |
| SD-05 | Cải tiến | Duyệt báo giá không bắt buộc gửi `sketch_id` | Tab cũ có thể duyệt phác thảo khách chưa xem, trong khi bản ghi vẫn ghi "đã duyệt bản mới" | Bắt buộc `sketch_id` | P2 | XS |
| SD-06 | Thiếu luồng | Đã cọc mà gói sản xuất không phát hành được thì chỉ còn huỷ + hoàn tiền; lỗi lúc cọc bị nuốt | Manager chỉ biết khi xếp lịch | Báo Manager ngay khi phát hành lỗi; ghi rõ quy trình | P2 | S–M |
| SD-07 | Cần kiểm chứng | Khổ giấy của phác thảo không được đối chiếu với giấy của đơn | Quỹ đạo A4 cho đơn giấy A6: robot viết ra ngoài tờ | Từ chối chốt / phát hành khi khổ khác nhau | P2 | S |
| SD-08 | Bug | Web gọi `GET /workshop/queue-counts` không tồn tại ở BE | Mỗi lần mở hàng đợi tải toàn bộ đơn rồi lọc ở trình duyệt; chậm dần | Thêm endpoint ở BE hoặc bỏ nhánh ở web | P2 | S |
| SD-09 | Nợ KT | Giới hạn "sửa nhỏ" tính theo từng lệnh; số vòng yêu cầu chỉnh không giới hạn; nhận đơn không ghi nhật ký; phân công không thông báo | Lặp lệnh là biến dạng tuỳ ý; khó truy trách nhiệm | Giới hạn tổng lệch; đếm vòng; ghi `ORDER_CLAIM`; thông báo khi phân công | P3 | S |

## 3. Pricing & Payment

| ID | Loại | Vấn đề hiện tại | Hậu quả thực tế | Đề xuất | Ưu tiên | Công |
|---|---|---|---|---|---|---|
| PP-01 | Bảo mật | Chế độ MOCK: khách tự gọi `mock-checkout SUCCESS`. Chế độ sandbox: trả bằng thẻ test. payOS thật chạy song song | Đơn được xác nhận, robot viết, hàng được giao mà xưởng không nhận tiền | Cờ cho phép thanh toán thử, mặc định tắt; khi tắt thì từ chối cổng không phải LIVE và ẩn khỏi danh sách | **P0** khi mở cho khách thật, P1 nếu chỉ demo | S |
| PP-02 | Bug | payOS: tiền về link đã đóng hoặc đã thành công không được gắn cờ hoàn | Tiền thật về tài khoản xưởng nhưng không vào danh sách cần hoàn | Trong `_settle` xét trạng thái trước; cộng dồn số nhận | P2 | S |
| PP-03 | Thiếu luồng | Một Staff tự chuyển khoản và tự xác nhận hoàn tiền; tạo sai không huỷ được; Manager chỉ đọc | Không có đối soát; hoàn tiền của Staff nghỉ việc treo | Cho Manager xác nhận; thêm huỷ yêu cầu hoàn đang chờ; mã tham chiếu duy nhất | P2 | M |
| PP-04 | Cải tiến | Độ khó OT-1 (quyết định giá) dựa trên tỉ số hai số nhiễu, ngưỡng nằm giữa phân bố; thời gian viết dùng ba hằng số giả định | Gợi ý giá và lịch robot gần như ngẫu nhiên với OT-1 | Hiệu chỉnh trên đơn thật và log robot; hoặc để Staff chọn độ khó | P2 | M |
| PP-05 | Nợ KT | Báo giá `APPROVED` không đổi khi đơn bị huỷ; đọc báo giá không khoá có thể ghi hết hạn đè lên lượt duyệt | Báo cáo đếm thừa; khe hở vài mili giây quanh hạn | Khoá khi hết hạn; đổi `APPROVED` sang `CANCELLED` khi huỷ đơn | P3 | XS |
| PP-06 | Bảo mật | Khoá webhook GHN nằm trên URL; VNPay `querydr` không kiểm hash phản hồi; MoMo chưa chạy thật | Lộ nhật ký truy cập là giả mạo được "đã giao" | Dùng header; kiểm hash; ghi rõ MoMo chưa thử | P3 | S |

## 4. Technical Staff & Production

| ID | Loại | Vấn đề hiện tại | Hậu quả thực tế | Đề xuất | Ưu tiên | Công |
|---|---|---|---|---|---|---|
| TP-01 | Thiếu luồng | Kết thúc job, báo sự cố, huỷ đơn, đặt robot `BROKEN` không gửi STOP và không đóng lần chạy đang mở | Hệ thống ghi job đã hỏng trong khi cánh tay vẫn chạy; lần chạy mồ côi chặn job kế tiếp | Khi còn lần chạy mở: từ chối kết thúc; với sự cố / huỷ thì tự chèn STOP, đóng lần chạy, làm hết hạn lệnh chờ | **P0** | M |
| TP-02 | Bảo mật | Cảnh báo mức 4 chưa đóng, robot `MAINTENANCE` / `BROKEN` không chặn RUN / RESUME | Kỹ thuật viên cho robot chạy lại ngay sau E-Stop, trước khi Manager kiểm tra | Từ chối lệnh chuyển động và mở lần chạy khi còn cảnh báo mức 4 hoặc robot không sẵn sàng | **P0** | S |
| TP-03 | Bug | RESUME không kèm `job_id` bỏ qua kiểm tra "mô phỏng đã cũ"; Manager được RESUME từ xa | Sau khi hiệu chuẩn lại, robot viết tiếp theo mặt giấy chưa mô phỏng; người không đứng cạnh E-Stop cho robot chạy | RESUME tự tra job đang chạy và áp cùng kiểm tra; bỏ RESUME khỏi quyền Manager | P1 | XS |
| TP-04 | Bảo mật | Kết quả mô phỏng do máy trạm báo và mặc định được tin; hộp làm việc và giới hạn chuyển động cũng do máy trạm gửi | Một request `{"passed": true}` qua được cổng an toàn | Bật `MOTION_VALIDATION_REQUIRED` ở production; hộp làm việc và giới hạn lưu theo robot do Manager duyệt | P1 | M |
| TP-05 | Xung đột | "Viết xong" chỉ cần job đang `WRITING` | Trừ kho và chuyển sang chụp ảnh dù robot chưa viết | Yêu cầu một lần chạy thật kết thúc `DONE`; Manager ghi đè có nhật ký | P1 | S |
| TP-06 | Thiếu luồng | Manager không tiếp quản được job đã bắt đầu; khoá kỹ thuật viên không kiểm job; khoá agent của người bị khoá vẫn dùng được | Đơn kẹt vô hạn khi kỹ thuật viên vắng; người đã bị khoá vẫn điều khiển được qua máy trạm | Endpoint Manager "đánh hỏng / chuyển giao" kèm lý do; kiểm tài khoản còn hoạt động khi xác thực agent; thu hồi khoá phiên khi khoá | P1 | M |
| TP-07 | Cần kiểm chứng | Agent mất quyền đóng lần chạy khi job rời trạng thái đang chạy | Lần chạy mở mãi, chặn job sau | Cho khoá agent đóng lần chạy của chính robot mình bất kể trạng thái job | P1 | S |
| TP-08 | Nợ KT | `BUSY` không được gán; cùng robot để được hai job `WRITING`; phát hiện agent mất kết nối chỉ khi có người mở màn hình; lệnh `DELIVERED` không có hạn | Mất agent lúc đang viết mà không ai mở màn hình thì không có cảnh báo | Tác vụ nền quét; từ chối chuẩn bị khi robot đã có job đang chạy; đặt `BUSY` hoặc bỏ hẳn | P2 | S |
| TP-09 | Bug | Hệ trục giấy không kiểm thứ tự điểm dò và không so với khổ giấy | Đổi nhầm P1 / P2 thì chữ bị soi gương mà hệ thống vẫn chấp nhận | Từ chối khi tích có hướng sai dấu; so đáy với khổ giấy | P2 | XS |
| TP-10 | Nợ KT | Kiểm chuyển động chỉ xét trần tốc độ, không xét gia tốc / jerk; tồn kho không trừ giấy hỏng | "Kiểm độc lập" thực chất kiểm kế hoạch do cùng code sinh; kho lệch thực tế | Thêm kiểm gia tốc, jerk; báo sự cố nhận số tờ hỏng | P2 | S |

## 5. AI & Handwriting Intelligence

| ID | Loại | Vấn đề hiện tại | Hậu quả thực tế | Đề xuất | Ưu tiên | Công |
|---|---|---|---|---|---|---|
| AI-01 | Xung đột | Web tự áp dụng mọi đề xuất AI; số bản, ghi chú, dấu AI, chế độ phục dựng không hoàn tác được; AI tự quyết bỏ nét khách đã sửa tay | Không còn bước "khách đồng ý"; trợ lý mời bấm nút không tồn tại | Tự áp dụng chỉ với đề xuất đổi nội dung / phác thảo; hỏi xác nhận với trường không hoàn tác được; thêm thao tác hoàn lại đề xuất | P1 | S–M |
| AI-02 | Cần kiểm chứng | Mỗi lượt chat giữ một kết nối DB và khoá dòng đơn suốt thời gian chờ LLM; pool chỉ 5 | Năm lượt chat cùng lúc có thể làm đứng cả API, kể cả thanh toán | Giới hạn số lượt AI đồng thời; hạn tổng cho lượt; `lock_timeout` | P1 | M |
| AI-03 | Bug | Hoàn tác / làm lại do AI gọi ghi đè bản vẽ tay của khách dù đề xuất chưa áp dụng | Khách mất bản vẽ tay | Chụp và trả lại cả dữ liệu canvas; hoặc chặn AI hoàn tác khi canvas khác nhau | P1 | S |
| AI-04 | Bug | Chuyển hãng LLM không hoàn lại thay đổi của hãng lỗi; revision AI mồ côi không bị ẩn | Nút Làm lại của khách đưa vào đơn nét sửa chưa từng được đề xuất | Savepoint quanh mỗi lần thử hãng; ẩn revision của lượt không sinh đề xuất | P2 | S |
| AI-05 | Bảo mật | Phát lại lượt chat chạy trước khi kiểm chủ đơn | Người biết mã đơn và mã lượt đọc được tin nhắn và nội dung thư (khó đoán, nhưng thiếu lớp chặn) | Kiểm chủ đơn trước | P2 | XS |
| AI-06 | Nợ KT | Chi phí LLM không chặn theo khách; lượt lỗi không đếm; trả rỗng vẫn báo "đã cập nhật"; phân tích phản hồi có thể ném lỗi 500 | Một tài khoản tiêu hết ngân sách ngày; khách nhận câu trả lời sai | Trần theo khách; đếm lượt lỗi; rỗng thì coi là lỗi hãng | P2 | S |
| AI-07 | Xung đột | Chữ đọc từ ảnh đi tới hãng chat khác hãng khách đã đồng ý; bản chép chữ không có tác vụ xoá | Nội dung thư riêng tư tới bên thứ ba ngoài phạm vi công bố và còn lại sau hạn xoá | Bổ sung chính sách (tăng phiên bản) hoặc chặn; xoá bản chép cùng ảnh | P2 | S |
| AI-08 | Xung đột | "Độ giống 95–99%" là nét so với mực hệ thống tự lọc; F1 94,88% đo trên ảnh tổng hợp và chỉnh ngưỡng trên chính tập đó; NFR-02 chưa đạt theo thước đo gốc | Trình bày như "độ chính xác" là sai | Đổi nhãn; luôn nêu tập ảnh và cỡ mẫu; làm tập giữ lại 10–20 ảnh thật | P1 | S |
| AI-09 | Xung đột | OT-2 mang tên "learned style" nhưng là cắt ghép glyph; chưa đo người thật | Lời hứa "học nét chữ" không chứng minh được | Gọi là "số hoá bộ glyph cá nhân, R&D, chưa mở"; đo trên ≥ 2 phiếu thật | P1 | S |
| AI-10 | Bảo mật | Thiếu dòng `order_types_enabled` thì mọi loại đơn được mở | Trong lúc test chạy trên DB thật, hoặc DB chưa seed, khách đặt được OT-2 | Thiếu dòng thì dùng mặc định `[OT1, OT3]` | P1 | XS |
| AI-11 | Bảo mật | Giải mã ảnh trước mọi giới hạn số điểm ảnh; bản v2 chạy hai phép kiểm trên ảnh nguyên cỡ | PNG nén tốt làm sập tiến trình; ảnh điện thoại 12 MP có thể quá thời gian trên Render | Đọc header và từ chối trên ~40 MP; chạy phép kiểm ở bản thu nhỏ; đo trên Render | P1 | S |
| AI-12 | Nợ KT | Tài liệu và chú thích lệch code (mặc định v1/v2, "không gọi dịch vụ ngoài"); trợ lý studio cũ còn mở; trợ lý lưu được cỡ chữ ngoài khoảng form cho phép; 2-opt dừng theo đồng hồ | Hội đồng đọc tài liệu thấy mâu thuẫn; cùng nội dung có thể ra thứ tự nét khác | Sửa tài liệu; tắt route cũ; đưa kiểm tra vào service; dừng theo số vòng | P3 | S |

## 6. Robotics & IoT

| ID | Loại | Vấn đề hiện tại | Hậu quả thực tế | Đề xuất | Ưu tiên | Công |
|---|---|---|---|---|---|---|
| RB-01 | Cần kiểm chứng | Chưa từng viết xong một trang; MoveL dừng hẳn sau mỗi đoạn nên chạy khoảng 1 mm/s | Demo chính chưa được chứng minh; một trang có thể mất hàng chục phút; bút đứng yên trên giấy dễ đọng mực | Chạy trọn nội dung demo có log + video; gộp điểm theo dung sai hình học | **P0** | L |
| RB-02 | Cần kiểm chứng | Độ sâu Z theo điểm dò tay; đúng 3 điểm thì sai số luôn 0; sàn Z duy nhất do người nhập hiệu chuẩn gõ; chạy không cảm biến | Gõ sai vài mm thì gripper ép xuống bàn | REAL yêu cầu ≥ 4 điểm dò; thêm sàn Z và trần độ nhấn trong cấu hình agent, không lấy từ BE | **P0** | S |
| RB-03 | Bảo mật | Tham số an toàn chỉ kiểm > 0; khối chuyển động và hộp làm việc đến từ BE, không ký | Đặt dung sai bám 1e9 là vô hiệu hoá giám sát | Đặt "vỏ trạm" cứng trong agent, từ chối giá trị vượt | P1 | S |
| RB-04 | Bảo mật | File mẫu bind `0.0.0.0`; `real-enable` không kiểm địa chỉ; mã AUTHORIZE được trả về và tự điền; bỏ chạy thử chỉ cần hằng số | Thiết bị bất kỳ trong LAN có token kỹ thuật viên tự bật và chạy REAL; ba lớp khoá quy về một bí mật | Bind `127.0.0.1`; chỉ loopback bật REAL; không trả mã cho client từ xa | P1 | S |
| RB-05 | Cần kiểm chứng | Chạy đua trên cờ `_busy`: preflight chen vào giữa làm STOP trỏ sang runner khác; kiểm "đã dừng thật" chạy sau khi đã ngắt kết nối | Nút DỪNG phần mềm có thể mất tác dụng khi bút đang chạy; báo động đỏ giả | Một khoá cho mọi thao tác chạm robot; kiểm dừng trước khi ngắt | P1 | S |
| RB-06 | Bug | `mark_dry_run_ok` không ghi khi `progress.json` mang mã kế hoạch cũ | Sau hiệu chuẩn lại, chạy thử REAL không bao giờ được ghi nhận; lối ra duy nhất là "bỏ chạy thử" | Ghi đè mã khi chưa viết nét nào | P1 | XS |
| RB-07 | Xung đột | Dừng hoặc lỗi không nhấc bút dù tài liệu ghi "dừng và nhấc"; lỗi bất ngờ không gửi STOP; căn về điểm đầu là một MoveL tới 1.000 mm không kiểm dọc đường | Bút nằm trên giấy khi dừng; chuyển động dài không được kiểm | Bắt mọi lỗi → STOP; chia đoạn ≤ 5 mm; sửa câu chữ | P1 | M |
| RB-08 | Thiếu luồng | Đường Hall / ESP32 chưa trọn: không firmware, bảng lực không dùng, cổng nối tiếp không đóng | BR-20 (quá lực → nhấc bút) không hoạt động; SRS ghi loadcell | Nêu là giới hạn; hoặc viết firmware | P2 | S (tài liệu) / L |
| RB-09 | Bảo mật | `require_signed_packages` mặc định tắt; kiểm chữ ký không kèm mã đơn; hiệu chuẩn không ký | Gói ký cũ của đơn khác, hoặc gói không ký, được nhận | Bật mặc định; truyền mã đơn và phác thảo vào kiểm | P2 | S |
| RB-10 | Cải tiến | Không kiểm va chạm ở REAL; SDK lấy theo commit nhưng file nhị phân không có checksum; SDK 3.8.7.1 trong khi bộ điều khiển V3.8.25 | Phụ thuộc mức phát hiện va chạm của bộ điều khiển | Ghi lại cấu hình va chạm và mặt phẳng an toàn; thêm checksum | P2 | M |
| RB-11 | Bug | Một test treo vô hạn trên macOS / Linux | Bộ test agent không chạy hết ngoài Windows | Dò tiến trình bằng `waitpid` không chặn, hoặc bỏ qua test ngoài Windows | P3 | XS |

## 7. Database & Backend Architecture

| ID | Loại | Vấn đề hiện tại | Hậu quả thực tế | Đề xuất | Ưu tiên | Công |
|---|---|---|---|---|---|---|
| AR-01 | Nợ KT | Bộ test chạy trên Supabase thật, xoá theo mẫu trên hơn 30 bảng, xoá `order_types_enabled` suốt phiên | Mẫu xoá sai là mất dữ liệu thật; tiến trình bị ngắt thì tham số mất hẳn | Chạy trên Postgres cục bộ (đã chứng minh: 3 phút 40 giây); `conftest` từ chối khi URL là máy chủ production | P1 | S |
| AR-02 | Cần kiểm chứng | Bốn webhook `async def` chạy SQL đồng bộ trên tiến trình duy nhất; không có `lock_timeout` | Trong lúc xử lý IPN cả API đứng; có kịch bản treo hẳn | Đổi sang `def`; thêm `lock_timeout` và `statement_timeout` | P1 | XS |
| AR-03 | Cần kiểm chứng | `render.yaml` không khai `PAYMENT_MODE`, `BACKGROUND_JOBS_ENABLED`, `MOTION_VALIDATION_REQUIRED`; trạng thái nằm trong RAM | Quên bật tác vụ nền thì báo giá không hết hạn, cọc quá hạn không huỷ, ảnh không xoá | Khai đủ biến; `/health` báo tuổi lần chạy tác vụ gần nhất | P1 | XS |
| AR-04 | Nợ KT | Gọi HTTP ngoài và xử lý ảnh nặng trong giao dịch đang giữ khoá | Storage hoặc payOS chậm thì cạn pool | Đọc file trước khi khoá; giới hạn đồng thời cho xử lý ảnh | P2 | M |
| AR-05 | Nợ KT | Không có handler cho lỗi chung; không cấu hình logging; không mã request | Lỗi 500 hiện thành lỗi CORS ở web; không truy được sự cố | Hai handler + logging ra stdout + mã request | P2 | S |
| AR-06 | Nợ KT | Migration gốc là no-op trên Supabase; không có kiểm lệch ORM ↔ SQL; hai file SQL để nộp | Lệch không ai phát hiện; nộp nhầm file cũ | Kiểm tự động: dựng DB trống, so schema; bỏ file `AI-VHRS_database.sql` | P2 | S |
| AR-08 | Bug | Hook "sau commit" chạy cả khi nhả SAVEPOINT (phát hiện khi sửa AR-02) | Thông báo đầu của request gửi hai thông báo bị bỏ push và email; xin kết nối thứ hai khi còn giữ khoá đơn gây deadlock 30 giây khi tải đồng thời; ảnh vật tư cũ bị xoá trước commit | Ba hook bỏ qua khi đang ở trong SAVEPOINT. **Đã sửa 2026-11-27** | P1 | XS |
| AR-07 | Nợ KT | Khoảng 40 endpoint không client nào gọi; tài liệu lỗi thời; module lớn; `pytest` không ghim phiên bản | Tốn bảo trì, tăng bề mặt tấn công | Quyết định nối hoặc ẩn; cập nhật tài liệu | P3 | M |

## 8. Security & Reliability

| ID | Loại | Vấn đề hiện tại | Hậu quả thực tế | Đề xuất | Ưu tiên | Công |
|---|---|---|---|---|---|---|
| SR-01 | Bảo mật | Đăng ký không xác minh email + Google khớp theo email | Kẻ xấu đăng ký trước email nạn nhân, sau vẫn xem được đơn, địa chỉ, ảnh chữ viết | Lần Google đầu vào tài khoản có sẵn: đặt mật khẩu ngẫu nhiên và thu hồi mọi phiên | P1 | S |
| SR-02 | Bảo mật | `audit_logs` sửa / xoá được; bản ghi duyệt và gói sản xuất chỉ chặn sửa; thiếu nhật ký đăng nhập | Không chứng minh được nhật ký chưa bị sửa | Trigger chặn sửa / xoá; thêm 3–4 hành động đăng nhập | P2 | S |
| SR-03 | Bảo mật | Quên mật khẩu lộ email qua thời gian trả lời; SMTP chạy trong request | Dò được email nào có tài khoản; SMTP chậm chiếm kết nối | Gửi mail sau commit bằng luồng riêng | P2 | S |
| SR-04 | Bảo mật | Vé xem 3D là JWT 60 phút nằm trên URL, không thu hồi được; `JWT_SECRET` không kiểm độ dài | Kỹ thuật viên bị khoá vẫn xem robot; vé vào nhật ký truy cập | Rút ngắn hạn vé; kiểm tài khoản; kiểm độ dài secret | P2 | XS |
| SR-05 | Bảo mật | Khoá agent mở gần hết `/technician/*`; khoá Manager không hết hạn; hai agent cùng kéo lệnh một robot được | Lộ khoá là kết thúc job, đặt robot hỏng, nộp ảnh thay người | Danh sách route cho phép; hạn cho khoá; từ chối agent thứ hai | P2 | S |
| SR-06 | Thiếu luồng | Xoá ảnh khách chỉ chạy khi bật hai cờ; không có quy trình sao lưu / khôi phục | Ảnh chữ viết có thể lưu vô hạn; mất dữ liệu không có đường lùi | Xác nhận cờ; viết quy trình sao lưu | P2 | S |
| SR-07 | Bảo mật | Việc "xoay mật khẩu DB và secret đã lộ trong chat" còn treo | Secret đã lộ vẫn dùng được | Xoay ngay | P1 | XS |
| SR-08 | Cải tiến | Refresh token không xoay vòng; Swagger bật ở production; giới hạn tần suất trong RAM theo IP; endpoint vẽ ảnh mẫu công khai không giới hạn | Bề mặt tấn công rộng hơn cần thiết | Tắt Swagger; giới hạn endpoint vẽ ảnh | P3 | S |

## 9. Demo Readiness

| ID | Loại | Vấn đề hiện tại | Hậu quả thực tế | Đề xuất | Ưu tiên | Công |
|---|---|---|---|---|---|---|
| DM-01 | Cần kiểm chứng | Không có bằng chứng lưu được về robot viết (log, video, ảnh) | Hội đồng hỏi là không có gì đưa ra | Một lần viết trọn trang có video liên tục + log; ảnh bản viết cạnh phác thảo có thước | **P0** | L |
| DM-02 | Xung đột | Kênh kỹ thuật viên: tài liệu ghi Flutter, quyết định mới là màn máy trạm; chuỗi BE + agent + robot chưa chạy trọn | Bước robot viết có thể gãy khi demo | Chốt một kênh, tập trọn luồng ≥ 2 lần | P1 | M |
| DM-03 | Nợ KT | Tài liệu mâu thuẫn: robot đã chạy hay chưa, loadcell, "AI không gọi dịch vụ ngoài", `HANDOFF.md` | Hội đồng đọc thấy mâu thuẫn | Sửa trước khi nộp | P1 | S |
| DM-04 | Cần kiểm chứng | NFR-02..05 và câu hỏi nghiên cứu hứa số đo; chưa có số đo trên robot | Không trả lời được "sai lệch bao nhiêu mm" | Đo trên bản viết thật bằng Service G + thước; hoặc nêu là giới hạn | P1 | L |
| DM-05 | Cải tiến | Giao hàng và thanh toán khi demo là MOCK | Dễ bị hiểu là thật | Nói rõ trên slide; nhãn `mode=MOCK` đã có sẵn trên giao diện | P2 | XS |

---

## Phụ lục — Bằng chứng theo ID

Đường dẫn BE tính từ `BE/app/`. **✓** = tôi đã tự đọc lại đoạn code này sau khi nhóm phân tích báo cáo. Mục không có ✓ dựa trên một lượt đọc của nhóm phân tích.

| ID | Bằng chứng |
|---|---|
| CO-01 ✓ | `services/orders.py:34` (`CANCELLABLE_ONLINE` không có `ACCEPTED`); trigger `database/AI-VHRS_database_full.sql:466`; `domain/refund_rules.py:66-67`; `api/v1/workshop.py` không có endpoint huỷ |
| CO-02 | Trigger dòng 473-475; `services/refunds.py:133`; `services/delivery.py:170,284`; `services/background_jobs.py` không có tác vụ cho các trạng thái này |
| CO-03 | `docs/source/03_report3_srs.md:353`; `domain/photo_rules.py:118-122`; `services/acceptance.py:150` |
| CO-04 | `FE/src/pages/order/OrderReview.tsx:106,346` |
| CO-05 | `api/v1/reviews.py:214-257`; `FE/src/pages/landing/components/Showcase.tsx` |
| CO-06 | `FE/src/utils/pickupSlots.ts:1-12` |
| SD-01 ✓ | `services/accounts.py:61-91`; `services/messages.py:125-129`; `services/refunds.py:84,249`; `services/eta.py:123` |
| SD-02 | `services/sketches.py:186-193, 288-300, 410-417, 435`; `services/quotations.py:533-545`; `services/sketch_geometry.py:72` |
| SD-03 | `repositories/workshop.py:120-127`; `services/messages.py:169-171`; `FE/src/services/workshop.ts:577`; `api/v1/messages.py:49-59` |
| SD-04 | `api/v1/workshop.py:147-154`; `services/sketches.py:142-163` |
| SD-05 | `api/ops_schemas.py:32`; `services/payments.py:66` |
| SD-06 | `services/production_snapshot.py:170-177`; trigger dòng 471 |
| SD-07 | `services/sketches.py:60-64`; `services/stroke_ai/trajectory.py:116-119` |
| SD-08 ✓ | `FE/src/services/workshop.ts:99,125`; không có `queue-counts` trong `BE/app` |
| SD-09 | `services/sketch_geometry.py:58-72`; `services/quotations.py:602-615`; `services/staff_orders.py:56-77` |
| PP-01 ✓ | `services/payments.py:129-165, 177-183`; `integrations/payment_gateway.py:124-180`; `services/delivery.py:241`; `render.yaml` không khai `PAYMENT_MODE` |
| PP-02 | `services/payments.py:220-230, 287-288, 356` |
| PP-03 | `services/refunds.py:247-253, 270-272, 296-305`; `api/v1/refunds.py:90-107` |
| PP-04 | `services/stroke_ai/engine.py:75-78`; `services/stroke_ai/trajectory.py:25-29, 78-79`; `docs/benchmarks/U3_recovery_viet_hw_2026-11-12.md` |
| PP-05 | `services/quotations.py:59-64, 479-489`; `services/orders.py:271-274` |
| PP-06 | `integrations/ghn.py:157-161`; `integrations/vnpay.py:130`; `integrations/momo.py:12-16` |
| TP-01 ✓ | `services/technician.py:467-510`; `services/manager_catalog.py:303-315`; `services/refunds.py:148-152` |
| TP-02 ✓ | `services/robot_link.py:281-344` (không đọc `RobotAlert`, `Incident`, `Robot.status`); `services/robot_ops.py:98-137` |
| TP-03 ✓ | `services/robot_link.py:40-42, 320-322` |
| TP-04 ✓ | `core/config.py:139`; `services/technician.py:366-383` |
| TP-05 ✓ | `services/technician.py:467-488`; `services/robot_ops.py:482-485` |
| TP-06 | `services/scheduling.py:295-302`; `api/deps.py:35-44`; `services/robot_link.py:152-163` |
| TP-07 | `services/robot_link.py` `technician_for_agent`; `PATCH /technician/runs/{run_id}` |
| TP-08 | Không có phép gán `RobotStatus.BUSY` trong `app/`; `api/v1/robot_ops.py:80,162`; `services/scheduling.py:245` |
| TP-09 | `services/motion/frame.py:103-105` |
| TP-10 | `services/motion/validate.py` `_check_plan`; `services/motion/plan.py:183-190`; `domain/job_rules.py:148-154` |
| AI-01 ✓ | `FE/src/pages/create-order/ai/OrderAssistant.tsx:193-203`; `services/ai/assistant.py:82-85,106`; `services/ai/proposals.py:280-281`; `services/sketch_work.py:80-92` |
| AI-02 | `services/ai/assistant.py:315,321,451`; `core/config.py:17-18` |
| AI-03 | `services/ai/order_tools.py:464-470`; `services/sketch_work.py:303-347`; `services/ai/proposals.py:91-119` |
| AI-04 | `services/ai/assistant.py:335-349, 404-414`; `services/sketch_work.py:174-182` |
| AI-05 ✓ | `services/ai/assistant.py:252-268, 315-318`; `api/v1/order_assistant.py:308-309` |
| AI-06 | `services/ai/order_tools.py:335-338`; `services/ai/assistant.py:133-141, 172-182, 417-418, 454-456`; `services/ai/llm.py:153,193,240` |
| AI-07 | `services/ai/order_tools.py:278-309`; `services/ai/chat_policy.py:39-47`; `services/ai/chat_sessions.py:81-104` |
| AI-08 | `services/stroke_ai/recovery_v2.py:148-157`; `scripts/benchmark_ot1v2.py:1-20`; `docs/benchmarks/OT1v2_R4_product_2026-11-22.md` mục 2, 6, 8 |
| AI-09 | `services/stroke_ai/sample_sheet.py`; `services/stroke_ai/style_source.py:22-24, 67-75`; `services/stroke_ai/engine.py:222`; `docs/OT2_LEARNED_STYLE_PLAN.md:221,233` |
| AI-10 ✓ | `services/orders.py:174-176`; `services/studio.py:116-118`; `tests/conftest.py:201-202` |
| AI-11 | `services/handwriting_image.py:91`; `services/stroke_ai/recovery.py:505`; `recovery_v2.py:300-309`; `services/stroke_ai/paper.py:125,154` |
| AI-12 | `services/stroke_ai/recovery_v2.py:27-28`; `services/ai/tools.py:21,121`; `services/ai/order_tools.py:340-369`; `services/stroke_ai/path_order.py:25,98,102` |
| RB-01 | `robot_agent/vhrs_agent/linear_motion.py:59-63, 80-117`; `PROJECT_STATUS.md:434` |
| RB-02 | `services/motion/frame.py:113-124`; `services/motion/plan.py:72-74,302`; `robot_agent/vhrs_agent/runner.py:357-363` |
| RB-03 | `services/motion/plan.py:62-69`; `robot_agent/vhrs_agent/runner.py:51-53`; `services/motion/validate.py:43-45` |
| RB-04 ✓ | `robot_agent/agent.example.json:4`; `robot_agent/vhrs_agent/server.py:570, 715-722`; `static/assets/app.js:532,577`; `docs/source/README.md:36` (quyết định 2026-11-26) |
| RB-05 | `robot_agent/vhrs_agent/server.py:338,364,609,655-659`; `runner.py:266-279` |
| RB-06 ✓ | `robot_agent/vhrs_agent/runner.py:88-98, 370-373` |
| RB-07 | `robot_agent/vhrs_agent/linear_motion.py:131-133, 150-152, 194`; `gripper.py:112` |
| RB-08 | `robot_agent/vhrs_agent/gripper.py:195`; `docs/ROBOT_INTEGRATION.md:107`; `docs/ROBOT_FIRST_REAL_TEST.md` mục A3 |
| RB-09 | `robot_agent/vhrs_agent/bridge.py:118` |
| RB-10 | `robot_agent/vhrs_agent/kinematics.py:186-191`; `fairino_robot.py:199-208`; `scripts/fetch_fairino_sdk.py` |
| RB-11 ✓ | `robot_agent/vhrs_agent/server.py:845-850`; tái hiện bằng chạy test trong đợt audit |
| AR-01 ✓ | `tests/conftest.py:49-147, 192-209`; `CLAUDE.md` (luật chạy test trên Supabase) |
| AR-02 ✓ | `api/v1/payments.py:85,103,140`; `api/v1/shipments.py:112`; `db/session.py:19` |
| AR-03 | `render.yaml`; `core/config.py:54,133,139` |
| AR-04 | `services/orders.py` `confirm_upload`; `services/quality_service.py:35-60`; `services/payments.py:130-145` |
| AR-05 | `core/errors.py:26-47` |
| AR-06 | `migrations/versions/0001_baseline.py`; `migrations/env.py:13`; `database/AI-VHRS_database.sql` |
| AR-08 ✓ | `services/notifications.py` `_after_commit`; `services/notification_stream.py` `_after_commit`; `services/manager_catalog.py` `_after_commit`; tái hiện bằng script: `after_commit` phát khi nhả SAVEPOINT với `in_nested_transaction() == True` |
| AR-07 | Danh sách ở báo cáo tích hợp FE: showcase, `/styles*`, ảnh và hồ sơ vật tư, so sánh phác thảo, lệnh robot phía Manager |
| SR-01 ✓ | `services/auth.py:47-55, 89-108` |
| SR-02 | `database/AI-VHRS_database_full.sql:944-960, 3923, 3959`; `migrations/versions/0017_sketch_approvals.py:27-29` |
| SR-03 | `services/auth.py:119-131, 155-167` |
| SR-04 | `services/robot_view.py:25-35`; `api/v1/robot_link.py:160-161`; `core/config.py:19` |
| SR-05 | `api/deps.py:39` |
| SR-06 | `services/background_jobs.py:216-234`; `DEPLOY.md` |
| SR-07 | `PROJECT_STATUS.md` mục 1, việc chờ chủ dự án số (4) |
| SR-08 | `services/auth.py:110-116`; `render.yaml:28-29`; `core/ratelimit.py:20`; `api/v1/catalog.py:109-113` |
| DM-01..05 | Xem `04_AI_ROBOTICS_AUDIT.md` mục 5 và `01_BUSINESS_LOGIC_AUDIT.md` mục 5 |

### Đã kiểm và không thấy lỗi

- Hai Staff cùng nhận một đơn; hai kỹ thuật viên cùng bắt đầu một job; trùng lịch robot.
- Bấm nhiều lần ở gửi đơn, duyệt báo giá, đặt cọc, thanh toán cuối, huỷ.
- Callback thanh toán trùng, sai số tiền, cho đơn đã huỷ (trừ PP-02).
- Giá đổi sau khi khách duyệt; Staff sửa phác thảo sau khi khách duyệt; khách sửa nội dung sau khi gửi.
- Khách đọc đơn, báo giá, thanh toán, vận đơn, phác thảo của khách khác (trừ AI-05).
- Ảnh trắng, ảnh đen, dữ liệu rác: trả lỗi 422 đúng.
- Secret trong mã nguồn và lịch sử git theo mẫu thường gặp: không có.
