# Bảng task FE, hạn Chủ Nhật 15/11/2026

Lập ngày 12/11/2026 từ code hiện tại (nhánh `fe`, đã merge `main`). Mỗi thành viên dùng Claude/Codex làm task của mình và cập nhật cột trạng thái trong file này.

## 1. Mục tiêu, deadline, phân công

**Mục tiêu:** đến hết Chủ Nhật 15/11/2026 hoàn tất các UI còn lại của ba nhóm vai trò nội bộ, nối các API BE đã có mà FE chưa gọi, và qua được tiêu chí tích hợp ở mục 6. Không có kế hoạch nhiều tuần: việc không kịp thì chuyển backlog (P1), không làm dở.

| Người | Phụ trách | Ghi chú |
|---|---|---|
| Ân | Technical / Technician; đồng thời hoàn thiện UI Admin | Xong UI Admin thì báo Nhã để bàn giao (task ADM-HANDOFF) |
| Quang | Manager | Dashboard/báo cáo, giám sát robot và cảnh báo |
| Nhã | UI Staff; sau handoff từ Ân thì đối chiếu và nối API Admin | Task Admin API chỉ bắt đầu khi nhận bàn giao |

Mốc đề xuất (có thể chỉnh trong nhóm): giữa tuần xong đối chiếu API, Thứ Bảy 14/11 xong task P0, Chủ Nhật 15/11 chạy kiểm tra tích hợp và sửa lỗi.

Trạng thái dùng: `TODO`, `IN PROGRESS`, `BLOCKED`, `DONE`. Mức ưu tiên: P0 bắt buộc trước Chủ Nhật, P1 chuyển backlog nếu không kịp an toàn.

## 2. Quy tắc cho agent

1. Chỉ làm task có `owner` là người đang giao việc cho bạn. Không tự nhận task của người khác; thấy việc thuộc người khác thì ghi chú vào task đó, không sửa.
2. Đọc `FE/AGENTS.md` trước khi sửa: mọi chữ hiển thị phải có đủ en, ja, vi; không dùng gạch ngang dài trong nội dung; icon từ `@phosphor-icons/react`; màu từ `src/styles/theme.css`.
3. Dữ liệu lấy từ API. Không đưa dữ liệu mẫu vào production, không dựng nút cho API chưa có.
4. Mỗi lần bắt đầu: đổi trạng thái task sang `IN PROGRESS`. Gặp vướng (chờ người khác, thiếu API, BE trả khác tài liệu): đổi `BLOCKED` và ghi lý do, không đoán.
5. Chỉ đổi `DONE` khi đạt toàn bộ "Tiêu chí hoàn thành" của task và bốn lệnh ở mục 7 đều qua. Ghi ngày và người xác nhận ở cuối dòng trạng thái.
6. Điều gì không xác minh được từ source thì ghi `VERIFY WITH BE`, không bịa endpoint hay trường dữ liệu. `BE/docs/FE_API_GUIDE.md` có thể chưa cập nhật; code trong `BE/app/api/v1/` là nguồn đúng.
7. Không sửa file của task khác đang `IN PROGRESS` (đặc biệt `src/i18n/*.ts`, `src/App.tsx`, `src/components/ws/Shell.tsx`: cả ba dùng chung, merge nhỏ và thường xuyên).
8. Không commit/push khi chưa được người phụ trách task đồng ý.

## 3. Kết quả đối chiếu BE và FE (12/11/2026)

Cách kiểm: so các route trong `BE/app/api/v1/*.py` (prefix `/api/v1` ở `BE/app/main.py`) với các lời gọi `api()` trong `FE/src/services/*.ts`.

**Admin (`/admin/*`):** FE `services/admin.ts` đã gọi đủ 12 route hiện có trong `BE/app/api/v1/admin.py`: `GET/POST /accounts`, `PATCH /accounts/{id}`, `GET /audit-logs`, `POST /jobs/run`, `GET /jobs/last`, `GET /settings`, `PUT /settings/{key}`, `GET /integrations`, `PUT /integrations/{name}`, `GET /dashboard`. Tại thời điểm này chưa thấy route Admin nào chưa nối. BE có thể thêm route sau; vì vậy Nhã phải đối chiếu lại sau handoff (task ADM-API-1), không dựa vào kết luận này.

**Technician (`/technician/*`):** đã nối: danh sách/chi tiết job, package, prepare, simulation, start, events, finish, incidents, photos (upload-url, tạo, sửa, xoá, submit), qc-fail, robot-commands, live, view-ticket, robot-status, ack/resolve alert. Chưa nối (đã kiểm tra, không có lời gọi trong `FE/src`):
- `POST /technician/jobs/{job_id}/photos/{photo_id}/evaluate` và `GET /technician/jobs/{job_id}/quality` (`quality.py`).
- `POST /technician/jobs/{job_id}/calibration`: theo `FE/AGENTS.md`, hiệu chuẩn gửi từ máy trạm, không từ web. Chỉ kiểm payload, không dựng form gửi.
- `GET /technician/alerts` (danh sách cảnh báo có phân trang), `POST /technician/alerts` (tạo cảnh báo), `POST /technician/jobs/{job_id}/runs`, `PATCH /technician/runs/{run_id}`, `GET /technician/robots/{id}/scene`, `POST/DELETE .../agent-session`: thuộc Robot Agent hoặc vận hành; xếp P1.

**Manager (`/manager/*`):** đã nối: staff, assignment, quotations pending-approval/approve/reject, papers/pens/inks/compat/templates/styles/robots/pricing-config, schedule queue/config/suggestion/schedule/reschedule/unschedule, jobs, technicians. Chưa nối (không có lời gọi trong `FE/src`):
- Báo cáo: `GET /manager/dashboard`, `GET /manager/reports`, `GET /manager/reports/export` (`reports.py`).
- Robot operations (`robot_ops.py`): `GET /manager/robot-status`, `GET /manager/robots/{id}/health`, `GET /manager/runs`, `GET /manager/jobs/{id}/compliance`, `GET /manager/alerts`, `POST /manager/alerts/{id}/ack`, `POST /manager/alerts/{id}/resolve`, `GET /manager/alert-catalog`, `PATCH /manager/alert-catalog/{code}`.
- Robot link (`robot_link.py`): `POST /manager/robots/{id}/robot-commands`, `GET .../live`, `GET .../scene`, `GET .../agent`, `POST/DELETE .../agent-key`, `POST .../view-ticket`.
- Sự cố (`scheduling.py`): `GET /manager/incidents`, `POST /manager/incidents/{id}/resolve`; sự kiện job `GET /manager/jobs/{id}/events` (VERIFY WITH BE về việc FE đã cần hay chưa).
- Chất lượng: `GET /manager/jobs/{job_id}/quality`.
- Đánh giá: `GET /manager/reviews`, `POST /manager/reviews/{id}/hide|unhide`.
- `FE/src/pages/staff/ManagerDashboard.tsx` hiện tự tính số liệu từ `allWork`, `scheduleQueue`, `listRobots`, `pendingApprovals`, `adminPapers/Pens/Inks`, không dùng `/manager/dashboard`.

**Staff (`/workshop/*`):** đã nối: danh sách/chi tiết đơn, claim, accept, reject, request-info, sketches, quotations, adjustment, send, cancel, pdf, payments, jobs, shipment, pickup, refunds, ETA, chat. Chưa nối: `GET /workshop/orders/{order_id}/material-suggestions`, `GET /workshop/orders/{order_id}/product-photos` (`workshop.py`); showcase `GET/POST/PATCH/DELETE /workshop/showcase` và `POST /workshop/showcase/upload-url` (`reviews.py`).

**Công khai và khách (ngoài phạm vi sprint):** `GET /catalog/reviews`, `GET /catalog/showcase`, `/orders/{id}/review` chưa dùng trong FE. Xếp backlog.

## 4. Task theo người

### 4.1. Ân: Technician và Admin UI

**Việc của Ân đối với Admin:** UI Admin đã có khung `AdminFrame`, dashboard, tài khoản, nhật ký, cài đặt (xem mục "Admin area" trong `FE/AGENTS.md`). Ân hoàn tất, kiểm tra và báo Nhã.

| ID | Owner | Status | Phụ thuộc | File / route liên quan | Việc cần làm | API | Tiêu chí hoàn thành |
|---|---|---|---|---|---|---|---|
| ADM-UI | Ân | IN PROGRESS | Không | `src/pages/admin/*`, `src/components/admin/*`, `/admin`, `/admin/accounts`, `/admin/audit`, `/admin/settings` | Hoàn thiện và chốt UI Admin, commit phần Admin, chạy `node scripts/check-admin-browser.mjs` sau build | Các route Admin đã nối trong `services/admin.ts` | Bốn lệnh mục 7 qua; script browser Admin qua; ba ngôn ngữ; responsive (drawer trên màn nhỏ); không còn thay đổi Admin chưa commit |
| ADM-HANDOFF | Ân | TODO | ADM-UI = DONE | Tin nhắn gửi Nhã; có thể ghi vào mục "Bàn giao Admin" cuối file | Ân báo Nhã khi UI Admin xong: nhánh/commit chứa UI, danh sách màn đã xong, phần còn lỗi biết trước | Không | Nhã xác nhận đã nhận; ghi ngày giờ bàn giao vào mục "Bàn giao Admin". Nhã chỉ bắt đầu ADM-API-1 sau bước này |
| TECH-1 | Ân | TODO | Không | `src/pages/tech/TechDashboard.tsx`, `src/components/ws/*` (rail `TechRail`) | Chỉnh dashboard Technician: job đang hoạt động, job sắp tới, cảnh báo robot đang mở; làm rõ trạng thái trống và lỗi | `GET /technician/jobs`, `GET /technician/robot-status` (đã nối) | Dashboard hiển thị đúng số job theo trạng thái; có loading/error/empty; ba ngôn ngữ; responsive; không chữ bị cắt ở tiếng Việt và tiếng Nhật |
| TECH-2 | Ân | TODO | Không | `src/pages/tech/PreviewOrders.tsx`, `JobDetail.tsx`, `JobWorkflow.tsx`, `JobPreparation.tsx`, `JobEvents.tsx`, `JobHistory.tsx`, `/tech/preview`, `/tech/qc`, `/tech/jobs/:id` | Chỉnh danh sách và chi tiết job: lọc trạng thái/khoảng ngày, bước chuẩn bị, mô phỏng, chạy, kết thúc; thanh tiến trình rõ | `GET /technician/jobs`, `GET /technician/jobs/{id}`, `.../package`, `.../events`, `.../prepare`, `.../simulation`, `.../start`, `.../finish` | Mỗi nút theo đúng điều kiện (`flow.ts`); lỗi API hiện chữ đã dịch (`orderErrorKey`); phân quyền `role="technician"` giữ nguyên; ba ngôn ngữ |
| TECH-3 | Ân | TODO | Không | `src/pages/tech/RobotConsole.tsx`, `src/services/robot.ts`, `JobWorkflow.tsx` | Chỉnh phần cảnh báo: banner E-Stop mức 4, danh sách cảnh báo đang mở, nút ack và resolve có ghi chú | `GET /technician/robot-status`, `POST /technician/alerts/{id}/ack`, `POST /technician/alerts/{id}/resolve` (đã nối); `GET /technician/alerts` chưa nối, chỉ nối nếu cần danh sách đầy đủ có phân trang (VERIFY WITH BE về việc có cần) | Cảnh báo mới hiện không cần tải lại trang (poll hiện có); ack/resolve có xác nhận và lỗi hiển thị; không thay thế E-Stop vật lý (giữ chú thích) |
| TECH-4 | Ân | TODO | TECH-2 | `src/services/technician.ts`, `src/pages/tech/JobPhotos.tsx`, `JobFeedback.tsx`, `qc.css`, `/tech/qc` | Nối đánh giá ảnh QC: sau khi tải ảnh, gọi evaluate cho ảnh và hiển thị kết quả; trang job hiển thị lịch sử đánh giá. Đọc `BE/app/api/v1/quality.py` và schema `QualityOut` trước khi định kiểu; trường nào không rõ ghi `VERIFY WITH BE` | `POST /technician/jobs/{job_id}/photos/{photo_id}/evaluate` (201), `GET /technician/jobs/{job_id}/quality` (mới đến cũ) | Hai API được gọi từ UI; trạng thái đang đánh giá, lỗi, chưa có kết quả đều có; kết quả khớp phản hồi BE (không tự suy diễn đạt/không đạt); luồng `qc-fail` và `photos/submit` hiện có không bị hỏng; ba ngôn ngữ |
| TECH-5 | Ân | TODO | Không | `BE/app/api/ops_schemas.py` (`CalibrationIn`), `BE/app/services/technician.py` (`_server_validation`, `frame_transform.schema = "vhrs-motion/1"`), `FE/src/services/technician.ts` | Kiểm tra payload hiệu chuẩn: `frame_transform` là `dict` tùy chọn, bắt buộc `schema = "vhrs-motion/1"` khi bật `MOTION_VALIDATION_REQUIRED`; FE không gửi hiệu chuẩn (máy trạm gửi), nên chỉ đối chiếu FE hiển thị `calibration` từ chi tiết job không giả định khối này. Kết luận ghi vào mục "Ghi chú kiểm tra" | `POST /technician/jobs/{job_id}/calibration` (không dựng form web) | Có ghi chú nêu rõ: payload mẫu khớp `CalibrationIn`, FE không tự dựng `frame_transform`, nơi nào cần BE trả lời ghi `VERIFY WITH BE` |
| TECH-6 | Ân | TODO | Không | `FE/src/services/technician.ts` (`canStart`, dòng `start:` trong điều kiện), `src/pages/tech/flow.ts` | Xác nhận FE dùng kết quả simulation và `can_start` do server trả: nút Start chỉ bật khi `simulation_passed === true` và `can_start`; nếu server trả `422`/mã lỗi khác thì hiển thị đúng và tải lại job. Không tự tính thay server | `GET /technician/jobs/{id}` (`can_start`, `simulation_passed`), `POST .../simulation`, `POST .../start` | Với `can_start = false` nút Start tắt và có lý do; sau lỗi API trạng thái trên màn hình khớp server; ghi vào "Ghi chú kiểm tra" |

### 4.2. Quang: Manager

| ID | Owner | Status | Phụ thuộc | File / route liên quan | Việc cần làm | API | Tiêu chí hoàn thành |
|---|---|---|---|---|---|---|---|
| MGR-1 | Quang | TODO | Không | `src/services/manage.ts` hoặc `src/services/workshop.ts` (thêm hàm), `BE/app/api/v1/reports.py` | Đối chiếu Manager: đọc `reports.py`, `robot_ops.py`, `robot_link.py`, `scheduling.py`; lập danh sách API chưa nối (mục 3 là điểm xuất phát, kiểm lại bằng code). Kiểu dữ liệu `dict[str, Any]` của dashboard/reports: lấy cấu trúc từ `BE/app/services` hoặc gọi thử, trường nào không rõ ghi `VERIFY WITH BE` | `GET /manager/dashboard`, `GET /manager/reports` (`from`, `to`, `group`) | Có danh sách đối chiếu trong "Ghi chú kiểm tra"; hàm service có kiểu rõ; chưa đổi UI |
| MGR-2 | Quang | TODO | MGR-1 | `src/pages/staff/ManagerDashboard.tsx`, `src/components/ws/charts.tsx`, `/staff` | P0. Chỉnh dashboard Manager theo số liệu từ API dashboard sản xuất thay vì tự tính khi dữ liệu có. Giữ bố cục Manager hiện có (xem "Staff presentation" trong `AGENTS.md`: Manager giữ layout) | `GET /manager/dashboard` | Số liệu khớp phản hồi BE; loading/error/empty; ba ngôn ngữ; responsive; vai trò Staff không thấy dashboard Manager |
| MGR-3 | Quang | TODO | MGR-1 | trang mới dưới `src/pages/staff/` (ví dụ `Reports.tsx`), `src/App.tsx` (route `<RequireStaff manager>`), `src/components/ws/Shell.tsx` (mục điều hướng) | P0. Trang báo cáo: chọn khoảng ngày và nhóm (`day`, theo giá trị BE chấp nhận: kiểm `Group` trong `reports.py`), hiển thị doanh thu, sản lượng, tỷ lệ từ chối/viết lại, robot, trễ ETA. Mỗi biểu đồ có bảng số | `GET /manager/reports` | Đổi khoảng ngày gọi lại API; lỗi `422` hiện thông báo; có bảng số bên cạnh biểu đồ; ba ngôn ngữ |
| MGR-4 | Quang | TODO | MGR-3 | Trang báo cáo | P1 (backlog nếu không kịp). Nút xuất Excel/PDF; tải bằng `fetch` có Bearer rồi tạo file, không dùng liên kết thường | `GET /manager/reports/export` (`format=xlsx|pdf`) | File tải được, tên lấy từ `Content-Disposition`; lỗi hiện đã dịch |
| MGR-5 | Quang | TODO | MGR-1 | trang mới (ví dụ `src/pages/staff/Robots.tsx`), `src/services/` (hàm mới), `Shell.tsx` | P0. Giám sát trạng thái robot: bảng tất cả robot (online/offline, chế độ, cảnh báo đang mở, tuổi hiệu chuẩn) và sức khỏe theo N ngày | `GET /manager/robot-status`, `GET /manager/robots/{id}/health` | Trạng thái không chỉ dựa vào màu (có chữ/icon); có loading/error/empty; ba ngôn ngữ; responsive |
| MGR-6 | Quang | TODO | MGR-5 | trang giám sát robot | P0. Cảnh báo robot cho Manager: danh sách chưa xử lý (nặng nhất trước), ack và resolve có ghi chú, hiển thị lời nhắn và việc cần làm từ danh mục | `GET /manager/alerts`, `POST /manager/alerts/{id}/ack`, `POST /manager/alerts/{id}/resolve`, `GET /manager/alert-catalog` | Hành động cập nhật danh sách; mức 4 nổi bật có chữ; sai quyền (Staff/Technician) bị `RequireStaff manager` chặn |
| MGR-7 | Quang | TODO | MGR-6 | trang giám sát robot | P1. Lịch sử lần chạy, compliance từng job, sự cố robot/vật tư, chỉnh danh mục cảnh báo | `GET /manager/runs`, `GET /manager/jobs/{id}/compliance`, `GET /manager/incidents`, `POST /manager/incidents/{id}/resolve`, `PATCH /manager/alert-catalog/{code}` | Làm khi P0 xong; nếu không, giữ TODO và chuyển backlog |
| MGR-8 | Quang | TODO | Không | `src/pages/staff/Approvals.tsx`, `Schedule.tsx`, `Catalog.tsx`, `Pricing.tsx` | P1. Rà soát chung: lỗi và trạng thái trống của các màn Manager hiện có sau thay đổi Shell/i18n | Không đổi API | Không hỏng hồi quy; ghi chú nếu có |
| MGR-BACKLOG | Quang | TODO | Không | Chưa có file | Backlog (không làm trước Chủ Nhật): lệnh robot từ Manager, khóa Robot Agent, cảnh 3D, vé xem (`/manager/robots/{id}/robot-commands`, `/agent`, `/agent-key`, `/view-ticket`, `/live`, `/scene`), `/manager/jobs/{id}/quality`, `/manager/reviews` | Xem mục 3 | Chỉ khi cả P0 đã DONE |

### 4.3. Nhã: Admin API và UI Staff

**Phần Admin phải chờ Ân.** Nhã không bắt đầu ADM-API-1 trước khi ADM-HANDOFF = DONE (trạng thái `BLOCKED` ghi rõ "chờ Ân bàn giao UI Admin"). Trong lúc chờ, Nhã làm các task Staff không phụ thuộc Admin.

| ID | Owner | Status | Phụ thuộc | File / route liên quan | Việc cần làm | API | Tiêu chí hoàn thành |
|---|---|---|---|---|---|---|---|
| ADM-API-1 | Nhã | BLOCKED | ADM-HANDOFF = DONE | `BE/app/api/v1/admin.py`, `BE/app/main.py` (prefix `/api/v1`), `FE/src/services/admin.ts` | Sau khi nhận bàn giao: `git pull` nhánh mới nhất, đọc lại mọi route trong `admin.py` (và bất kỳ router Admin mới trong `main.py`), so với từng hàm trong `services/admin.ts`. Chỉ ghi "chưa nối" cho route đã xác minh trong code và không có lời gọi trong `FE/src`. Ghi kết quả vào bảng "Đối chiếu Admin" cuối file | Mọi `/admin/*` | Bảng có đủ cột: route, method, có trong `admin.py`, hàm FE gọi, kết luận (Đã nối / Chưa nối / VERIFY WITH BE); không có hàng bịa |
| ADM-API-2 | Nhã | BLOCKED | ADM-API-1 | `FE/src/services/admin.ts`, `FE/src/pages/admin/*` | Nối từng API còn thiếu theo bảng ADM-API-1: thêm hàm service có kiểu, gắn vào UI do Ân bàn giao mà không đổi kiểu thiết kế (làm đúng "Admin area" trong `AGENTS.md`). Nếu không có API nào thiếu: ghi rõ và đánh DONE | Theo kết quả ADM-API-1 | Mỗi API mới có loading/error/empty; ba ngôn ngữ; `node scripts/check-admin-browser.mjs` qua; không đổi UI mà không báo Ân |
| STF-1 | Nhã | TODO | Không | `src/pages/staff/StaffDashboard.tsx`, `src/components/ws/staff-ui.css`, `docs/STAFF_CRM_UI.md`, `/staff` | P0. Hoàn thiện dashboard Staff theo thiết kế CRM trong `docs/STAFF_CRM_UI.md`: KPI giữ tổng hiện tại, biểu đồ đơn nhận có chọn 7/30 ngày; không dữ liệu mẫu, không hành động CRM không có API | `GET /workshop/orders` (qua `allWork`) | `node scripts/check-staff-ui-browser.mjs` qua; loading/error/empty; ba ngôn ngữ; responsive; phân quyền Staff/Manager đúng |
| STF-2 | Nhã | TODO | Không | `src/pages/staff/Workbench.tsx`, `/staff/review`, `/staff/review/:id` | P0. Hàng đợi đơn: các cột pipeline, thẻ mở `/staff/review/:id`, lọc bằng `AdminSelect`, tìm kiếm, phân trang; giữ nguyên hành động claim/accept/reject/request-info; không kéo-thả đổi trạng thái | `GET /workshop/orders`, `GET /workshop/orders/{id}`, `POST .../claim|accept|reject|request-info` | Mọi hành động cũ còn hoạt động; lỗi API đã dịch; không chữ bị cắt ở tiếng Việt/Nhật; mobile không tràn ngang |
| STF-3 | Nhã | TODO | STF-2 | `src/pages/staff/Workbench.tsx` (phần tiếp nhận, phác thảo, báo giá), `QuotationPanel.tsx`, `SketchPanel.tsx`, `src/services/workshop.ts` | P0. Workbench: kiểm tra toàn luồng tiếp nhận, phác thảo, báo giá, chat sau thay đổi giao diện. Nối API gợi ý vật tư vào chỗ Staff chọn giấy/bút/mực khi lập báo giá; đọc `material_candidates` (trong `BE/app/services`) để định kiểu, trường không rõ ghi `VERIFY WITH BE` | `GET /workshop/orders/{order_id}/material-suggestions` | Gợi ý hiển thị theo lựa chọn của khách và luật tương thích; không có gợi ý thì hiện trạng thái trống; Staff chọn được gợi ý và gửi báo giá như cũ; ba ngôn ngữ |
| STF-4 | Nhã | TODO | STF-2 | `src/pages/staff/Refunds.tsx`, `PaidOrderDesk.tsx`, `FulfillmentPanel.tsx`, `/staff/refunds`, `/staff/fulfillment` | P0. Kiểm tra các màn Staff đã nối (hoàn tiền, giao hàng, nhận tại xưởng) còn đúng sau thay đổi UI; đối chiếu `docs/REFUND_FLOW.md` và `docs/FULFILLMENT_UI.md` | `/workshop/refunds`, `/workshop/payments/{id}/refund`, `/workshop/refunds/{id}/confirm`, `/workshop/orders/{id}/shipment`, `.../pickup/confirm` | `npm run test:fulfillment:browser` qua; hoàn tiền xác nhận thủ công hoạt động |
| STF-5 | Nhã | TODO | STF-3 | `src/services/workshop.ts`, UI ảnh sản phẩm trong chi tiết đơn | P1. Ảnh sản phẩm của đơn cho Staff | `GET /workshop/orders/{order_id}/product-photos` | Làm khi P0 xong |
| STF-BACKLOG | Nhã | TODO | Không | Chưa có file | Backlog: showcase của xưởng (`/workshop/showcase`, `upload-url`), đánh giá của khách, SMS OTP, chat realtime/SSE mới, các API vận hành ít ưu tiên | Xem mục 3 | Không làm trước Chủ Nhật nếu P0 chưa DONE |

## 5. Backlog chung (P1, không làm nếu P0 chưa DONE)

- Showcase (`/workshop/showcase`, `/catalog/showcase`) và đánh giá (`/orders/{id}/review`, `/manager/reviews`, `/catalog/reviews`).
- SMS OTP (đặt lại mật khẩu, xác minh số điện thoại) ngoài những gì FE đã có: VERIFY WITH BE trước khi nối.
- Chat realtime mới và các API vận hành robot của Robot Agent (`/agent/*`, `/technician/robots/{id}/agent-session`, `/technician/jobs/{id}/runs`).
- Báo cáo xuất file (MGR-4) và nhóm Manager P1 (MGR-7, MGR-8).

## 6. Tiêu chí tích hợp cuối (Chủ Nhật 15/11)

Chạy trên nhánh gộp của cả ba người, bằng tài khoản seed (`admin@netviet.vn`, `manager@netviet.vn`, `staff@netviet.vn`, `tech@netviet.vn`, mật khẩu `ChangeMe@123`):

1. **Phân quyền:** mỗi vai trò chỉ thấy và vào được màn của mình (`RequireStaff`, `manager`, `role="admin"`, `role="technician"`). Staff không vào `/staff/catalog`, `/staff/pricing`, `/staff/approvals`, `/staff/schedule` và các trang Manager mới. Truy cập thẳng bằng URL cũng bị chặn. Technician và Admin không vào được màn Staff/Manager.
2. **Trạng thái:** mọi màn mới hoặc sửa có đủ loading, lỗi (chữ đã dịch, không lộ mã thô) và trống.
3. **Responsive:** kiểm ở 360 px, 768 px và desktop; không tràn ngang, không đè chữ; menu mobile hoạt động.
4. **Ba ngôn ngữ:** chuyển en, vi, ja; không còn chữ Anh trái quy định (`FE/AGENTS.md`). Chiều dài tiếng Việt và tiếng Nhật không cắt nút.
5. **Dữ liệu:** không dữ liệu mẫu; không nút cho API chưa nối.
6. **Hồi quy:** luồng khách (tạo đơn, cọc, hoàn tiền) và thông báo vẫn chạy.

Mỗi người ghi kết quả từng mục cho phần của mình vào "Ghi chú kiểm tra"; chỉ khi cả sáu mục qua thì sprint DONE.

## 7. Lệnh kiểm tra FE (chạy trong thư mục `FE/`)

```bash
npx tsc -b            # lỗi nếu vi.ts hoặc ja.ts thiếu khóa
npm run i18n:check    # chữ Anh cứng trong JSX, khóa không tồn tại
npm run lint          # oxlint
npm run build         # tsc -b && vite build
```

Kiểm tra thêm khi chạm vào phần liên quan:

```bash
node scripts/check-admin-browser.mjs          # sau build, cho Admin
node scripts/check-staff-ui-browser.mjs       # sau build, cho Staff
npm run test:technician                       # Technician
npm run test:technician:browser               # Technician, có build
npm run test:fulfillment:browser              # giao hàng/nhận tại xưởng
```

## 8. Bàn giao Admin (điền khi ADM-HANDOFF xảy ra)

- Ân báo Nhã lúc: `…`
- Nhánh / commit chứa UI Admin: `…`
- Màn đã xong: `…`
- Việc còn dở biết trước: `…`
- Nhã xác nhận đã nhận lúc: `…`

## 9. Đối chiếu Admin (Nhã điền ở ADM-API-1)

| Route | Method | Có trong `admin.py` | Hàm FE gọi | Kết luận |
|---|---|---|---|---|
| (điền sau handoff) | | | | |

## 10. Ghi chú kiểm tra

Mỗi người ghi ngắn: task, ngày, kết quả (đạt/không đạt), nội dung `VERIFY WITH BE` còn treo.

- …
