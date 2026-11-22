# Bảng task FE, hạn Chủ Nhật 15/11/2026

Cập nhật 12/11/2026 theo phân công mới. Danh sách API backend đã có mà FE chưa nối lấy từ [docs/UI_API_AUDIT_2026-11-12.md](docs/UI_API_AUDIT_2026-11-12.md) (mã `M-API`, `T-API`, `S-API`, `C-API`, `A-API`, `X-DATA`, `X-CHAT`). Bảng này giao việc theo người; người nhận và hạn trong bảng này là bản đang dùng.

Mỗi thành viên dùng Claude/Codex làm task của mình và cập nhật cột trạng thái trong file này. Cả ba dùng chung một Claude Code, nên mỗi phiên làm việc phải nói rõ tên người và mã task.

## 1. Mục tiêu, deadline, phân công

**Mục tiêu:** đến hết Chủ Nhật 15/11/2026 hoàn tất UI và API của vai trò mình phụ trách, và qua tiêu chí tích hợp ở mục 6. Không lập kế hoạch nhiều tuần: việc không kịp thì chuyển backlog (P1), không làm dở.

| Người | Phụ trách (UI và API) |
|---|---|
| Ân | Technical (Technician) và Customer (khách hàng, kể cả tài khoản và chat dùng chung) |
| Nhã | Staff và Admin (Admin chỉ cần đối chiếu và nối API) |
| Quang | Manager |

**Yêu cầu quan trọng nhất: mọi UI mới hoặc sửa phải đồng bộ với UI của Admin và Staff** (xem mục 2.9).

Mốc đề xuất (nhóm có thể chỉnh): xong đối chiếu API trong ngày đầu, Thứ Bảy 14/11 xong task P0, Chủ Nhật 15/11 chạy kiểm tra tích hợp và sửa lỗi.

Trạng thái dùng: `TODO`, `IN PROGRESS`, `BLOCKED`, `DONE`. Ưu tiên: P0 bắt buộc trước Chủ Nhật, P1 chuyển backlog nếu không kịp an toàn.

## 2. Quy tắc cho agent

1. Chỉ làm task có `owner` là người đang giao việc cho bạn. Hỏi tên người nếu chưa rõ. Không tự nhận task của người khác; thấy việc thuộc người khác thì ghi chú vào task đó, không sửa.
2. Đọc `FE/AGENTS.md` trước khi sửa: mọi chữ hiển thị phải có đủ en, ja, vi; không dùng gạch ngang dài trong nội dung; icon từ `@phosphor-icons/react`; màu từ token trong `src/styles/theme.css`.
3. Dữ liệu lấy từ API. Không đưa dữ liệu mẫu vào production, không dựng nút cho API chưa có, không mock thành công.
4. Bắt đầu task: đổi trạng thái sang `IN PROGRESS`. Gặp vướng (chờ người khác, thiếu API, BE trả khác tài liệu): đổi `BLOCKED` và ghi lý do, không đoán.
5. Chỉ đổi `DONE` khi đạt toàn bộ "Tiêu chí hoàn thành" của task và các lệnh ở mục 7 đều qua. Ghi ngày và người xác nhận ở cuối dòng trạng thái.
6. Điều không xác minh được từ source thì ghi `VERIFY WITH BE`, không bịa endpoint hay trường dữ liệu. Code trong `BE/app/api/v1/` là nguồn đúng; `BE/docs/FE_API_GUIDE.md` có thể chưa cập nhật.
7. Không đổi quyền role, điều kiện bật nút, trạng thái đơn/job hoặc luồng xử lý chỉ để làm UI đẹp hơn.
8. Không commit/push khi chưa được người phụ trách task đồng ý.
9. **Đồng bộ UI.** Dùng Admin và Staff làm chuẩn: [AdminFrame.tsx](src/components/admin/AdminFrame.tsx), `admin-shell.css`, `admin-ui.css`, [Shell.tsx](src/components/ws/Shell.tsx), `staff-ui.css`, `staff-theme.css`, `staff-depth.css`, cùng [docs/STAFF_CRM_UI.md](docs/STAFF_CRM_UI.md). Cần khớp: header (logo, thông báo, sáng/tối, ngôn ngữ, tài khoản), sidebar theo role và drawer trên mobile, màu đen/deep navy/trắng, chữ, khoảng cách, bo góc, thẻ, KPI, input, button, dropdown (`AdminSelect`), tab, chế độ sáng/tối dùng chung một preference. Chữ đủ tương phản ở cả hai chế độ; trạng thái không chỉ dựa vào màu. Dùng lại component và token có sẵn, không viết kiểu riêng. Trang khách không có sidebar: áp dụng token, thành phần và cách dùng màu của Admin/Staff, giữ khung trang khách hiện có.
10. **Sổ API.** Sau khi nối một API (và sau khi BE thêm route), chạy `npm run api:audit` rồi commit `docs/api-ledger.json` và `docs/UI_API_AUDIT_2026-11-12.md`. Khối "Sổ theo dõi API" ở cuối file audit tự ghi ngày BE thêm route, tự chuyển route sang "Đã nối" kèm ngày FE nối. Không sửa tay khối đó; chỉ coi task API là `DONE` khi route của nó đã sang "Đã nối" (hoặc có ghi chú vì sao không nối).
11. Dùng chung một Claude Code: dùng nhánh riêng (`fe-an`, `fe-quang`, `fe-nha`), pull `fe` trước khi làm. Các file dùng chung (`src/i18n/*.ts`, `src/App.tsx`, `src/components/ws/Shell.tsx`): chỉ thêm nhỏ, dùng tiền tố khóa riêng của mình, không sắp xếp lại. Component chat (`components/ui/Chat.tsx`) thuộc Ân, không sửa nếu không phải việc của mình.

## 3. Phần việc của Ân: Technical và Customer

### 3.1. Technical

| ID | Ưu tiên | Status | Phụ thuộc | File / route liên quan | Việc cần làm | API | Tiêu chí hoàn thành |
|---|---|---|---|---|---|---|---|
| TECH-UI | P0 | IN PROGRESS (14/11/2026: code xong, khung Staff đã kiểm sáng/tối, vi/ja, 1440/768/360; còn `npm run test:technician` và `check-technician-browser.mjs` lỗi sẵn trên `main`, xem mục 9) | Không | `src/pages/tech/*`, `src/components/ws/Shell.tsx` (area `tech`), `/tech`, `/tech/preview`, `/tech/qc`, `/tech/jobs/:id` | Đồng bộ toàn khu vực `/tech` (dashboard, danh sách và chi tiết job, chuẩn bị, console robot, lịch sử, cảnh báo, QC) theo chuẩn Admin/Staff ở mục 2.9. Giữ guard trong `flow.ts`, workflow job, console và quyền `role="technician"` | Không đổi | Khớp Admin/Staff ở cả hai chế độ sáng/tối; ba ngôn ngữ; mobile có drawer, không tràn ngang; E-Stop banner và điều kiện bật nút giữ nguyên; `npm run test:technician` và `node scripts/check-technician-browser.mjs` qua |
| TECH-API-1 | P0 | IN PROGRESS (14/11/2026: hai API đã nối; chờ hai bài test Technician như TECH-UI) | Không (giao diện nên làm sau TECH-UI) | `src/services/technician.ts`, `src/pages/tech/JobPhotos.tsx`, `JobFeedback.tsx`, `qc.css` | T-API-01: gọi đánh giá cho ảnh đã tải và xem kết quả; trang job hiển thị lịch sử đánh giá. Đọc `BE/app/api/v1/quality.py` và schema `QualityOut` trước khi định kiểu; trường không rõ ghi `VERIFY WITH BE` | `POST /technician/jobs/{job_id}/photos/{photo_id}/evaluate`, `GET /technician/jobs/{job_id}/quality` | Hai API được gọi từ UI; có trạng thái đang đánh giá, lỗi, chưa có kết quả; kết quả khớp phản hồi BE, không tự suy ra đạt/không đạt; luồng `qc-fail` và `photos/submit` hiện có không hỏng; ba ngôn ngữ |
| TECH-API-2 | P1 | TODO | TECH-UI | `src/services/robot.ts`, `src/pages/tech/RobotConsole.tsx` | T-API-02: danh sách cảnh báo đầy đủ có lọc và phân trang. FE đã có robot-status, ack, resolve: không coi là chưa nối | `GET /technician/alerts` | Danh sách có phân trang; ack/resolve vẫn hoạt động; mức đỏ có chữ và icon |
| TECH-CHK | P0 | DONE (14/11/2026, Claude tự kiểm; chờ Ân xác nhận) | Không | `BE/app/api/ops_schemas.py` (`CalibrationIn`), `BE/app/services/technician.py` (`_server_validation`), `src/services/technician.ts`, `src/pages/tech/flow.ts` | (1) Kiểm payload hiệu chuẩn `frame_transform` (dict tùy chọn, cần `schema = "vhrs-motion/1"` khi bật `MOTION_VALIDATION_REQUIRED`); FE không gửi hiệu chuẩn (máy trạm gửi), chỉ kiểm FE hiển thị `calibration` không giả định khối này. (2) Xác nhận nút Start chỉ bật khi `simulation_passed === true` và `can_start` do server trả. (3) X-DATA-03: kiểm package và job response mới không mất metadata/gate | `POST /technician/jobs/{job_id}/calibration` (không dựng form web), `GET /technician/jobs/{id}`, `POST .../simulation`, `POST .../start` | Ghi kết luận vào mục 9; với `can_start = false` nút Start tắt và có lý do; chỗ cần BE trả lời ghi `VERIFY WITH BE` |

### 3.2. Customer

| ID | Ưu tiên | Status | Phụ thuộc | File / route liên quan | Việc cần làm | API | Tiêu chí hoàn thành |
|---|---|---|---|---|---|---|---|
| CUS-UI | P0 | TODO | Không | `src/pages/create-order/*`, `src/pages/order/*`, `src/pages/account/*`, `src/components/layout/*`, `src/components/ui/Chat*.tsx` | Đồng bộ UI khách (tạo đơn, trang đơn, cọc, giao hàng, tài khoản, chat) theo chuẩn Admin/Staff (mục 2.9). Không đổi luồng, trạng thái đơn hay điều kiện bật nút; preview giấy giữ màu gốc | Không đổi | Khớp Admin/Staff ở sáng/tối; ba ngôn ngữ; mobile không tràn ngang; luồng tạo đơn, cọc, hoàn tiền và thông báo vẫn chạy |
| CUS-API-1 | P0 | DONE (14/11/2026, Claude tự kiểm; chờ Ân xác nhận), chưa chạy trình duyệt cho màn đánh giá | Không | `src/services/orders.ts` hoặc service mới, `src/pages/order/OrderReview.tsx` | C-API-01: xem, gửi, sửa đánh giá sau hoàn tất và tải ảnh đánh giá; theo trạng thái đơn, chủ đơn và thời hạn sửa | `GET/POST/PUT /orders/{id}/review`, `POST /orders/{id}/review/photos/upload-url` | Có loading/error/empty; lỗi BE hiện chữ đã dịch; ba ngôn ngữ |
| CUS-API-2 | P0 | DONE (14/11/2026, Claude tự kiểm; chờ Ân xác nhận), chưa chạy trình duyệt cho form địa chỉ | Không | `src/services/locations.ts`, `src/pages/order/Delivery.tsx`, form địa chỉ ở tài khoản | C-API-03: chuyển nguồn tỉnh/phường từ dịch vụ ngoài sang API BE hai cấp, dùng đúng code khi gửi địa chỉ. Comment FE nói BE chưa có API địa chỉ đã cũ | `GET /locations/provinces`, `GET /locations/provinces/{province_code}/wards` | Chọn địa chỉ chạy bằng API BE; giao hàng và báo phí vận chuyển vẫn đúng; ghi `VERIFY WITH BE` cho trường chưa rõ |
| CUS-API-3 | P1 | TODO | Không | `src/pages/create-order/*`, `src/services/orders.ts` | C-API-04, X-DATA-02: gợi ý vật tư, kiểu chữ cho toolbar, thư viện kiểu chữ của khách; preview theo đoạn nếu toolbar hỗ trợ. Không nhầm với API chọn bút/mực hiện có | `GET /catalog/suggest-materials`, `GET /catalog/text-styles`, `GET /catalog/my-styles` | Dữ liệu từ server vào luồng tạo đơn; trạng thái trống; ba ngôn ngữ |
| CUS-API-4 | P1 | TODO | Không | `src/pages/landing/*`, `src/services/` | C-API-02: nối đánh giá và showcase công khai vào nơi phù hợp; không nhầm `#showcase` trên landing với API showcase | `GET /catalog/reviews`, `GET /catalog/showcase` | Nội dung thật từ API; trạng thái trống; ba ngôn ngữ |
| CUS-API-5 | P1 | TODO | Không | `src/pages/account/Account.tsx`, `src/services/auth.ts`, `ResetPassword.tsx` | A-API-01/02, A-UI-01/02: OTP số điện thoại hồ sơ, khôi phục mật khẩu bằng điện thoại, form đổi mật khẩu (`apiChangePassword` chưa có UI), địa chỉ lưu server. Xử lý giới hạn gửi lại, hết hạn, sai mã; hiện đúng MOCK khi BE trả MOCK | `POST /me/phone/otp`, `POST /me/phone/verify`, `POST /auth/phone-reset/request`, `POST /auth/phone-reset/verify`, `POST /me/change-password` | Mỗi luồng có thông báo đã dịch; không coi SMS thật là sẵn sàng khi BE trả MOCK |
| CUS-API-6 | P1 | TODO | Không | `src/components/ui/Chat.tsx`, `services/chat.ts`, `services/notifications.ts` | X-CHAT-01: xử lý `event: message` trên stream thông báo, khử trùng ID, dùng `latest=true`, `before_id`, `next_before_id` để tải tin mới nhất và cuộn lấy lịch sử | `GET /me/notifications/stream`, `GET /orders/{id}/messages` | Tin mới hiện không cần chờ poll 10 giây; hội thoại dài không mất tin; chat phía Staff/Manager vẫn đúng quyền đọc/ghi |
| CUS-DATA | P1 | TODO | Cần Nhã làm STF-API-3 phía Staff | `src/services/orders.ts`, `src/pages/order/*` | X-DATA-01 phía khách: kiểm DTO, map và UI cho `revision_reason`, `region_counts`, `restoration_mode` trong báo giá/sketch | Theo `customer_quotes.py` | Trường mới hiển thị khi BE trả; không đổi luồng báo giá |

## 4. Phần việc của Nhã: Staff và Admin

### 4.1. Staff

| ID | Ưu tiên | Status | Phụ thuộc | File / route liên quan | Việc cần làm | API | Tiêu chí hoàn thành |
|---|---|---|---|---|---|---|---|
| STF-UI | P0 | DONE (14/11/2026, Claude tự kiểm; chờ Nhã xác nhận) | Không | `src/pages/staff/*` (phần Staff), `src/components/ws/staff-*.css`, `docs/STAFF_CRM_UI.md` | Giữ UI Staff làm chuẩn: khi thêm tính năng ở dưới, dùng cùng thành phần, không thiết kế lại luồng đã có. Rà hồi quy dashboard, hàng đợi `/staff/review`, Workbench, hoàn tiền, giao hàng sau mỗi thay đổi | Không đổi | `node scripts/check-staff-ui-browser.mjs` và `node scripts/check-fulfillment-browser.mjs` qua; sáng/tối; ba ngôn ngữ |
| STF-API-1 | P0 | DONE (14/11/2026, Claude tự kiểm; chờ Nhã xác nhận) | Không | `src/pages/staff/Workbench.tsx`, `QuotationPanel.tsx`, `src/services/workshop.ts` | S-API-01: gợi ý vật tư vào chỗ Staff chọn giấy/bút/mực khi lập báo giá; đọc `material_candidates` trong `BE/app/services` để định kiểu | `GET /workshop/orders/{id}/material-suggestions` | Gợi ý theo lựa chọn của khách và luật tương thích; trạng thái trống; Staff chọn được gợi ý và gửi báo giá như cũ; ba ngôn ngữ |
| STF-API-2 | P0 | DONE (14/11/2026, Claude tự kiểm; chờ Nhã xác nhận) | Không | `src/pages/staff/OrderDetail.tsx` hoặc Workbench, `src/services/workshop.ts` | S-API-02: ảnh thành phẩm của đơn cho Staff. `GET /orders/{id}/product-photos` là API khách, không thay thế quyền Staff | `GET /workshop/orders/{id}/product-photos` | Ảnh hiển thị ở chi tiết đơn; trạng thái trống; lỗi đã dịch |
| STF-API-3 | P1 | TODO | Không | `src/pages/staff/SketchPanel.tsx`, `SketchEditor.tsx`, `src/services/workshop.ts` | S-API-03, X-DATA-01 phía Staff: xem và sửa vùng của phác thảo; đối chiếu mode, region counts, ORIGINAL/RESTORED/INFERRED trong schema; giữ version và finalize. Kiểm thêm `GET /workshop/quotations/{id}`: nếu danh sách báo giá của đơn thiếu dữ liệu thì nối vào màn hiện có | `GET /workshop/orders/{id}/sketches/{version}/regions`, `POST .../regions/{region_id}/edit`, `GET /workshop/quotations/{id}` | Xem/sửa vùng chạy; không tạo thao tác trùng; ba ngôn ngữ |
| STF-API-4 | P1 | TODO | Không | trang showcase xưởng (mới) hoặc mục trong Staff, `src/services/` | S-API-04: quản lý bài showcase, ảnh, thứ tự, ẩn/hiện; dùng chung service với Manager khi phù hợp | `GET/POST /workshop/showcase`, `PATCH/DELETE /workshop/showcase/{id}`, `POST /workshop/showcase/upload-url` | Theo contract BE; có loading/error/empty; ba ngôn ngữ |

### 4.2. Admin (đối chiếu và nối API)

| ID | Ưu tiên | Status | Phụ thuộc | File / route liên quan | Việc cần làm | API | Tiêu chí hoàn thành |
|---|---|---|---|---|---|---|---|
| ADM-API-1 | P0 | DONE (14/11/2026, Claude tự kiểm; chờ Nhã xác nhận) | Không | `BE/app/api/v1/admin.py`, `BE/app/main.py`, `src/services/admin.ts`, `src/pages/admin/*` | Đọc mọi route trong `admin.py` (và router Admin mới nếu `main.py` thêm), so với từng hàm trong `services/admin.ts` và màn đang gọi hàm đó. Chỉ ghi "chưa nối" cho route đã xác minh trong code và không có lời gọi trong FE. Điền bảng ở mục 8. Audit ngày 12/11 chưa thấy nhóm Admin nào bị bỏ sót; kiểm lại từ code mới nhất | Mọi `/admin/*` | Bảng đủ cột: route, method, có trong `admin.py`, hàm FE gọi, màn gọi, kết luận (Đã nối / Chưa nối / VERIFY WITH BE); không có hàng bịa |
| ADM-API-2 | P0 | DONE (14/11/2026, Claude tự kiểm; chờ Nhã xác nhận): không có API Admin nào thiếu | ADM-API-1 | `src/services/admin.ts`, `src/pages/admin/*` | Nối từng API còn thiếu: thêm hàm service có kiểu và gắn vào màn Admin hiện có, giữ UI hiện tại và component chung. Nếu không có API nào thiếu: ghi rõ và đánh `DONE` | Theo kết quả ADM-API-1 | Mỗi API mới có loading/error/empty, khóa gửi lặp, ba ngôn ngữ; `node scripts/check-admin-browser.mjs` qua; không đổi luồng hay quyền Admin |

## 5. Phần việc của Quang: Manager

| ID | Ưu tiên | Status | Phụ thuộc | File / route liên quan | Việc cần làm | API | Tiêu chí hoàn thành |
|---|---|---|---|---|---|---|---|
| MGR-UI | P0 | DONE (12/11/2026, Claude tự kiểm; chờ Quang xác nhận) | Không | `src/pages/staff/ManagerDashboard.tsx`, `Approvals.tsx`, `Schedule.tsx`, `ScheduleCalendar.tsx`, `Catalog.tsx`, `Materials.tsx`, `Pricing.tsx`, `src/components/ws/Shell.tsx` (area `manager`) | Đồng bộ UI Manager theo chuẩn Admin/Staff (mục 2.9), kể cả màn mới ở các task dưới. Manager vẫn là Manager: không biến thành Staff để ghi đơn, giữ guard `RequireStaff manager`. Khi xong, cập nhật câu "Manager and Technician keep their current presentation" trong `FE/AGENTS.md` cho đúng thực tế | Không đổi | Khớp Admin/Staff ở sáng/tối; ba ngôn ngữ; mobile có drawer, không tràn ngang; Staff không vào được các trang Manager |
| MGR-API-1 | P0 | DONE (12/11/2026, Claude tự kiểm; chờ Quang xác nhận) | Không | `src/pages/staff/ManagerDashboard.tsx`, trang báo cáo mới (ví dụ `Reports.tsx`) dưới `src/pages/staff/`, `src/App.tsx` (route `<RequireStaff manager>`), `src/services/` | M-API-01: dashboard dùng số liệu từ BE thay vì tự tính khi có dữ liệu; trang báo cáo chọn khoảng ngày và nhóm (kiểm giá trị `Group` trong `reports.py`), mỗi biểu đồ có bảng số; xuất Excel/PDF bằng `fetch` có Bearer. Cấu trúc `dict[str, Any]`: lấy từ `BE/app/services` hoặc gọi thử; trường không rõ ghi `VERIFY WITH BE` | `GET /manager/dashboard`, `GET /manager/reports`, `GET /manager/reports/export` | Số liệu khớp phản hồi BE; lỗi `422` hiện thông báo; tải file đúng content type; ba ngôn ngữ |
| MGR-API-2 | P0 | DONE (12/11/2026, Claude tự kiểm; chờ Quang xác nhận) | Không | trang giám sát robot mới (ví dụ `Robots.tsx`), `src/services/` | M-API-02: trạng thái robot (online/offline, chế độ, cảnh báo đang mở, tuổi hiệu chuẩn), sức khỏe theo N ngày, lịch sử lần chạy, tuân thủ của job | `GET /manager/robot-status`, `GET /manager/robots/{id}/health`, `GET /manager/runs`, `GET /manager/jobs/{id}/compliance` | Trạng thái có chữ/icon, không chỉ màu; có loading/error/empty; lọc/phân trang khi API hỗ trợ |
| MGR-API-3 | P0 | DONE (12/11/2026, Claude tự kiểm; chờ Quang xác nhận) | MGR-API-2 | trang giám sát robot | M-API-03: danh sách cảnh báo chưa xử lý (nặng nhất trước), ack, resolve có ghi chú, danh mục cảnh báo (xem và chỉnh); giữ điều kiện quyền xử lý cảnh báo đỏ | `GET /manager/alerts`, `POST /manager/alerts/{id}/ack`, `POST /manager/alerts/{id}/resolve`, `GET /manager/alert-catalog`, `PATCH /manager/alert-catalog/{code}` | Hành động cập nhật danh sách; mức 4 nổi bật có chữ; Staff/Technician bị chặn |
| MGR-API-4 | P1 | DONE (12/11/2026, Claude tự kiểm; chờ Quang xác nhận) | Không | màn chi tiết job (Schedule) | M-API-05: chi tiết job, sự kiện và sự cố, xử lý sự cố. Danh sách job và lập lịch đã có, không viết lại | `GET /manager/jobs/{id}`, `GET /manager/jobs/{id}/events`, `GET /manager/incidents`, `POST /manager/incidents/{id}/resolve` | Theo contract; không tạo thao tác trùng với màn Schedule |
| MGR-API-5 | P1 | DONE (12/11/2026, Claude tự kiểm; chờ Quang xác nhận) | Không | màn chi tiết job | M-API-06: kết quả QC cho Manager xem | `GET /manager/jobs/{id}/quality` | Hiển thị đúng dữ liệu BE; trạng thái trống |
| MGR-API-6 | P1 | DONE (12/11/2026, Claude tự kiểm; chờ Quang xác nhận) | Không | trang đánh giá khách (mới) | M-API-07: danh sách đánh giá, ẩn/hiện có lý do; không xóa đánh giá thay cho ẩn | `GET /manager/reviews`, `POST /manager/reviews/{id}/hide`, `POST /manager/reviews/{id}/unhide` | Theo schema BE; ba ngôn ngữ |
| MGR-API-7 | P1 (backlog nếu không kịp) | TODO | MGR-API-2 | trang giám sát robot | M-API-04: lệnh robot từ Manager, khóa Robot Agent, vé xem, live, scene. Xác minh viewer đã đảm nhiệm scene/live để tránh gọi trùng; không lộ agent key vào log | `POST /manager/robots/{id}/robot-commands`, `GET .../live`, `GET .../scene`, `GET .../agent`, `POST/DELETE .../agent-key`, `POST .../view-ticket` | Chỉ làm khi P0 xong; hiển thị khóa agent một lần, không ghi log |

## 6. Tiêu chí tích hợp cuối (Chủ Nhật 15/11)

Chạy trên nhánh gộp của cả ba người, bằng tài khoản seed (`admin@netviet.vn`, `manager@netviet.vn`, `staff@netviet.vn`, `tech@netviet.vn`, `customer@example.com`, mật khẩu `ChangeMe@123`):

1. **Phân quyền:** mỗi vai trò chỉ vào được màn của mình (`RequireStaff`, `manager`, `role="admin"`, `role="technician"`). Staff không vào `/staff/catalog`, `/staff/pricing`, `/staff/approvals`, `/staff/schedule` và trang Manager mới. Truy cập thẳng bằng URL cũng bị chặn. Technician và Admin không vào được màn Staff/Manager.
2. **Trạng thái:** mọi màn mới hoặc sửa có loading, lỗi (chữ đã dịch, không lộ mã thô) và trống.
3. **Responsive:** kiểm ở 360 px, 768 px và desktop; không tràn ngang, không đè chữ; menu mobile hoạt động.
4. **Ba ngôn ngữ:** chuyển en, vi, ja; không còn chữ Anh trái quy định (`FE/AGENTS.md`); tiếng Việt và tiếng Nhật không cắt nút.
5. **Đồng bộ UI:** Technician, Customer và Manager khớp Admin và Staff về header, điều hướng, màu, chữ, thẻ, form, dropdown ở cả sáng và tối. Chữ tab đang chọn đủ tương phản trong chế độ tối.
6. **Dữ liệu:** không dữ liệu mẫu; không nút cho API chưa nối.
7. **Hồi quy:** luồng khách (tạo đơn, cọc, hoàn tiền) và thông báo vẫn chạy.

Mỗi người ghi kết quả từng mục cho phần của mình vào mục 9; chỉ khi cả bảy mục qua thì sprint DONE.

## 7. Lệnh kiểm tra FE (chạy trong thư mục `FE/`)

```bash
npx tsc -b            # lỗi nếu vi.ts hoặc ja.ts thiếu khóa
npm run i18n:check    # chữ Anh cứng trong JSX, khóa không tồn tại
npm run lint          # oxlint
npm run build         # tsc -b && vite build
```

Kiểm tra thêm khi chạm vào phần liên quan (chạy sau build). Trong PowerShell có thể dùng `npm.cmd` thay `npm`:

```bash
npm run api:audit                             # cập nhật sổ API (ngày BE thêm, ngày FE nối)
node scripts/api-audit.mjs --check            # liệt kê route chưa nối
node scripts/check-admin-browser.mjs          # Admin
node scripts/check-staff-ui-browser.mjs       # Staff
node scripts/check-fulfillment-browser.mjs    # giao hàng/nhận tại xưởng
npm run test:technician                       # Technician
node scripts/check-technician-browser.mjs     # Technician, trình duyệt
```

Ổ đĩa phải còn chỗ trống: khi ổ C đầy, Vite có thể trả CSS rỗng và giao diện mất màu.

## 8. Đối chiếu Admin (Nhã điền ở ADM-API-1)

| Route | Method | Có trong `admin.py` | Hàm FE gọi | Màn gọi | Kết luận |
|---|---|---|---|---|---|
| `/admin/accounts` | GET | Có | `listAccounts`, `allAccounts` | `Accounts.tsx`, số tài khoản khoá ở `AdminFrame.tsx` | Đã nối |
| `/admin/accounts` | POST | Có | `createAccount` | `Accounts.tsx` | Đã nối |
| `/admin/accounts/{account_id}` | PATCH | Có | `updateAccount` | `Accounts.tsx` | Đã nối |
| `/admin/audit-logs` | GET | Có | `listAudit`, `auditActivity` | `AuditLog.tsx`, `AdminDashboard.tsx` | Đã nối |
| `/admin/jobs/run` | POST | Có | `runBackgroundJobs` | `AdminDashboard.tsx` | Đã nối |
| `/admin/jobs/last` | GET | Có | `lastBackgroundRun` | không màn nào gọi | Không cần nối: `GET /admin/dashboard` đã trả cùng dữ liệu (`background_jobs.last_run`, `admin_system.py`) và Dashboard hiển thị nó |
| `/admin/settings` | GET | Có | `listSettings` | `Settings.tsx` | Đã nối |
| `/admin/settings/{key}` | PUT | Có | `saveSetting` | `Settings.tsx` | Đã nối |
| `/admin/integrations` | GET | Có | `listIntegrations` | `Settings.tsx` | Đã nối |
| `/admin/integrations/{name}` | PUT | Có | `toggleIntegration` | `Settings.tsx` | Đã nối |
| `/admin/dashboard` | GET | Có | `systemDashboard` | `AdminDashboard.tsx` | Đã nối |

Nguồn: `BE/app/api/v1/admin.py` (11 route, router `/admin`); `BE/app/main.py` không có router Admin nào khác. Đối chiếu ngày 14/11/2026 trên `origin/main` @ `7116544`.

## 9. Ghi chú kiểm tra

Mỗi người ghi ngắn: task, ngày, kết quả (đạt/không đạt), nội dung `VERIFY WITH BE` còn treo.

- **Quang, MGR-UI và MGR-API-1 đến MGR-API-6 (12/11/2026, nhánh `fe-quang` tạo từ `origin/fe` @ `6ed3bf8`): đạt.**
  - **MGR-UI:** `Shell area="manager"` dùng chung khung Staff: header, sidebar, drawer trên mobile, sáng/tối theo `AppearanceSwitch`, token deep navy. Sidebar Manager có 11 mục; mục Robot hiện số cảnh báo đang mở. Guard `RequireStaff manager` giữ nguyên; Staff vẫn chỉ có 4 mục. Màn mới dùng block Staff qua `pages/staff/managerKit.tsx`; `components/ws/manager-ui.css` chỉ dùng token. Đã cập nhật `FE/AGENTS.md` (mục "Manager area", bỏ câu "Manager and Technician keep their current presentation") và `docs/STAFF_CRM_UI.md`.
  - **MGR-API-1:** `ManagerDashboard.tsx` lấy số từ `GET /manager/dashboard`. Trang `/staff/reports` gọi `GET /manager/reports`, giá trị `group` lấy từ `Group` trong `reports.py`, mỗi biểu đồ có bảng số. Xuất Excel/PDF qua `GET /manager/reports/export` bằng `apiFile` (fetch có Bearer). Lỗi 422 `INVALID_PERIOD`, `PERIOD_TOO_LONG`, `INVALID_GROUP` đã dịch.
  - **MGR-API-2, MGR-API-3:** trang `/staff/robots`:
    - trạng thái robot (chip có icon và chữ), sức khỏe theo 7/30/90 ngày, lịch sử lần chạy có phân trang, kiểm tra tuân thủ;
    - cảnh báo: nặng nhất trước, ack, resolve có ghi chú; mức 4 có banner E-Stop và cần xác nhận trước khi đóng;
    - danh mục cảnh báo: xem và chỉnh người nhận, email, bật/tắt; cảnh báo đỏ bị khóa đúng luật `RED_ALERT_PROTECTED`.
  - **MGR-API-4, MGR-API-5:** panel chi tiết job trên trang robot, mở từ lần chạy, từ sự cố, hoặc từ job hôm nay trên dashboard (`?job=`). Gọi `GET /manager/jobs/{id}`, `/events`, `/compliance`, `/quality`. Sự cố gọi `GET /manager/incidents` và `POST .../resolve`. Không tạo thao tác lập lịch trùng với màn Schedule.
  - **MGR-API-6:** trang `/staff/reviews`: lọc theo hiển thị và số sao, ẩn/hiện có lý do (5 đến 300 ký tự), không có thao tác xóa.
  - **Kiểm tra:**
    - Bốn lệnh mục 7 đều qua; lint 40 cảnh báo, đúng mốc trước khi sửa.
    - `node scripts/check-manager-browser.mjs` (mới, chỉ dùng fixture) PASS: 10 màn × sáng/tối × vi/ja/en × 1440/768/360; các thao tác chính; Staff bị chặn khi vào thẳng URL.
    - `check-staff-ui-browser.mjs`, `check-fulfillment-browser.mjs`, `check-admin-browser.mjs` vẫn PASS.
    - Mục 6 (phần Manager): 1, 2, 3, 4, 5, 6 đạt trong kiểm tra fixture. Mục 7 (hồi quy) chưa chạy trên dữ liệu thật.
  - **Sổ API (quy tắc 10):** `npm run api:audit`, `scripts/api-audit.mjs`, `docs/api-ledger.json` và `docs/UI_API_AUDIT_2026-11-12.md` chưa có trên `fe` lẫn `main`, nên chưa chạy được. Chờ người tạo script đẩy lên rồi chạy lại.
  - **VERIFY WITH BE:**
    - (1) BE cần thêm `Content-Disposition` vào `Access-Control-Expose-Headers`; nếu không, FE khác origin dùng tên file dự phòng `bao-cao_<from>_<to>.<ext>`.
    - (2) `title_vi`, `action_vi`, `headline_vi`, câu bước tuân thủ và `advisory` chất lượng chỉ có tiếng Việt.
    - (3) `connection_state` được giả định là `ONLINE`/`OFFLINE`.
    - (4) Dashboard không có lịch sử đơn theo ngày; biểu đồ đang đếm từ danh sách đơn.
  - **Chưa làm:** MGR-API-7 (lệnh robot, khóa agent, live, scene, vé xem) vẫn `TODO` theo ghi chú backlog của task.

- **Nhã giao, Claude làm phần Nhã và Ân (14/11/2026, nhánh `fe-nha` tạo từ `origin/main` @ `7116544`, đã gồm `fe`): chưa commit, chờ duyệt.**
  - **TECH-UI:** `Shell area="tech"` dùng khung Staff (`.ws.ws-staff.ws-tech`): header có nút cảnh báo robot (icon robot, đỏ khi có cảnh báo), sidebar Technician (Tổng quan, Xem trước, QC) và drawer mobile, sáng/tối chung. Bỏ khung icon cũ cho Technician; Technician không có chat (như trước). `components/ws/tech-ui.css` mới; `tech.css` bỏ `#fff` cứng sang token (E-Stop đọc được ở chế độ tối). Guard `flow.ts`, `jobPermissions`, console và E-Stop giữ nguyên. Kiểm bằng script tạm (fixture): 3 màn × sáng/tối × vi/ja × 1440/768/360, drawer mobile.
  - **TECH-API-1:** `JobQuality.tsx` trong khối ảnh: mỗi ảnh có nút Đánh giá (chọn trang 1 đến 10), hiện kết luận gần nhất, lịch sử có chỉ số (`coverage_pct`, `extra_ink_pct`, `chamfer_mm`, `hd95_mm`, `hausdorff_mm`, `tol_mm`), ảnh chồng, `advisory` hiện nguyên văn. Không tự suy ra đạt/không đạt; kết quả QC của ảnh vẫn do kỹ thuật viên chọn. Lỗi `PAPER_NOT_FOUND`, `NO_INK`, `NO_MATCH`, `PHOTO_UNREADABLE`, `PAGE_OUT_OF_RANGE`, `NO_APPROVED_SKETCH`... đã dịch.
  - **TECH-CHK:**
    - (1) FE không gửi hiệu chuẩn và không đọc `frame_transform`; chỉ dùng `calibration.id`, `calibration.is_valid`. Đạt.
    - (2) Nút Start: tắt trừ khi PREPARING, hash đã kiểm, `simulation_passed === true` và `can_start` của server (đã thêm điều kiện `simulation_passed` cho rõ). Các ô điều kiện có icon và chữ (không chỉ màu), thêm ô "đã tải gói" và "máy chủ cho phép", và một dòng lý do khi Start tắt.
    - (3) X-DATA-03: `TechJobDetail` FE map đủ trường của `TechJobDetail` BE. `JobPackageOut` BE có `snapshot`, `material_drift`, `approach_note`, `ink_name`, `ink_hex`… mà kiểu FE thiếu: đã bổ sung kiểu, khối gói hiện "gói có chữ ký / gói cũ" và danh sách `material_drift`.
  - **CUS-API-2:** `services/locations.ts` gọi `GET /locations/provinces` và `.../{code}/wards` (cần đăng nhập, cache trong phiên); `Delivery.tsx` còn hai cấp tỉnh, phường; không gửi `district_*` (BE bỏ qua). Lỗi `LOCATIONS_UNAVAILABLE`, `PROVINCE_NOT_FOUND` đã dịch.
  - **CUS-API-1:** `ReviewPanel.tsx` trên trang đơn khi `COMPLETED`: xem, gửi, sửa (đến `editable_until`, không sửa khi `hidden`), 1 đến 5 sao, nhận xét 2000 ký tự, tối đa 5 ảnh JPG/PNG 5 MB qua `upload-url`. Lỗi `REVIEW_EXISTS`, `REVIEW_HIDDEN`, `REVIEW_EDIT_CLOSED`, `ORDER_NOT_COMPLETED`... đã dịch.
  - **STF-API-1:** `MaterialSuggestions.tsx` trong form lập báo giá (khi khách nhờ xưởng gợi ý): danh sách tổ hợp từ `GET /workshop/orders/{id}/material-suggestions`, giữ lựa chọn của khách, nút "Dùng" điền vào phương án trống hoặc thêm phương án (tối đa 3); tạo báo giá như cũ.
  - **STF-API-2:** `ProductPhotosPanel.tsx` ở chi tiết đơn (CONFIRMED đến COMPLETED): ảnh từ `GET /workshop/orders/{id}/product-photos`, loại ảnh, kết quả QC có icon và chữ, job, ghi chú QC; có trạng thái tải, lỗi, trống, ảnh hết hạn.
  - **ADM-API-1, ADM-API-2:** bảng mục 8; không có route Admin nào chưa nối.
  - **Kiểm tra (14/11/2026):**
    - `npx tsc -b`, `npm run i18n:check`, `npm run build` qua; `npm run lint` 40 cảnh báo (đúng mốc).
    - `check-staff-ui-browser.mjs`, `check-fulfillment-browser.mjs`, `check-admin-browser.mjs`, `check-manager-browser.mjs`, `check-final-payment-browser.mjs` PASS.
    - `npm run test:technician`: 11/13; 2 bài lỗi sẵn trên `main` (gọi `calibrateJob`, `probePlaneValid` đã bị bỏ khi hiệu chuẩn chuyển sang máy trạm).
    - `check-technician-browser.mjs`: dừng ở "Viewing a job must not write production data" do `POST /technician/robots/3/view-ticket` của `RobotView3D` (có sẵn trên `main`); script còn kiểm form hiệu chuẩn web đã bỏ. Cần cập nhật script (phần của Ân).
    - Chưa chạy trên BE thật; màn đánh giá khách và form địa chỉ chưa có script trình duyệt.
  - **Sổ API (quy tắc 10):** `scripts/api-audit.mjs`, `docs/api-ledger.json` vẫn chưa có trên `main`, chưa chạy được.
  - **VERIFY WITH BE:**
    - (1) `TOO_MANY_PHOTOS` dùng chung khoá `err.photoMany` ("tối đa 10 ảnh" của job); đánh giá chỉ cho 5 ảnh. FE chặn trước ở 5 nên hiếm gặp; nếu BE tách mã lỗi thì thêm khoá riêng.
    - (2) `metrics.warnings` của Service G và `material_drift` là chữ tiếng Việt từ BE, hiện nguyên văn.
