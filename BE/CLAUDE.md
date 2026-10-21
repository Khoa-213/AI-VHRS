# Hướng dẫn cho AI làm việc trong `BE/` (AI-VHRS backend)

Đọc theo thứ tự trước khi làm bất cứ việc gì:
1. `PROJECT_STATUS.md` – dự án đang ở phase nào, việc gì đã/chưa làm, giả định chưa xác nhận, việc kế tiếp.
2. `AI_PLAYBOOK.md` – luật không thương lượng, quy trình, bộ kỹ năng và các bẫy đã gặp.
3. `docs/FE_API_GUIDE.md` – hợp đồng API và luồng cho Frontend (phải cập nhật khi API đổi).
4. `docs/source/README.md` – **tài liệu yêu cầu gốc** (Report 1–3 SRS, danh sách FR/entity bản 2, phiếu đăng ký) đã chép sang markdown, kèm bảng quyết định đã override và các điểm còn mơ hồ. Tra mã BR/FR/UC/MSG/LI ở đó trước khi hỏi chủ dự án (`grep -rn "BR-14" docs/source`); `05_legacy_ui_flow_3actor.md` là bản lỗi thời, không dùng làm yêu cầu.

Tóm tắt luật (chi tiết ở `AI_PLAYBOOK.md`):
- Giao tiếp tiếng Việt, giữ thuật ngữ kỹ thuật tiếng Anh; báo cáo trung thực việc đã chạy / chưa chạy.
- Chỉ làm trong `BE/`. Kết nối robot thật là việc của BE nhưng **chỉ làm khi chủ dự án yêu cầu rõ** (mặc định chừa lại, làm luồng web app trước). Cổng thanh toán/vận chuyển là MOCK có nhãn `mode=MOCK`. Dữ liệu seed thật, không hard-code giả.
- Không đổi schema/migration khi chưa được duyệt; không commit/push khi chưa được yêu cầu; không `--force` lên nhánh chung; **không thêm `Co-Authored-By: Claude`**.
- Không in/commit secret (`BE/.env`).
- Chạy lệnh trong `BE/` (`source .venv/bin/activate`). Code xong phải **chạy test trên Supabase thật** (file mới → toàn bộ suite) rồi **cập nhật `PROJECT_STATUS.md`, `docs/FE_API_GUIDE.md`** (và `AI_PLAYBOOK.md` mục 8 nếu có bài học mới) trong cùng lượt làm việc.
- Phase mới: trình bày kế hoạch và chờ chủ dự án "duyệt" (trừ khi họ đã uỷ quyền rõ ràng cho phase đó).
