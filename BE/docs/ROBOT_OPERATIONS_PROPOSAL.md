# Đề xuất: hệ thống điều khiển và quản lý robot hoàn chỉnh (nhật ký, cảnh báo E-Stop, mô phỏng 3D)

Ngày 2026-10-23. **Cập nhật cùng ngày: chủ dự án đã duyệt migration 0008, cảnh báo đỏ báo cho Technical Staff trên màn hình + email, người xem từ xa được bấm DỪNG phần mềm (vẫn có nút E-Stop vật lý), camera để sau. Phần cảnh báo/nhật ký/tuân thủ/DB/API/agent đã làm (xem `ROBOT_INTEGRATION.md` mục 10b); bản sao số 3D chờ quyết định tải URDF/STL.** Chủ dự án đã cho phép: thay đổi DB cần thiết thì áp thẳng lên Supabase và ghi vào `database/AI-VHRS_database_full.sql`
(làm theo quy trình ở `PROJECT_STATUS.md` mục 2: thử trên DB cục bộ, kiểm trước/sau, áp dụng, tạo lại script, báo lại; không xoá hay sửa dữ liệu thật).

## 1. Nguyên tắc: bốn mức, một câu hỏi duy nhất cho người vận hành

Technical Staff không cần hiểu robot, chỉ cần biết "tôi phải làm gì bây giờ". Mọi sự kiện kỹ thuật được dịch thành 4 mức, mỗi mức có câu tiếng Việt cố định, việc cần làm và người được báo:

| Mức | Màu | Nghĩa | Việc của người vận hành |
|---|---|---|---|
| 1 | Xanh | chạy bình thường | không cần làm gì |
| 2 | Vàng | chú ý, vẫn chạy được | xử lý trong lúc rảnh (ví dụ hiệu chuẩn đã cũ) |
| 3 | Cam | **robot đã tự dừng an toàn** | xem tờ giấy/bút, rồi chọn tiếp tục hoặc bỏ qua nét dở; không tự chạy lại từ đầu |
| 4 | Đỏ + còi | **BẤM E-STOP NGAY** | bấm nút dừng khẩn vật lý trước, giải thích sau |

Phần mềm không bấm được E-Stop. Mức đỏ chỉ dành cho tình huống phần mềm **không chắc robot đã dừng hoặc không còn kiểm soát được**; mức cam là khi phần mềm đã dừng được và biết chắc.

## 2. Danh mục cảnh báo (mỗi dòng là một mã trong DB, câu chữ do Manager chỉnh được)

Các ngưỡng ghi "(đo)" là đề xuất, chỉ được bật sau khi nhóm đo trên robot thật.

| Mã | Mức | Câu hiển thị cho Technical Staff | Phát hiện bằng | Ai được báo |
|---|---|---|---|---|
| `STOP_NOT_EFFECTIVE` | 4 | Đã gửi lệnh dừng nhưng đầu bút vẫn đang di chuyển. Bấm E-Stop ngay. | sau lệnh dừng, vị trí TCP vẫn đổi quá (đo) mm trong (đo) ms | Tech + Manager |
| `LINK_LOST_MOVING` | 4 | Mất kết nối với robot khi đang chạy. Nếu robot còn chuyển động, bấm E-Stop. | mất phản hồi giữa lệnh | Tech + Manager |
| `TRACKING_ERROR` | 4 | Đầu bút lệch xa đường đã định. Bấm E-Stop. | so vị trí thật (`GetActualTCPPose`) với vị trí vừa ra lệnh > (đo) mm | Tech + Manager |
| `CONTROLLER_SAFETY_FAULT` | 4 | Robot báo lỗi an toàn/va chạm trong lúc di chuyển. | mã lỗi controller ≠ 0 mà vị trí vẫn đổi | Tech + Manager |
| `OVER_FORCE_STILL` | 4 | Lực vẫn vượt giới hạn dù đã dừng. Bấm E-Stop. | lực > F_hard sau lệnh dừng | Tech + Manager |
| `OVER_FORCE` | 3 | Bút ép quá mạnh, robot đã tự dừng. | lực > F_hard (đã có) | Tech + Manager |
| `SENSOR_LOST` | 3 | Mất tín hiệu cảm biến lực, robot đã dừng. | không có khung > 100 ms (đã có) | Tech + Manager |
| `STROKE_LOST` | 3 | Bút rời giấy khi đang viết, robot tạm dừng. | lực < 0,3·F_min quá 60 ms (đã có) | Tech |
| `RUN_OUTCOME_UNKNOWN` | 3 | Agent mất kết nối giữa chừng: chưa biết bản viết đến đâu. | trạng thái UNKNOWN (đã có) | Tech + Manager |
| `STROKE_INTERRUPTED` | 3 | Nét số N đang viết dở. Chọn viết lại hoặc bỏ qua. | progress.json (đã có) | Tech |
| `PREFLIGHT_REFUSED` | 2 | Chưa chạy được vì: (lý do dễ hiểu). | từ chối của preflight (đã có) | Tech |
| `CALIBRATION_OLD` | 2 | Hiệu chuẩn đã N giờ, nên làm lại. | tuổi hiệu chuẩn > (đo) | Tech |
| `FORCE_NEAR_LIMIT` | 2 | Lực thường xuyên sát giới hạn. Kiểm tra bút/giấy. | ≥ 80% F_max nhiều lần | Tech |
| `DROPPED_FRAMES` | 2 | Cảm biến lực mất nhiều gói tin. Kiểm tra dây USB. | `SafetyMonitor.dropped` (đã có) | Tech |
| `AGENT_OFFLINE` | 2 | Máy trạm không báo về server N giây. | không có heartbeat > 15 s | Manager |
| `PAPER_CHANGE` | 1 | Đặt tờ giấy mới cho trang 2 rồi xác nhận. | (đã có) | Tech |

Hai cảnh báo mức 4 giá trị nhất là `STOP_NOT_EFFECTIVE` và `TRACKING_ERROR`: chúng kiểm tra robot **thật sự** làm gì thay vì tin lệnh đã gửi. Cảnh báo mức 4 bật còi/đèn đỏ ở máy trạm (và đèn LED đỏ trên gripper, đã có trong thiết kế ESP32).
Việc phát hiện người bước vào vùng làm việc cần cảm biến (camera/rèm sáng) mà hiện chưa có: không giả vờ làm bằng phần mềm.

## 3. Hai màn hình

**Technical Staff (cockpit, xem mô hình mẫu trong cuộc trò chuyện):** trạng thái một dòng; cảnh báo đang mở (câu + việc cần làm, bấm "đã thấy"); 4 chỉ số (lực, kết nối, gripper, tuổi hiệu chuẩn); chuỗi bước quy trình tick xanh; nút Tiếp tục / Bỏ qua nét dở / Tạm dừng / DỪNG; bản 3D (mục 5) và, nếu có, camera.
**Manager (bảng robot):** mỗi robot một thẻ (kết nối, phiên bản controller/SDK/agent, giờ chạy, số job, số lần dừng và E-Stop theo tuần, % lực trong dải, tuổi hiệu chuẩn, sự cố mở); danh sách cảnh báo mức 3–4 chưa xử lý; **dòng thời gian tuân thủ quy trình theo job**: từng bước (hash khớp, hiệu chuẩn, server kiểm lại, chạy khô, ai xác nhận lúc mấy giờ, viết, ảnh QC) và các "ngoại lệ" (hiệu chuẩn cũ, dừng nhiều lần, viết dở rồi tiếp tục, ai cho tiếp tục). Báo cáo tuần xuất được.
"Chạy đúng quy trình" được suy ra từ dữ liệu, không do người vận hành tự khai: các bước bắt buộc đã bị code chặn nên ngoại lệ chỉ còn là chuyện chất lượng và thói quen.

## 4. Thay đổi DB đề xuất (migration `0008`, cộng thêm, không xoá gì)

- `robots` thêm cột: `controller_version`, `firmware_version`, `sdk_version`, `agent_version`, `connection_state` (ONLINE/OFFLINE/UNKNOWN), `last_seen_at`, `last_mode`.
- `robot_runs`: mỗi lần agent chạy (kể cả chạy khô và bị từ chối): `job_id`, `robot_id`, `run_id` duy nhất, `mode` (MOCK/SIM/REAL), `dry_run`, `started_at`, `ended_at`, `result` (DONE/STOPPED/FAULT/UNKNOWN/DRY_RUN_DONE/REFUSED), `completed_strokes`, `total_strokes`, `plan_digest`, `authorized_by` + `authorized_at` (người vận hành bấm xác nhận REAL), `robot_info` (JSONB), `summary` (JSONB: lực, thời lượng).
- `robot_alerts`: `robot_id`, `job_id?`, `run_id?`, `level` 1–4, `code`, `message_vi`, `action_vi`, `estop_advised`, `details` (JSONB), `raised_at`, `acknowledged_by/at`, `resolved_at`, `resolution_note`; chỉ mục cho cảnh báo chưa xử lý.
- `alert_catalog` (bảng tra mã → câu tiếng Việt, mức, việc cần làm, ngưỡng): Manager sửa chữ và ngưỡng mà không cần sửa code; seed bằng script idempotent.
- Cập nhật `tests/conftest.py::_cleanup` (bảng mới tham chiếu `production_jobs`/`robots`), RLS theo mẫu hiện có, rollback bằng `alembic downgrade 0007` (xoá 3 bảng mới và các cột mới; chỉ mất dữ liệu nhật ký mới).
Dữ liệu tần số cao (vị trí, lực từng mẫu) **không** lên DB: ở file `runs/*.jsonl` trên máy trạm; DB chỉ nhận tóm tắt, cảnh báo và trạng thái 1 Hz.

## 5. API (đa số là thêm; hợp đồng cũ giữ nguyên)

Agent → BE (bằng token Technical Staff): `POST /technician/jobs/{id}/runs` (mở), `PATCH …/runs/{run_id}` (đóng), `POST /technician/alerts`, `PUT /technician/robots/{id}/heartbeat` (1 Hz: trạng thái, phiên bản, chế độ).
Đọc: `GET /technician/robot-status`, `GET /technician/alerts?open=true`, `POST /technician/alerts/{id}/ack`; Manager: `GET /manager/robots/{id}/health`, `GET /manager/runs`, `GET /manager/jobs/{id}/compliance`, `GET /manager/alerts`, `PATCH /manager/alert-catalog/{code}`.
Cần thêm vào `tests/test_permission_matrix.py` (mọi route phải có quy tắc). Đẩy tức thời cho cảnh báo mức 3–4 dùng WebSocket của viewer (agent) và, ở BE, SSE hoặc polling 2 giây cho tới khi có thông báo (phase 4e).

## 6. Mô phỏng nhìn thấy robot như Unity / Isaac

Có tài nguyên chính thức: gói `fairino_description` trong repo `FAIR-INNOVATION/frcobot_ros2` có **`fairino3_v6.urdf`** (đúng FR3 V6) và 7 file lưới STL (~5,7 MB) cho từng khâu. Repo không có file LICENSE, nên cần hỏi hãng hoặc chỉ dùng nội bộ trước khi đưa lên sản phẩm.

| Phương án | Là gì | Ưu | Nhược |
|---|---|---|---|
| **A. Bản sao số 3D trên web (khuyến nghị)** | three.js + URDF + STL, chạy trong trình duyệt, nhận góc khớp từ Agent | xem từ xa không cần cài, rẻ, đủ thấy cánh tay, tờ giấy, đường bút, lực, vùng cấm, trạng thái E-Stop | không mô phỏng vật lý |
| B. Unity | cũng dựng được từ URDF | đẹp, có physics | nặng, giấy phép, người xem phải cài, không hơn A về giám sát |
| C. NVIDIA Isaac Sim | mô phỏng vật lý chuẩn công nghiệp | phát hiện va chạm, camera ảo | cần GPU RTX và cài đặt nặng, thừa cho việc "theo dõi" |

Cách làm A: góc khớp lấy từ `GetActualJointPosDegree` của controller thật (hoặc của **FAIRINO SimMachine**, controller ảo của hãng) rồi vẽ bằng động học thuận của URDF, nên cái người xem thấy là dữ liệu thật của robot chứ không phải hoạt hình. Với chế độ SIM của chúng ta (chỉ có vị trí bút) sẽ cần giải IK số từ chính URDF để vẽ cả cánh tay; việc này còn **cho phép kiểm tầm với và giới hạn khớp ở chế độ mô phỏng** (hiện chỉ controller thật làm được). Kết quả đó vẫn ghi nhãn "mô hình của chúng ta", không phải controller.
Isaac/Unity chỉ đáng làm nếu sau này cần mô phỏng va chạm với môi trường; SimMachine + bản sao số A đã đáp ứng yêu cầu "xem robot từ xa mà không đứng cạnh". Một **camera USB** tại trạm (SRS đã có) vẫn cần cho những thứ mô hình không thấy được (giấy kẹt, người đến gần, bút gãy).

## 7. Phần còn thiếu để hệ thống "hoàn chỉnh" (theo thứ tự ưu tiên)

1. **Cảnh báo + nhật ký có cấu trúc + màn Technical Staff/Manager** (mục 2–5): lớn.
2. **Bản sao số 3D** (mục 6) và đẩy trạng thái 1 Hz: vừa.
3. **Camera tại trạm** (MJPEG/WebRTC) gắn vào cockpit: vừa.
4. **Màn hình hiệu chuẩn có hướng dẫn** (nhập khối `vhrs-motion/1`, đọc TCP/điểm giấy từ Agent bằng một nút thay vì gõ số): vừa. Không có nó, kỹ thuật viên phải tính tay, trái yêu cầu.
5. **Firmware ESP32** + hiệu chuẩn lực (cần bo/chân thực), **module đo chất lượng bản viết** (ảnh chụp ↔ phác thảo: SSIM, Chamfer, Hausdorff sau căn chỉnh) và **benchmark OT-1** trên bộ ảnh chữ Việt thật: lớn, phụ thuộc phần cứng/dữ liệu.
6. **Thông báo thật** (phase 4e): cảnh báo mức 3–4 tới Manager qua in-app/email; tiến trình nền (phase 5) để đóng cảnh báo cũ, nhắc hiệu chuẩn.
7. **An ninh vận hành:** token riêng cho agent thay vì token người (hết hạn 30 phút hiện nay làm gián đoạn chạy dài), ghi `authorized_by` của người bấm xác nhận REAL, đồng hồ máy trạm đồng bộ NTP, sao lưu `runs/`.
8. **Đánh giá rủi ro an toàn máy** do người có chuyên môn thực hiện (ISO 10218 / ISO/TS 15066 cho robot cộng tác) trước khi dùng cho khách thật; nút E-Stop trong tầm tay, hàng rào/biển cảnh báo. Tôi không thể thay phần này.

## 8. Cần chủ dự án quyết định

1. Duyệt phạm vi migration `0008` (mục 4)? Nếu duyệt, tôi làm trọn: thử trên DB cục bộ, áp lên Supabase, tạo lại script DB tổng.
2. Chọn phương án 3D: A (khuyến nghị) / B / C; và đồng ý tải URDF + STL chính thức (5,7 MB) để dùng nội bộ (repo không có LICENSE).
3. Có gắn camera USB tại trạm không (ảnh hưởng thiết kế cockpit)?
4. Ai nhận cảnh báo mức 4: Technical Staff + Manager qua kênh nào (in-app cần phase 4e; email)?
5. Người xem từ xa có được bấm DỪNG phần mềm không (đề xuất: có, nhưng chạy REAL luôn cần một người trực tiếp ở cạnh nút E-Stop)?
