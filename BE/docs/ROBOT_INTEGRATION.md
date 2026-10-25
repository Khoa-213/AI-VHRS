# Tích hợp FAIRINO FR3 + AI + Gripper IoT: hướng dẫn kỹ thuật

Cập nhật 2026-10-23. Tài liệu đi kèm: `ROBOT_INTEGRATION_AUDIT.md` (rà soát + quyết định), `FE_API_GUIDE.md` (hợp đồng API), `../../robot_agent/README.md` (chạy agent).
Nhãn trạng thái dùng xuyên suốt: **IMPLEMENTED** (có code + test tự động), **TESTED_IN_SIMULATION**, **READY_FOR_HARDWARE_VALIDATION**
(code xong, chưa từng chạy với phần cứng), **VERIFIED_ON_REAL_ROBOT** (chưa có mục nào), **BLOCKED** (thiếu số đo/quyết định).

## 1. Robot của xưởng (đọc từ trang web robot, ảnh người dùng gửi 2026-10-23)

| Mục | Giá trị |
|---|---|
| Robot model | FR3 V6.0 (FAIRINO) |
| Web version | v3.8.5.1 (2025-08-29) |
| Controller version | V3.8.25-QX |
| Firmware (carrier plate) | FR_CTRL_FV2.010.12, Apr 29 2025 |
| Địa chỉ trang web | 192.168.58.2 (trùng IP mặc định trong SDK) |

**Tương thích SDK: CHƯA XÁC MINH.** Repo SDK chính thức (Apache-2.0) gắn tag theo phiên bản phần mềm robot; tag cuối của dòng 3.8.x là
`Python_SDK_2.1.7.1_robot_v3.8.7.1` (commit `55bcce6`), cũ hơn controller V3.8.25. Bản mới nhất của repo (V4.0.0) nhắm tới robot V4.0.0. Agent ghim `55bcce6`
(`robot_agent/scripts/fetch_fairino_sdk.py`) và `FairinoRobot.connect()` chỉ ĐỌC (phiên bản, tool đang dùng, giới hạn khớp), từ chối nếu mẫu không phải FR3 hoặc controller ngoài
dòng `V3.8`. Người vận hành xem kết quả đó trước khi làm bất cứ việc gì khác. Nếu controller mới hơn gây lỗi, các lựa chọn (cần chủ dự án quyết định): thử tag SDK 3.8.x khác,
hoặc nâng phần mềm controller (**không tự làm**).

**Giả lập chính thức của hãng (đã đọc trang hướng dẫn):** FAIRINO SimMachine là một **máy ảo chạy phần mềm controller** (ảnh VMware `FAIRINO_SimMachine.zip`, mở bằng VMware Workstation 17.6.3; có bản Docker cho Linux; có WebApp truy cập bằng IP của máy ảo, ví dụ `http://192.168.182.222`). Nó **không điều khiển robot thật**; trang không nói SDK có kết nối được hay không (cần thử).

**Giả lập chính thức của hãng (tóm tắt trước đó):** trang tải của hãng có **FAIRINO SimMachine** (ảnh VMware, ảnh Docker và phần mềm), kèm mô hình 3D STEP, bản vẽ kích thước và mô hình vị trí zero của FR3.
Bản phần mềm cobot đang đăng là V4.0.0.1 (QX / LA), khác dòng 3.8.x của robot. Chưa tải (cần chủ dự án đồng ý, xem mục 11). Khi có, `FairinoRobot` có thể trỏ IP vào SimMachine để chạy
đúng adapter thật mà không có robot thật.

**SimMachine bản Docker đã tải (chưa chạy)**, `D:\K9	oolsairino-simmachine\` (git không theo dõi): `FAIRINO_SimMachine_Docker_v4.0.0.1.zip` 298.967.831 byte (SHA-256 `1d1e5f63…eef769c`); đã giải nén `FAIRINOSimMachine.tar` (2,19 GB, image `fairino_simmachine:latest`). Quy trình của hãng: `docker load -i FAIRINOSimMachine.tar`; `docker network create --driver bridge --subnet 192.168.58.0/24 --gateway 192.168.58.1 fairino-net`; `docker run -d -P --name fairino-container --privileged -u root --net fairino-net fairino_simmachine`; WebApp `http://192.168.58.2`, tài khoản mặc định của máy ảo `admin` / `123`. Hướng dẫn viết cho **Ubuntu 18.04 làm máy chủ Docker** (4 GB RAM, 6 CPU, 50 GB đĩa). Hai vấn đề với máy này: (1) mạng mẫu `192.168.58.0/24` trùng đúng dải IP mặc định của robot thật (`192.168.58.2`); (2) trên Docker Desktop (Windows) mạng bridge nằm trong máy ảo WSL2 nên máy Windows không tới được `192.168.58.2` của container, chỉ tới được cổng được publish (hướng dẫn không liệt kê số cổng).

## 2. Kiến trúc

```
Customer/Staff web ─▶ BE (FastAPI, Render) ──── nguồn sự thật: đơn, phác thảo đã duyệt + hash, hiệu chuẩn, job, nhật ký
                          ▲   │ /technician/*  (API sẵn có, không thêm route)
                          │   ▼
        Flutter App / trình duyệt  ◀─ WebSocket ─▶  Robot Agent (Python, máy trạm)  ◀─ USB serial ─▶ ESP32 gripper
        (technician)                                   │  RobotPort: MOCK | SIM | REAL
                                                       ▼
                                              FAIRINO FR3 (SDK, TCP/IP)    Trình theo dõi từ xa: http://<máy trạm>:8765
```

- BE **không bao giờ** gọi SDK robot. Agent chạy trên máy trạm cạnh robot, dùng đúng mã hình học của BE (`app.services.motion`) nên server và máy trạm kiểm chứng cùng một thuật toán.
- Một nguồn điều phối: khoá file `agent.lock` + khoá tiến trình; lần chạy thứ hai bị từ chối, không xếp hàng.
- Agent đăng nhập bằng token của Technical Staff (`VHRS_TOKEN`), nên mọi luật BR-19 / hash / hiệu chuẩn / mô phỏng của server vẫn áp dụng. Customer không có đường nào tới robot.

## 3. Ba chế độ, và mỗi chế độ chứng minh được gì

| Chế độ | Là gì | Chứng minh | Không chứng minh |
|---|---|---|---|
| MOCK | nhảy tức thời tới từng điểm | luồng phần mềm, từ chối, ghi log | thời gian, tốc độ |
| SIM | mô hình thời gian của chúng ta, chạy đúng tốc độ kế hoạch (có thể nhanh gấp N) | đường bút, thứ tự pen-up/down, thời lượng, an toàn lực (mô hình lò xo), dừng/tiếp tục/khôi phục | tầm với khớp, IK, dị điểm, độ chính xác cơ khí |
| REAL | controller FAIRINO qua SDK | (chưa chạy lần nào) | |

Giao diện luôn hiển thị chế độ. Kết quả SIM không bao giờ được ghi là kết quả robot thật.

## 4. Hệ tọa độ và biến đổi (`BE/app/services/motion/`)

1. **Ảnh gốc** (px) → 2. **Phác thảo chuẩn hoá**: mm, gốc trên-trái giấy, x phải, y xuống (`vhrs-trajectory/1`).
3. **Giấy → gốc robot** (`frame.py`): người vận hành chạm bút vào P0 (gốc giấy), P1 (trên trục +x), P2 (trên trục +y), có thể thêm lưới điểm. Robot báo toạ độ TCP trong hệ **gốc robot**.
   `x̂ = (P1−P0)/|…|`, `ŷ` = Gram–Schmidt của `P2−P0`, pháp tuyến `n = x̂ × ŷ` (đổi dấu để hướng lên, thành phần Z dương). Điểm thứ 4 trở đi khớp bình phương tối thiểu một mặt phẳng độ cao
   `h(x, y) = a·x + b·y + c`. `p_base = P0 + x·x̂ + y·ŷ + (h + lift)·n`. Mặt giấy nghiêng được xử lý (Z không bị coi là hằng số); dốc quá 60° so với phương ngang bị từ chối.
4. **TCP (đầu bút)**: tool coordinate hiệu chuẩn trên robot (phương pháp 4 điểm / 6 điểm của hãng, thực hiện trên trang web robot hoặc tay dạy). Agent kiểm tra tool đang chọn đúng số cấu hình và,
   nếu có số đo độ dài bút, khoảng cách flange–TCP khớp ±1 mm. **Tâm mặt bích không bao giờ được dùng làm đầu bút.**
5. **Hướng bút**: giữ cố định bằng hướng (rx, ry, rz) của tư thế lúc dò P0 (bút vuông góc giấy). Không đổi Euler.

Kiểm tra bất biến (test): bốn góc giấy ánh xạ chính xác; mặt phẳng nghiêng; nâng bút đi theo pháp tuyến; dò sai (thẳng hàng, quá ngắn, lệch vuông góc > 3°, ngoài mặt phẳng > 1 mm) bị từ chối.
Ngưỡng 3° / 1 mm / 20 mm / 60° là **ngưỡng chấp nhận dữ liệu dò của phần mềm** (`FrameChecks`), chỉnh được, không phải thông số robot.

## 5. Từ phác thảo tới lệnh (`plan.py`, `validate.py`)

- S5: lấy mẫu lại ≤ 0,2 mm, **giữ nguyên đỉnh có góc > 60°**, không làm mượt (chỉ đổi cách lấy mẫu; test đo độ lệch hình học).
- S6: `v ≤ min(v_max_bút, √(a_lat/κ))`, góc và hai đầu nét 5 mm/s, quét xuôi/ngược theo `a_tan`.
- Mỗi nét: `travel` (bút nâng ở độ cao an toàn) → `plunge` (xuống thẳng) → `write` → `retract`. Độ sâu viết = mặt giấy − `F_mục_tiêu / k` (nén lò xo, theo tài liệu gripper mục 6.4). Nén quá hành trình → từ chối.
- **Validator xác định (Service F)**: cấu hình đo đủ; hộp không gian làm việc (bắt buộc khi REAL); mặt phẳng dò hợp lệ; mọi điểm trong vùng viết của giấy; không nhảy điểm; chuỗi pen-up/down đúng; độ cao viết/độ nâng được **tính lại độc lập** từ toạ độ robot; tốc độ ≤ giới hạn bút;
  tầm với ≤ 0,9 × 622 mm tính từ gốc robot (xấp xỉ bảo thủ). **Không kiểm ở server:** IK, giới hạn khớp, dị điểm cổ tay; báo cáo ghi `NOT_CHECKED` và Agent kiểm bằng IK của chính controller (không chuyển động) với khoảng cách 5° tới giới hạn khớp.
- BE: `POST /technician/jobs/{id}/simulation` giờ tự kiểm lại nếu hiệu chuẩn có khối `frame_transform = {"schema":"vhrs-motion/1","motion":{…},"workspace":{…}}`. Server **ghi đè** lời khai `passed=true` khi validator thất bại
  (lỗi ghi trong `simulation_report.errors`, tiền tố `SERVER`). Đặt `MOTION_VALIDATION_REQUIRED=true` ở trạm có robot thật để hiệu chuẩn thiếu khối này bị coi là không đạt. Mặc định `false` để client cũ vẫn chạy.
  `f_target_n` và `v_max_mm_s` luôn lấy từ hồ sơ bút trong DB, không tin giá trị client.

## 6. Hiệu chuẩn và thông số cần đo (UNCONFIGURED cho tới khi có)

Mọi giá trị dưới đây hiện **chưa có**. Hệ thống từ chối chạy robot thật khi thiếu; không có giá trị mặc định thay thế (số trong test/demo là dữ liệu thử, ghi rõ trong code).

| Thông số (đơn vị) | Vì sao cần | Cách đo / lấy | Lưu ở đâu | Hiệu chuẩn lại khi | Thiếu thì |
|---|---|---|---|---|---|
| IP robot, số tool | kết nối, chọn TCP | trang web robot (192.168.58.2); tool nhóm đã tạo | cấu hình Agent (không lên DB) | đổi mạng/tool | không kết nối |
| TCP đầu bút (mm, độ) | vị trí ngòi bút | hiệu chuẩn 4/6 điểm của hãng trên robot | robot (tool slot) + `tcp_offset_mm` trong cấu hình Agent để đối chiếu | đổi bút, tháo gripper, va chạm | từ chối chạy |
| Hướng bút rx,ry,rz (độ) | giữ bút vuông góc | đọc `GetActualTCPPose` lúc chạm P0 | `calibrations.probe_points` (kèm) / cấu hình Agent | mỗi lần dò giấy | từ chối |
| P0,P1,P2 (+lưới) (mm, gốc robot) | khung giấy, mặt phẳng | chạm bút vào giấy đã kẹp, đọc TCP | `calibrations.probe_points` | **mỗi tờ giấy / mỗi job** | từ chối |
| Hộp làm việc min/max (mm) | giới hạn an toàn | xác định theo bàn/giá kẹp, nhỏ hơn tầm với | `calibrations.frame_transform.workspace` | đổi bố trí | từ chối (REAL) |
| `pen_up_clearance_mm` | tránh kéo lê | chọn theo độ phẳng giấy + hành trình lò xo | `frame_transform.motion` | đổi giấy/bút | từ chối |
| `spring_k_n_per_mm` | độ sâu viết Z = F/k | thí nghiệm E1–E2 tài liệu gripper (cân tiểu ly) | `frame_transform.motion` + `calibrations.force_curve` | đổi lò xo/nam châm; hàng tháng | từ chối |
| `max_spring_travel_mm` | giới hạn cơ khí | đo hành trình tới chặn | `frame_transform.motion` | đổi gripper | từ chối |
| `a_lat`, `a_tan` (mm/s²), `travel_speed`, `approach_speed` (mm/s) | hồ sơ vận tốc | chọn thận trọng khi chạy khô, tăng dần | `frame_transform.motion` | sau thử viết | từ chối |
| Bảng Hall→mN (≥ 2 điểm, đơn điệu) | Hall chưa phải lực | quy trình tài liệu gripper mục 7 (50 điểm, 5 chu kỳ) | NVS ESP32 + `calibrations.force_curve` | đổi lò xo/nam châm, trôi > 0,05 N, hàng tháng | cờ UNCAL → không viết |
| Lực lúc nhấc bút (zero) | phát hiện trôi | TARE khi bút nhấc | cảm biến; Agent kiểm ±0,05 N | mỗi job | từ chối |
| Khối lượng + tâm khối công cụ | payload controller | cân gripper + bút, tính tâm | cài trên robot | đổi bút | không chạy thật |
| Chu kỳ ServoCart (s) | tốc độ viết đúng | spike thời gian trên robot | cấu hình Agent | đổi phiên bản controller | không kết nối REAL |
| Sơ đồ chân giắc cuối tay, độ phân giải AI0 | chỉ khi muốn đấu AI0 | sổ tay đi kèm robot / nhà cung cấp | tài liệu | – | không đấu AI0 |

## 7. Gripper, lò xo, Hall (`robot_agent/vhrs_agent/gripper.py`)

Theo tài liệu nhóm (08/10/2026): lò xo dẫn hướng + nam châm + Hall SS49E + ADS1115 + ESP32, lực **không** điều khiển vòng kín nhanh. Phần mềm Agent: parser khung `$F,seq,t_ms,raw,force_mN,flags*cs`
(checksum XOR, từ chối khung hỏng), bảng raw→mN nội suy tuyến tính **không ngoại suy**, và `SafetyMonitor`:
mất khung > 100 ms, cờ chưa hiệu chuẩn, bão hoà (tới chặn cơ khí), lực > `F_hard` của bút → **dừng**; mất tiếp xúc (< 0,3·F_min quá 60 ms khi đang viết) → **tạm dừng**. Hall được coi là đo độ nén, không phải lực, cho tới khi bảng hiệu chuẩn thật tồn tại.
**Firmware ESP32 chưa viết** (BLOCKED: chưa biết bo, chân, thiết bị thật; các GPIO trong tài liệu chỉ là gợi ý). Kênh lên server dùng `FORCE_SUMMARY` có sẵn (không MQTT, không bảng mới).

## 8. An toàn và thực thi

- Dừng **bằng phần mềm** (nút DỪNG, lỗi lực, mất cảm biến) **không thay** nút E-stop vật lý và chức năng an toàn chứng nhận của robot. Người vận hành phải ở gần nút E-stop khi chạy REAL.
- REAL cần: (1) preflight đạt (robot sẵn sàng, validator, IK qua controller, gripper đã hiệu chuẩn và zero trong ±0,05 N), (2) **chạy thử pen-up** thành công cho đúng kế hoạch, (3) mã xác nhận `AUTHORIZE-<job>-<8 ký tự digest>` do người vận hành nhập (`cli authorize`) — gắn với job và kế hoạch cụ thể (đổi hiệu chuẩn → mã đổi).
- Không gửi lại lệnh chuyển động: mất kết nối / agent chết giữa chừng → `UNKNOWN`, bắt buộc người vận hành xem giấy rồi chọn `resume_from` (nét dở viết lại, hoặc bỏ qua). Không bao giờ tự chạy lại từ nét 0 trên job đã viết dở.
- Điểm bắt đầu: bút phải đang cao ≥ độ nâng; Agent không tự di chuyển tới đó.
- SDK Fairino gửi lại lệnh **vô hạn** khi lỗi socket (`while flag: try/except socket.error`). `FairinoRobot` bọc mọi lệnh SDK trong deadline: quá hạn → StopMotion, đánh dấu mất kết nối, không gọi lại.
- Nhật ký: `runs/job<id>/run-<time>.jsonl` (mọi lệnh, lỗi, dừng), `progress.json` (nét đã viết, ghi **trước** nét kế tiếp).

## 9. Quy trình kiểm thử

| Mức | Nội dung | Trạng thái |
|---|---|---|
| 1 Unit | hình học, validator, gripper, outline font | **IMPLEMENTED**, test tự động |
| 2 Integration (mock) | server tái kiểm mô phỏng; runner + bridge; adapter Fairino với SDK giả | **IMPLEMENTED** |
| 3 Simulation | `python -m vhrs_agent.cli demo` + trình theo dõi | **TESTED_IN_SIMULATION** (chạy tay, ảnh chụp màn hình) |
| 4 Hiệu chuẩn | TCP, khung giấy, gripper | **BLOCKED** (chờ số đo) |
| 5 Chạy khô pen-up | `run --dry-run` trên robot thật, người vận hành giám sát | chưa làm |
| 6 Viết có kiểm soát | hình đơn giản → nét cơ bản → chữ mẫu → chữ thật | chưa làm |

**Luồng A (ảnh → viết):** upload → tiền xử lý + phục dựng (đã có, cổ điển) → hiện ảnh gốc/phác thảo (đã có) → khách duyệt báo giá = xác nhận phác thảo → job → hiệu chuẩn → validator → preview đúng từ quỹ đạo → mô phỏng → chạy khô → viết có người giám sát → ảnh sản phẩm + QC (đã có) → đánh giá.
**Đã có (mục 10d):** Service G đo Chamfer/Hausdorff/độ phủ giữa ảnh chụp và phác thảo (chưa hiệu chuẩn ngoài đời thật). **Chưa có:** SSIM; benchmark OT-1 trên chữ Việt thật. Hiện độ giống chỉ là IoU tự so sánh nên **không được dùng để tuyên bố "phục dựng chính xác"**.
**Luồng B (gõ chữ):** nhập chữ → chọn font (Hershey hoặc 4 font OFL mới) → preview từ chính quỹ đạo → xác nhận (duyệt báo giá) → job → như trên.

## 10. Dữ liệu lưu (trả lời câu hỏi "log và thông tin robot nằm đâu")

Không cần migration. Đã có sẵn trong DB: thời gian job (`started_at`, `finished_at`, `estimated_duration_min`), `job_events` (nhật ký từng sự kiện, kèm `payload`), `calibrations` (khung giấy, điểm dò, đường cong lực), `incidents`, tồn kho khi WRITTEN.
Agent bổ sung vào sự kiện đầu tiên của lần chạy (`PROGRESS`, `payload.agent_run`): mã lần chạy, **chế độ (MOCK/SIM/REAL)**, thông tin robot đọc được (mẫu, phiên bản controller, SDK, IP), digest kế hoạch, số nét, thời gian ước tính;
cuối job `FORCE_SUMMARY` kèm mã lần chạy. Dừng do phần mềm ghi `payload.source = "agent_software_stop"`. Log chi tiết (từng lệnh, từng lỗi, tần số cao) nằm ở file `runs/…jsonl` trên máy trạm, không đẩy lên DB.
Nếu muốn **truy vấn lịch sử theo robot** (tổng giờ chạy, số lần lỗi theo phiên bản controller…) thì cần bảng mới (ví dụ `robot_runs`) và cột phiên bản trên `robots`: đó là migration, chưa làm, cần chủ dự án duyệt.

## 10a. Bản sao số 3D và mô phỏng có khớp (đã làm 2026-10-23)

**Cái gì chạy:** trình theo dõi của agent (`http://<máy trạm>:8765/`) có khung 3D thật của **FR3 V6** (URDF + STL của hãng, three.js) đặt cạnh tờ giấy, đường nét dự kiến, vết bút đang viết và màu đầu bút theo lực. Góc khớp lấy từ:
- chế độ **SIM**: `PyBulletSimRobot` giải động học ngược bằng PyBullet từ chính URDF của hãng (cho từng ~1 mm của đường bút);
- chế độ **REAL**: `GetActualJointPosDegree` của controller (cùng khung vẽ, cùng API).
**API cho web** (agent phục vụ, FE nhúng hoặc tự vẽ): `GET /api/model` (có mô hình chưa, tên khớp + giới hạn, chiều dài công cụ), `GET /api/joints` (góc khớp, vị trí bút, lực, mức cảnh báo), `WS /ws` (cả trạng thái 10 lần/giây gồm `joints_deg`), `GET /api/job` (tờ giấy, khung toạ độ, nét), `GET /fr3/fairino3_v6.urdf` + `/fr3/meshes/fairino3_v6/*.STL`.
**Kiểm tra ở mức khớp (SIM):** tầm với, khoảng cách ≥ 5° tới giới hạn khớp, cùng một nhánh nghiệm (nhảy khớp > 25° giữa hai mẫu cách nhau 5 mm bị từ chối), điểm kỳ dị (tỉ số giá trị suy biến của Jacobian), va chạm bàn (cả mặt bích). Preflight chạy trên mọi đoạn đường, kể cả đoạn nâng bút dài (chia nhỏ 5 mm).
**Lưu ý về giả định (chưa xác minh trên robot thật):**
1. Khung gốc của URDF = khung gốc của controller. Dấu hiệu ủng hộ: ví dụ trong SDK có cặp (góc khớp, toạ độ) với x âm và j1 gần 0, khớp với cách URDF đặt tay chỉ về hướng **-X** ở tư thế zero (vì vậy tờ giấy phải nằm ở phía x âm trước robot, bản demo đã đặt như vậy). Dùng `FR3Kinematics.verify_against_controller` để so FK của URDF với tư thế controller báo cho cùng góc khớp.
2. `tool_offset_mm` là khoảng cách từ **khung của link wrist3** tới đầu bút. Khung đó nằm khoảng **103 mm sau mặt bích**, nên giá trị = bích + gripper + bút, không phải riêng chiều dài bút. Bản demo dùng 250 mm (số thử).
3. Giới hạn khớp của URDF (±175°, j2/j4 -265..85°, j3 ±162°) cần đối chiếu `GetJointSoftLimitDeg` của robot.
**Giới hạn:** đây là bản sao số hiển thị dữ liệu, không mô phỏng vật lý (lực, ma sát, giấy). Camera USB vẫn cần cho những gì mô hình không thấy (theo quyết định: để sau).
**Dựng môi trường:** `python robot_agent/scripts/setup_sim_env.py` (micromamba + conda-forge, không cần MSVC). Đã gặp và xử lý: numpy MKL của conda làm sập LAPACK (mã 0xc06d007f) nên thay bằng wheel pip.

## 10c. Điều khiển qua BE đã deploy (kiến trúc A, đã làm 2026-10-24)

**Quyết định của chủ dự án:** Technical Staff dùng một app riêng (FE làm); **mọi API liên quan robot nằm ở BE**; máy trạm (sau LAN) chạy Robot Agent **gọi ra** BE. Thay cho bản LAN-only làm trước đó (vẫn còn, là đường phụ, mục 7g.5 của `FE_API_GUIDE.md`).
- **Lệnh bền trong DB** (`robot_commands`, migration 0010): app `POST /technician/robot-commands`, agent kéo bằng `POST /agent/sync` (~1 lần/giây, 4 lần/giây khi chạy), trả kết quả bằng `POST /agent/commands/{id}/result`. Lệnh PENDING quá hạn thành EXPIRED, **không chạy trễ**; STOP luôn được giao trước; từ chối ngay (`AGENT_OFFLINE`) khi agent chưa kết nối; `idempotency_key` chống bấm đúp.
- **Khoá phiên theo đăng nhập** (migration 0012, đường chính cho app desktop): `POST /technician/robots/{id}/agent-session`. Chỉ technical staff đang giữ job hoạt động của robot; sống ~4 giờ; gia hạn êm (cùng `instance_id`, khoá cũ còn ~2 phút); **mỗi robot một app điều khiển** (`409 ROBOT_IN_USE`, không cướp quyền giữa chừng, kể cả khi lần chạy đang mở); chỉ nằm trong bộ nhớ app. Cấp lại khoá **không** ảnh hưởng kết nối agent ↔ robot (đường riêng); chỉ khi khoá bị cắt giữa lúc viết thì mới thành "mất liên lạc BE" (viết nốt nét, tạm dừng).
- **Khoá cố định của Manager** (`robot_agents`, `kind=MANAGER`): đường phụ cho máy trạm không có người đăng nhập, hiện một lần, BE chỉ lưu SHA-256. Với khoá đó agent chỉ gọi được `/agent/*` và `/technician/*` **với tư cách kỹ thuật viên đang giữ job hoạt động của robot đó**; không gọi được `/technician/robot-commands` (agent không tự ra lệnh cho mình).
- **Trạng thái sống** (khớp, TCP, lực, mức cảnh báo) nằm trong bộ nhớ BE (1 worker uvicorn, theo Dockerfile): `GET /technician/robots/{id}/live`. Chỉ các sự thật cần lưu (lần chạy, cảnh báo, sự kiện job, kết quả lệnh) vào DB.
- **3D**: trang `/viewer/robot.html` do BE phục vụ, vé chỉ-đọc 60 phút (`POST .../view-ticket`); mô hình URDF/STL của hãng nằm trong Storage (`robot-models/fr3/`) và được phục vụ ở `/api/v1/robot-model/...`; three.js r160 + urdf-loader 0.12.1 tải từ jsDelivr ở phiên bản ghim. FE nhúng bằng WebView/iframe.
- **Mất liên lạc agent ↔ BE khi đang viết** (đã chốt): sau `link_loss_grace_s` (mặc định 6 giây, là chính sách chứ không phải số vật lý) agent viết nốt nét, nhấc bút, tạm dừng, cảnh báo cam `BACKEND_LINK_LOST` (mức 3) tại chỗ rồi báo lên BE khi nối lại; **không tự tiếp tục**. E-Stop vật lý là an toàn thật.
- **Giữ nguyên cổng chạy THẬT tại chỗ** (`real-enable` + mã xác nhận gắn kế hoạch + đã chạy thử); lệnh từ BE không thay được.
- **Đã chạy thật (MOCK/SIM) toàn đường**: BE thật (uvicorn) + agent thật (PyBullet + URDF FR3) + Supabase Storage thật + DB cục bộ: LOAD → PREFLIGHT → DRY_RUN → RUN, 35/35 nét, xem 3D qua trang của BE. Chưa chạm robot thật.
- Quy trình cho buổi test thật và danh sách việc cần đo: **`ROBOT_REAL_TEST_RUNBOOK.md`**.

**Không cần controller ảo (SimMachine)**: mô phỏng khớp 3D đã chạy bằng PyBullet + URDF của hãng. Controller ảo chỉ thử được đường mã `FairinoRobot` (SDK thật) khi chưa có robot, và là bản 4.0.0.1 (khác controller 3.8.25-QX), nên không chứng minh gì về robot thật. Bước giá trị hơn là `IDENTIFY` chỉ-đọc trên robot thật khi có người vận hành. Image Docker SimMachine đã tải về `D:\K9\tools\fairino-simmachine` nhưng **chưa nạp/chạy**.
**Một lỗi an toàn tìm thấy và sửa**: chạy thử pen-up sau khi job đã viết xong từng ghi đè `progress.json` về rỗng, cho phép "Chạy viết" lần nữa lên tờ giấy đã viết. Nay chạy thử không bao giờ ghi vào trạng thái tờ giấy (có test). Cũng sửa: `POST /api/paper-changed` (LAN) đặt nhầm sự kiện nên không bao giờ nhả bước chờ thay giấy.

## 10d. Ảnh phác thảo và đánh giá chất lượng (đã làm 2026-10-24)
- **Ảnh phác thảo JPG cho khách** (`sketches.image_urls`, migration 0009): mỗi trang một ảnh `sketch_p{n}.jpg` (mực, độ dày nét, tông giấy theo đơn) cạnh PNG kỹ thuật và JSON quỹ đạo, trong `orders/{id}/sketches/v{n}/`. DB chỉ lưu **đường dẫn** (file nằm ở Storage), nên JPG không cần đổi kiểu cột; đã kiểm tra khứ hồi JPEG thật với Supabase Storage (ghi, đọc, link ký, xoá). Khách xem ảnh này ở `GET /orders/{id}/quotation` (`sketch.image_urls`) để quyết định đặt cọc; Staff xem ảnh + `trajectory_url`.
- **Service G** (`quality_evaluations`, migration 0011): so ảnh chụp bản viết với phác thảo đã duyệt: tìm và nắn phẳng tờ giấy, thử 4 hướng, tách nét mực, căn chỉnh nhỏ, rồi đo độ phủ, mực thừa, Chamfer, HD95, Hausdorff (mm) và vẽ ảnh chồng. Kiểm bằng ảnh tổng hợp (phối cảnh, xoay, ánh sáng không đều, nhiễu): đúng ảnh → PASS (độ phủ ≈ 99 %, Chamfer ≈ 0,1–0,2 mm), thiếu nửa nét → FAIL, ảnh không có tờ giấy → báo lỗi. **Chưa thử với ảnh điện thoại thật; số mm chưa hiệu chuẩn bằng thước; ngưỡng là mặc định chưa kiểm chứng.** Kết luận QC vẫn của kỹ thuật viên.

## 10b. Cảnh báo, E-Stop và nhật ký cho Technical Staff / Manager (đã làm 2026-10-23)

Chi tiết API ở `FE_API_GUIDE.md` mục 7f; thiết kế và lý do ở `ROBOT_OPERATIONS_PROPOSAL.md`. Tóm tắt:
- **4 mức**: 1 xanh · 2 vàng · 3 cam (robot đã tự dừng, kiểm tra rồi mới tiếp tục) · 4 đỏ (**bấm E-Stop vật lý ngay**). Câu chữ do bảng `alert_catalog` quyết định (Manager sửa được, mức thì không); agent chỉ gọi tên mã.
- **Mức đỏ chỉ khi phần mềm không chắc robot đã dừng**: `STOP_NOT_EFFECTIVE` (sau lệnh dừng đầu bút vẫn dịch chuyển), `TRACKING_ERROR` (vị trí thật lệch vị trí ra lệnh), `LINK_LOST_MOVING`, `CONTROLLER_SAFETY_FAULT`, `OVER_FORCE_STILL`. Hai watchdog đầu **kiểm tra robot thật sự làm gì**; ngưỡng của chúng (`stop_settle_s`, `stop_window_s`, `stop_tolerance_mm`, `tracking_tolerance_mm`, `tracking_grace_s`) phải do nhóm đo; thiếu thì chế độ REAL từ chối chạy.
- **Màn hình agent** hiện banner đỏ nhấp nháy và còi (bấm "Bật âm thanh cảnh báo" một lần để trình duyệt cho phép), có nội dung dự phòng ngay trên máy trạm khi mất mạng. Cảnh báo đỏ còn **gửi email** cho Technical Staff của job và các Manager (cần `SMTP_*`), và hiện trên màn hình Staff qua `GET /technician/robot-status`.
- **Diễn tập** (không có robot): `python -m vhrs_agent.cli demo --scenario overforce` (cam) và `--scenario runaway` (robot giả lờ lệnh dừng: cảnh báo đỏ).
- **Tuân thủ quy trình** của job: `GET /manager/jobs/{id}/compliance`. Quan trọng nhất: job được ghi nhận "đã viết" mà không có lần chạy robot thật hoàn tất bị đánh dấu.
- **Lưu DB**: bảng `robot_runs` (mỗi lần chạy, ai xác nhận REAL, kết quả, số nét, tóm tắt lực), `robot_alerts`, `alert_catalog`, và cột phiên bản/kết nối/lần cuối thấy trên `robots`. Log chi tiết tần số cao vẫn ở file `runs/*.jsonl` trên máy trạm.

## 11. Việc nhóm cần làm / quyết định

1. Đồng ý tải FAIRINO SimMachine (Docker/VMware, kích thước chưa biết) để chạy adapter thật trên controller ảo; và quyết định có nâng controller hay không (bản đang đăng V4.0.0.1-QX).
2. Chạy `fetch_fairino_sdk.py`, rồi `connect()` chỉ-đọc trên robot thật (có mặt người vận hành): xác nhận phiên bản và tool.
3. Đo các thông số mục 6, đặc biệt TCP, 3–9 điểm giấy, k lò xo, bảng Hall.
4. Chọn bo/chân ESP32 thật để viết firmware; xác minh chân giắc cuối tay trước khi đấu AI0.
5. Chốt phạm vi FE: màn hình hiệu chuẩn (nhập khối `vhrs-motion/1`), màn trình theo dõi (hoặc nhúng `http://<agent>:8765`), hiển thị `simulation_report.server_validation`, danh sách mẫu chữ loại `TYPOGRAPHY`.

## 12. Xử lý sự cố nhanh

| Hiện tượng | Nguyên nhân thường gặp |
|---|---|
| `UNCONFIGURED` | thiếu số đo ở mục 6 (liệt kê trong lỗi) |
| `CONTROLLER_UNSUPPORTED` | controller ngoài dòng V3.8x: kiểm tra tương thích SDK, không ép |
| `TOOL_MISMATCH` / `TCP_OFFSET_MISMATCH` | chọn sai tool hoặc TCP chưa hiệu chuẩn |
| `START_POSE_UNSAFE` | bút đang thấp hơn độ nâng: nâng bút bằng tay dạy trước |
| `PARTIAL_JOB_EXISTS` / `OUTCOME_UNKNOWN` | job dở: xem giấy, chọn `resume_from`; xem log |
| `GRIPPER_ZERO_DRIFT` | TARE lúc nhấc bút; nếu lặp lại → hiệu chuẩn lại |
| `CONTROLLER_BUSY` | agent khác đang chạy; nếu chắc chắn không, xoá `runs/agent.lock` |
| Mô phỏng đạt nhưng server đánh `SERVER OUTSIDE_WORKSPACE` | hộp làm việc/điểm dò sai; không bỏ qua |
