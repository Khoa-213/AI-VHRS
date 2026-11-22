# Kế hoạch tăng tốc test (I-b)

Trạng thái: **chủ dự án duyệt T1 + T2 ngày 2026-11-21** (Q1: T1 + T2; Q2: đổi luật như mục T2, theo khuyến nghị; Q3: T3 để sau). **T1 và T2 xong** (2026-11-21, chưa commit). Tiến độ ở mục 5.

## 1. Hiện trạng (đo 2026-11-21, máy dev ở Việt Nam → Supabase Singapore)

- Toàn suite trên Supabase: 953 passed trong 2 giờ 31 phút (9.061 s), trung bình 9,5 s / test.
- Một lượt gọi tới Supabase (`select 1` trên kết nối có sẵn): trung vị **61 ms**.
- Một transaction kiểu app (lấy kết nối có kiểm tra, BEGIN, 2 `set_config`, 1 câu lệnh, COMMIT): trung vị **370 ms**, tức khoảng 6 lượt gọi.
- `tests/test_api_payments.py` (20 test, 353 s), đo bằng plugin tạm (không commit) đếm câu lệnh SQL:

| Hạng mục | Số lượt | Thời gian (ước tính) | Tỷ lệ |
|---|---|---|---|
| Câu lệnh SQL | 4.180 (209 / test) | 273 s (đo, trung bình 65 ms / câu) | 77 % |
| Lấy kết nối từ pool (có `pool_pre_ping`) | 512 | ~31 s (512 × 61 ms) | ~9 % |
| BEGIN (psycopg gửi riêng) | 513 | ~31 s | ~9 % |
| COMMIT | 453 | ~28 s | ~8 % |
| bcrypt (tạo tài khoản + đăng nhập) | | 10,8 s (đo) | 3 % |

Các dòng ước tính được tính bằng số lượt × 61 ms. Tổng của chúng vượt wall time một chút, nên đây chỉ là con số gần đúng.

**Kết luận:** gần như toàn bộ thời gian là độ trễ mạng: số lượt gọi nhân 61 ms. CPU, bcrypt và vẽ phác thảo chỉ chiếm phần nhỏ. Muốn nhanh thì phải bớt lượt gọi, chạy song song, hoặc chạy gần DB hơn.

## 2. Các hướng

**T1. Bớt lượt gọi trong mỗi request (code sản phẩm, không thêm thư viện)**
- `set_actor`: gộp 2 câu `set_config` thành 1 câu. Bớt khoảng 160 lượt trên 4.180 ở file đo.
- `current_principal`: đọc tài khoản và phiên đăng nhập bằng 1 câu thay vì 2. Vẫn đọc lại DB ở mỗi request (giữ quy tắc khoá / đăng xuất có hiệu lực ngay).
- Test: tính sẵn hash của mật khẩu test một lần (`make_account` hiện băm bcrypt mỗi lần gọi).
- Giữ `pool_pre_ping`, vì Supabase vẫn đóng kết nối giữa chừng. Không đụng BEGIN / COMMIT.
- Ước tính: nhanh hơn khoảng 10–15 %. Đây là dự đoán, sẽ đo lại sau khi làm.
- Rủi ro thấp. Toàn suite xác nhận hành vi không đổi.

**T2. Chạy song song theo nhóm file (không thêm thư viện)**
- Script `scripts/run_tests_sharded.py` chia các file test thành N nhóm (mặc định 4), cân bằng theo thời gian của lượt trước, và chạy N tiến trình pytest cùng lúc.
- Mỗi nhóm dùng tiền tố dữ liệu riêng `pytest_s<k>_`. Nhóm nào chỉ dọn dữ liệu của mình. Khoá advisory tính theo nhóm.
- Khoá chung của cả bộ chạy chặn việc chạy lẫn với lượt `pytest` thường. Lượt `pytest` thường vẫn dọn toàn bộ `pytest_*` như cũ.
- Các file đụng trạng thái chung (`system_settings`, bảng giá đang dùng, `order_types_enabled`, lập lịch robot, tác vụ nền, đếm số đơn toàn hệ thống; khoảng 19 file cần rà) chạy **nối tiếp** trong một nhóm riêng, sau khi các nhóm song song xong.
- Mỗi tiến trình dùng pool nhỏ hơn (2 + 1). Trước khi bật, kiểm giới hạn kết nối của Supabase session pooler.
- Ước tính: toàn suite từ 2,5 giờ còn khoảng 50–70 phút với 4 nhóm. Đây là dự đoán; phần nối tiếp và số lần mất kết nối sẽ quyết định con số thật.
- Rủi ro trung bình: test phụ thuộc lẫn nhau qua dữ liệu chung có thể lỗi chập chờn. Phải chạy song song 2 lượt sạch rồi mới coi là xong.
- **Cần chủ dự án đổi luật** "không chạy hai phiên pytest cùng lúc": cho phép bộ chạy chia nhóm, còn hai lượt `pytest` thường vẫn cấm chạy cùng lúc.

**T3. Chạy suite từ máy ở Singapore (không đổi code)**
- Ví dụ GitHub Codespace vùng Southeast Asia. Độ trễ tới DB chỉ còn vài ms, nên suite có thể chỉ còn khoảng 10–20 phút. Con số này chưa đo.
- Cần chủ dự án tạo Codespace và đặt `DATABASE_URL` làm secret của Codespace. AI không tự tạo tài khoản hay khoá.
- Dùng quota miễn phí của GitHub. Vượt quota là tốn phí, nên cần chủ dự án quyết.

**Không làm**
- Bỏ `pool_pre_ping`.
- Chạy test trên DB cục bộ thay cho Supabase (trái luật kiểm chứng).
- Gộp nhiều test vào một đơn dùng chung (giảm độ độc lập của test).
- Thêm `pytest-xdist` (thư viện mới; T2 làm được mà không cần nó).

## 3. Câu hỏi cho chủ dự án

- **Q1:** làm những hướng nào? Khuyến nghị: T1 và T2.
- **Q2 (nếu làm T2):** đồng ý đổi luật như mục T2 không? Khuyến nghị: có, kèm khoá chung chặn lẫn với `pytest` thường.
- **Q3:** T3 để chủ dự án tự quyết sau. AI chỉ viết hướng dẫn nếu được yêu cầu.

## 4. Thứ tự nếu duyệt

1. T1 → toàn suite Supabase (nối tiếp như hiện nay) → ghi số đo trước / sau.
2. T2 → rà 19 file trạng thái chung → 2 lượt chia nhóm sạch trên Supabase → cập nhật `CLAUDE.md`, `AI_PLAYBOOK.md`, `PROJECT_STATUS.md` mục 6.

## 5. Tiến độ

- **T1 xong (2026-11-21, chưa commit).** Bớt lượt gọi DB (`app/db/session.py`, `app/api/deps.py`, `app/repositories/sessions.py`), pool nhỏ (`db_pool_size` 3, `db_max_overflow` 2 trong `app/core/config.py`), 6 file test dùng `fresh_email` / `fresh_code`. Toàn suite Supabase (nối tiếp như cũ): **953 passed, 3 skipped, 0 failed, 7.255 s (2 giờ 0 phút 55 giây)**, trước T1 9.061 s: **−20 %**. Dữ liệu thật không đổi, 0 dữ liệu test sót.
- **T2 xong (2026-11-21, chưa commit).** `scripts/run_tests_sharded.py` (3 nhóm, pool 3 + 1 mỗi nhóm), `tests/conftest.py` (tiền tố theo nhóm, khoá của bộ chạy, giữ `order_types_enabled` ở bộ chạy).
  - Lượt T2a (65,9 phút): 951 passed, 1 failed, 1 lỗi dọn. `test_api_materials.py` đếm danh sách gợi ý giới hạn 60 → chuyển sang nối tiếp; tài khoản nhóm bị đơn của nhóm khác trỏ tới (FK) → sửa cách dọn.
  - Lượt T2b (56,4 phút): 950 passed, 2 failed, 1 lỗi. Hai test đồng thời gặp `EMAXCONNSESSION` (Supabase session pooler hết chỗ) → 13 test đồng thời / đếm toàn hệ thống đưa vào `SERIAL_TESTS` (nhóm bỏ qua bằng `--deselect`, phần nối tiếp chạy); cách gỡ liên kết đơn khác nhóm vi phạm `chk_orders_staff_after_accept` → đổi thành: savepoint, xoá được thì xoá, không thì giữ tài khoản, ghi `.test_progress/cross_shard.log`, phần nối tiếp (dọn toàn bộ `pytest_`) xoá sau.
  - **Lượt sạch 1, T2c: 953 passed, 3 skipped, 0 failed, 0 errors, 65,1 phút** (song song 37,9 phút).
  - **Lượt sạch 2, T2d: 960 passed, 3 skipped, 0 failed, 0 errors, 65,7 phút** (thêm 7 test OT-1 v2 không cần DB).
  - Sau mỗi lượt: `cross_shard.log` trống, 0 tài khoản `pytest_` sót, 70 đơn thật cũ đúng checksum.
  - Kết quả: toàn suite **2 giờ 31 phút → 2 giờ 1 phút (T1) → ~65 phút (T1 + T2)**, đúng khoảng dự đoán 50–70 phút. Phần nối tiếp (8 file + 13 test, ~27 phút) là phần dài nhất còn lại.
  - Luật đã đổi theo Q2: `CLAUDE.md`, `AI_PLAYBOOK.md`, `PROJECT_STATUS.md` mục 2 và 6.
- T3 (máy ở Singapore): chưa làm, chờ chủ dự án.
