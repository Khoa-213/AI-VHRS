# Ghi chú cho máy trạm: chạy robot thật sau đợt sửa 2026-11-27 / 28

Viết cho người vận hành và cho Claude (hoặc AI khác) đang chạy **trên máy trạm nối robot FAIRINO FR3**. Mục đích: khi một bước chạy robot bị từ chối, đọc mã lỗi, tìm đúng nguyên nhân và biết ai phải làm gì. Mọi tên trường, mã lỗi và đường dẫn dưới đây lấy từ code tại `main` `791ca0d` (2026-11-28).

Bối cảnh ngắn: ngày 2026-11-27 / 28 có một đợt audit và sửa. Kết quả là máy chủ và agent **từ chối nhiều trường hợp hơn trước**. Robot chạy được hôm 2026-11-27 không có nghĩa là hôm nay chạy được với cùng cấu hình. Lý do từng thay đổi nằm ở `BE/docs/audit/09_APPROVAL_AND_IMPLEMENTATION_PLAN.md` mục 6 và 7.

## 1. Luật cho AI trên máy trạm (không thương lượng)

1. **Không gửi lệnh làm robot thật chuyển động** (RUN, DRY_RUN, RESUME, ALIGN_START ở `mode=real`, `real-enable`) khi người vận hành đứng tại máy chưa nói rõ trong chính cuộc trò chuyện đó là cho phép. Đọc trạng thái, đọc log, chạy SIM / MOCK và chạy test thì được.
2. **Không sửa một ngưỡng an toàn để lỗi biến mất.** Cụ thể, không tự ý: hạ `z_floor_mm`, tăng `max_press_mm`, nới `watchdogs`, nới `workspace`, đặt `unsensed_gripper: true`, dùng `waive_dry_run`, đặt `require_signed_packages: false` để lách, sửa hoặc xoá `REAL_ENABLED.json`, `progress.json`, `pending_closes.json`.
3. **Không tự nghĩ ra con số đo.** Toạ độ điểm dò, `z_floor_mm`, `max_press_mm`, các ngưỡng `watchdogs`, `spring_k_n_per_mm` phải do người đo tại bàn. Thiếu số thì hỏi người vận hành, không điền số "hợp lý".
4. **Không sửa code để vượt một cổng kiểm tra.** Nếu cổng kiểm tra sai thật, ghi lại bằng chứng và báo chủ dự án.
5. **Không in secret**: `agent.json` có thể chứa `agent_key`; `BE/.env` trỏ vào database thật. Khi cần xem cấu hình, chỉ in tên trường và việc trường đó có giá trị hay không.
6. Có nguy hiểm thì người vận hành **nhấn E-Stop vật lý**. Phần mềm không thay được nút đó.
7. Báo cáo trung thực: nói rõ việc gì đã chạy thật, việc gì chỉ chạy mô phỏng, việc gì chưa chạy.

## 2. Kiểm tra trước khi chạy (chỉ đọc, không làm robot chuyển động)

### 2.0. Sau mỗi lần máy chủ được cập nhật

Khởi động lại app desktop (và agent) một lần trước khi chạy REAL. Khoá của agent cấp trước bản cập nhật có thể chưa gắn với phiên đăng nhập, và lệnh REAL sẽ bị từ chối `REAL_ONLY_AT_WORKSTATION`.

### 2.1. Máy trạm đang chạy code nào

```bash
git log --oneline -1
git merge-base --is-ancestor ef3f21a HEAD && echo "da co cac khoa moi cua agent" || echo "agent con la ban cu"
```

- **Bản cũ** (chưa có `ef3f21a`): mục 2.3 chưa áp dụng cho agent, nhưng mục 2.2 (máy chủ) vẫn áp dụng. Bản cũ tương thích với máy chủ mới.
- **Bản mới**: áp dụng tất cả.

### 2.2. Máy chủ (Render deploy từ `main`)

| Kiểm | Cách | Nếu sai |
|---|---|---|
| Máy chủ sống | `GET <backend_url>/api/v1/health` trả `{"status":"ok"}` | Chờ deploy xong; xem log Render |
| Không còn cảnh báo đỏ mở trên robot | Web Manager, màn "Robot và cảnh báo" | Manager đóng cảnh báo kèm ghi chú sau khi kiểm robot |
| Robot không ở `MAINTENANCE` / `BROKEN` | Web Manager, danh mục robot | Manager đổi trạng thái |
| Không còn lần chạy treo | Web Manager, chi tiết job: khối "Lần chạy còn mở trên máy chủ" | Nút "Đóng lần chạy treo" (cần lý do) |
| Đơn test cọc bằng cổng mô phỏng / sandbox | Biến `ALLOW_TEST_PAYMENTS` trên Render | Đặt `true` trên bản demo. Mặc định là `false` |

### 2.3. `agent.json` (cùng thư mục với file này; mẫu ở `agent.example.json`)

| Trường | Yêu cầu cho REAL | Lỗi khi thiếu |
|---|---|---|
| `modes` | có `"real"` | `MODE_DISABLED` |
| `fairino` | `ip`, `tool_id`, `orientation_deg`, `servo_cmd_period_s` | `REAL_NOT_CONFIGURED`, `ROBOT_UNREACHABLE`, `ROBOT_CONFIG_MISMATCH` |
| `watchdogs` | đủ 5 số: `stop_settle_s`, `stop_window_s`, `stop_tolerance_mm`, `tracking_tolerance_mm`, `tracking_grace_s`; mỗi số > 0; thời gian ≤ 10 giây, khoảng cách ≤ 10 mm | `WATCHDOG_UNCONFIGURED` (kèm danh sách số sai) |
| `station_limits` | `{"z_floor_mm": <số>, "max_press_mm": <số > 0>}` | `STATION_LIMITS_UNCONFIGURED` |
| `production_public_keys` | khoá công khai của máy chủ (`BE/scripts/production_key.py public`) | `PRODUCTION_KEY_MISSING` |
| `gripper_port` **hoặc** `unsensed_gripper: true` | chủ dự án đã chọn một trong hai | `GRIPPER_NOT_CONFIGURED`, `GRIPPER_REQUIRED` |

`station_limits` là mục mới và dễ thiếu nhất, vì file mẫu để `null`:

- `z_floor_mm`: độ cao thấp nhất (mm, hệ BASE của robot) mà đầu bút được phép tới, ngay dưới mặt giấy trên bàn này. Kế hoạch đưa bút xuống thấp hơn số này thì bị từ chối (`BELOW_Z_FLOOR`). Điểm thấp nhất của kế hoạch xấp xỉ bằng độ cao mặt giấy thấp nhất trừ đi độ nén lò xo, nên số này phải thấp hơn mức đó một chút và cao hơn mặt bàn.
- `max_press_mm`: độ nén lò xo lớn nhất cho phép, nhỏ hơn hành trình của gripper. Độ nén trong kế hoạch = `f_target_n` của bút chia `spring_k_n_per_mm` trong `calibration.json`; lớn hơn `max_press_mm` thì bị từ chối (`PRESS_ABOVE_STATION_LIMIT`).

Hai số này do người đo. AI không điền thay.

### 2.4. `calibration.json` (mẫu ở `calibration.example.json`)

| Yêu cầu | Lỗi khi sai |
|---|---|
| `probe_points` có **ít nhất 4 điểm**: P0 góc trên trái, P1 góc trên phải, P2 góc dưới trái, P3 góc dưới phải (điểm kiểm tra) | `PROBE_CHECK_POINT_REQUIRED` |
| P0, P1, P2 đúng thứ tự (không lật gương) | `PROBE_ORDER_MIRRORED` |
| Có khối `frame_transform` với `"schema": "vhrs-motion/1"`, `motion` và `workspace` (`box_min_mm`, `box_max_mm`) | Máy chủ: `SERVER_VALIDATION_REQUIRED`. Agent: `START_OUTSIDE_WORKSPACE`, `VALIDATION_FAILED` |
| `checklist` chỉ đặt `true` khi việc đó đã làm thật | `CHECKLIST_INCOMPLETE` |

Sau khi gửi hiệu chuẩn mới lên máy chủ phải **ghi lại kết quả mô phỏng**; kết quả cũ bị coi là hết hạn (`SIMULATION_STALE`).

## 3. Mã lỗi: nguyên nhân và việc cần làm

Cột "Ai": **VH** = người vận hành tại máy, **QL** = Manager trên web, **AI** = AI được làm (chỉ việc đọc, kiểm, giải thích), **CDA** = chủ dự án.

### 3.1. Cổng REAL của agent

| Mã | Nguyên nhân | Việc cần làm | Ai |
|---|---|---|---|
| `REAL_ONLY_AT_WORKSTATION` (từ máy chủ) | Lệnh REAL không đến từ đúng phiên đăng nhập của app đã khởi động agent (chủ dự án chốt 2026-11-28: robot thật chỉ được khởi động từ máy trạm). Hay gặp nhất **ngay sau khi máy chủ được cập nhật**: khoá cũ của agent chưa gắn phiên | Tại máy trạm: đăng xuất, đăng nhập lại app desktop và khởi động lại agent. Nếu đang ngồi ở máy khác: tới máy trạm | VH |
| `REAL_ONLY_AT_WORKSTATION` (từ agent) | Bật REAL, chạy REAL, "Tiếp tục" hoặc "đã thay giấy" của lần chạy REAL được gọi từ máy khác, hoặc qua reverse proxy | Thao tác trên chính máy trạm | VH |
| `BACKEND_UNREACHABLE` kèm `RUN_REPORT_AGENT_ONLY` | Agent không có khoá của agent, nên máy chủ không nhận bản ghi lần chạy (từ 2026-11-28 lần chạy chỉ do agent báo bằng khoá của nó) | Chạy agent từ app desktop (app cấp khoá phiên), hoặc đặt `VHRS_AGENT_KEY` do Manager cấp rồi khởi động lại agent | VH, QL |
| `MODE_DISABLED` | `agent.json` không có `"real"` trong `modes` | Thêm `"real"` chỉ trên máy nối robot, khởi động lại agent | VH |
| `REAL_NOT_ENABLED_ON_SITE` | Chưa bật REAL cho đúng job này, hoặc đã hết hạn | Bấm "Bật REAL" cho job trên màn máy trạm / app desktop | VH |
| `AUTHORIZATION_REQUIRED` | Thiếu hoặc sai mã `AUTHORIZE-<job>-<kế hoạch>`. Mã đổi khi gói job hoặc hiệu chuẩn đổi | Nạp lại job để lấy mã mới | VH |
| `DRY_RUN_REQUIRED` | Chưa chạy thử nhấc bút bằng robot **thật** cho đúng kế hoạch này (chạy thử SIM không tính) | Chạy thử REAL trước, rồi mới viết | VH |
| `STATION_LIMITS_UNCONFIGURED` | Thiếu `station_limits` | Mục 2.3 | VH đo, điền |
| `WATCHDOG_UNCONFIGURED` | Thiếu hoặc sai ngưỡng `watchdogs` | Mục 2.3; chi tiết lỗi liệt kê từng số | VH đo, điền |
| `PACKAGE_NOT_SIGNED` | Gói job không có chữ ký. Robot thật không viết gói không ký, dù `require_signed_packages` là gì | QL xếp lịch lại job để phát hành gói ký | QL |
| `PRODUCTION_KEY_MISSING` | Máy trạm chưa có khoá công khai | Điền `production_public_keys` | VH, CDA |
| `PRODUCTION_PACKAGE_INVALID`, `JOB_HASH_MISMATCH` | Gói không khớp bản đã ký. **Không chạy** | Báo QL; không tìm cách vượt | QL, CDA |
| `GRIPPER_REQUIRED`, `GRIPPER_NO_DATA`, `GRIPPER_UNCALIBRATED`, `GRIPPER_ZERO_DRIFT` | Viết cần dữ liệu lực mà gripper không cho | Kiểm cổng và hiệu chuẩn gripper. Dùng gripper lò xo không cảm biến là quyết định của chủ dự án (`unsensed_gripper`), AI không tự bật | VH, CDA |
| `ROBOT_NOT_READY`, `ROBOT_UNREACHABLE` | Robot không trả lời, đang lỗi hoặc đang dừng khẩn | Kiểm nguồn, cáp mạng, IP, trạng thái trên pendant | VH |
| `ROBOT_CONFIG_MISMATCH` | Robot có trả lời nhưng tool / hệ toạ độ không khớp `fairino` trong `agent.json` | Sửa cấu hình cho khớp robot, không sửa robot cho khớp file | VH |
| `CONTROLLER_BUSY`, `AGENT_BUSY` | Agent đang chạy việc khác, hoặc một tiến trình agent khác đang giữ robot | Chờ, hoặc tắt tiến trình thừa | VH |

### 3.2. Hiệu chuẩn và kế hoạch

| Mã | Nguyên nhân | Việc cần làm | Ai |
|---|---|---|---|
| `PROBE_CHECK_POINT_REQUIRED` | Dưới 4 điểm dò | Dò thêm P3 (góc dưới phải) | VH |
| `PROBE_ORDER_MIRRORED` | P1 và P2 bị đổi chỗ: chữ sẽ bị soi gương | Kiểm lại P1, P2, hiệu chuẩn lại | VH |
| `BELOW_Z_FLOOR` | Kế hoạch (hoặc thao tác gắn bút ở góc giấy) xuống thấp hơn `z_floor_mm` | Gần như luôn là **điểm dò nhập sai độ cao**. Kiểm lại z của các điểm dò trước. Không hạ `z_floor_mm` | VH |
| `PRESS_ABOVE_STATION_LIMIT` | Độ nén lò xo trong kế hoạch lớn hơn `max_press_mm` | Kiểm `spring_k_n_per_mm` và `f_target_n` của bút. Không tăng `max_press_mm` khi chưa đo | VH |
| `START_OUTSIDE_WORKSPACE` | Vị trí hiện tại hoặc điểm đến nằm ngoài `workspace` | Đưa robot về tư thế khởi đầu bằng jog tại máy; kiểm `box_min_mm`, `box_max_mm` | VH |
| `START_POSE_UNSAFE` | Đầu bút đang thấp hơn độ cao nhấc bút | Nhấc bút lên bằng jog | VH |
| `VALIDATION_FAILED`, `NOT_REACHABLE` | Quỹ đạo không qua kiểm chứng hoặc ngoài tầm với | Đọc danh sách lỗi kèm theo; thường do điểm dò hoặc `workspace` | VH, AI giải thích |
| `PLAN_CHANGED` | Gói job hoặc hiệu chuẩn đổi trong khi tờ giấy đang viết dở | Giấy mới, rồi "Đặt lại tiến độ" | VH |

### 3.3. Máy chủ từ chối

| Mã | Nguyên nhân | Việc cần làm | Ai |
|---|---|---|---|
| `SERVER_VALIDATION_REQUIRED` | Lần viết REAL cần máy chủ tự kiểm quỹ đạo và đạt. `details.server_validation` là `NOT_RUN` (hiệu chuẩn thiếu `frame_transform`) hoặc `FAIL` | Gửi hiệu chuẩn có khối `frame_transform`, ghi lại mô phỏng | VH |
| `SIMULATION_STALE`, `SIMULATION_REQUIRED`, `SIMULATION_FAILED` | Mô phỏng chưa có, không đạt, hoặc cũ hơn hiệu chuẩn | Ghi lại mô phỏng sau hiệu chuẩn | VH |
| `RED_ALERT_OPEN` | Robot còn cảnh báo mức 4 chưa đóng | QL kiểm robot rồi đóng cảnh báo trên web | QL |
| `ROBOT_UNAVAILABLE` | Robot đang `MAINTENANCE` / `BROKEN` | QL đổi trạng thái | QL |
| `ROBOT_BUSY` | Máy chủ còn giữ một lần chạy mở của robot này | Mục 4.2 | VH, QL |
| `JOB_STATE_CONFLICT` | Job chưa ở đúng bước (ví dụ gửi RUN khi chưa "Bắt đầu viết") | Làm đúng thứ tự bước | VH |
| `STOCK_NOT_ISSUED` | Chưa xuất giấy cho job trước bước Chuẩn bị | Xuất kho giấy | VH |
| `AGENT_OFFLINE` | Máy chủ không thấy agent sync | Kiểm agent đang chạy, mạng, `backend_url`, khoá agent | VH |
| `ROBOT_IN_USE` | Kỹ thuật viên khác đang giữ robot | Chờ hoặc nhờ người đó nhả | VH |
| `AGENT_ACCOUNT_INACTIVE`, 401 | Tài khoản kỹ thuật viên bị khoá, hoặc khoá agent hết hạn | Admin / QL; đăng nhập lại | QL |

### 3.4. "Viết xong" và số bản

| Mã | Nguyên nhân | Việc cần làm | Ai |
|---|---|---|---|
| `RUN_EVIDENCE_REQUIRED` | Chưa có lần chạy nào được tính là một bản. Trên robot thật **chỉ lần chạy REAL kết thúc `DONE` mới được tính**; lần chạy SIM / MOCK không được tính (`details.simulated_runs_not_counted` cho biết có bao nhiêu lần như vậy) | Cho robot viết xong; nếu đã viết mà không báo về được thì QL "Ghi nhận viết xong thay" | VH, QL |
| `COPIES_MISSING` | Đơn cần N bản, robot mới xong k bản (`details`) | Mục 4.1 | VH |
| `RUN_OPEN` | Còn lần chạy mở. `details.orphan` cho biết có ai đang chạy nó không | `orphan: false`: chờ hoặc dừng robot. `orphan: true`: mục 4.2 | VH, QL |
| `RESULT_INVALID` | Đóng lần chạy `DONE` mà số nét khác tổng số nét | Lần chạy dở phải là `STOPPED`, `FAULT` hoặc `UNKNOWN` | AI giải thích |
| `JOB_ALREADY_WRITTEN` | Agent thấy job đã viết xong trên tờ giấy này | Bản tiếp theo: mục 4.1. Không phải lỗi | VH |
| `PARTIAL_JOB_EXISTS` | Đã viết dở k nét | Người vận hành xem tờ giấy rồi chọn viết lại nét dở hoặc bỏ qua | VH |
| `OUTCOME_UNKNOWN` | Lần chạy trước kết thúc không rõ (mất kết nối, agent tắt đột ngột) | Người vận hành kiểm tờ giấy rồi xác nhận | VH |

### 3.5. Lệnh gửi qua máy chủ

| Hiện tượng | Nghĩa | Việc cần làm |
|---|---|---|
| Lệnh `FAILED` với `error_code: NO_ANSWER` | Agent đã nhận lệnh nhưng không báo kết quả trong 30 giây (PAUSE, RESUME, STOP) hoặc 300 giây (lệnh khác). **Chưa biết lệnh có được thực hiện không** | Nhìn robot. Không gửi lại lệnh chạy cho tới khi biết robot đang ở đâu. Xem log agent |
| Lệnh `EXPIRED` | Agent không lấy lệnh kịp hạn | Kiểm agent đang chạy và mạng |
| `IDEMPOTENCY_KEY_REUSED` | Gửi lại cùng khoá với tham số khác | Mỗi lần bấm dùng một khoá mới |

## 4. Các tình huống thường gặp

### 4.1. Đơn nhiều bản

Một lần chạy viết **một bản**. Agent không tự lặp. Máy chủ đếm số lần chạy `DONE` và chỉ cho "Viết xong" khi đủ số bản. Trên robot thật chỉ lần chạy REAL được đếm (chủ dự án chốt 2026-11-28); lần chạy SIM / MOCK chỉ được đếm trên robot Manager gắn cờ mô phỏng.

1. Robot viết xong bản 1 (`DONE`). Màn máy trạm hiện "Robot đã viết xong 1/N bản".
2. Đặt tờ giấy mới, kẹp đúng vị trí cũ.
3. Mở "Đặt lại tiến độ", xác nhận giấy mới (`POST /api/jobs/{id}/reset-progress {"confirm":"NEW_SHEET"}`).
4. Chạy lại. Lặp cho tới khi đủ N.
5. Bấm "Viết xong".

Kênh làm việc chính của kỹ thuật viên là app desktop Flutter chạy trên máy trạm (chủ dự án chốt 2026-11-28); trang `http://<máy trạm>:8765/` do agent phục vụ là đường dự phòng. App desktop chưa có nút "giấy mới" (tính tới 2026-11-28), nên bước 3 tạm làm trên trang dự phòng đó.

### 4.2. Lần chạy treo (mất mạng lúc robot kết thúc)

- Agent bản mới giữ kết quả lần chạy ở `runs/pending_closes.json` và tự gửi lại sau mỗi lần sync thành công, kể cả sau khi agent khởi động lại. **Việc đầu tiên là chờ agent kết nối lại**, không xoá file này.
- Nếu vẫn treo: kỹ thuật viên dùng "Đóng lần chạy treo" trên trang máy trạm, hoặc QL dùng nút cùng tên trên web (chi tiết job). Cần lý do ít nhất 10 ký tự. Kết quả ghi là `UNKNOWN`.
- Bị từ chối `RUN_STILL_ACTIVE`: máy trạm còn báo robot đang chạy. Dừng robot trước.
- Lần chạy đóng `UNKNOWN` không được tính là một bản đã viết. Nếu sau đó agent gửi được kết quả thật, kết quả thật thay cho `UNKNOWN`.

### 4.4. Job hỏng hoặc bị huỷ mà còn giữ giấy đã xuất

Giấy đã xuất cho job chỉ tự trả về kho ở bước "Viết xong", hoặc khi job bị huỷ lúc chưa chuẩn bị. Job đã bắt đầu rồi báo sự cố (hoặc bị huỷ giữa chừng) vẫn giữ số giấy đó cho tới khi có người quyết toán: đếm số tờ đã hỏng, phần còn lại trả về kho. Kỹ thuật viên gọi `POST /api/technician/jobs/{id}/stock/settle {"waste": <số tờ hỏng>}` (qua proxy của agent); Manager có nút "Quyết toán giấy" trên web ở chi tiết job. Mỗi job chỉ quyết toán một lần.

### 4.3. Thao tác gắn bút ở góc giấy (hạ đầu bút xuống mặt giấy)

Ở REAL, thao tác này qua cùng các khoá của máy trạm như một lần chạy: `station_limits`, 4 điểm dò, không lật gương, mặt giấy không thấp hơn `z_floor_mm`. Lỗi tra ở mục 3.1 và 3.2.

## 5. Bằng chứng nằm ở đâu

| Cần biết | Nơi xem |
|---|---|
| Agent đang ở chế độ nào, có bận không, REAL có bật không | `GET http://127.0.0.1:8765/api/agent`, `GET /api/real` |
| Vì sao kiểm tra trước bị từ chối, không làm robot chuyển động | `POST /api/jobs/{id}/preflight` |
| Nhật ký lần chạy gần nhất của job | `GET /api/jobs/{id}/log?tail=200`, hoặc file `runs/job<id>/run-*.jsonl` (dòng `preflight_fail`, `bridge_error`, `alert`, `run_end`) |
| Tờ giấy đã viết tới nét nào | `runs/job<id>/progress.json` (`state`, `completed`, `interrupted`, `dry_run_ok`) |
| Kết quả lần chạy đang chờ gửi | `runs/pending_closes.json` |
| REAL đang bật cho job nào, tới khi nào | `runs/REAL_ENABLED.json` |
| Máy chủ thấy job thế nào | `GET /api/technician/jobs/{id}` qua proxy của agent: `status`, `copies_written`, `quantity`, `open_run`, `simulation_passed`, `calibration` |
| Lệnh đã gửi cho job | `GET /api/technician/jobs/{id}/robot-commands` |

Các route `/api/...` của agent cần đăng nhập bằng tài khoản kỹ thuật viên. Thư mục `runs/` là `run_dir` trong `agent.json`.

## 6. Thứ tự chẩn đoán gợi ý cho AI

1. Hỏi người vận hành: đang làm bước nào, màn hình báo mã lỗi gì, robot đang đứng yên hay đang chạy.
2. Mục 2.1: máy trạm chạy bản code nào.
3. Tra mã lỗi ở mục 3. Nếu mã không có trong bảng, tìm trong code: `grep -rn "<MÃ>" robot_agent/vhrs_agent BE/app`.
4. Đọc bằng chứng ở mục 5 (chỉ đọc).
5. Chạy lại đúng job ở **SIM** để tách lỗi cấu hình REAL khỏi lỗi của job. SIM qua mà REAL bị từ chối thì nguyên nhân nằm ở mục 3.1 hoặc 3.2.
6. Nói rõ cho người vận hành: nguyên nhân, việc cần làm, ai làm, và số nào cần đo. Sửa file cấu hình chỉ sau khi người vận hành đưa số đo và đồng ý.
7. Nghi là lỗi phần mềm: chạy test của agent (không cần robot) rồi báo chủ dự án kèm log.

```bash
# trong robot_agent/, không chạm robot thật
python -m pytest -q --deselect tests/test_server_api.py::test_waiting_for_a_process_returns_when_it_ends
```

Test bị bỏ qua ở trên treo vô hạn trên macOS và Linux (lỗi đã biết, không liên quan tới robot).

## 7. Những điều chưa được kiểm chứng (đừng coi là đã chạy)

- Các khoá mới của agent mới chạy với robot mô phỏng và robot giả trong test. **Chưa lần nào chạy trên FR3 thật.** Lần chạy thật đầu tiên sau khi cập nhật phải có người đứng cạnh E-Stop.
- `station_limits` và 4 điểm dò chưa từng được đặt trên máy trạm thật tính tới 2026-11-28.
- Gripper lò xo không cảm biến lực: phần mềm không phát hiện được quá lực hay mất tiếp xúc. Bỏ chạy thử (`waive_dry_run`) là ngoại lệ có ghi nhật ký, không phải cách làm thường ngày.
- App desktop chưa có câu chữ cho các mã mới (`COPIES_MISSING`, `SERVER_VALIDATION_REQUIRED`, `PACKAGE_NOT_SIGNED`, `NO_ANSWER`, `RUN_STILL_ACTIVE`): app có thể chỉ hiện mã hoặc câu tiếng Việt của máy chủ.
