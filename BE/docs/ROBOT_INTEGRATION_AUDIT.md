# Rà soát tích hợp FAIRINO FR3 + AI + Gripper IoT (Phase 0–1, chưa sửa code)

Ngày: 2026-10-23. Trạng thái: **đã đọc và đối chiếu, chưa thay đổi mã nguồn nào**. Mọi mục "CHƯA XÁC MINH" phải được kiểm tra trên SDK/robot thật trước khi đưa vào chương trình điều khiển.

## 0. Quyết định của chủ dự án (2026-10-23), trả lời mục 7 bên dưới

Q1 cho phép `robot_agent/`. Q2 robot FR3 V6.0, controller V3.8.25-QX, firmware FR_CTRL_FV2.010.12, web v3.8.5.1, IP 192.168.58.2; được cài SDK/phần mềm; **cần có giả lập cho Technical Staff theo dõi từ xa** (đã làm: trình theo dõi của Agent; chưa tải giả lập chính thức của hãng, xem `ROBOT_INTEGRATION.md` mục 1 và 11).
Q3 theo tài liệu gripper (lò xo + Hall), **không** theo SRS loadcell. Q4 duyệt báo giá + cọc = xác nhận phác thảo. Q5 khảo sát và thêm font OK thẳng vào Supabase (đã thêm 4, mục `REGISTRY.md`).
Q6 chủ dự án hỏi thêm: dữ liệu nào lưu DB và log robot nằm đâu → `ROBOT_INTEGRATION.md` mục 10 (không cần migration, chờ chủ dự án quyết định có muốn bảng `robot_runs` hay không). Q7 xác nhận: **không chạy robot thật nếu chưa hỏi và được đồng ý.**

## 1. Đã đọc

`BE/` (CLAUDE.md, PROJECT_STATUS.md, AI_PLAYBOOK.md, docs/source/* gồm SRS, models/ops.py, domain/job_rules.py, services/technician.py, services/stroke_ai/*, requirements, .env.example), tài liệu gripper `AI-VHRS_Gripper_IoT_NghienCuu (1).docx`, và các trang SDK Fairino đọc được (xem mục 5). **Chưa đọc kỹ từng dòng:** các service thanh toán/vận chuyển/chat (ngoài phạm vi robot), `Mobile/` (Flutter), `FE/`. Không có file nào không đọc được.

## 2. Phát hiện kiến trúc quan trọng nhất

SRS (FR-46, mục 3.6, NFR-10) đã chốt: **Robot Agent là tiến trình Python độc lập trên máy trạm**, nói chuyện với FR3 qua SDK Fairino (TCP/IP), nói chuyện với Flutter App qua WebSocket cục bộ, nhận lực từ ESP32 qua USB serial. **BE (FastAPI trên Render) không bao giờ gọi SDK robot** (không với tới mạng LAN của robot, Render free còn ngủ). Các endpoint `/technician/*` (11 route) đã có đủ hợp đồng cho Agent/App: tải gói job + kiểm hash, hiệu chuẩn, ghi kết quả mô phỏng, start/progress/pause/estop/over_force/force_summary, finish, incident. `PROJECT_STATUS.md` #13 cũng ghi "khi kết nối robot, giữ nguyên `/technician/*`, chỉ thêm adapter Robot Agent phía sau".

=> Đề xuất: giữ BE là nguồn sự thật và bộ kiểm chứng; thêm **`robot_agent/`** (package Python riêng, ngoài `BE/app`, chạy trên máy trạm) với `RobotPort` có 3 adapter: `MockRobot`, `SimRobot`, `Fairino`. Kiến trúc này khớp tên mục "Robot Integration Service" trong yêu cầu.

## 3. Dependency & Readiness Matrix

| # | Thành phần | Hiện trạng | Loại | Việc cần làm |
|---|---|---|---|---|
| 1 | Job lifecycle, event, incident, kho | IMPLEMENTED, có test (Postgres cục bộ; Supabase mốc 411 test cũ) | giữ | không đổi |
| 2 | Hash gói job (FR-38), BR-19, ràng buộc DB `simulation_passed` | IMPLEMENTED | giữ | không đổi |
| 3 | OT-1: ảnh → nét (Zhang-Suen) | IMPLEMENTED nhưng **chưa benchmark trên chữ Việt thật**; IoU chỉ tự-so-sánh; thứ tự/chiều nét là heuristic | A | benchmark có số đo; đánh dấu nét suy đoán |
| 4 | OT-3: text → nét (Hershey + ghép dấu Việt) | IMPLEMENTED, 8 font Hershey một nét, dấu thiết kế tay **chưa kiểm trên giấy** | A | mở rộng font (OFL, một nét) + kiểm dấu |
| 5 | Định dạng quỹ đạo `vhrs-trajectory/1` | mm, gốc trên-trái, pen-up ngầm, không có độ rộng nét, không có cờ "AI suy đoán", không có vận tốc | A | bản `/2` tương thích ngược hoặc trường mở rộng |
| 6 | S5 lấy mẫu 0,2 mm / làm phẳng Bézier | CHƯA (chỉ simplify 0,7 px) | A | làm |
| 7 | S6 hồ sơ vận tốc | CHƯA (chỉ hằng số ước tính thời gian) | A | làm (thuần, test được) |
| 8 | S7 giấy → gốc robot từ P0,P1,P2 (+z_map) | CHƯA; BE chỉ lưu `probe_points`/`frame_transform` tự do, không kiểm | A | làm, hàm thuần |
| 9 | S8 khả thi (tầm với, IK, giới hạn khớp, dị điểm) | CHƯA; `simulation_passed` do **client tự khai** | A | validator ở BE (Service F) + chạy lại ở Agent. IK cần thông số động học FR3 chính thức: **CHƯA XÁC MINH** |
| 10 | S9 sinh lệnh SDK | CHƯA; SRS ghi "xác minh ở spike" | A | spike trên SDK + robot |
| 11 | Robot Agent (SDK, heartbeat, pause/stop, idempotency) | CHƯA | A | làm: mock → sim → thật |
| 12 | Firmware ESP32 + giao thức serial `$F,...` | CHƯA | A | làm sau khi chốt phần cứng (câu hỏi 3) |
| 13 | Kênh dữ liệu lực lên server (MQTT/ForceLog/DeviceEvent) | CHƯA; bảng không có trong schema | B | cần migration (xin duyệt) |
| 14 | Thiết bị gripper trong PenProfile (k, F_target…) | `pen_types` có f_target/min/max/hard/v_max; không có hệ số lò xo, bảng hiệu chuẩn Hall | B | lưu trong `calibrations.force_curve` (JSONB đã có) → có thể không cần migration |
| 15 | Quản lý font (Supabase Storage + metadata + giấy phép) | CHƯA; `templates.font_uri = "hershey:<tên>"` | B | xem câu hỏi 5 |
| 16 | Khách xác nhận bản phác thảo cuối | Hiện: Staff `finalize` → khách xem preview **trong báo giá** (sau chính sách riêng tư) → duyệt báo giá. Không có bước "xác nhận phác thảo" riêng | B | câu hỏi 4 |
| 17 | Đánh giá chất lượng (Service G: so ảnh chụp với phác thảo) | **ĐÃ CÓ (2026-10-24)**: `quality_evaluations`, Chamfer/Hausdorff/độ phủ mm + ảnh chồng (`overlay_url`); thử bằng ảnh tổng hợp, **chưa** ảnh thật, mm chưa hiệu chuẩn | B | hiệu chuẩn bằng thước + ảnh thật; SSIM nếu cần |
| 18 | Quản trị `robots` (loại FAIRINO_FR3, simulated) | IMPLEMENTED | giữ | thêm trường kết nối chỉ nếu cần (câu hỏi 6) |
| C | Hoàn tiền 4d, thông báo 4e, scheduler 5, cổng MoMo/GHN/GHTK thật | chưa/đang chờ | C | **không đụng** |
| D1 | `simulation_passed` tin lời client | rủi ro an toàn | D | validator phía BE (dòng 9) |
| D2 | Mô hình lực trong SRS (loadcell 500 Hz, F>F_hard dừng ≤100 ms) mâu thuẫn tài liệu gripper (lò xo + Hall + ADS1115, 100 Hz, dừng nếu mất gói >100 ms) | mâu thuẫn tài liệu | D | câu hỏi 3 |
| D3 | Hằng số thời gian viết (`AVG_SPEED_FACTOR`…) là giả định, ảnh hưởng giá/lịch | ước tính | D | thay bằng số từ profile vận tốc thật khi có S6 |
| D4 | Mốc test toàn suite trên Supabase còn ở 411 test cũ | tồn đọng | D | ngoài phase, chỉ ghi nhận |

## 4. Mâu thuẫn tài liệu cần chủ dự án chốt (xem mục 7)

- SRS 3.6: loadcell + HX711, ESP32 ≥500 Hz, vòng Z bám lực admittance/PI (băng thông ~3 Hz). Tài liệu gripper (08/10/2026): lò xo k≈0,4 N/mm + Hall SS49E + ADS1115, **không** servo lực nhanh; dò mặt giấy 9 điểm rồi `Z = mặt_giấy − F_mục_tiêu/k`, bù chậm theo nét. Theo mức ưu tiên trong `docs/source/README.md` thì quyết định mới của chủ dự án đè lên SRS, nhưng cần xác nhận bằng chữ.
- Tài liệu gripper dùng **MQTT/Mosquitto** và bảng `ForceLog/DeviceEvent`. Schema hiện tại không có hai bảng này; Render free không chạy được broker.
- SRS: điểm dò 3 điểm (P0,P1,P2); gripper: 9 điểm khớp mặt phẳng. BE đã nhận 3..400 điểm, nên chứa được cả hai.

## 5. Nghiên cứu FAIRINO (nguồn chính thức, đã xác minh được gì)

Đã xác minh từ trang chính thức:
- Python SDK chính thức: repo `FAIR-INNOVATION/fairino-python-sdk` (Apache-2.0, thư mục `linux/` và `windows/`, **không có release, không thấy gói `pip`** và không nêu bảng tương thích SDK ↔ controller). Dùng bằng `from fairino import Robot; robot = Robot.RPC('<ip>')` (ví dụ bên thứ ba dùng IP `192.168.58.2`: chỉ là ví dụ, **IP thực của robot nhóm phải đo**).
- Mục lục sổ tay SDK v2.0.0 có: chuyển động khớp, MoveL (Cartesian), cung tròn, vòng tròn, servo khớp/Cartesian, spline, dừng/tạm dừng/tiếp tục, hiệu chuẩn TCP 4 điểm/6 điểm, hiệu chuẩn hệ workpiece 3 điểm, truy vấn mã lỗi, xoá lỗi.
- Đã đọc nguyên văn chữ ký: `GetActualTCPPose(flag=1)`, `GetActualJointPosDegree(flag=1)`, `GetActualToolFlangePose(flag=1)`, `GetJointTorques(flag=1)`, `GetRobotMotionDone()`, `GetRobotEmergencyStopState()`, `GetRobotRealTimeState()`, `GetToolAI(id, block=0)` (trả % 0–100 của 0–10 V/0–20 mA), `WaitToolAI(id, sign, value, maxtime, opt)`. Trang AI **không nêu độ phân giải**.

**CHƯA XÁC MINH (tôi không viết vào code cho tới khi đọc đúng trang hoặc thử trên robot/simulator):** chữ ký chính xác của `MoveL`, `MoveJ`, `ServoCart`, `StopMotion`, `PauseMotion`, `ResumeMotion`, hàm hiệu chuẩn TCP, `GetRobotErrorCode`, hàm đọc phiên bản; tần số gói trạng thái; phiên bản controller tương thích; có simulator chính thức hay không; Python tối thiểu của SDK; sơ đồ chân giắc cuối tay. Hai URL `PythonRobotMotion.html` và `PythonRobotBasic.html` trả 404 (tên trang khác), nên cần lấy chữ ký từ **bản SDK nhóm tải về đúng phiên bản controller** (nguồn đáng tin nhất vì nó là mã thực chạy).

Kết luận công nghệ: viết Agent bằng Python, vendoring SDK chính thức và **ghim đúng commit tương ứng phiên bản controller** (nếu nhóm cho biết). Không dùng ROS/MoveIt2 (không cần cho vẽ phẳng; thêm phụ thuộc, không làm tăng độ chính xác).

## 6. Kế hoạch triển khai đề xuất (chỉ làm sau khi chốt mục 7)

1. **Hình học thuần trong BE** (`BE/app/services/stroke_ai/` + `domain/`): S5 resample/giữ góc, S6 vận tốc, S7 biến đổi giấy→robot (3 điểm và khớp mặt phẳng ≥3 điểm), kiểm tra hợp lệ quỹ đạo (workspace, nhảy toạ độ, pen-up/down, giới hạn giấy). Mọi tham số vật lý là `UNCONFIGURED` cho tới khi nhóm đo. Có test thuần (biến đổi tái lập, các trường hợp từ chối).
2. **Validator phía BE** thay cho "client tự khai" mô phỏng: endpoint hiện có (`simulation`) nhận báo cáo, BE tự dựng lại và đối chiếu; không thêm route mới nếu chưa cần.
3. **`robot_agent/`**: `RobotPort` + `MockRobot` + `SimRobot` + `FairinoRobot` (chỉ import SDK khi `mode=real`), state machine, heartbeat, mất kết nối → dừng an toàn, không tự gửi lại lệnh chuyển động, khoá một nguồn điều phối, nhật ký lệnh. Chế độ thật cần cờ vận hành rõ ràng + xác nhận từng job.
4. **Gripper**: firmware ESP32 + parser serial `$F` có checksum XOR, bộ lọc, bảng hiệu chuẩn Hall→N, ngưỡng an toàn; kênh lên server theo câu hỏi 3.
5. **AI**: benchmark nhỏ (SSIM, Chamfer, Hausdorff) cho OT-1 hiện tại so với 1–2 phương án CV khác; cờ `inferred` cho nét AI suy đoán; không gọi dịch vụ ngoài tính phí.
6. **Font**: khảo sát font một nét giấy phép OFL/CC hỗ trợ tiếng Việt, đưa vào Supabase Storage theo cách nhóm chọn.
7. **Tài liệu + test E2E** hai luồng A/B tới mức mô phỏng; bước chuyển động thật chờ người vận hành.

## 7. Câu hỏi cần chủ dự án trả lời

**Q1. Nơi chạy Robot Agent.** A: package `robot_agent/` trong repo, chạy trên máy trạm (đúng SRS). B: nhúng vào BE. **Recommendation: A** (BE trên Render không với được LAN robot). Impact: thêm thư mục ngoài `BE/app`; BE giữ nguyên hợp đồng `/technician/*`. *Xác nhận: được thêm thư mục `robot_agent/` ở gốc repo (ngoài `BE/`)?*

**Q2. Phiên bản SDK/controller và simulator.** Tôi không tự đoán. *Cần: số phiên bản phần mềm controller + firmware của FR3 nhóm (xem trên WebApp của robot), commit/ZIP SDK nhóm đang dùng, có dùng simulator của Fairino hay không (nếu không, "SimRobot" sẽ là mô phỏng động học của riêng chúng ta, và sẽ ghi nhãn đúng như vậy).*

**Q3. Mô hình đo lực.** A: theo tài liệu gripper (lò xo+Hall+ADS1115, serial 100 Hz, bù chậm theo nét, vòng lực nhanh bỏ). B: giữ SRS (loadcell, vòng admittance). **Recommendation: A**, vì tài liệu mới hơn và đã có tiêu chí thí nghiệm E1–E11. Kênh lên server: A1 = Robot Agent đẩy tóm tắt qua `POST /technician/jobs/{id}/events` (`FORCE_SUMMARY`, đã có, **không cần migration, không cần MQTT**); A2 = MQTT + bảng mới `force_logs` (cần migration và broker, Render free không hỗ trợ). **Recommendation: A1 trước**, MQTT để sau nếu nhóm thật sự cần dashboard. *Xác nhận A + A1?*

**Q4. Khách xác nhận phác thảo.** Hiện khách chỉ xem phác thảo trong báo giá và duyệt báo giá. A: coi duyệt báo giá = xác nhận phác thảo (không đổi workflow). B: thêm bước xác nhận riêng (đổi workflow/trạng thái, cần migration). **Recommendation: A**, vì yêu cầu của bạn cấm tự đổi workflow; preview đã được render từ chính quỹ đạo và hash khoá bản đã duyệt. Impact A: không đổi DB.

**Q5. Font.** A: font một nét tải từ nguồn có giấy phép rõ (cần danh sách ứng viên, tôi sẽ nghiên cứu và nêu giấy phép) lưu Supabase Storage + metadata trong `templates` (cột hiện có `font_uri`; có thể cần thêm cột license → migration nhỏ). B: chỉ giữ Hershey. **Recommendation: A**; tôi chỉ trình danh sách và phạm vi tác động trước khi upload gì lên Supabase.

**Q6. Cấu hình kết nối robot.** Lưu IP/cổng/mode trong cấu hình Agent (file/env trên máy trạm), không lưu trong DB. **Recommendation: giữ như vậy**; `robots` chỉ nhận thêm `is_simulated` đã có. Không cần migration.

**Q7. Tên chuyển động thật.** Xác nhận nguyên tắc: tôi **không bao giờ** chạy chương trình làm robot thật chuyển động; chỉ chuẩn bị và hướng dẫn người vận hành.

### Số đo nhóm cần cung cấp (danh sách ngắn; bản đầy đủ khi viết Calibration Guide)

| Tham số | Đơn vị | Cách lấy | Lưu ở đâu | Thiếu thì |
|---|---|---|---|---|
| Phiên bản controller/firmware, IP robot | – | WebApp robot | cấu hình Agent | không kết nối thật |
| TCP đầu bút (x,y,z,rx,ry,rz) | mm, độ | hiệu chuẩn 4/6 điểm của Fairino, ghi lại số robot trả | `calibrations.frame_transform` + cấu hình Agent | `UNCONFIGURED`, từ chối chạy |
| Bốn góc giấy / 3–9 điểm chạm | mm, hệ gốc robot | chạm bằng robot | `calibrations.probe_points` | từ chối chạy |
| Khối lượng + trọng tâm công cụ (payload) | kg, mm | cân + tính | cấu hình Agent | không chạy thật |
| k lò xo, hành trình tối đa, ma sát | N/mm, mm | thí nghiệm E1–E2 trong tài liệu gripper | `calibrations.force_curve` | không bù Z theo lực |
| Bảng Hall→N (32 điểm) | raw→N | quy trình mục 7 tài liệu gripper | NVS ESP32 + `force_curve` | cờ "chưa hiệu chuẩn", không viết |
| Chân giắc cuối tay, ADC AI0 | – | sổ tay đi kèm robot / nhà cung cấp | tài liệu | không đấu AI0 |
