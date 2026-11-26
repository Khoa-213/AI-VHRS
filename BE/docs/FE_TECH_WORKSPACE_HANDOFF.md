# Bàn giao FE: giao robot cố định + một nơi làm việc cho kỹ thuật viên

Ngày 2026-11-26. **BE đã xong** (migration 0032, xem `FE_API_GUIDE.md` mục 7.3 và 7b.0). Tài liệu này là **việc FE cần làm**.
Schema chi tiết: Swagger `/docs`, nhóm *Scheduling*, *Technician*, *Robot operations*.

## 0. Thay đổi nghiệp vụ (đọc trước)

| Trước | Bây giờ |
|---|---|
| Manager chọn **robot + kỹ thuật viên + giờ** cho từng job | Manager **giao cố định** robot cho kỹ thuật viên (mỗi robot thuộc tối đa 1 người, 1 người giữ nhiều robot) |
| Lịch luôn có robot | Manager xếp lịch cho **kỹ thuật viên + giờ**; robot **tuỳ chọn** (phải là robot của người đó) |
| Kỹ thuật viên chỉ thấy robot có job của mình | Kỹ thuật viên thấy **đúng các robot được giao**, kể cả khi chưa có job |
| — | Kỹ thuật viên **tự chọn robot** cho job trước khi bấm Chuẩn bị |

`JobOut.robot_id` giờ có thể là `null` (`robot_code = ""`): mọi chỗ đang hiện mã robot của job phải xử lý trường hợp này
("Chưa chọn robot"). Kiểu `TechJob` / `Job` trong `FE/src/services/technician.ts` và màn lịch cần `robotId: number | null`.

## 1. Manager

### 1.1 Màn Robot (`FE/src/pages/staff/Robots.tsx`, route `/staff/robots`)
- Thêm cột / ô **"Kỹ thuật viên phụ trách"** cho mỗi robot: đọc `technician_id`, `technician_name` từ `GET /manager/robots`.
- Ô chọn kỹ thuật viên (danh sách từ `GET /manager/technicians`), lưu bằng `PUT /manager/robots/{id}/technician {technician_id}`;
  nút "Thu hồi" gọi `DELETE /manager/robots/{id}/technician`. Cả hai trả `RobotOut` mới.
- Lỗi: `409 ROBOT_HAS_ACTIVE_JOBS` → "Robot còn job chưa xong của <tên>: xếp lại các job này trước" và liệt kê `details.job_ids`
  (link sang lịch). `422 INVALID_TECHNICIAN`, `404 ROBOT_NOT_FOUND`.
- Gợi ý hiển thị thêm: ở trang kỹ thuật viên (nếu có) hiện `robots[]` của `GET /manager/technicians`.

### 1.2 Màn xếp lịch (`Schedule.tsx`, `ScheduleCalendar.tsx`, route `/staff/schedule`)
- Thứ tự chọn: **kỹ thuật viên trước**, rồi giờ, rồi robot (tuỳ chọn). Ô robot chỉ liệt kê `robots[]` của kỹ thuật viên đã chọn
  (từ `GET /manager/technicians`), có lựa chọn mặc định **"Để kỹ thuật viên tự chọn"** (không gửi `robot_id`).
- Kỹ thuật viên chưa có robot nào: hiện cảnh báo và link sang màn Robot (BE sẽ trả `422 TECHNICIAN_HAS_NO_ROBOT`).
- Gợi ý lịch: mỗi kỹ thuật viên **một** gợi ý kèm robot của họ; khi bấm áp dụng gợi ý, có thể gửi hoặc bỏ `robot_id`.
- Đổi lịch: gửi `technician_id` khác thì robot cũ bị bỏ nếu không thuộc người mới (BE trả job mới `robot_id = null`).
- Lịch / calendar: job chưa có robot hiện ở hàng của **kỹ thuật viên** (không có hàng robot), nhãn "Chưa chọn robot".
- Lỗi mới: `422 ROBOT_NOT_ASSIGNED`, `422 TECHNICIAN_HAS_NO_ROBOT`, `409 SLOT_CONFLICT` (`details.resource = "robot"`:
  "Không robot nào của <tên> rảnh khung giờ này").

## 2. Kỹ thuật viên: một nơi làm việc duy nhất (`/tech`)

Gộp `TechDashboard.tsx`, `PreviewOrders.tsx` (`/tech/preview`, `/tech/qc`) và `JobDetail.tsx` (`/tech/jobs/:id`) thành **một trang**.
Đường dẫn cũ chuyển về `/tech?job=<id>` (giữ link trong thông báo / email hoạt động).

### 2.1 Bố cục
```
┌──────────────────────────────────────────────────────────────────────────────┐
│ Robot của tôi: Đang kết nối 2 / 3 · Đang hoạt động 1                          │
│ [FR3-01 ● Kết nối · Đang viết 45% · SIM/REAL] [FR3-02 ● Kết nối · Sẵn sàng]   │
│ [FR3-03 ○ Mất kết nối · Bảo trì]                                              │
├───────────────────────┬──────────────────────────────────────────────────────┤
│ Job của tôi           │ Job VHRS-xxxx (đang chọn)                            │
│  Đang viết (1)        │  ① Tải gói ② Chọn robot ③ Chuẩn bị ④ Hiệu chuẩn ...  │
│  Sẵn sàng (2)         │  [bước hiện tại + lý do bước sau bị khoá]             │
│  Chờ QC (1)           │  [Điều khiển robot + 3D khi đang chạy]               │
│  Cần chú ý / Lịch sử  │  [Ảnh + QC khi đã viết xong]                         │
└───────────────────────┴──────────────────────────────────────────────────────┘
```

### 2.2 Dải robot (yêu cầu chính của chủ dự án)
- Nguồn: **`GET /technician/robots`** → `{total, online, active, robots[]}`. Chỉ robot Manager giao cho người đang đăng nhập.
- Dòng tổng: **"Đang kết nối {online} / {total} · Đang hoạt động {active}"**.
- Mỗi thẻ robot:
  - `robot_code`, `station`;
  - chip kết nối theo `connection_state`: `ONLINE` = "Đã kết nối", `OFFLINE` = "Mất kết nối", `UNKNOWN` = "Chưa từng kết nối";
  - trạng thái theo `state` + `headline_vi` (IDLE, PREPARING, WRITING, PAUSED_SAFE, DANGER, OFFLINE); `active = true` → nhấn mạnh "Đang hoạt động";
  - `robot_status` khác AVAILABLE/BUSY → nhãn "Bảo trì" / "Hỏng";
  - `enabled_modes` (MOCK / SIM / REAL), `agent_busy`, `job_id` + `job_status` (link mở job), mức cảnh báo `level` và `open_alerts`.
  - `level >= 4` → banner đỏ "BẤM NÚT E-STOP NGAY" trên đầu trang (như hiện có).
- Làm mới: 5 giây khi có robot `active` hoặc `level >= 3`, còn lại 15 giây; tạm dừng khi tab ẩn. Bấm thẻ → lọc danh sách job theo robot.
- Thay `useRobotStatus()` (đang gọi `/technician/robot-status`) bằng nguồn này ở trang `/tech`; chuông cảnh báo giữ nguyên.

### 2.3 Danh sách job (cột trái)
- `GET /technician/jobs` (như `allTechJobs`), nhóm: Đang viết (WRITING, PAUSED) · Sẵn sàng (SCHEDULED, PREPARING) · Chờ QC (WRITTEN)
  · Cần chú ý (FAILED, REWRITE_REQUIRED) · Lịch sử (PHOTO_UPLOADED, DONE, CANCELLED).
- Mỗi dòng: mã đơn, giờ, robot (hoặc "Chưa chọn robot"), trạng thái, tiến độ.

### 2.4 Quy trình một job (cột phải), theo thứ tự
| # | Bước | Gọi | Khi nào xong / mở khoá |
|---|---|---|---|
| 1 | Tải gói + kiểm hash | `GET /technician/jobs/{id}/package` (như `downloadJobPackage`) | `downloaded_at` có giá trị và hash khớp trong trình duyệt |
| 2 | **Chọn robot (mới)** | `PUT /technician/jobs/{id}/robot {robot_id}` | `robot_id` khác null. Chỉ khi job `SCHEDULED`. Liệt kê robot từ dải robot; làm mờ robot `MAINTENANCE`/`BROKEN`, robot không hợp loại bút (so `supported_pen_categories` với bút của job), và cảnh báo (không chặn) robot đang mất kết nối |
| 3 | Chuẩn bị | `POST /technician/jobs/{id}/prepare` | `PREPARING` |
| 4 | **Hiệu chuẩn (mới trên web)** | `POST /technician/jobs/{id}/calibration` | `calibration.is_valid` (xem 2.5) |
| 5 | Nạp job | lệnh `LOAD` | lệnh DONE, lưu `authorization_token` |
| 6 | Bật REAL tại máy trạm | **không có API** (an toàn) | hiện hướng dẫn + nút sao chép lệnh `real-enable --config agent.json --job {id} --minutes 30` |
| 7 | Kiểm tra trước | lệnh `PREFLIGHT` | `ok` |
| 8 | Ghi kết quả mô phỏng | `POST /technician/jobs/{id}/simulation` (như `recordSimulation` hiện có) | `simulation_passed = true` |
| 9 | Chạy thử nhấc bút | lệnh `DRY_RUN` + mã `AUTHORIZE-…` | `DRY_RUN_DONE` |
| 10 | Bắt đầu viết + Viết | `POST .../start`, rồi lệnh `RUN` | `WRITING`, tiến độ chạy |
| 11 | Viết xong | `POST .../finish` | `WRITTEN` |
| 12 | Ảnh + QC + Gửi khách | như `JobPhotos.tsx` | `PHOTO_UPLOADED` |

- Bước đã xong có dấu ✓; bước bị khoá ghi **lý do** (dùng mã lỗi BE, ví dụ `ROBOT_NOT_SELECTED`, `JOB_NOT_DOWNLOADED`).
- Khi job `WRITING`/`PAUSED`: các nút Tạm dừng / Tiếp tục / DỪNG và 3D **luôn ghim** trong tầm nhìn (tái dùng `RobotConsole.tsx`, `RobotView3D.tsx`).
- Lỗi mới cần câu chữ: `ROBOT_NOT_SELECTED` ("Hãy chọn robot cho job"), `ROBOT_NOT_FOUND` khi chọn robot ("Robot này không được giao cho bạn"),
  `ROBOT_UNAVAILABLE`, `ROBOT_NOT_SUITABLE`, `SLOT_CONFLICT` ("Robot đã có job khác giờ này").

### 2.5 Form hiệu chuẩn (bước 4)
Body `POST /technician/jobs/{id}/calibration` (Swagger: `CalibrationIn`):
`{checklist: {frame_mounted, paper_clamped, pen_installed, force_zeroed: true}, force_zero_offset, probe_points: [{x,y,z} ≥ 3, P0 P1 P2 không thẳng hàng], frame_transform?, height_map?, force_curve?}`.
- Cách chính: **chọn file `calibration.json`** của máy trạm (`robot_agent/calibration.json`). Làm giống `robot_console.py calibrate`:
  bỏ mọi khoá bắt đầu bằng `_` (ghi chú cho người), **từ chối** nếu còn giá trị `null` hoặc chuỗi bắt đầu bằng `<` (chưa đo) và liệt kê
  đường dẫn các ô thiếu; còn lại gửi nguyên.
- Cách phụ: nhập tay 4 ô checklist + `force_zero_offset` + 3 điểm P0–P2 (`frame_transform` để trống).
- Gửi hiệu chuẩn mới **xoá kết quả mô phỏng cũ**: báo người dùng phải làm lại bước 7–8.

### 2.6 i18n, kiểm thử
- Thêm câu chữ vi / en / ja, chạy `npm run i18n:check`.
- Cập nhật `scripts/check-technician.mjs` / `check-technician-browser.mjs` theo trang mới.
- Kiểm trên trình duyệt với BE cục bộ: một kỹ thuật viên có 2 robot (1 có agent SIM chạy, 1 không) → dải robot hiện "1 / 2".

## 3. BE chưa làm (để biết, không chặn FE)
- **Trạng thái "đã bật REAL" của máy trạm** chưa được agent báo lên BE, nên bước 6 chỉ hiện hướng dẫn, chưa tự đánh dấu xong.
  Muốn có: agent gửi thêm `real_enabled {job_id, expires_at}` trong trạng thái đồng bộ (sửa `robot_agent/vhrs_agent/link.py`) và BE trả
  ra trong `live.status`; cần chủ dự án duyệt.
- Không có thông báo (in-app/email) khi Manager giao / thu hồi robot (loại thông báo là enum trong DB, cần migration riêng).
