# 09 — Phương án cần phê duyệt và kế hoạch thực hiện

Trạng thái: **chờ chủ dự án quyết định**. Chưa có dòng code nào được sửa.

Cách trả lời nhanh bằng mã: ghi mã quyết định + chữ cái phương án, ví dụ `D01-A D03-B`. Các mục không cần quyết định nghiệp vụ được gom thành gói ở mục 2.

## 1. Quyết định nghiệp vụ

Phương án A luôn là phương án được khuyến nghị.

### D01 — Thanh toán thử tự xác nhận (PP-01)

- A. Thêm cờ cho phép thanh toán thử, mặc định tắt; môi trường demo bật cờ. Khi tắt: từ chối cổng không phải LIVE, `mock-checkout` trả 403.
- B. Tách hẳn một môi trường demo riêng; môi trường chính chỉ nhận payOS.
- C. Giữ nguyên.
- D. Để sau.

Lý do chọn A: sửa nhỏ, giữ được demo, đóng được lỗ khi mở cho khách thật.
Ảnh hưởng: `services/payments.py`, `services/gateway_checkout.py`, `integrations/payment_gateway.py`, `render.yaml`, web (ẩn cổng thử).

### D02 — Trợ lý AI tự áp dụng đề xuất (AI-01)

- A. Tự áp dụng chỉ với đề xuất đổi nội dung hoặc phác thảo (hoàn tác được); đề xuất đổi số bản, ghi chú, dấu AI, chế độ phục dựng, hoặc bỏ nét khách đã sửa tay thì hỏi xác nhận. Thêm thao tác hoàn lại đề xuất.
- B. Quay lại nút Áp dụng / Bỏ qua cho mọi đề xuất.
- C. Giữ tự áp dụng cho mọi thứ.
- D. Để sau.

Lý do chọn A: giữ trải nghiệm nhanh mà chủ dự án đã chọn ở FE, nhưng không để AI đổi thứ không hoàn tác được.
Ảnh hưởng: `ai/proposals.py`, `ai/assistant.py` (câu chữ prompt), `FE/.../OrderAssistant.tsx`.

### D03 — Bật robot thật từ máy khác trong LAN (RB-04)

Ngày 2026-11-26 chủ dự án đã chọn bỏ xác nhận "có người cạnh E-Stop" và đã được báo rủi ro. Câu hỏi này xin xác nhận lại sau khi thấy đầy đủ chuỗi: mã AUTHORIZE tự điền + bỏ chạy thử bằng một hằng số + cổng mở ra LAN.

- A. Agent chỉ nghe `127.0.0.1` theo mặc định; bật REAL và chạy REAL chỉ nhận từ chính máy trạm; mã AUTHORIZE không trả cho client từ xa.
- B. Giữ mở LAN, khôi phục xác nhận "có người cạnh E-Stop".
- C. Giữ nguyên quyết định 2026-11-26.
- D. Để sau.

Lý do chọn A: người bật robot phải ở cạnh robot là yêu cầu an toàn tối thiểu; không ảnh hưởng cách làm việc tại máy trạm.
Ảnh hưởng: `robot_agent/agent.example.json`, `robot_agent/vhrs_agent/server.py`.

### D04 — Đơn `ACCEPTED` không ai huỷ được (CO-01)

- A. Khách huỷ được ở `ACCEPTED`; Staff phụ trách huỷ được kèm lý do bắt buộc.
- B. Chỉ Staff huỷ được.
- C. Giữ nguyên.
- D. Để sau.

Ảnh hưởng: `services/orders.py`, `api/v1/workshop.py`, web. Không đổi database (trigger đã cho phép).

### D05 — Khoá hoặc đổi vai trò nhân sự đang giữ việc (SD-01, TP-06)

- A. Chặn: trả 409 kèm danh sách đơn / job đang mở; Manager phải phân công lại trước. Thu hồi khoá agent của người đó khi khoá.
- B. Cho khoá ngay; hệ thống tự trả đơn `SUBMITTED` về hàng đợi và báo Manager phần còn lại.
- C. Giữ nguyên.
- D. Để sau.

Lý do chọn A: không có việc nào bị bỏ rơi im lặng. Trường hợp khẩn cấp (cần khoá ngay) vẫn nên có tham số ép buộc kèm lý do.
Ảnh hưởng: `services/accounts.py`, `services/robot_link.py`, `api/deps.py`.

### D06 — "Viết xong" không cần bằng chứng robot (TP-05)

- A. Bắt buộc có một lần chạy thật kết thúc `DONE` cho job; Manager ghi đè được kèm lý do, có nhật ký. Robot mô phỏng được tính.
- B. Không chặn, chỉ hiện cảnh báo cho Manager.
- C. Giữ nguyên.
- D. Để sau.

Ảnh hưởng: `services/technician.py`. Cần kiểm thứ tự gọi của agent (TP-07) trước khi bật.

### D07 — Cách gọi OT-2 (AI-09)

- A. Đổi cách gọi trong tài liệu, slide và giao diện thành "số hoá bộ glyph cá nhân (R&D, chưa mở)"; giữ tên trong code và API để không vỡ hợp đồng.
- B. Đổi cả tên trong code và API.
- C. Giữ nguyên.
- D. Để sau.

### D08 — Đơn kẹt sau sản xuất (CO-02)

- A. Làm tối thiểu: nhắc và đặt hạn thanh toán cuối, báo Manager khi quá hạn; giao thất bại nêu là giới hạn hiện tại.
- B. Làm đầy đủ: thêm đổi sang nhận tại xưởng khi giao thất bại, Manager đóng đơn + hoàn tiền. Cần đổi trigger.
- C. Chỉ nêu là giới hạn.
- D. Để sau.

Lý do chọn A: B cần đổi trigger trạng thái và nhiều module, rủi ro cao sát ngày bảo vệ.

### D09 — Viết lại lần hai (CO-03)

- A. Sửa BR-13 theo code; thêm thao tác Manager mở thêm một lượt viết lại, có nhật ký.
- B. Làm viết lại có phí theo báo giá mới.
- C. Giữ nguyên, nêu là giới hạn.
- D. Để sau.

### D10 — Kênh làm việc của kỹ thuật viên cho buổi demo (DM-02)

- A. Màn máy trạm của Robot Agent (theo quyết định 2026-11-26); cập nhật SRS; DesktopApp nêu là kênh phụ.
- B. DesktopApp Flutter (đúng phiếu đăng ký).
- C. Trình bày cả hai.

Không có khuyến nghị mạnh: A khớp với code mới nhất, B khớp với phiếu đăng ký. Cần chủ dự án chọn theo yêu cầu của hội đồng.

### D11 — Phần robot trong buổi demo (DM-01)

- A. Robot thật viết trọn trang trước buổi bảo vệ (sau khi sửa gói an toàn), demo trực tiếp, có video dự phòng.
- B. Demo bằng mô phỏng + video robot thật, nói rõ.
- C. Chỉ mô phỏng.

### D12 — Chạy test trên Supabase thật (AR-01)

Luật hiện hành ở `BE/CLAUDE.md` yêu cầu chạy test trên Supabase thật sau mỗi lần sửa.

- A. Đổi luật: test chạy trên Postgres cục bộ; `conftest` từ chối khi URL là máy chủ production. Kiểm trên Supabase chỉ còn là kiểm migration.
- B. Giữ luật, chỉ sửa lỗ `order_types_enabled` (AI-10).
- C. Giữ nguyên.

Lý do chọn A: đợt audit này đã chạy đủ bộ test trên Postgres cục bộ trong 3 phút 40 giây với 1.091 test đạt.

## 2. Gói sửa không cần quyết định nghiệp vụ

Các mục này là sửa lỗi hoặc siết an toàn, không đổi nghiệp vụ, không đổi hợp đồng API theo hướng làm vỡ web.

| Gói | Nội dung | Mục | Công | Đổi database |
|---|---|---|---|---|
| G1 — An toàn robot phía BE | Chặn lệnh chuyển động khi còn cảnh báo mức 4 hoặc robot không sẵn sàng; RESUME áp kiểm tra "mô phỏng đã cũ"; bỏ RESUME khỏi quyền Manager; sự cố / huỷ đơn tự gửi STOP và đóng lần chạy; hệ trục giấy kiểm thứ tự điểm dò | TP-01, TP-02, TP-03, TP-09 | M | Không |
| G2 — An toàn robot phía agent | Ghi nhận chạy thử khi mã kế hoạch đổi; REAL cần ≥ 4 điểm dò; sàn Z và trần độ nhấn trong cấu hình agent; bắt mọi lỗi → STOP; một khoá cho thao tác chạm robot; kiểm dừng trước khi ngắt kết nối | RB-02, RB-03, RB-05, RB-06, RB-07 | M | Không |
| G3 — Cổng đóng mặc định | Thiếu `order_types_enabled` thì dùng mặc định; từ chối ảnh quá ~40 MP trước khi giải mã; phát lại lượt chat kiểm chủ đơn trước; duyệt báo giá bắt buộc `sketch_id` | AI-10, AI-11, AI-05, SD-05 | S | Không |
| G4 — Độ tin cậy | Webhook đổi sang `def`; thêm `lock_timeout` + `statement_timeout`; khai đủ biến trong `render.yaml`; handler lỗi chung + logging | AR-02, AR-03, AR-05 | S | Không |
| G5 — Trợ lý AI | Hoàn tác do AI gọi không đổi canvas; savepoint quanh mỗi lần thử hãng; trả rỗng coi là lỗi; giới hạn số lượt AI đồng thời | AI-03, AI-04, AI-06, AI-02 | M | Không |
| G6 — Tài khoản | Lần Google đầu vào tài khoản có sẵn: đặt lại mật khẩu ngẫu nhiên + thu hồi phiên; quên mật khẩu gửi mail sau commit | SR-01, SR-03 | S | Không |
| G7 — Tài liệu | Sửa mâu thuẫn "robot đã chạy", loadcell, "AI không gọi dịch vụ ngoài", `HANDOFF.md`, mặc định v1/v2, nhãn "độ giống" | DM-03, AI-08, AI-12 | S | Không |
| G8 — Nợ nhỏ | Test agent treo trên macOS; webhook GHN dùng header; tắt Swagger ở production; `queue-counts` | RB-11, PP-06, SR-08, SD-08 | S | Không |

Cần đổi database (phải duyệt riêng theo `BE/CLAUDE.md`): SR-02 (trigger chống sửa nhật ký), SD-03 (bảng đã đọc theo người), D08-B (trigger trạng thái).

## 3. Thứ tự thực hiện đề xuất

| Đợt | Nội dung | Điều kiện xong |
|---|---|---|
| 1 | G1 + G2 (an toàn robot) | Test BE và agent đạt; thêm test cho từng mục; chưa chạy robot thật |
| 2 | D01 + G3 + G4 (tiền, cổng, độ tin cậy) | Test đạt; `render.yaml` khai đủ |
| 3 | D04, D05, D06 (lối ra và trách nhiệm) | Test đạt; cập nhật `FE_API_GUIDE.md` |
| 4 | D02 + G5 + G6 (AI và tài khoản) | Test đạt; web kiểm type |
| 5 | G7 + D07 + D09 phần tài liệu | Tài liệu khớp code |
| 6 | Robot thật: tập trọn luồng, thu bằng chứng (D11) | **Chỉ khi có người vận hành và chủ dự án cho phép trực tiếp** |
| 7 | Cập nhật lại 10 file audit theo code cuối | Bảng vấn đề, điểm, kịch bản demo khớp thực tế |

Sau mỗi đợt: chạy lại toàn bộ test BE trên Postgres cục bộ và test agent; `tsc -b` + `i18n:check` cho web nếu có đổi web.

## 4. Ràng buộc khi thực hiện

- Không commit, không push khi chưa được yêu cầu. Commit BE theo tài khoản `Khoa-213`, FE theo `hbaoan07`, không thêm dòng đồng tác giả AI.
- Không đổi schema hay migration ngoài các mục đã ghi "cần đổi database" và đã được duyệt riêng.
- Không đổi hợp đồng API theo hướng làm vỡ web; mục nào đổi (SD-05 bắt buộc `sketch_id`, D01 ẩn cổng thử) thì sửa web trong cùng đợt.
- Không chạy robot thật, không gọi cổng thanh toán thật, không chạy test trên Supabase.
- Mỗi sửa đổi đi kèm test tái hiện vấn đề trước khi sửa.

## 5. Quyết định đã ghi nhận

Chủ dự án trả lời qua hộp chọn ngày 2026-11-27.

| Mã | Quyết định | Ghi chú thực hiện |
|---|---|---|
| Gói sửa | **G1–G7** | G8 chưa duyệt |
| D01 | **A** — cờ cho phép thanh toán thử, mặc định tắt | Sửa BE + ẩn cổng thử ở web |
| D02 | **A** — tự áp dụng có chọn lọc + hoàn lại đề xuất | Sửa BE + FE |
| D03 | **Để sau** | RB-04 giữ nguyên: không đổi `host` trong `agent.example.json`, không đổi `real-enable` (file mẫu chỉ được thêm khoá `station_limits` của gói G2) |
| D04 | **A** — khách và Staff huỷ được ở `ACCEPTED` | Không đổi database |
| D05 | **A** — chặn tới khi phân công lại, có tham số ép buộc kèm lý do | Thu hồi khoá agent khi khoá |
| D06 | **A** — bắt buộc lần chạy `DONE`, Manager ghi đè có nhật ký | Làm sau TP-07 |
| D07 | **A** (gộp vào G7) | Chỉ đổi cách gọi trong tài liệu |
| D08 | **B** — làm đầy đủ | Cần migration đổi trigger trạng thái: viết và thử trên DB cục bộ; **chưa áp lên Supabase khi chưa được xác nhận riêng** |
| D09 | Trả lời tự do, xem dưới | Còn một điểm cần hỏi lại |
| D10 | **B** — DesktopApp Flutter là kênh chính | Ngược với quyết định 2026-11-26; phải kiểm app chạy trọn luồng với BE hiện tại (máy audit không có Flutter) |
| D11 | **A** — robot thật + video dự phòng | Chỉ sau khi xong G1 + G2, có người vận hành |
| D12 | **B** — giữ luật test trên Supabase, chỉ vá lỗ OT-2 (AI-10) | AR-01 không sửa. Trong đợt sửa này tôi chỉ chạy test trên Postgres cục bộ và ghi rõ như vậy; lượt chạy trên Supabase cần chủ dự án cho phép riêng |

**D09 — nguyên văn chủ dự án:** "Được thêm 1 lần viết lại không tốn phí mà, trừ phi đổi nội dung hay vật tư thì mới phải tính báo giá lại từ đầu. Còn nếu không thì được viết lại miễn phí."

Cách tôi hiểu (diễn giải của tôi, cần xác nhận):
- Quy tắc hiện tại trong code (một lần viết lại miễn phí) là đúng ý chủ dự án.
- BR-13 cần viết lại: chỉ tính phí khi khách đổi nội dung hoặc vật tư, và khi đó là báo giá lại từ đầu; không làm luồng "viết lại có phí".
- Điểm chưa rõ: bản viết lại vẫn lỗi (không đổi nội dung, vật tư) thì khách được viết lại miễn phí tiếp, hay vẫn dừng ở một lần và chuyển sang chat với xưởng. Chưa sửa code cho mục này tới khi có câu trả lời.

## 6. Tiến độ thực hiện

Mọi lượt test dưới đây chạy trên Postgres cục bộ tạm, **chưa chạy trên Supabase** (theo luật dự án thì chưa được coi là "đã kiểm chứng"). Chưa commit.

| Đợt | Trạng thái | Kết quả test cục bộ |
|---|---|---|
| 1a — G1 an toàn robot phía BE (TP-01, TP-02, TP-03, TP-07, TP-09 phần BE; kiểm tài khoản kỹ thuật viên khi agent xác thực) | Xong | BE 1.101 đạt, 3 hỏng do môi trường (thiếu `SUPABASE_URL`), 5 bỏ qua. 10 test mới ở `tests/test_audit_robot_safety.py`; 9/10 hỏng khi gỡ phần sửa |
| 1b — G2 an toàn robot phía agent (RB-02, RB-03, RB-05, RB-06, RB-07 phần bắt lỗi, TP-09 phần agent) | Xong | agent 197 đạt, 3 bỏ qua, 1 loại ra (test treo trên macOS, RB-11). 14 test mới ở `robot_agent/tests/test_audit_safety.py` |
| 2 — D01 (cờ thanh toán thử) + G3 (AI-10, AI-11, AI-05, SD-05 phía web) + G4 (AR-02, AR-03, AR-05) + AR-08 (phát hiện mới) | Xong | BE **1.120 đạt, 0 hỏng**, 5 bỏ qua (chạy với `SUPABASE_URL` giả nên 3 test ảnh danh mục không còn hỏng do môi trường). 19 test mới ở `tests/test_audit_gates.py` + 1 ở `tests/test_api_orders.py`. Web: `tsc -b` và `i18n:check` đạt |
| 3 — D04 (huỷ đơn `ACCEPTED`), D05 (chặn khoá / đổi vai trò khi còn việc), D06 ("viết xong" cần lần chạy `DONE`) | Xong | BE **1.128 đạt, 0 hỏng**, 5 bỏ qua; agent 197 đạt. 8 test mới ở `tests/test_audit_workflow.py`; D06 kiểm trong `tests/test_api_technician.py` và `tests/test_api_robot_ops.py` |
| 4 — D02 (trợ lý AI tự áp dụng có chọn lọc + hoàn lại đề xuất), G5 (AI-02, AI-03, AI-04, AI-06), G6 (SR-01, SR-03) | Xong | BE **1.144 đạt, 0 hỏng**, 5 bỏ qua. 11 test mới ở `tests/test_audit_assistant.py`, 5 ở `tests/test_audit_accounts.py`. Web: `tsc -b`, `i18n:check` (3.487 khoá), `npm run build` đạt; **chưa mở trình duyệt để xem bằng mắt** |
| 5 — G7 + D07 + D10 (tài liệu) | Xong | Sửa `PROJECT_STATUS.md` (changelog, hai dòng "robot thật", câu "không gọi dịch vụ ngoài"), `docs/FE_API_GUIDE.md` (mục 7z mới), `docs/source/README.md` (bảng quyết định sau audit), `docs/ROBOT_INTEGRATION.md`, `README.md`, `HANDOFF.md`, `robot_agent/README.md`, `FE/AGENTS.md`; nhãn "Độ giống bản gốc" trên web đổi thành "Nét khớp với mực đã tách" |
| D08-B — lối ra cho đơn kẹt sau sản xuất | Xong (BE) | Migration `0033` (thử upgrade, downgrade, upgrade trên DB cục bộ); `database/AI-VHRS_database_full.sql` sinh lại ở 0033. BE **1.149 đạt, 0 hỏng**. 5 test mới ở `tests/test_audit_order_exits.py`. **Chưa áp lên Supabase**; web chưa có màn cho hai endpoint mới |
| D09 | Chờ chủ dự án trả lời điểm chưa rõ | |

### Thay đổi hành vi cần nhóm biết (đợt 1)

Phía backend:
- Lệnh `RUN`, `DRY_RUN`, `RESUME`, `ALIGN_START` và việc mở lần chạy bị từ chối `409 RED_ALERT_OPEN` khi robot còn cảnh báo mức 4 chưa đóng, và `409 ROBOT_UNAVAILABLE` khi robot đang `MAINTENANCE` / `BROKEN`. `PAUSE` và `STOP` không bị chặn.
- Manager không còn gửi được `RESUME` (chỉ `PAUSE`, `STOP`).
- `RESUME` không kèm `job_id` nay áp cùng kiểm tra `SIMULATION_STALE` như khi có `job_id`.
- `POST /technician/jobs/{id}/finish` trả `409 RUN_OPEN` khi job còn lần chạy chưa đóng.
- Báo sự cố, huỷ đơn sau cọc, đặt robot `MAINTENANCE` / `BROKEN`: lệnh đang chờ của job bị làm hết hạn (`JOB_ENDED`), và nếu còn lần chạy mở hoặc lệnh chuyển động đã giao thì backend tự xếp một lệnh `STOP` (`params.system = true`).
- Khoá agent vẫn đóng được lần chạy của chính nó sau khi job rời trạng thái đang chạy; và bị từ chối `401 AGENT_ACCOUNT_INACTIVE` khi tài khoản kỹ thuật viên bị khoá.
- Báo cáo kiểm chuyển động có thêm cảnh báo `PROBE_ORDER_MIRRORED` và trường `stats.frame.mirrored`.

Phía agent (áp dụng cho chế độ REAL; MOCK và SIM không đổi):
- **Phải thêm `station_limits` vào `agent.json`** (`z_floor_mm`, `max_press_mm`), nếu không REAL trả `STATION_LIMITS_UNCONFIGURED`. Mẫu ở `robot_agent/agent.example.json`.
- **Phải dò ít nhất 4 điểm** (thêm góc dưới-phải), nếu không REAL trả `PROBE_CHECK_POINT_REQUIRED`. Mẫu ở `robot_agent/calibration.example.json`.
- Điểm dò quay ngược chiều (đổi nhầm P1 và P2) bị từ chối `PROBE_ORDER_MIRRORED`.
- Kế hoạch đưa đầu bút thấp hơn `z_floor_mm` bị từ chối `BELOW_Z_FLOOR`; nén lò xo quá `max_press_mm` bị từ chối `PRESS_ABOVE_STATION_LIMIT`.
- Ngưỡng watchdog vượt 10 mm hoặc 10 giây bị coi là chưa cấu hình.
- Chạy thử REAL sau khi hiệu chuẩn lại nay được ghi nhận (trước đây bị kẹt ở `DRY_RUN_REQUIRED`).

### Phát hiện thêm trong lúc sửa

- **Bộ điểm dò mẫu của agent (`DEMO_PROBES`) và của nhiều test cho ra chữ soi gương** khi nhìn từ trên xuống: P0 và P1 bị đặt ngược. Tôi đã tính thử với chữ L và sửa lại bộ điểm mẫu. Hệ quả: mô phỏng 3D ở chế độ SIM trước đây có thể đã hiển thị chữ ngược; cần nhóm mở lại màn 3D để xác nhận bằng mắt. Robot thật không bị ảnh hưởng vì người vận hành dò góc thật của tờ giấy.
- Không sửa hàm căn về điểm bắt đầu (`align_to_start`, một lệnh MoveL dài tới 1.000 mm): đây là lựa chọn có chủ ý của nhóm ("người vận hành giữ E-Stop"). Phần này của RB-07 giữ nguyên, ghi là rủi ro đã chấp nhận.
- Dừng hoặc lỗi vẫn không nhấc bút (phần còn lại của RB-07): cần thử trên robot thật mới dám đổi, nên chưa sửa.

### Thay đổi hành vi cần nhóm biết (đợt 2)

- **Thanh toán thử mặc định bị tắt.** Thêm biến `ALLOW_TEST_PAYMENTS` (mặc định `false`). Khi tắt: cổng MOCK và sandbox không hiện trong `GET /payments/gateways`, tạo thanh toán trả `403 TEST_PAYMENTS_DISABLED`, `mock-checkout` và webhook mô phỏng cũng vậy. **Môi trường demo phải đặt `ALLOW_TEST_PAYMENTS=true` trên Render trước lần deploy tới, nếu không khách demo không thanh toán được** (trừ payOS thật). Bộ test tự bật cờ này.
- Thiếu dòng `order_types_enabled` nay nghĩa là chỉ OT-1 và OT-3 (trước là mở hết). Bộ test và `scripts/run_tests_sharded.py` **không còn xoá dòng này khỏi database**; tiến trình test tự mở mọi loại đơn trong bộ nhớ của nó. Chạy test trên Supabase vì thế không còn mở OT-2 cho khách thật.
- Ảnh trên 40 triệu điểm ảnh bị từ chối `422 IMAGE_TOO_LARGE` trước khi giải mã, ở mọi nơi đọc ảnh khách hoặc ảnh kỹ thuật viên (phân tích ảnh, OT-1 v1 và v2, phiếu mẫu OT-2, ảnh sản phẩm, đo chất lượng, đọc chữ).
- Web gửi `sketch_id` khi duyệt báo giá; nếu xưởng đã thay phác thảo thì nhận `409 SKETCH_VERSION_STALE` và trang tự tải lại. BE vẫn để `sketch_id` là tuỳ chọn để không làm vỡ client cũ.
- Phát lại lượt chat AI (`client_ref`) chỉ còn tìm trong cuộc chat của chính người gọi.
- Bốn webhook (payOS, mô phỏng, MoMo, hãng vận chuyển) chạy phần database trong thread pool thay vì trên vòng lặp sự kiện.
- Mỗi kết nối database đặt `lock_timeout` 20 giây (`DB_LOCK_TIMEOUT_MS`, 0 để tắt). Hết hạn chờ khoá trả `409 RESOURCE_BUSY` kèm `Retry-After: 5`.
- Route không tồn tại và sai method trả khung lỗi chuẩn `{"error": {...}}` (vẫn giữ khoá `detail` cũ bên cạnh). Lỗi không ai xử lý trả `500 INTERNAL_ERROR` trong khung chuẩn, có header CORS, và được ghi log kèm traceback.
- Bật logging ra stdout cho ứng dụng (trước đây `log.info` bị bỏ). Log của `httpx` hạ xuống WARNING để không ghi URL có token.
- `render.yaml` và `.env.example` khai thêm `PAYMENT_MODE`, `ALLOW_TEST_PAYMENTS`, `BACKGROUND_JOBS_ENABLED`, `MOTION_VALIDATION_REQUIRED`, `PRODUCTION_SIGNING_KEY`, `DB_LOCK_TIMEOUT_MS` dưới dạng `sync: false`: chỉ khai tên, **không đổi giá trị nào đang chạy trên Render**.

### Phát hiện thêm trong lúc sửa (đợt 2)

- **AR-08 — Hook "sau commit" chạy cả khi nhả SAVEPOINT** (lỗi có sẵn, đã sửa). SQLAlchemy phát sự kiện `after_commit` cho cả việc nhả một SAVEPOINT. Ba chỗ dùng sự kiện này để làm việc "sau khi commit" vì thế chạy sớm, khi chưa có gì được commit:
  - `services/notifications.py`: request gửi hai thông báo (ví dụ thanh toán cuối: báo khách và báo Staff) thì thông báo đầu bị đẩy đi từ một kết nối thứ hai chưa nhìn thấy dòng đó, nên **push tức thời và email của nó bị bỏ lặng lẽ**. Kết nối thứ hai còn được xin trong lúc request đang giữ khoá đơn: khi pool bận thì thành deadlock, chỉ tự gỡ sau 30 giây (hết hạn pool). Đây là lý do test `test_concurrent_final_payment_starts_and_webhooks_settle_exactly_once` luôn mất 30 giây; sau khi sửa còn 0,65 giây.
  - `services/notification_stream.py`: tin chat được đẩy trước khi commit, kể cả khi request sau đó rollback.
  - `services/manager_catalog.py`: file ảnh cũ của vật tư bị xoá trước khi commit; request rollback thì mất ảnh.
  Cách sửa: ba hook bỏ qua khi `session.in_nested_transaction()`. Có 4 test mới.
- Hàm kiểm ảnh ban đầu của tôi có lỗ: Pillow từ chối mở file quá lớn bằng một ngoại lệ riêng, và tôi coi đó là "định dạng lạ, để OpenCV thử". Test của chính đợt này bắt được; đã sửa và thêm kiểm với JPEG khai kích thước khổng lồ.

### Thay đổi hành vi cần nhóm biết (đợt 3)

- **D04.** Khách huỷ được đơn `ACCEPTED` qua `POST /orders/{id}/cancel` (báo giá đang soạn bị huỷ theo, Staff phụ trách nhận thông báo). Staff phụ trách huỷ đơn `ACCEPTED` qua endpoint **đã có sẵn** `POST /workshop/orders/{id}/cancel` (trước chỉ dùng cho đơn đã cọc): lý do ít nhất 5 ký tự, khách nhận thông báo. Không thêm đường dẫn mới.
- **D05.** `PATCH /admin/accounts/{id}`: khoá, vô hiệu hoá hoặc đổi vai trò một tài khoản còn giữ đơn / job / robot trả `409 ACCOUNT_HAS_OPEN_WORK` kèm danh sách. Gửi `force: true` cùng `reason` để làm ngay trong trường hợp khẩn; danh sách việc bỏ lại được ghi vào nhật ký. Khi khoá hoặc đổi vai trò, khoá agent của tài khoản đó bị thu hồi.
- **D06.** `POST /technician/jobs/{id}/finish` trả `409 RUN_EVIDENCE_REQUIRED` khi job chưa có lần chạy robot nào (không phải chạy thử) kết thúc `DONE`; lần chạy MOCK / SIM được tính. Endpoint mới `POST /manager/jobs/{id}/finish-override` (`reason` ít nhất 10 ký tự) cho Quản lý ghi nhận thay, ghi `JOB_FINISH_OVERRIDE` vào nhật ký. **Luồng demo thuần web (không có agent) phải dùng endpoint ghi đè này, hoặc chạy agent ở chế độ MOCK / SIM.**

### Thay đổi hành vi cần nhóm biết (đợt 4)

Trợ lý AI:
- **D02.** Mỗi đề xuất có thêm `needs_confirmation`, `confirm_reasons`, `revertible`. Web chỉ tự áp dụng đề xuất có `needs_confirmation = false` (đổi nội dung, bố cục, vật tư, phác thảo). Đề xuất đổi số bản, ghi chú, dòng xác thực, chế độ phục dựng, công tắc "để xưởng chọn vật tư", hoặc vẽ lại đè lên nét khách đã tự sửa thì hiện thẻ có nút **Áp dụng vào đơn / Bỏ qua**. Đề xuất đã áp dụng mà đơn chưa đổi gì thì có nút **Hoàn lại** (`POST /orders/{id}/assistant/proposals/{pid}/revert`): đưa lại mọi trường, không chỉ phác thảo; sau đó đề xuất có `status = REJECTED`. Không đổi database. Câu chữ hướng dẫn trong prompt của trợ lý và `FE/AGENTS.md` đã sửa theo.
- **AI-02.** Tối đa 2 lượt trợ lý chạy cùng lúc trong một tiến trình (`AI_MAX_CONCURRENT_TURNS`); lượt thứ ba nhận `503 AI_BUSY`. Một lượt quá 90 giây (`AI_TURN_DEADLINE_SECONDS`) thì thôi không gọi model nữa.
- **AI-03.** Trợ lý gọi hoàn tác / làm lại mà bước đó sẽ đổi hình vẽ tay của khách thì bị từ chối (`CANVAS_WOULD_CHANGE`); khách tự bấm Hoàn tác thì vẫn như cũ.
- **AI-04.** Mỗi lần thử một hãng model chạy trong SAVEPOINT: hãng lỗi thì mọi thay đổi do tool của nó làm bị huỷ, không còn revision mồ côi cho nút Làm lại.
- **AI-06.** Model trả rỗng mà chưa làm gì thì coi là lỗi hãng (`BAD_RESPONSE`, chuyển hãng khác), không còn câu "Tôi đã cập nhật bản nháp". Số lần gọi của hãng lỗi được cộng vào `model_calls`.

Tài khoản:
- **SR-01.** Lần đầu đăng nhập Google vào một tài khoản được tạo bằng mật khẩu: mật khẩu cũ bị vô hiệu, mọi phiên khác bị đăng xuất, chủ email nhận thư giải thích; ghi `ACCOUNT_GOOGLE_LINK` vào nhật ký. Các lần Google sau không đụng gì. Khách đã đăng ký bằng mật khẩu rồi mới dùng Google sẽ phải bấm "Quên mật khẩu" nếu muốn dùng lại mật khẩu.
- **SR-03.** Thư của luồng đăng nhập (mã đặt lại mật khẩu, báo đổi mật khẩu, báo liên kết Google) gửi sau khi commit; với SMTP thật thì gửi ở luồng riêng. "Quên mật khẩu" không còn chậm hơn khi email có tồn tại.
- File mới `app/db/after_commit.py`: hàm `run_after_commit` dùng chung, đã tính đến việc SQLAlchemy phát `after_commit` cả khi nhả SAVEPOINT (AR-08).

### Thay đổi hành vi cần nhóm biết (D08 và đợt 5)

- **D08.** Migration `0033` thêm ba chuyển trạng thái vào trigger: `AWAITING_FINAL_PAYMENT → CANCELLED`, `READY_TO_DELIVER → CANCELLED`, `DELIVERING → READY_TO_DELIVER | CANCELLED`. Không đụng dữ liệu.
  - `POST /workshop/orders/{id}/shipment/to-pickup` (Staff phụ trách): giao thất bại hoặc hàng hoàn thì chuyển đơn sang nhận tại xưởng. Phí vận chuyển đã trả không tự hoàn.
  - `POST /manager/orders/{id}/close` (Manager): đóng đơn chờ thanh toán cuối, chờ nhận, hoặc giao không được; kèm số tiền hoàn do Manager quyết định (0 tới số đã trả chưa hoàn). Mở yêu cầu hoàn `PENDING` với `rule = MANAGER_CLOSE` để Staff chuyển khoản và xác nhận. Sản phẩm đã viết nên `production_status` giữ `FINISHED`.
  - Tác vụ nền `stuck_orders`: nhắc khách sau 3 ngày chưa thanh toán phần còn lại; báo mọi Manager sau 7 ngày chờ thanh toán cuối hoặc 7 ngày chờ khách đến nhận. Ba tham số Admin mới. Chỉ chạy khi `BACKGROUND_JOBS_ENABLED=true`.
  - **Merge vào `main` sẽ làm Render chạy `alembic upgrade head`, tức áp 0033 lên Supabase.**
- Yêu cầu hoàn của lối đóng đơn dùng loại `CANCELLATION` sẵn có với `rule` mới, vì API và web chỉ biết hai loại `CANCELLATION` / `ORPHAN` (bản đầu tôi dùng loại mới và làm hỏng màn danh sách hoàn tiền; test bắt được).
- `database/AI-VHRS_database_full.sql` sinh lại bằng `scripts/build_database_script.py` từ DB cục bộ. Khác bản cũ ở 3 dòng trigger, số revision, và cách `pg_dump` viết lại khoảng 30 ràng buộc CHECK (cùng nghĩa, chỉ khác cách viết ép kiểu).

### Trạng thái từng vấn đề sau khi sửa

| Nhóm | Đã sửa | Sửa một phần | Chưa sửa |
|---|---|---|---|
| CO | CO-01, CO-02 (BE) | | CO-03 (chờ D09), CO-04, CO-05, CO-06 |
| SD | SD-01, SD-05 (web gửi `sketch_id`) | | SD-02, SD-03, SD-04, SD-06, SD-07, SD-08, SD-09 |
| PP | PP-01 | | PP-02, PP-03, PP-04, PP-05, PP-06 |
| TP | TP-01, TP-02, TP-03, TP-05, TP-07, TP-09 | TP-06 (khoá agent và chặn khoá tài khoản xong; Manager chuyển giao job đang chạy chưa có, mới có `finish-override`) | TP-04 (chỉ khai biến, mặc định chưa đổi), TP-08, TP-10 |
| AI | AI-01, AI-03, AI-04, AI-05, AI-10 | AI-02 (giới hạn đồng thời + hạn lượt; vẫn giữ kết nối khi chờ model), AI-06 (chưa có trần theo khách), AI-08 (đổi nhãn; chưa có tập ảnh giữ lại), AI-09 (tài liệu; chưa đo phiếu thật), AI-11 (chặn điểm ảnh; chưa đo thời gian trên Render), AI-12 | AI-07 |
| RB | RB-02, RB-06 | RB-03 (trần watchdog + giới hạn trạm; khối chuyển động vẫn không ký), RB-05 (mới kiểm trên mô phỏng), RB-07 (lỗi bất ngờ gửi STOP; dừng vẫn không nhấc bút) | RB-01, RB-04 (để sau), RB-08, RB-09, RB-10, RB-11 |
| AR | AR-02, AR-03 (khai biến), AR-05, AR-08 | AR-01 (theo D12: chỉ thôi xoá dòng cấu hình) | AR-04, AR-06, AR-07 |
| SR | SR-01, SR-03 | | SR-02, SR-04, SR-05, SR-06, SR-07 (việc của chủ dự án), SR-08 |
| DM | | DM-03 | DM-01, DM-02, DM-04, DM-05 |

Tính theo mức ưu tiên: 3 trong 6 mục P0 đã sửa ở phần mềm (TP-01, TP-02, RB-02) và PP-01 đã có cờ; hai mục P0 còn lại (RB-01, DM-01) cần robot thật.

### Còn lại khi làm tiếp

1. ~~Đợt 4~~ đã xong (xem bảng trên).
2. ~~D08-B~~ đã xong phần BE; còn màn web.
3. ~~Đợt 5~~ đã xong.
4. D09: chờ chủ dự án trả lời điểm chưa rõ.
5. Chưa commit gì. Chưa chạy test trên Supabase. Chưa áp gì lên Supabase hay Render.
6. Chạy toàn bộ suite trên Supabase (luật dự án, D12) khi chủ dự án cho phép; áp 0033 lên Supabase.
7. Mở web bằng trình duyệt để xem thẻ đề xuất mới (Áp dụng / Bỏ qua / Hoàn lại) ở ba ngôn ngữ; chạy `node scripts/check-order-ai-browser.mjs`.
8. Kiểm DesktopApp chạy trọn luồng với BE hiện tại (D10) và xử lý các mã lỗi mới: `RED_ALERT_OPEN`, `RUN_OPEN`, `RUN_EVIDENCE_REQUIRED`.
9. Trên robot thật, có người vận hành: tập trọn luồng với `station_limits` và 4 điểm dò; thu video, log (D11).
