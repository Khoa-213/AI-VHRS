# 04 — Trợ lý AI, xử lý nét chữ, robot và IoT

Đường dẫn tính từ gốc repo. Mã vấn đề tra ở `05_ISSUES_AND_RECOMMENDATIONS.md`.

## 1. Trả lời thẳng ba câu hỏi lớn

**Hệ thống có học hay sinh nét chữ của một người không?** Không. Repo không có mô hình huấn luyện hay file trọng số nào; `BE/requirements.txt` không có torch, onnx hay sklearn. Ba việc hệ thống thật sự làm:

| Loại đơn | Thực chất |
|---|---|
| OT-1 chép / phục dựng | Vector hoá mực từ ảnh bằng thị giác máy tính cổ điển, tự cài đặt |
| OT-3 viết theo mẫu | Dàn chữ từ font một nét cố định, dấu tiếng Việt ghép hình học |
| OT-2 "learned style" | Cắt glyph từ phiếu mẫu 3 trang do khách tự viết rồi ghép lại; mỗi chữ có 2–3 mẫu xoay vòng. Không có tham số nào được học. Đang tắt với khách, chưa đo trên phiếu người thật |

**Điều khiển robot là vòng hở hay vòng kín?** Vòng hở có giám sát. Vị trí thật của đầu bút chỉ dùng để chặn bắt đầu, chờ tới đích và dừng khi lệch; không hiệu chỉnh quỹ đạo. Lực tì do lò xo thụ động. Vòng kín duy nhất là servo khớp bên trong bộ điều khiển của hãng.

**Kết quả AI chưa kiểm tra có thành lệnh robot được không?** Không, trên đường code đã đọc. LLM chỉ gọi được các hàm có tên của hệ thống trên bản nháp của khách; nét do engine tất định sinh. Bản tới robot phải qua: Staff chốt bản final → khách duyệt (ghi hash) → cọc → gói ký Ed25519 → kiểm hash khi tải và khi bắt đầu → agent kiểm chữ ký. Điểm hở còn lại là kết quả mô phỏng do máy trạm tự báo (TP-04) và gói không ký vẫn được agent nhận theo mặc định (RB-09).

## 2. Trợ lý AI (LLM)

| Phần | Hiện trạng | Bằng chứng |
|---|---|---|
| Nhà cung cấp | Claude, GPT, Gemini qua adapter HTTP tự viết; thứ tự theo `LLM_PROVIDER_ORDER`; lỗi thì chuyển hãng và chạy lại cả lượt | `BE/app/services/ai/llm.py` |
| Công cụ | 14 hàm trên đơn: đọc đơn, sửa nội dung, bố cục, vật tư, tuỳ chọn, vẽ lại, sửa nét, hoàn tác, gắn cờ cho Staff | `ai/order_tools.py:45-120` |
| Không có | Hàm gửi đơn, thanh toán, huỷ, đổi giá, đổi trạng thái; `order_id` không phải tham số của hàm | như trên |
| Vòng lặp | Tối đa 12 lần gọi hàm mỗi lượt; mỗi hàm chạy trong savepoint; lỗi trả về model dạng mã | `ai/assistant.py:441-477` |
| Ngữ cảnh | Luật hệ thống + tóm tắt đơn (không có tên, email, số điện thoại) + 20 tin gần nhất của đúng cuộc chat | `ai/assistant.py:208-219` |
| Kiểm đầu ra | Mọi tham số đi qua đúng service của form: vật tư còn bán và tương thích, bố cục hợp lệ; sửa nét chỉ nhận tên lệnh + id, có giới hạn theo loại đơn | `ai/order_tools.py`, `sketch_geometry.py` |
| Đề xuất | Hàm chạy trên đơn → chụp trạng thái → trả đơn về như cũ → lưu đề xuất kèm hash trạng thái gốc; áp dụng chỉ khi đơn chưa đổi | `ai/proposals.py` |
| Phiên bản | Mỗi lần sửa nét là một revision có tác giả, công cụ, hãng, model, hash | `sketch_work.py` |
| Đồng ý / lưu giữ | Đồng ý một lần theo phiên bản chính sách; xoá cuộc chat khi đơn còn nháp; tự xoá sau thời hạn lưu ảnh | `ai/chat_policy.py`, `ai/chat_sessions.py` |
| Đọc chữ từ ảnh (HTR) | Khách bấm, xin đồng ý từng lần, mặc định tắt; kết quả chỉ là gợi ý cho vùng chữ, không ghi vào nét hay giá | `ai/htr.py`, `htr_hints.py` |

Ba cấp Document / Region / Stroke Editing: chỉ có hai đường code thật. Cấp văn bản (sửa nội dung rồi engine vẽ lại) và cấp hình học (một hàm `edit_strokes`). "Vùng" và "nét" chỉ khác bước đổi id thành danh sách nét.

Vấn đề chính: web tự áp dụng mọi đề xuất (AI-01); mỗi lượt chat giữ một kết nối DB và khoá đơn suốt thời gian chờ LLM (AI-02); hoàn tác do AI gọi làm đổi bản vẽ tay thật (AI-03); chuyển hãng không hoàn lại thay đổi của hãng lỗi (AI-04); chi phí không chặn theo từng khách (AI-06).

## 3. Xử lý nét chữ

### OT-1 (bản v2, đang là mặc định)

`BE/app/services/stroke_ai/recovery_v2.py:recover_page`, theo thứ tự:

1. Giải mã ảnh, áp xoay / cắt của khách.
2. Tìm tờ giấy bằng GrabCut, nắn phối cảnh (`paper.py`).
3. Làm phẳng ánh sáng, ngưỡng Otsu + ngưỡng thứ hai cho mực nhạt.
4. Khử đốm, chỉnh nghiêng ±5°.
5. Bỏ dòng kẻ và ô ly (`ruling.py`), nếp gấp (`folds.py`), lỗ bấm, mực in khác màu.
6. Làm mảnh Zhang-Suen → đồ thị khung xương → tỉa nhánh → ghép cạnh tại giao điểm theo hướng → làm trơn + Douglas-Peucker.
7. Thứ tự đọc: dòng → từ → chữ gốc rồi dấu.
8. Chia vùng theo từ, gắn nhãn `ORIGINAL` / `RESTORED` ở ngưỡng 0,6.
9. Tối ưu thứ tự nét, tính thời gian viết, gợi ý độ khó.

### OT-3

`stroke_ai/engine.py:generate_ot3`: seed từ SHA-256 của nội dung + font + bố cục → nguồn glyph (8 font Hershey, hoặc TTF làm mảnh thành đường tâm) → ghép dấu Việt qua NFD → ngắt dòng, căn lề, phân trang → rung nhẹ có seed → tối ưu thứ tự nét.

### Số liệu đang có và cách đọc đúng

| Con số | Thật sự đo cái gì | Nguồn |
|---|---|---|
| F1 94,88% (OT-1 v2) | Độ khớp đường tâm trên **220 ảnh tổng hợp** = 22 ảnh quét thật × 10 loại nhiễu nhân tạo; ngưỡng được chỉnh trên chính tập này | `BE/docs/benchmarks/OT1v2_R4_product_2026-11-22.md` |
| "Độ giống" 95–99% hiện trong sản phẩm | Nét so với mực **do hệ thống tự giữ lại**; tương quan 0,30 với F1 thật | `recovery_v2.py:148-157`, báo cáo R4 mục 2 |
| 50/50 ảnh chữ Việt thật chạy được, trung vị 1,03 giây | Chạy không lỗi, bản v1, máy phát triển | `U3_recovery_viet_hw_2026-11-12.md` |
| 0/50 ảnh đạt IoU ≥ 80 | NFR-02 theo thước đo gốc chưa đạt | như trên |
| −37,8% quãng nhấc bút | Trung vị trên 50 trang OT-1, tính trên giấy ảo | `U7_path_order_2026-11-12.md` |
| CER 0,024 | Gemini đọc 50 trang | `E_htr_benchmark_2026-11-19.md` (chưa mở file, trích từ docstring) |
| Nhận người viết 11,4% so với ngẫu nhiên 5,2% | Thử thu glyph từ trang tự do: không dùng được | `O1a_glyph_harvest_2026-11-20.md` |

Chưa từng đo: thứ tự và chiều nét (không có quỹ đạo bút gốc để so), ảnh khách thật, thời gian trên Render với ảnh điện thoại 12 MP, phiếu OT-2 người thật, hình dấu thanh trên giấy thật.

## 4. Robot: từ gói ký tới chuyển động bút

| Bước | Cách làm | File |
|---|---|---|
| Nhận lệnh | Agent chủ động gọi ra BE (`/agent/sync`, 1 giây khi rảnh, 0,25 giây khi chạy); không mở cổng vào xưởng | `robot_agent/vhrs_agent/link.py` |
| Kiểm gói | SHA-256 file quỹ đạo; nếu có snapshot thì kiểm Ed25519, schema, thông số bút, dòng xác thực | `bridge.py` |
| Hiệu chuẩn | 3 điểm chạm bút đọc từ pendant → hệ trục giấy bằng Gram-Schmidt; từ 4 điểm thì khớp mặt phẳng bình phương tối thiểu | `BE/app/services/motion/frame.py` |
| Sinh quỹ đạo | Mỗi nét: di chuyển → hạ bút → viết → nhấc. Lấy mẫu đều 0,2 mm, tốc độ theo độ cong, quét tiến / lùi theo gia tốc | `motion/plan.py` |
| Hạ bút | Lệnh vị trí thuần: mặt giấy − `F/k` (Hooke). Không dò tiếp xúc | `plan.py` |
| Kiểm | Trong giấy, thứ tự bút, độ cao, tốc độ, tầm với 0,9 × 622 mm, hộp làm việc | `motion/validate.py` |
| Động học ngược | REAL: IK của bộ điều khiển (`GetInverseKin`, `GetInverseKinRef`), biên 5° tới giới hạn khớp. SIM: PyBullet + URDF của hãng | `fairino_robot.py`, `kinematics.py` |
| Va chạm | REAL: không có. SIM: chỉ mặt bàn | `kinematics.py:186-191` |
| Giao tiếp | `MoveL` qua XML-RPC tự dựng, mỗi lần một đoạn ≤ 5 mm, chờ tới đích rồi mới gửi đoạn sau. `ServoCart` đã thử và bỏ | `linear_motion.py` |
| Dừng | `StopMotion` qua kết nối riêng; không bao giờ gửi lại lệnh chuyển động | `fairino_robot.py:73-127` |
| Khôi phục | Ghi `progress.json` trước và sau mỗi nét; tiếp tục đúng nét; job đã xong bị từ chối viết lại | `runner.py` |
| Khoá REAL | Chế độ `real` trong cấu hình + file cho phép theo job có hạn + mã `AUTHORIZE-<job>-<mã kế hoạch>` + lần chạy thử REAL cùng kế hoạch | `server.py`, `runner.py` |

### Cảm biến Hall, ESP32

Có bộ phân tích khung `$F/$E` với XOR checksum, bộ giám sát an toàn, gripper mô phỏng và 7 test. `SerialGripper` chưa từng chạy; `ForceTable` không được gọi ở đâu; **không có firmware trong repo**. Các lần chạy thật dùng `unsensed_gripper: true`, tức viết thật không có phát hiện quá lực hay mất tiếp xúc.

### Bản viết có khớp phác thảo không

Agent không kiểm. Chỉ có ảnh của kỹ thuật viên + QC, và Service G phía BE (so ảnh với phác thảo bằng Chamfer / HD95 / độ phủ), ngưỡng ghi rõ là chưa hiệu chuẩn, mới thử trên ảnh tổng hợp.

## 5. Mức kiểm chứng từng năng lực

| Năng lực | Mức | Bằng chứng |
|---|---|---|
| Kết nối chỉ-đọc, nhận dạng robot, kiểm TCP | Đã chạy trên robot thật | `BE/PROJECT_STATUS.md:431,434` (2026-10-25, 10-31) |
| MoveL từng đoạn, chạy thử nhấc bút | Đã chạy trên robot thật: 45/45 nét trong 489 giây | như trên |
| Viết có mực | Đã chạy trên robot thật: **2 nét**, chưa hết trang | như trên |
| ServoCart | Đã chạy trên robot thật: thất bại (~47 ms mỗi lệnh), bỏ | như trên |
| Hệ trục giấy 3 điểm | Đã chạy trên robot thật (gián tiếp qua 2 nét) | như trên |
| Khớp mặt phẳng ≥ 4 điểm, tốc độ theo độ cong, giới hạn jerk | Đã triển khai, mới kiểm chứng bằng simulation | `BE/tests/test_motion_geometry.py` |
| Lệnh bền, đồng bộ, lần chạy, cảnh báo, heartbeat | Đã triển khai, mới kiểm chứng bằng simulation | `BE/tests/test_api_robot_link.py`, `test_api_robot_ops.py` |
| Gói ký Ed25519 + kiểm ở agent | Đã triển khai, mới kiểm chứng bằng simulation | `test_production_snapshot.py`, `robot_agent/tests/test_signed_package.py` |
| Tạm dừng / tiếp tục / dừng, mất liên lạc BE | Đã triển khai, mới kiểm chứng bằng simulation | `robot_agent/tests/test_runner.py`, `test_link.py` |
| Giám sát dừng và bám quỹ đạo | Đã triển khai, mới kiểm chứng bằng simulation; ngưỡng chưa đo | `test_ops_watchdogs.py` |
| Nút REAL trên máy trạm, giao robot cố định (0032) | Đã tích hợp code, chưa có bằng chứng chạy | commit `19798df`; `PROJECT_STATUS.md:360` |
| Đọc cảm biến Hall (`SerialGripper`) | Đã tích hợp code, chưa có bằng chứng chạy | `gripper.py:195` |
| Bảng Hall → lực (`ForceTable`) | Mock hoặc placeholder | không nơi nào gọi |
| Firmware ESP32 | Chưa triển khai | `BE/docs/ROBOT_INTEGRATION.md:107` |
| Trạng thái robot `BUSY` tự động | Chỉ có trong tài liệu | SRS FR-39 |
| Kiểm va chạm ở REAL | Chưa triển khai | — |
| Service G | Đã triển khai, mới kiểm chứng bằng simulation | `test_quality_eval.py` |
| Đo NFR-03/04/05 | Chưa triển khai | `UPGRADE_AI_ROBOT_PLAN.md:43,61` |

Tài liệu mâu thuẫn nhau: `HANDOFF.md`, `robot_agent/README.md`, `ROBOT_INTEGRATION.md` và bảng phase ghi "robot thật chưa chạy"; changelog 2026-10-25 ghi đã chạy kèm số đo cụ thể. Đọc kỹ thì robot đã chạy một phần do người vận hành; các dòng "chưa chạy" là tài liệu cũ. Bằng chứng hiện chỉ là lời kể trong changelog: repo không có log, video hay ảnh.

## 6. Kết quả chạy test trong đợt audit

- `robot_agent`: 183 đạt, 3 bỏ qua (2 test chỉ Windows, 1 cần PyBullet), 1 treo vô hạn trên macOS / Linux.
- Test treo là `tests/test_server_api.py::test_waiting_for_a_process_returns_when_it_ends`. Nguyên nhân: `wait_for_process_exit` (`server.py:845-850`) dò bằng `os.kill(pid, 0)`, mà tiến trình con đã thoát nhưng chưa được thu hồi vẫn trả lời tín hiệu này. Trên Windows (máy trạm đích) nhánh code khác được dùng nên không bị (RB-11).
