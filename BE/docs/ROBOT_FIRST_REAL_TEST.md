# Buổi test robot thật đầu tiên: từng bước, điền vào đâu

Dành cho người chưa đọc source code. Làm đúng thứ tự, mỗi bước có "Kết quả đúng" để biết đã xong chưa; sai thì **dừng và gửi lại kết quả**, đừng thử cho qua.
Cấu hình: gripper thường có lò xo (không cảm biến), robot FR3 mã `FR3-01` (id 46 trong DB), tài khoản technical staff `tech@netviet.vn` (id 4). Mã nối robot **chưa từng chạy trên FR3 thật**.

**Hai thư mục cần nhớ (cùng máy này):**
- `D:\K9\AI-VHRS\BE` : hệ thống (backend).
- `D:\K9\AI-VHRS\robot_agent` : chương trình điều khiển robot (agent) và công cụ dòng lệnh `scripts\robot_console.py`.

**Bốn cửa sổ PowerShell** dùng trong buổi test (đặt tên cho dễ): **BE**, **AGENT**, **LỆNH**, và khi cần **XÁC NHẬN**. Mọi lệnh của AGENT, LỆNH, XÁC NHẬN chạy trong thư mục `D:\K9\AI-VHRS\robot_agent`.

> Backend chạy **ngay trên máy này** (cửa sổ BE), dùng chung database Supabase, nên không cần commit hay deploy trước. Job bạn dùng là dữ liệu thật trong database.

---
## Phần A. Chuẩn bị một lần

**A1. Mạng tới robot.** Cắm dây LAN từ máy này tới robot. Đặt IP tĩnh cho cổng Ethernet đó (Settings → Network → Ethernet → IP assignment → Edit → Manual): IP `192.168.58.10`, Subnet mask `255.255.255.0`, để trống Gateway. Wi-Fi giữ nguyên để máy vẫn ra internet. Địa chỉ robot mặc định của hãng là `192.168.58.2`: **kiểm tra trên màn hình/trang web của robot**. Rồi:
```powershell
ping 192.168.58.2
```
Kết quả đúng: có phản hồi. Mở thử `http://192.168.58.2` trên trình duyệt (trang web của robot).

**A2. Chọn job để thử.** Đang có các job của `tech@netviet.vn` trên `FR3-01`: **280** (PREPARING, giờ hẹn hôm nay), 276 (PREPARING), 275/277/278/288 (SCHEDULED). Khuyên dùng **280**. Ghi số job vào bước A5. (Muốn job mới: tạo đơn trên web, Staff làm phác thảo và báo giá, khách duyệt và cọc, Manager xếp lịch cho `tech@netviet.vn` và `FR3-01`.)

**A3. File cấu hình agent.** Mở PowerShell (cửa sổ AGENT):
```powershell
cd D:\K9\AI-VHRS\robot_agent
copy agent.example.json agent.json
notepad agent.json
```
Thay **toàn bộ** nội dung bằng (giữ dấu ngoặc và dấu phẩy; chỗ `<...>` là số bạn đo ở Phần B):
```json
{
  "backend_url": "http://127.0.0.1:8000",
  "modes": ["mock", "sim", "real"],
  "run_dir": "runs",
  "lan_server": false,
  "unsensed_gripper": true,
  "robot_id": 46,
  "fairino": {
    "ip": "192.168.58.2",
    "tool_id": <số slot TCP của bút, mục B1>,
    "orientation_deg": [<rx>, <ry>, <rz>],
    "servo_cmd_period_s": 0.008,
    "tcp_offset_mm": <chiều dài bút đo bằng thước, mục B2>
  },
  "watchdogs": {"stop_settle_s": 0.3, "stop_window_s": 0.5, "stop_tolerance_mm": 1.0, "tracking_tolerance_mm": 5.0, "tracking_grace_s": 0.5},
  "sim": {"tool_offset_mm": 250.0, "table_z_mm": 19.0, "start_mm": [-350.0, 0.0, 80.0], "speed_factor": 1.0, "yaw_deg": 0.0}
}
```
Lưu và đóng. Ghi chú: `unsensed_gripper: true` = bạn đồng ý viết không có cảm biến lực (bạn giữ E-Stop). `watchdogs` là **số khởi điểm chưa đo**, chỉnh sau lần chạy thử. `servo_cmd_period_s` 0,008 là mặc định của hãng. Phần `sim` chỉ để chạy mô phỏng.

**A4. File công cụ lệnh.** Trong cửa sổ LỆNH:
```powershell
cd D:\K9\AI-VHRS\robot_agent
copy console.example.json console.json
notepad console.json
```
Điền: `backend_url` = `http://127.0.0.1:8000`; `email` = `tech@netviet.vn`; `job_id` = số job ở A2 (số, không có ngoặc kép); `mode` để `SIM` lúc đầu. Lưu.

**A5. Mật khẩu.** Trong cả hai cửa sổ AGENT và LỆNH, mỗi lần mở cửa sổ mới gõ (thay mật khẩu thật của technical staff; chỉ nằm trong cửa sổ đó, không lưu ra file):
```powershell
$env:VHRS_TECH_EMAIL = "tech@netviet.vn"
$env:VHRS_TECH_PASSWORD = "<mật khẩu>"
```
(Bỏ qua dòng này ở LỆNH nếu thích gõ mật khẩu khi được hỏi.)

---
## Phần B. Đo (robot đứng yên, bút gắn vào gripper, giấy chưa cần)

Đọc toạ độ/pose từ **trang web của robot (`http://192.168.58.2`) hoặc tay cầm dạy**. Tôi không biết tên menu chính xác của controller V3.8.25: nếu không thấy, chụp màn hình gửi tôi.

**B1. TCP đầu bút (`tool_id`).** Dùng chức năng hiệu chuẩn hệ toạ độ công cụ (TCP) của controller với bút đã gắn (đầu bút chạm cùng một điểm cố định từ nhiều hướng). Lưu vào một slot, ghi **số slot** → điền `tool_id` trong `agent.json`. Chọn slot đó làm công cụ đang dùng.

**B2. Chiều dài bút.** Dùng thước đo khoảng cách từ **mặt bích** (mặt phẳng gắn gripper) tới **đầu bút** dọc trục bút, đơn vị mm → điền `tcp_offset_mm`. Agent so với TCP của controller; lệch quá 1 mm thì từ chối điều khiển (nghĩa là TCP chưa đúng).

**B3. Hướng bút.** Jog tay cho bút **thẳng đứng, vuông góc mặt giấy**, đọc ba góc **rx, ry, rz (độ)** của pose hiện tại → điền `orientation_deg`. Giữ đúng hướng này khi chạm các điểm B4.

**B4. Ba điểm chạm giấy.** Kẹp tờ giấy đúng khổ của job (xem `status` ở bước C1: khổ A5 hay A4). Jog đầu bút **chạm nhẹ** vào từng điểm và đọc toạ độ **x, y, z (mm)** của đầu bút trong hệ toạ độ gốc robot:
- **P0** = góc trên-trái của tờ giấy (gốc),
- **P1** = góc trên-phải (cùng cạnh trên với P0: khoảng cách P0→P1 bằng chiều rộng giấy, A5: 148 mm),
- **P2** = góc dưới-trái (khoảng cách P0→P2 bằng chiều cao giấy, A5: 210 mm).
Ba điểm không được thẳng hàng. Nhấc bút lên sau mỗi điểm.

**B5. Lò xo.** Đo **độ cứng** `k = lực / độ nén` (nén lò xo một đoạn đo được, đọc lực trên cân hoặc lực kế, N chia mm) và **hành trình nén tối đa** của gripper (mm).

**B6. Hộp an toàn.** Quanh tờ giấy, chọn vùng robot được phép đưa đầu bút tới: góc nhỏ nhất `(x, y, z)` và góc lớn nhất `(x, y, z)` (mm, cùng hệ toạ độ). Chừa lề ngoài tờ giấy; z từ thấp hơn mặt giấy một chút tới cao hơn độ nhấc bút.

**B7. File hiệu chuẩn.** Trong cửa sổ LỆNH:
```powershell
copy calibration.example.json calibration.json
notepad calibration.json
```
Thay mọi `<...>` bằng số (không để chữ):
- `probe_points`: ba điểm P0, P1, P2 ở B4.
- `spring_k_n_per_mm` và `max_spring_travel_mm`: B5.
- `workspace`: `box_min_mm` và `box_max_mm` ở B6, `edge_margin_mm` vài mm.
- Các số **chọn** (không đo; bắt đầu chậm): `a_lat_mm_s2` 200, `a_tan_mm_s2` 100, `travel_speed_mm_s` 30, `approach_speed_mm_s` 5, `pen_up_clearance_mm` 20. Chưa kiểm chứng ngoài đời, chỉ là điểm xuất phát an toàn.
- `checklist`: để `true` **chỉ khi thật sự đã làm** (khung giấy gắn, giấy kẹp, bút lắp). `force_zero_offset` để `0.0`.

---
## Phần C. Chạy: mô phỏng trước, rồi robot thật

**C0. Bật hệ thống.**
- Cửa sổ **BE**:
  ```powershell
  cd D:\K9\AI-VHRS\BE
  .venv\Scripts\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8000
  ```
  Kết quả đúng: "Application startup complete". Kiểm: mở `http://127.0.0.1:8000/api/v1/health` thấy `{"status":"ok"}`.
- Cửa sổ **AGENT** (đã đặt mật khẩu ở A5):
  ```powershell
  cd D:\K9\AI-VHRS\robot_agent
  .simenv\python.exe -m vhrs_agent.cli serve --config agent.json
  ```
  Kết quả đúng: dòng `Backend link ON (session of tech@netviet.vn on robot 46)`. Nếu thấy `ROBOT_IN_USE`: có app/máy khác đang giữ robot. Nếu `NO_ROBOT`: tài khoản chưa có job hoạt động trên robot.

**C1. Xem trạng thái** (cửa sổ LỆNH, mọi lệnh có dạng `.simenv\python.exe scripts\robot_console.py <lệnh>`):
```powershell
.simenv\python.exe scripts\robot_console.py status
```
Kết quả đúng: `Job N: PREPARING` (hoặc SCHEDULED) và `Agent: ĐANG KẾT NỐI`.

**C2. Chuẩn bị và hiệu chuẩn:**
```powershell
.simenv\python.exe scripts\robot_console.py prepare        # chỉ khi job đang SCHEDULED
.simenv\python.exe scripts\robot_console.py calibrate
.simenv\python.exe scripts\robot_console.py simulate
```
Kết quả đúng: `Job: PREPARING`, `can_start = True`. Nếu `calibrate` báo "còn chỗ chưa điền", sửa `calibration.json`. Nếu `can_start = False`, đọc lý do bằng `status` (backend tự kiểm lại hiệu chuẩn).

**C3. Nạp job và kiểm tra:**
```powershell
.simenv\python.exe scripts\robot_console.py load
.simenv\python.exe scripts\robot_console.py preflight
```
Kết quả đúng: `kiểm chứng quỹ đạo: ĐẠT`, `preflight ok: true`. `load` lưu mã xác nhận chạy thật.

**C4. Tập dượt mô phỏng** (robot không động): `dry-run --speed 6`, rồi `start`, `run --speed 6`, `finish` hoặc dừng ở `dry-run` nếu chỉ muốn thử. (Bỏ qua `start/run/finish` nếu bạn muốn giữ job cho lần chạy thật: **`finish` không hoàn tác được**.)
> Lưu ý: một lần `run` thành công trên cùng job rồi thì agent từ chối viết lại tờ đó (`JOB_ALREADY_WRITTEN`). Với lần chạy thật hãy **không** `run` mô phỏng trên job đó, hoặc dùng job khác.

**C5. Nối robot thật, chỉ đọc.** Sửa `console.json` thành `"mode": "REAL"` (hoặc thêm `--mode REAL` vào từng lệnh). Khởi động lại cửa sổ AGENT (Ctrl+C rồi chạy lại lệnh serve). Rồi:
```powershell
.simenv\python.exe scripts\robot_console.py identify --mode REAL
```
Kết quả đúng: `IDENTIFY DONE` kèm `info` (mẫu, phiên bản controller/firmware/SDK), `tcp_mm`, `joints_deg`. **Gửi tôi toàn bộ phần này.** Nếu lỗi (`SDK_*`, `ROBOT_UNREACHABLE`, `TCP_OFFSET_MISMATCH`, `CONTROLLER_*`): dừng, gửi tôi.

**C6. Chạy thử pen-up trên robot thật** (cánh tay CHUYỂN ĐỘNG):
1. Chuẩn bị: bạn đứng cạnh, tay trên E-Stop, vùng robot trống, giấy kẹp chặt, bút gắn nhưng đầu bút ở trên mặt giấy.
2. Cửa sổ **XÁC NHẬN** (mới, ở thư mục `robot_agent`), gõ số job thật:
   ```powershell
   .simenv\python.exe -m vhrs_agent.cli real-enable --config agent.json --job <SỐ JOB> --minutes 30
   ```
   Gõ `YES` khi được hỏi. (Hết 30 phút hoặc khác job thì phải làm lại. Tắt sớm: thêm `--off`.)
3. `.simenv\python.exe scripts\robot_console.py preflight` (REAL), rồi:
   ```powershell
   .simenv\python.exe scripts\robot_console.py dry-run
   ```
   Gõ `YES` khi được hỏi. Theo dõi bằng mắt và, ở cửa sổ khác, `.simenv\python.exe scripts\robot_console.py watch`.
4. Kết quả đúng: `status` cho thấy lần chạy gần nhất `DRY_RUN_DONE`, robot đã đi qua các nét với bút nhấc. **Bấm E-Stop ngay nếu** robot đi sai hướng, tiến sát giấy, hoặc có tiếng/rung bất thường.

**C7. Viết thật lần đầu** (chỉ khi C6 sạch): ban đầu nên chọn job có chữ ngắn.
```powershell
.simenv\python.exe scripts\robot_console.py start
.simenv\python.exe scripts\robot_console.py run
```
Gõ `YES`. Quan sát nét bút: ra mực đều, không lún sâu, không kẹt. Bất thường thì **E-Stop**. Xong: `status` (kết quả `DONE`), rồi `finish`.

**Lệnh dừng mềm** (cửa sổ LỆNH): `pause`, `resume`, `stop`. Chúng **không thay** E-Stop.

---
## Phần D. Gửi lại cho tôi sau buổi test
- Kết quả `identify` (C5).
- Lỗi/kết quả của từng lệnh nếu có lệnh nào không đạt.
- Thư mục `D:\K9\AI-VHRS\robot_agent\runs\job<SỐ JOB>\` (nhật ký từng lệnh) và ảnh chụp tờ giấy; ảnh có thước đặt cạnh để đo sai số.
- Bạn thấy gì: nét có đúng vị trí trên giấy không (đo bằng thước, lệch bao nhiêu mm), áp lực bút, độ giật.

## Khi gặp lỗi hay gặp
| Thông báo | Nghĩa là | Làm gì |
|---|---|---|
| `AGENT_OFFLINE` | agent chưa chạy / chưa kết nối BE | xem cửa sổ AGENT, chạy lại, kiểm tra `backend_url` |
| `ROBOT_IN_USE` | robot đang do người/máy khác điều khiển | đóng agent kia, hoặc chờ khoá hết hạn |
| `REAL_NOT_ENABLED_ON_SITE` | chưa chạy `real-enable` cho đúng job, hoặc đã hết hạn | làm C6 bước 2 |
| `AUTHORIZATION_REQUIRED` | thiếu mã xác nhận | chạy `load` lại rồi lệnh cần chạy (mã gắn với kế hoạch) |
| `DRY_RUN_REQUIRED` | chưa chạy thử pen-up thành công cho đúng kế hoạch | làm C6 |
| `GRIPPER_NOT_CONFIGURED` | thiếu `"unsensed_gripper": true` | sửa `agent.json`, chạy lại AGENT |
| `WATCHDOG_UNCONFIGURED` | thiếu khối `watchdogs` | sửa `agent.json` |
| `TCP_OFFSET_MISMATCH` | chiều dài bút đo khác TCP của controller quá 1 mm | kiểm tra B1 và B2 |
| `NOT_REACHABLE` / `START_POSE_UNSAFE` | điểm ngoài tầm với hoặc tư thế khởi đầu không an toàn | kiểm tra vị trí giấy, B4 và B6 |
| `VALIDATION_FAILED` | quỹ đạo vượt khỏi giấy/hộp an toàn/giới hạn | đọc `details` trong kết quả; sửa B4, B6 hoặc calibration |
| `JOB_STATE_CONFLICT` | sai bước (ví dụ `run` khi chưa `start`) | xem `status`, làm đúng thứ tự |
