# Tiến độ lượt toàn suite trên Supabase (dừng giữa chừng)

Không commit thư mục này (dữ liệu tạm của một lượt test).

- Bắt đầu 2026-11-16 13:32, chủ dự án yêu cầu dừng lúc khoảng 17:00, tới khoảng 72%. Code lúc chạy: phần còn của U2 + U5, migration 0022, chưa commit.
- `all.txt`: 877 test (collect sau khi dừng).
- `passed.txt`: 624, `skipped.txt`: 3, `failed.txt`: 3, `remaining.txt`: 247 test chưa chạy.
- `supabase_2026-11-16.log`: log gốc (không có traceback vì bị dừng trước phần tóm tắt cuối).
- 3 test fail cần xem lại:
  - `test_background_jobs.py::test_customer_photos_are_purged_after_90_days_only_when_enabled`
  - `test_background_jobs.py::test_the_runner_never_overlaps_and_keeps_going_after_an_error`
  - `test_permission_matrix.py::test_permission_matrix_is_enforced_on_every_route` (cục bộ đã pass sau khi sửa route stream; trên Supabase vẫn fail, chưa rõ nguyên nhân)
- Sau khi dừng đã dọn Supabase: xoá dữ liệu `pytest_*` (43 tài khoản, 11 đơn test), `order_types_enabled` vẫn là `["OT1_COPY_RESTORE", "OT3_TEMPLATE"]`; còn 67 đơn (md5 `fffd9b1a5542009bfe7b99a12870b5ec`, như trước), 15 tài khoản.

## Chạy tiếp

Từ `BE/`: `bash .test_progress/run_remaining.sh` (247 test còn lại + 3 test fail, trên Supabase).
Nếu code đã đổi nhiều kể từ 2026-11-16 thì nên chạy lại toàn suite thay vì chạy tiếp.
Lưu ý: 8 test `test_esms_*` trong `test_api_phone_otp.py` có trong file nhưng không chạy ở lượt đầu (được thêm vào file sau khi lượt chạy bắt đầu), nên nằm trong danh sách còn lại.

## Kết quả chạy tiếp (2026-11-17)

`supabase_resume_2026-11-17_1108.log`: 244 passed, 6 failed (U6 2, U8 4; tạo đơn OT-3 bị 409 CONFLICT). Chạy lại riêng / theo nhóm: đều pass. Cả 877 test đã pass trên Supabase (qua nhiều lượt). Có thể xoá thư mục này.
