# Bàn giao: giao robot cố định + màn desktop là nơi làm việc DUY NHẤT của kỹ thuật viên

Ngày 2026-11-26. Chủ dự án chốt:
1. Manager giao robot cố định cho kỹ thuật viên; kỹ thuật viên tự chọn robot cho job.
2. **Bỏ giao diện kỹ thuật viên trên web.** Kỹ thuật viên chỉ làm việc trên **màn desktop ở máy trạm**: trang do Robot Agent phục vụ, `robot_agent/vhrs_agent/static/`, hiện tên "VHRS Robot Monitor".
3. **Bật REAL bằng nút trên màn desktop**: phương án c1, không còn phải gõ lệnh `real-enable` hay gõ `YES`. **Không bật được từ xa qua BE** (web, điện thoại).

**Đã làm:**
- BE: migration 0032, xem `FE_API_GUIDE.md` mục 7.3 và 7b.0.
- API cục bộ của agent: mục 2.2 dưới đây.

- **2026-11-26 (tối, chưa commit): mục 1, 2, 3 đã làm theo tài liệu này.**
  - Mục 2: màn máy trạm `robot_agent/vhrs_agent/static/` (`index.html`, `assets/app.js`, `assets/app.css`): đăng nhập, dải robot, job theo nhóm, 12 bước (mở/gập, lý do khoá, tự sang bước kế), đo P0–P2 bằng robot hoặc file, Bật/Tắt REAL có đếm ngược, Về điểm chờ, Viết lại từ đầu, nhật ký, sự cố, ảnh + QC + gửi, lệnh Tạm dừng/DỪNG cho robot ở máy khác, thanh Tạm dừng/Tiếp tục/DỪNG luôn ở đáy. `/api/agent` trả thêm `robot_id`; agent phục vụ `/assets`. SHA-256 tự tính khi trang mở qua http LAN (không có `crypto.subtle`).
  - Kiểm: agent `pytest` 178 passed, 3 skipped; `scripts/check_workspace_browser.mjs` PASS (Edge thật, mọi API giả lập, đi hết bước 1–12 với REAL). **Chưa chạy với BE cục bộ + agent `serve` thật như mục 2.7**, chưa thử robot thật.
  - Mục 1: `RobotAssignments.tsx`, lịch theo kỹ thuật viên, nhãn đỏ "REAL đang bật cho job X tới hh:mm" (1.3). Mục 3: trang `/tech*` gỡ, còn trang thông báo địa chỉ máy trạm + danh sách job chỉ xem. `FE/scripts/check-robot-assignment-browser.mjs` PASS.

**Tài liệu này là việc người khác cần làm:** web Manager (mục 1), gỡ trang kỹ thuật viên trên web (mục 3), dựng màn desktop (mục 2).

## 0. Thay đổi nghiệp vụ

| Trước | Bây giờ |
|---|---|
| Manager chọn **robot + kỹ thuật viên + giờ** | Manager **giao cố định** robot cho kỹ thuật viên: mỗi robot thuộc tối đa 1 người, 1 người giữ được nhiều robot |
| Lịch luôn có robot | Manager xếp lịch cho **kỹ thuật viên + giờ**; robot **tuỳ chọn**, nếu chọn thì phải là robot của người đó |
| Kỹ thuật viên làm trên web `/tech` và trên máy trạm (console + Robot Monitor) | **Chỉ màn desktop ở máy trạm** |
| Bật REAL: gõ `real-enable` + `YES` trong terminal | Bấm **"Bật REAL"** trên màn desktop: chỉ cho job đã nạp ở máy đó, chỉ khi agent có chế độ `real` |

`JobOut.robot_id` giờ có thể là `null`, khi đó `robot_code = ""`. Mọi chỗ hiện mã robot của job phải hiện "Chưa chọn robot" trong trường hợp này.

## 1. Web Manager (FE web, `FE/`)

### 1.1 Màn Robot (`FE/src/pages/staff/Robots.tsx`, `/staff/robots`)
- **Cột "Kỹ thuật viên phụ trách":** lấy `technician_id`, `technician_name` từ `GET /manager/robots`.
- **Giao robot:** chọn người trong `GET /manager/technicians`, lưu bằng `PUT /manager/robots/{id}/technician {technician_id}`.
- **Thu hồi:** `DELETE /manager/robots/{id}/technician`. Cả giao và thu hồi đều trả về `RobotOut` mới.
- **Lỗi cần xử lý:**
  - `409 ROBOT_HAS_ACTIVE_JOBS`: liệt kê `details.job_ids` và báo "xếp lại các job này trước".
  - `422 INVALID_TECHNICIAN`.
  - `404 ROBOT_NOT_FOUND`.

### 1.2 Màn xếp lịch (`Schedule.tsx`, `ScheduleCalendar.tsx`, `/staff/schedule`)
- **Thứ tự chọn:** kỹ thuật viên trước, rồi giờ, rồi robot (tuỳ chọn).
  - Danh sách robot chỉ gồm `robots[]` của người đã chọn.
  - Mặc định là **"Để kỹ thuật viên tự chọn"**, khi đó không gửi `robot_id`.
- **Người chưa có robot:** hiện cảnh báo kèm link sang màn Robot (BE trả `422 TECHNICIAN_HAS_NO_ROBOT`).
- **Gợi ý lịch:** mỗi kỹ thuật viên một gợi ý.
- **Đổi người nhận job:** robot cũ bị bỏ nếu nó không thuộc người mới.
- **Calendar:** job chưa có robot nằm ở hàng của kỹ thuật viên, kèm nhãn "Chưa chọn robot".
- **Lỗi mới:**
  - `422 ROBOT_NOT_ASSIGNED`.
  - `422 TECHNICIAN_HAS_NO_ROBOT`.
  - `409 SLOT_CONFLICT` với `details.resource = "robot"`: "Không robot nào của <tên> rảnh khung giờ này".

### 1.3 Manager xem robot
Giữ màn giám sát robot của Manager trên web như hiện có (live, cảnh báo, tạm dừng/dừng).
`live.status.real_enabled` có giá trị khác `null` nghĩa là máy trạm đang bật REAL. Cần hiện nhãn đỏ "REAL đang bật cho job X tới hh:mm".

## 2. Màn desktop của kỹ thuật viên (`robot_agent/vhrs_agent/static/`)

Màn này do Robot Agent phục vụ tại `http://<máy trạm>:8765/` (lệnh `serve`). Hiện tại nó là "VHRS Robot Monitor" (`index.html` + `twin.js`): đăng nhập, 3D, trạng thái, cảnh báo, nút dừng.
Cần mở rộng nó thành **nơi làm việc đầy đủ**, thay thế web `/tech` và `robot_console.py`.

- Viết thuần HTML/JS như hiện tại, không có bước build. Thư viện để trong `static/vendor`.
- Chạy được trên Chrome / Edge của máy trạm.

### 2.1 Gọi API thế nào
**Một token cho cả màn hình:**
- `POST /api/login {email, password}` trả về `access_token`. Mọi request gửi kèm header `Authorization: Bearer <token>`.
- Chỉ Technical Staff và Manager đăng nhập được. Riêng Technical Staff mới thao tác được job.

**Hai nhóm API:**

| Nhóm | Gọi ở đâu |
|---|---|
| Nghiệp vụ BE `/api/v1/technician/*` (job, gói, chọn robot, chuẩn bị, hiệu chuẩn, mô phỏng, bắt đầu, xong, sự cố, ảnh, QC, robot của tôi, lệnh robot, live) | Qua agent: **`/api/technician/<đường dẫn>`**, cùng phương thức, query và body. Agent chuyển tiếp nguyên trạng tới BE bằng token của người dùng. Ví dụ: `GET /api/technician/robots`, `PUT /api/technician/jobs/12/robot`. Màn hình không cần CORS tới BE |
| Robot nối với máy trạm này | API cục bộ của agent, mục 2.2 |

**Ảnh sản phẩm:** `POST /api/technician/jobs/{id}/photos/upload-url` trả về URL có chữ ký. Trình duyệt `PUT` file thẳng lên URL đó, sau đó gọi `POST /api/technician/jobs/{id}/photos`.

### 2.2 API cục bộ của agent

**Đã có sẵn:**
```
GET    /api/agent                         version, modes, busy, current, last, real_enabled
POST   /api/robot/identify {mode}         đọc robot, không di chuyển; trả tcp_mm, joints_deg (dùng khi đo P0–P2)
POST   /api/jobs/{id}/load                nạp job, trả summary + authorization_token (AUTHORIZE-<job>-<kế hoạch>)
GET    /api/jobs/{id}                     summary + progress + busy
POST   /api/jobs/{id}/preflight {mode}
POST   /api/jobs/{id}/dry-run {mode, authorization?, speed?}     202
POST   /api/jobs/{id}/run {mode, authorization?, resume_from?, confirm_unknown?, speed?}   202
GET    /api/jobs/{id}/log?tail=200        nhật ký lần chạy gần nhất
WebSocket xem 3D / trạng thái             như index.html hiện tại; tạm dừng / tiếp tục / dừng như hiện tại
```

**Mới, 2026-11-26:**
```
GET    /api/real                                  {real_enabled: {job_id, expires_at, enabled_by, waive_dry_run} | null, real_available, max_minutes}
POST   /api/jobs/{id}/real-enable {minutes 1..120, waive_dry_run?, confirm_waive?}   bật REAL cho job này
DELETE /api/real-enable                           tắt REAL (kỹ thuật viên hoặc Manager)
POST   /api/jobs/{id}/reset-progress {confirm: "NEW_SHEET"}   lần chạy sau viết lại từ nét đầu (có sao lưu)
*      /api/technician/{path}                     chuyển tiếp tới BE /api/v1/technician/{path}
```

**Lỗi của `real-enable`:**
- `403 MODE_DISABLED`: máy này không nối robot thật, `agent.json` không có `real` → ẩn nút.
- `409 JOB_NOT_LOADED`: phải nạp job ở máy này trước, và chỉ người đã nạp job mới bật được.
- `422 CONFIRM_REQUIRED`: có `waive_dry_run` mà thiếu `confirm_waive = "SKIP-DRY-RUN"`.
- `422`: số phút nằm ngoài 1..120.

Bật REAL **không** bỏ qua hai lớp khoá còn lại. Chạy REAL vẫn cần mã `authorization_token` (lấy khi nạp job) và một lần chạy thử nhấc bút REAL đã đạt, trừ khi đã bỏ qua bằng `confirm_waive`.

### 2.3 Bố cục
```
┌ Đăng nhập ─ Tên · Máy trạm: robot FR3-01 (SIM/REAL) · [REAL đang bật cho job 12 tới 15:30 ✕] ─────────────────┐
│ Robot của tôi: Đang kết nối 2 / 3 · Đang hoạt động 1                                                           │
│ [FR3-01 ● Kết nối · Đang viết 45% · máy này] [FR3-02 ● Kết nối · Sẵn sàng] [FR3-03 ○ Mất kết nối · Bảo trì]    │
├ Job của tôi ──────────┬ Job VHRS-xxxx ───────────────────────────────────────────────────────────────────────────┤
│ Đang viết (1)         │ ① Tải gói ② Chọn robot ③ Chuẩn bị ④ Hiệu chuẩn ⑤ Nạp ⑥ Kiểm tra ⑦ Mô phỏng          │
│ Sẵn sàng (2)          │ ⑧ Chạy thử ⑨ Bật REAL ⑩ Bắt đầu + Viết ⑪ Xong ⑫ Ảnh + QC                              │
│ Chờ QC (1)            │ [bước hiện tại + lý do bước sau bị khoá]                                              │
│ Cần chú ý / Lịch sử   │ [3D + tạm dừng / tiếp tục / DỪNG luôn ghim khi đang chạy] [nhật ký chạy]            │
└───────────────────────┴───────────────────────────────────────────────────────────────────────────────────────────┘
```

### 2.4 Dải robot
- **Nguồn:** `GET /api/technician/robots` trả `{total, online, active, robots[]}`, chỉ gồm robot Manager giao cho người đăng nhập.
- **Dòng tổng:** "Đang kết nối {online} / {total} · Đang hoạt động {active}".
- **Mỗi thẻ robot hiện:**
  - `robot_code`, `station`;
  - `connection_state`: ONLINE = "Đã kết nối", OFFLINE = "Mất kết nối", UNKNOWN = "Chưa từng kết nối";
  - `state` + `headline_vi`; khi `active` thì nhấn mạnh "Đang hoạt động";
  - `robot_status` MAINTENANCE / BROKEN → "Bảo trì" / "Hỏng";
  - `enabled_modes`, `job_id` (bấm vào để mở job), `open_alerts`.
  - Khi `level >= 4` → banner đỏ "BẤM NÚT E-STOP NGAY".
- **Robot nối với máy này:** đánh dấu "máy này". Đó là robot có `robot_id` trùng `summary.robot_id` khi nạp job; agent chỉ có một robot.
  - Robot của máy này thao tác bằng API cục bộ.
  - Robot ở máy trạm khác vẫn xem được, và gửi được lệnh qua `POST /api/technician/robot-commands` (agent của máy đó nhận lệnh qua BE).
  - Riêng **Bật REAL chỉ làm được trên máy nối với robot đó.**
- **Làm mới:** mỗi 5 giây khi có robot `active` hoặc `level >= 3`, còn lại mỗi 15 giây.

### 2.5 Các bước của một job
| # | Bước | Gọi | Xong khi |
|---|---|---|---|
| 1 | Tải gói + kiểm hash | `GET /api/technician/jobs/{id}/package` | `downloaded_at` có giá trị, hash khớp |
| 2 | Chọn robot | `PUT /api/technician/jobs/{id}/robot {robot_id}` (chỉ khi job `SCHEDULED`) | `robot_id` khác null; mặc định chọn robot của máy này |
| 3 | Chuẩn bị | `POST /api/technician/jobs/{id}/prepare` | `PREPARING` |
| 4 | Hiệu chuẩn | `POST /api/technician/jobs/{id}/calibration` (mục 2.6) | `calibration.is_valid` |
| 5 | Nạp job | `POST /api/jobs/{id}/load` | trả `authorization_token`, giữ trong bộ nhớ trang |
| 6 | Kiểm tra trước | `POST /api/jobs/{id}/preflight {mode}` | `ok` |
| 7 | Ghi kết quả mô phỏng | `POST /api/technician/jobs/{id}/simulation` (cách làm như `robot_console.py simulate`) | `simulation_passed` |
| 8 | Chạy thử nhấc bút | `POST /api/jobs/{id}/dry-run {mode, authorization}` | `last.result.state = DRY_RUN_DONE` |
| 9 | **Bật REAL** (chỉ khi chạy REAL) | `POST /api/jobs/{id}/real-enable {minutes}` | `GET /api/real` trả job này |
| 10 | Bắt đầu + Viết | `POST /api/technician/jobs/{id}/start`, rồi `POST /api/jobs/{id}/run` | tiến độ chạy |
| 11 | Viết xong | `POST /api/technician/jobs/{id}/finish` | `WRITTEN` |
| 12 | Ảnh + QC + gửi | `/api/technician/jobs/{id}/photos*`, `.../photos/submit`, `.../qc-fail` | `PHOTO_UPLOADED` |

- **Thứ tự REAL:** bước 9 phải làm **trước** bước 8 nếu chạy thử ở chế độ REAL, vì `dry-run` với mode real cũng cần REAL đang bật.
  - Màn hình nên đề xuất: Bật REAL → chạy thử REAL → viết REAL.
- **Nút Bật REAL:**
  - Ô số phút, mặc định 30.
  - Hộp đánh dấu "Bỏ chạy thử nhấc bút"; khi đánh dấu thì gửi `confirm_waive: "SKIP-DRY-RUN"` và hiện cảnh báo đỏ.
  - Sau khi bật, hiện đồng hồ đếm ngược và nút **Tắt REAL** (`DELETE /api/real-enable`).
- **Các nút khác:**
  - **Về điểm chờ:** gửi lệnh `STOP`, đợi agent hết bận, rồi gửi lệnh `ALIGN_START`. Cả hai lệnh đi qua `POST /api/technician/robot-commands`. Cách làm như `robot_console.py home`.
  - **Viết lại từ đầu (tờ mới):** gọi `reset-progress`, kèm hộp xác nhận "tờ giấy mới, trắng, kẹp đúng chỗ".
  - **Nhật ký chạy:** `GET /api/jobs/{id}/log`.
  - **Báo sự cố:** `POST /api/technician/jobs/{id}/incidents`.
- **Câu chữ cho lỗi:**
  - `ROBOT_NOT_SELECTED`: "Hãy chọn robot cho job".
  - `ROBOT_NOT_FOUND`: "Robot không được giao cho bạn".
  - `ROBOT_UNAVAILABLE`, `ROBOT_NOT_SUITABLE`.
  - `SLOT_CONFLICT`.
  - `REAL_NOT_ENABLED_ON_SITE`: "Bấm Bật REAL".
  - `DRY_RUN_REQUIRED`, `AUTHORIZATION_REQUIRED`.

### 2.6 Hiệu chuẩn
Body của `POST /api/technician/jobs/{id}/calibration`:
```
{checklist: {frame_mounted, paper_clamped, pen_installed, force_zeroed: true},
 force_zero_offset,
 probe_points: [{x,y,z} ≥ 3: P0 P1 P2, không thẳng hàng],
 frame_transform?, height_map?, force_curve?}
```

**Cách 1: đo bằng robot (khuyên dùng).**
- Người vận hành đưa đầu bút tới từng góc giấy, rồi bấm "Lấy P0" / "Lấy P1" / "Lấy P2".
- Mỗi lần bấm gọi `POST /api/robot/identify {mode}` và lấy `tcp_mm`.

**Cách 2: chọn file `robot_agent/calibration.json`.**
- Bỏ mọi khoá bắt đầu bằng `_`.
- Từ chối file nếu còn giá trị `null` hoặc chuỗi bắt đầu bằng `<`, và liệt kê các ô còn thiếu. Làm giống `robot_console.py calibrate`.

**Sau khi gửi:** hiệu chuẩn mới xoá kết quả mô phỏng cũ, nên phải làm lại bước 5–8.

### 2.7 Kiểm thử
- Chạy `serve` với `modes: ["mock","sim"]` và BE cục bộ, dùng một kỹ thuật viên có 2 robot: 1 robot có agent chạy, 1 robot không có. Dải robot phải hiện "1 / 2".
- Đi hết luồng SIM, từ bước 1 tới bước 12.
- **Không chạy robot THẬT nếu chưa có người vận hành xác nhận.**

## 3. Gỡ trang kỹ thuật viên trên web (`FE/`)
- **Gỡ:** `TechDashboard.tsx`, `PreviewOrders.tsx` (`/tech/preview`, `/tech/qc`), `JobDetail.tsx` (`/tech/jobs/:id`), cùng `RobotConsole` và `RobotView3D` nếu chỉ trang tech dùng.
- **Khi kỹ thuật viên đăng nhập web:** mọi đường dẫn `/tech*` chuyển về **một trang thông báo**: "Kỹ thuật viên làm việc tại màn hình máy trạm: `http://<máy trạm>:8765/`".
  - Có thể hiện danh sách job đọc từ `GET /technician/jobs` để tiện xem, nhưng không có nút thao tác.
- **Dọn kèm:** gỡ i18n và các script `check-technician*.mjs` của trang cũ.
- **Không đổi:** API BE `/api/v1/technician/*` vẫn giữ nguyên, vì màn desktop dùng chúng qua agent.

## 4. Chưa làm / lưu ý
- **Bỏ lớp khoá "người có mặt tại robot".** Bật REAL không còn bắt người vận hành gõ `YES` xác nhận đang đứng cạnh nút E-Stop. Màn desktop mở được từ máy khác trong cùng mạng LAN (agent nghe ở `0.0.0.0:8765`). Muốn chỉ cho mở trên chính máy trạm thì chạy `serve --host 127.0.0.1`.
- **Đồng bộ trạng thái REAL:** agent gửi `real_enabled` lên BE trong mỗi lần đồng bộ, nên Manager thấy được trạng thái này qua `live.status`. **BE không có lệnh nào bật REAL được.**
- **Thông báo in-app** (`/notifications`) chưa đi qua proxy của agent. Nếu màn desktop cần thì báo để mở thêm.
- Không có thông báo khi Manager giao hoặc thu hồi robot.
