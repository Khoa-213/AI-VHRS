# Chạy thử với robot FAIRINO FR3 thật: quy trình và lệnh

Tài liệu cho chủ dự án và kỹ thuật viên. **Chưa có lần chạy nào trên robot thật được thực hiện bởi AI hay bởi bộ test**: mọi kiểm chứng tới nay là MOCK/SIM (xem mục 9). Mọi con số vật lý ở đây đều là **việc cần đo**, không có giá trị mặc định đáng tin.

Kiến trúc (đã chốt, "A"): app kỹ thuật viên → **BE (Render)** ← máy trạm (Robot Agent gọi RA). Không mở cổng nào vào xưởng. Chi tiết API: `FE_API_GUIDE.md` mục 7g.

## 0. Quy tắc an toàn (đọc trước, không bỏ qua)
1. Một người đứng **trong tầm với tới nút E-Stop vật lý** suốt lúc robot được bật. Phần mềm không bấm được E-Stop; lệnh DỪNG chỉ là dừng phần mềm.
2. Lần đầu: **không có người trong vùng làm việc**, bút/giấy kẹp chặt, tốc độ thấp nhất cho phép, tay luôn trên E-Stop.
3. Chạy THẬT chỉ khi đủ ba điều: `real` có trong `modes` của agent, người ở máy trạm chạy `real-enable` cho đúng job (hết hạn), và mã `AUTHORIZE-…` của đúng kế hoạch. Nếu thiếu một, agent từ chối.
4. Cảnh báo **đỏ** = bấm E-Stop ngay, rồi mới đọc tiếp.
5. Không nâng firmware/controller để "cho chạy được". Controller hiện tại V3.8.25-QX; SDK đang ghim theo robot 3.8.7.1: **chưa kiểm chứng tương thích**, `IDENTIFY` ở bước 5 sẽ cho biết.

## 1. BE trên Render (gói free)
- Cấu hình giống phần deploy hiện có (`DEPLOY.md`); BE chạy **1 worker** (bắt buộc, trạng thái sống nằm trong bộ nhớ).
- DB: migration `0011` đã áp lên Supabase (kiểm: `alembic current` = `0011`). Mô hình robot đã nằm trong Storage (`robot-models/fr3/`, script `scripts/upload_robot_model.py`).
- `CORS_ORIGINS`: thêm origin của FE web (cũng dùng cho iframe 3D).
- Gói free **ngủ sau ~15 phút không có request** và thức dậy chậm (có thể cả phút): trước buổi test hãy mở `https://<be>/api/v1/health` cho tới khi trả `ok`. Agent tự thử lại khi BE ngủ. **Nếu BE ngủ lúc robot đang viết**, agent viết nốt nét hiện tại rồi tạm dừng (mục 7); đó là cách gián đoạn được xử lý, và là lý do nên nâng gói nếu xảy ra.
- Email cảnh báo đỏ cần SMTP (`SMTP_HOST`, `SMTP_USER`, `SMTP_PASSWORD`, ...); chưa cấu hình thì chỉ hiện trong app.

## 2. Khoá cho agent: đăng nhập technical staff (đường chính) hoặc khoá của Manager
**Đường chính:** agent tự đăng nhập bằng tài khoản technical staff đang giữ job trên robot và xin khoá phiên (~4 giờ, tự gia hạn êm). Không cần ai cấp khoá; bỏ qua phần Manager bên dưới. Đặt thông tin đăng nhập bằng biến môi trường của tiến trình (không ghi vào file):
```powershell
$env:VHRS_TECH_EMAIL = "<email technical staff>"
$env:VHRS_TECH_PASSWORD = "<mat-khau>"
```
Nếu robot đang do người/máy khác điều khiển, agent dừng với lỗi `ROBOT_IN_USE` (không cướp quyền). Technical staff phải đang giữ **một job còn hoạt động** (SCHEDULED, PREPARING, WRITING, PAUSED) trên robot; nếu có nhiều robot, thêm `"robot_id": <id>` vào `agent.json`.

**Đường phụ (khoá cố định của Manager, cho máy trạm không có ai đăng nhập):**
```bash
BE=https://<be>.onrender.com/api/v1
TOKEN=$(curl -s $BE/auth/login -H 'content-type: application/json' -d '{"email":"<manager>","password":"<mat-khau>"}' | python -c "import sys,json;print(json.load(sys.stdin)['access_token'])")
curl -s -X POST $BE/manager/robots/<ROBOT_ID>/agent-key -H "authorization: Bearer $TOKEN"
```
Khoá `vhrs_ak_...` chỉ hiện một lần. Mất thì cấp lại (khoá cũ bị thu hồi). `GET $BE/manager/robots/<ROBOT_ID>/agent` cho biết đã có khoá và agent đang `online` chưa.

## 3. Máy trạm (Windows)
Một lần: dựng môi trường mô phỏng và lấy SDK/mô hình (đã làm được trên máy dev; làm lại trên máy trạm nếu khác máy):
```bash
cd robot_agent
python scripts/setup_sim_env.py           # micromamba + PyBullet (không cần trình biên dịch C++)
.simenv/python.exe scripts/fetch_fr3_model.py
.simenv/python.exe scripts/fetch_fairino_sdk.py     # SDK ghim commit 55bcce6
```
`agent.json` (không commit; mẫu `agent.example.json`). Chỉ mô phỏng:
```json
{"backend_url": "https://<be>.onrender.com", "modes": ["mock", "sim"], "run_dir": "runs", "lan_server": false,
 "sim": {"tool_offset_mm": 250.0, "table_z_mm": 19.0, "start_mm": [-350.0, 0.0, 80.0], "speed_factor": 1.0, "yaw_deg": 0.0}}
```
Chạy agent (đăng nhập technical staff như mục 2; hoặc đặt `$env:VHRS_AGENT_KEY = "vhrs_ak_..."` nếu dùng khoá của Manager):
```powershell
.simenv\python.exe -m vhrs_agent.cli serve --config agent.json
```
Thấy `Backend link ON (session of <email> on robot <id>)`. Kiểm từ app/curl: `GET $BE/technician/robots/<ROBOT_ID>/live` → `agent_online: true`. Muốn tự khởi động: Task Scheduler "At startup" chạy đúng lệnh trên (đặt biến môi trường trong tác vụ).

## 4. Tập dượt đủ quy trình bằng SIM, qua BE (chưa đụng robot)
Đã chạy được kiểu này trên máy dev (BE thật + agent thật + PyBullet + Supabase Storage thật, DB cục bộ): LOAD → PREFLIGHT → DRY_RUN → RUN, 35/35 nét, xem 3D bằng trang `/viewer/robot.html`. Làm lại với job thật của bạn:
```bash
H="authorization: Bearer $TECH_TOKEN"; JOB=<JOB_ID>
cmd() { curl -s -X POST $BE/technician/robot-commands -H "$H" -H 'content-type: application/json' \
  -d "{\"kind\":\"$1\",\"job_id\":$JOB,\"params\":$2,\"idempotency_key\":\"$(python -c 'import uuid;print(uuid.uuid4())')\"}"; }
poll() { curl -s $BE/technician/robot-commands/$1 -H "$H"; }

curl -s -X POST $BE/technician/jobs/$JOB/prepare -H "$H"      # sau khi đã tải gói (GET .../package), hiệu chuẩn và mô phỏng (xem FE guide 7b)
cmd LOAD '{}'                                   # lấy id lệnh rồi poll tới DONE; kết quả có authorization_token và plan_digest
cmd PREFLIGHT '{"mode":"SIM"}'
cmd DRY_RUN '{"mode":"SIM","speed":2}'          # job phải đang PREPARING
curl -s -X POST $BE/technician/jobs/$JOB/start -H "$H"
cmd RUN '{"mode":"SIM","speed":2}'              # job phải đang WRITING
curl -s $BE/technician/robots/<ROBOT_ID>/live -H "$H"        # trạng thái sống; lấy vé 3D: POST .../robots/<ROBOT_ID>/view-ticket
```
Dừng/tạm dừng: `cmd PAUSE '{}'`, `cmd RESUME '{}'`, `cmd STOP '{}'`.

## 5. Nối robot thật, CHỈ ĐỌC (không enable, không chuyển động)
Điều kiện: người trực E-Stop, robot đã bật nguồn và controller sẵn sàng. Thêm vào `agent.json` (chỉ ở máy trạm nối robot):
```json
"modes": ["mock", "sim", "real"],
"fairino": {"ip": "192.168.58.2", "tool_id": 1, "orientation_deg": [180.0, 0.0, 0.0], "servo_cmd_period_s": "<ĐO>", "tcp_offset_mm": "<ĐO>"}
```
`ip` là địa chỉ mặc định của hãng: xác nhận trên màn hình robot. Máy trạm phải cùng dải mạng với robot. Khởi động lại agent, rồi:
```bash
cmd_robot() { curl -s -X POST $BE/technician/robot-commands -H "$H" -H 'content-type: application/json' -d "{\"kind\":\"IDENTIFY\",\"robot_id\":<ROBOT_ID>,\"params\":{\"mode\":\"REAL\"}}"; }
```
Kết quả `DONE` cho biết mẫu, phiên bản controller/firmware/SDK, tư thế các khớp và vị trí TCP. **Gửi kết quả này cho dự án**: nó trả lời câu hỏi tương thích SDK 3.8.7.1 với controller V3.8.25-QX. Nếu `FAILED`/lỗi kết nối: dừng, đừng thử "cho qua".

## 6. Những thứ phải ĐO trước khi viết thật (mọi thứ này đang `UNCONFIGURED`)
| Cần đo | Dùng ở | Cách |
|---|---|---|
| `servo_cmd_period_s` | tốc độ gửi điểm | theo tài liệu hãng, xác nhận bằng log thời gian thực |
| `tcp_offset_mm` | đầu bút so với mặt bích | đo từ khung wrist3 (~103 mm sau mặt bích với giá kẹp hiện tại), nhập đúng |
| Hệ toạ độ tờ giấy | khung giấy → robot | 3 điểm chạm P0, P1, P2 trên giấy (kỹ thuật viên dạy điểm), cộng lưới chiều cao nếu giấy không phẳng |
| `workspace` (hộp an toàn) | từ chối quỹ đạo ra ngoài | đo thực tế quanh tờ giấy, trừ lề |
| `watchdogs` (stop_settle_s, stop_window_s, stop_tolerance_mm, tracking_tolerance_mm, tracking_grace_s) | tự phát hiện robot không dừng / lệch đường | đo khi chạy thử pen-up; **không có ngưỡng thì agent không chạy REAL** (`WATCHDOG_UNCONFIGURED`) |
| Gripper (`gripper_port`, bảng Hall→lực) | lực ép bút | theo `AI-VHRS_Gripper_IoT_NghienCuu`: hiệu chuẩn bằng cân/lực kế, ghi bảng; không ngoại suy ngoài dải đã đo |
Khối `frame_transform` gửi lên lúc hiệu chuẩn: `FE_API_GUIDE.md` mục 7b.

### 6b. Gripper thường có lò xo, KHÔNG cảm biến (lựa chọn của chủ dự án, 2026-10-24)
Chưa có gripper IoT (Hall + ESP32) thì đặt trong `agent.json` (chỉ ở máy trạm nối robot): `"unsensed_gripper": true` và **không** đặt `gripper_port`. Đây là lựa chọn rõ ràng của chủ dự án, không bao giờ là mặc định: thiếu dòng này agent từ chối REAL với `GRIPPER_NOT_CONFIGURED`.
- **Mất:** agent không thấy lực thật, nên **không có** phát hiện ép quá mạnh (`OVER_FORCE`), mất tiếp xúc giữa nét (`STROKE_LOST`) hay lệch lực. Độ ép bút chỉ theo mô hình lò xo (`press = f_target / k`, giới hạn bởi hành trình tối đa). Người vận hành đứng cạnh, tay trên E-Stop, là lớp an toàn duy nhất cho lực.
- **Vẫn giữ nguyên:** `real-enable` tại chỗ, mã `AUTHORIZE-…`, bắt buộc chạy thử pen-up trước, ngưỡng watchdog (robot không dừng, lệch đường), kiểm tra tầm với/hộp an toàn, giới hạn tốc độ.
- **Ghi lại:** mỗi lần chạy lưu `force_sensing: false` trong `robot_runs.summary`, nhật ký chạy có sự kiện `no_force_sensing`, màn hình agent hiện "KHÔNG có cảm biến lực".
- **Cần đo cho gripper này:** `spring_k_n_per_mm` (nén lò xo từng bước trên cân/lực kế, `k = F/x`) và `max_spring_travel_mm`; không cần bảng Hall → lực. Thử ép nhỏ trước: chọn bút `f_target_n` thấp và kiểm bằng mắt/giấy than rằng nét ra đều, không lún quá.
- Chạy thử `RUN` đầu tiên bằng chữ ngắn, tốc độ thấp, và dừng ngay (E-Stop) nếu bút lún sâu, kẹt hoặc ép vào giấy bất thường.

## 7. Chạy thử THẬT: bút nhấc (DRY_RUN) rồi viết (RUN)
**DRY_RUN ở chế độ REAL cũng làm cánh tay chuyển động thật** (bút nhấc lên khỏi giấy). Cùng đủ điều kiện an toàn như viết.
1. `LOAD` job (mục 4). Ghi lại `authorization_token` (dạng `AUTHORIZE-<job>-<8 ký tự>`) và đọc `validation` (phải `passed`).
2. **Tại máy trạm, người vận hành** xác nhận đã sẵn sàng (E-Stop trong tầm tay, giấy kẹp chặt, vùng robot trống):
   ```powershell
   .simenv\python.exe -m vhrs_agent.cli real-enable --config agent.json --job <JOB_ID> --minutes 30
   ```
   (gõ `YES`). File chỉ có hiệu lực cho đúng job đó và hết hạn. Tắt sớm: thêm `--off`.
3. `PREFLIGHT` với `{"mode":"REAL"}`: không chuyển động; phải `ok:true`.
4. `DRY_RUN` với `{"mode":"REAL","authorization":"AUTHORIZE-..."}`. Theo dõi `live` và 3D. Phải kết thúc `DRY_RUN_DONE`.
5. `POST /technician/jobs/<JOB>/start`, rồi `RUN` với `{"mode":"REAL","authorization":"AUTHORIZE-..."}`.
6. Theo dõi tới `busy=false`; kết quả ở `status.last`. Xong: `POST /technician/jobs/<JOB>/finish`, chụp ảnh QC, `evaluate` (FE guide 7c.2).

**Khi có sự cố:** (a) nguy hiểm hoặc robot không theo lệnh → **E-Stop vật lý**. (b) Cảnh báo cam (robot đã tự dừng an toàn) → xử lý nguyên nhân theo câu chữ, rồi `RESUME` hoặc `STOP`; một nét dở **không** tự chạy lại: chọn `resume_from` rõ ràng. (c) Mất liên lạc agent ↔ BE khi đang viết → agent viết nốt nét, nhấc bút, tạm dừng, cảnh báo cam tại chỗ; khi nối lại gửi `RESUME` hoặc `STOP`. (d) Sau mọi sự cố **giữ nguyên** thư mục `runs/job<ID>/` (log từng lệnh, từng cảnh báo) và gửi cho dự án; `GET /api/jobs/<ID>/log` ở agent hoặc `GET $BE/manager/jobs/<ID>/compliance` cho thấy quy trình có đúng không.

## 8. Báo lại cho dự án sau buổi test
- Kết quả `IDENTIFY` (phiên bản, tư thế khớp, TCP).
- Có/không: khung giấy khớp thực tế? điểm đầu bút chạm giấy có đúng mm? (đo bằng thước, sai số bao nhiêu)
- Thời gian trễ lệnh DỪNG, độ lệch tracking, lực đo được so với dải của bút.
- Thư mục `runs/job<ID>/` và ảnh chụp bản viết; ảnh chụp thước đặt cạnh tờ giấy để hiệu chuẩn số đo mm của Service G.

## 9. Trạng thái kiểm chứng (trung thực)
| Phần | Trạng thái |
|---|---|
| Đường lệnh app → BE → agent → kết quả; xem 3D qua BE; ảnh phác thảo JPG; Service G (ảnh tổng hợp) | **Đã chạy thật ở MOCK/SIM** (BE thật + agent thật + Storage thật), có test tự động |
| Điều khiển robot THẬT (FairinoRobot, SDK), gripper thật, IK trên robot thật, watchdog dừng/lệch | **CHƯA kiểm chứng**: mã đã viết và test bằng robot giả; chưa có lần chạy nào trên FR3 |
| Tương thích SDK 3.8.7.1 ↔ controller V3.8.25-QX | **CHƯA biết** (bước IDENTIFY trả lời) |
| Hệ toạ độ URDF = hệ toạ độ gốc controller | **Giả định** |
| Số đo mm của Service G | **Chưa hiệu chuẩn** bằng thước/ảnh thật |
| Gói free Render có đủ cho một buổi viết | **Chưa biết**; gián đoạn được xử lý bằng tạm dừng sau nét |
