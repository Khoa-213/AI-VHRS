# V2: báo cáo nghiệm thu 10 test (Phase I, 2026-11-20)

Mười test nghiệm thu chủ dự án đặt cho V2 (đơn hàng hợp nhất, phác thảo chuẩn, chỉnh sửa bằng AI), mỗi test trỏ tới test tự
động thật trong `tests/`. "Supabase" là lượt toàn suite trên database Supabase thật (Singapore); "cục bộ" là Postgres 18 trên
máy, không phải Supabase. Không test nào gọi mô hình AI thật (bên trả lời được viết sẵn) hay chạy robot thật; thanh toán là
MOCK. Phần đo thật ngoài test ghi ở cột cuối.

Kết quả toàn suite trên Supabase thật (lượt liền 2026-11-20 18:37–21:41): **933 passed, 3 skipped, 5 failed**, cả 5 do Supabase đóng kết nối giữa chừng (`server closed the connection unexpectedly`), chạy lại riêng: 5 passed. Không thấy lỗi logic; chưa có lượt Supabase 0 failed. Dữ liệu thật không đổi. Cục bộ (Postgres 18): 937 passed, 3 skipped, 1 failed, đã sửa (dòng Test 9 bên dưới).

| Test | Yêu cầu | Test tự động | Còn chưa kiểm chứng |
|---|---|---|---|
| 1 Document Editing | Sửa cả văn bản: chữ, font, cỡ theo đoạn, căn lề, giãn dòng, lề, màu mực; vẽ lại; hoàn tác trả lại form | `test_v2_document_level.py` (8 test) | - |
| 2 Region Editing | Sửa theo đoạn / dòng / từ, id ổn định, báo phạm vi ảnh hưởng, vẽ lại giữ id | `test_v2_lines_and_redraw.py` (2), `test_u4_regions.py` (sửa đúng một vùng OT-1, các vùng khác giữ nguyên từng byte) | Id ký tự (F-a: không làm); thay chữ vùng OT-1 bằng chữ gõ (F-d: để sau) |
| 3 Stroke Editing | Dời / xoay / co / nắn nét, chỉ phần chọn đổi, undo / redo | `test_v2_working_sketch.py` (`test_geometry_ops_change_only_the_selection_and_keep_shapes`, `test_geometry_refusals`), `test_v2_staff_editor.py` | - |
| 4 Image Restoration | Ảnh chữ cũ: đọc chữ, vùng không chắc, phục dựng, sửa được | `test_v2_acceptance.py::test_an_old_photo_end_to_end_…` (ảnh mực phai → gợi ý, chữ không đọc được báo cho khách và Staff, Staff viết chữ đó thành vùng `INFERRED`, báo giá, duyệt, snapshot, kiểm tra chuyển động); `test_v2_htr_hints.py` (5); `test_u4_regions.py` | Ảnh hư hại thật của khách (U3 chỉ đo trên bộ công khai); nét trên giấy thật |
| 5 AI Hallucination | AI không bịa chữ rồi coi là bản gốc | `test_v2_acceptance.py`: bản đọc nhiều chữ hơn mực / đoạn chữ không có trên trang → không vùng nào nhận gợi ý (`TOO_MANY_WORDS`); `[?]` → `UNREAD`; gợi ý không bao giờ thành `text` của vùng hay đổi nét; `test_v2_htr_hints.py` (Gemini từ chối, không ai đọc được → không gợi ý); `test_v2_order_assistant.py` (trợ lý đổi chữ → cờ cho Staff) | **Giới hạn đã biết:** bộ gắn chỉ so độ dài chữ với độ rộng mực. Một bản đọc bịa có số chữ và độ dài gần đúng vẫn được gắn; vì vậy gợi ý luôn là gợi ý, không đổi chữ, nét hay giá, và chữ Staff viết cho vùng được gắn nhãn `INFERRED` để khách thấy khi duyệt |
| 6 Unified Order | Một đơn DRAFT, sửa bằng AI, gửi Staff: không đơn trùng, không mất dữ liệu | `test_v2_acceptance.py::test_a_second_submit_is_refused_even_while_the_first_is_running_…` (lần gửi chạy cùng lúc bị chặn; trước Phase I lần gửi thứ hai trả 200 trên đơn đã gửi, đã thử lại bằng cách tạm bỏ khoá); `test_v2_working_sketch.py`; `test_v2_order_assistant.py` (cùng tin nhắn gửi hai lần chỉ chạy mô hình một lần) | `/studio` cũ vẫn là lớp tương thích tới khi FE chuyển xong |
| 7 Sketch Integrity | Không sửa sau khi gửi thì hình học Staff nhận giữ nguyên | `test_v2_working_sketch.py::test_the_staff_receive_exactly_the_strokes_…` (so mã băm v1 với revision khách gửi), `test_sketch_integrity.py` | - |
| 8 Approval & Production | Bản đã duyệt và gói sản xuất có chữ ký khớp nhau | `test_v2_staff_editor.py` (snapshot khoá đúng bản khách duyệt; lệch → `SKETCH_NOT_APPROVED`), `test_production_snapshot.py` (10) | Chạy robot thật (cần người vận hành xác nhận) |
| 9 Regression | Test cũ về đơn, thanh toán, Staff, robot, database không vỡ | Toàn suite (xem dòng kết quả trên) | - |
| 10 Failure & Security | Timeout, nhà cung cấp lỗi, request trùng, sửa đồng thời, revision cũ, công cụ ngoài quyền, lỗi lưu revision | `test_v2_order_assistant.py` (9); `test_v2_acceptance.py`: lưu file lỗi hoặc database lỗi sau khi đã ghi file → không còn gì lưu dở, lần sửa sau dùng lại được; công cụ của trợ lý lưu lỗi → `SAVE_FAILED`, lượt chat vẫn trả lời (trước Phase I cả lượt hỏng 500) | - |

## Đo thật ngoài test (Phase I2)

`I2_htr_product_2026-11-20.md`: 5 trang công khai đọc bằng Gemini thật qua đúng code sản phẩm: CER trung bình 0,018, 505 / 539
vùng nhận gợi ý. Claude chưa đo (không có khoá trên máy).

## Sửa trong Phase I

| Test | Lỗi tìm thấy | Sửa |
|---|---|---|
| 6 | Gửi đơn (và mọi lệnh khách sửa đơn DRAFT) không khoá dòng đơn: hai lần gửi cùng lúc đều qua kiểm tra | `OrderService._get_editable` khoá dòng (`FOR UPDATE`) |
| 10 | Công cụ của trợ lý gặp lỗi lưu bất ngờ (file / database) làm hỏng cả lượt chat, mất tin nhắn và chi phí mô hình đã tính | `OrderTools.run` lùi về savepoint, trả `SAVE_FAILED` cho mô hình, ghi log |
| 9 | Toàn suite cục bộ: 1 test cũ hỏng (`test_concurrent_requests_cannot_book_one_technician_twice`): hai lệnh xếp lịch song song trùng technician bị Postgres báo deadlock khi kiểm tra ràng buộc chống trùng, bên thua nhận 500. Lỗi có từ trước, các lượt trước qua nhờ thời điểm | `SchedulingService._add_job`: chèn job trong savepoint, deadlock (`40P01`) thì thử lại một lần → chờ bên kia rồi ra `409 SLOT_CONFLICT`. Nhánh thử lại chưa thấy chạy trong các lượt test |
| 5 | Bản đọc có nhiều chữ hơn mực (hay cả đoạn chữ không có trên trang) vẫn được chia vào các vùng | `htr_align.match` từ chối cả trang khi số chữ > 1,5 × số vùng mực (trang thật tối đa 1,22 trên 48 trang E2a); `text_hints.pages[].check = "TOO_MANY_WORDS"` |

## Chưa làm / chưa kiểm chứng của V2

- Robot thật, nét trên giấy thật, sai số thành phẩm (cần người vận hành).
- Claude đọc chữ viết tay thật; Gemini / Claude chọn công cụ trên cùng bộ kịch bản (trợ lý).
- OT-2: mô hình học nét chữ người viết (D3 đã chốt nghiên cứu; cần dữ liệu mẫu chữ).
- F-d: thay chữ vùng OT-1 bằng chữ gõ.
- FE chưa chuyển khỏi `/studio`.
