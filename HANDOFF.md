# Handoff: AI-VHRS, tiến độ ngày 2026-10-29

## 1. Repo và trạng thái git
- **Monorepo** `AI-VHRS/`, nhánh `main`, HEAD `45c9e39`. Thư mục:
  - `FE/`: React 19 + Vite + TypeScript.
  - `BE/`: FastAPI, deploy tại https://ai-vhrs.onrender.com/api/v1.
  - `DesktopApp/`: Flutter, trước là `Mobile/`.
  - `robot_agent/`: Python, chạy ở máy trạm.
- **Đã commit (`45c9e39`):** bảng Điều khiển robot, khung 3D, chuông cảnh báo, top bar dính, ô tick chính sách riêng tư.
- **Chưa commit:** chỉ `FE/src/pages/create-order/create-order.css` (sửa ảnh upload tràn khung xem trước bên phải).
- **Tài khoản demo** (mật khẩu `ChangeMe@123`): `customer@example.com`, `staff@netviet.vn`, `manager@netviet.vn`, `admin@netviet.vn`, `tech@netviet.vn`.
- **Dữ liệu thật để thử:**
  - Robot FR3-01 (id 46), agent đang offline, có 5 cảnh báo mở (2 cảnh báo mức 4).
  - Job 276 đang chuẩn bị, job 275 đã xếp lịch, job 279 đã xong.

## 2. Đã làm ở FE web (`FE/src`)
| Việc | File chính |
|---|---|
| Bảng Điều khiển robot. Chỉ chạy REAL, lệnh gửi `POST /technician/robot-commands` kèm `idempotency_key`, rồi poll tới khi xong. Gồm 5 bước chuẩn bị (LOAD → PREFLIGHT → ghi mô phỏng → DRY_RUN → bắt đầu viết), các nút Viết/Tạm dừng/Dừng, số liệu sống, lịch sử lệnh | `pages/tech/RobotConsole.tsx`, `services/robot.ts` |
| Khung 3D luôn hiện, nằm trên bảng điều khiển. Là iframe trang `/viewer/robot.html` của BE, vé xem tự gia hạn trước khi hết hạn 1 phút | `pages/tech/RobotView3D.tsx`, `vite.config.ts` (proxy `/viewer`) |
| Chuông cảnh báo trên top bar. Ack/resolve cảnh báo; mức 4 chỉ Quản lý đóng được | `components/ws/RobotAlertBell.tsx`, `robot-bell.css` |
| Store dùng chung cho `GET /technician/robot-status`: poll 2 giây, dừng khi tab bị ẩn | `store/robotStatus.ts` |
| Top bar dính khi cuộn, có slot `pinned` để ghim thanh tiến độ của job dưới top bar | `components/ws/Shell.tsx`, `ws.css`, `pages/tech/JobDetail.tsx` |
| Bỏ form hiệu chuẩn (hiệu chuẩn gửi từ máy trạm bằng `robot_console.py calibrate`). Form mô phỏng nhập tay gập lại làm phương án dự phòng | `JobPreparation.tsx`, `flow.ts`, `services/technician.ts` |
| Xoá mô phỏng giả `sim.ts` và `SimCanvas.tsx` | |
| Ô tick đồng ý chính sách riêng tư ngay trên nút đặt cọc. Đơn ở `AWAITING_PRIVACY`: tick thì gọi `POST /orders/{id}/privacy`. Đơn ở `QUOTED`: tick chỉ ghi nhận trên trình duyệt | `pages/order/OrderReview.tsx`, `order.css` |
| Ảnh upload thu gọn vừa khung xem trước bên phải (**chưa commit**) | `pages/create-order/create-order.css` |

**Kiểm chứng FE** (đều đã qua): `npx tsc -b`, `npm run i18n:check`, `npm run lint`, `npm run build`.

## 3. Quyết định đã thống nhất
- **Chạy REAL:** robot chỉ chạy REAL, không có MOCK/SIM trên UI. DRY_RUN, RUN và ALIGN_START cần mã `AUTHORIZE-…` (người vận hành tự gõ, không tự điền) và hỏi xác nhận trước khi chạy.
- **Kết quả mô phỏng:** lấy từ kết quả LOAD + PREFLIGHT của agent rồi gửi `POST .../simulation`. Máy chủ kiểm lại và có thể đổi thành "không đạt".
- **Hiệu chuẩn:** không làm form trên web hay app; hiệu chuẩn gửi từ máy trạm.
- **Banner E-Stop đỏ:** luôn hiện khi có cảnh báo mức 4. Câu chữ cảnh báo của BE chỉ có tiếng Việt (`*_vi`) và được hiển thị như dữ liệu.
- **Chữ hiển thị:** mọi chữ phải có đủ en/vi/ja (xem `FE/AGENTS.md`), không dùng gạch ngang dài trong câu chữ.
- **Git:** không commit hay push khi chưa được yêu cầu. Code trong `BE/` theo `BE/CLAUDE.md`: không tự thêm dòng `Co-Authored-By: Claude`, không đổi schema khi chưa được duyệt.
- **DesktopApp:**
  - Mobile là app kỹ thuật viên dùng chung code Flutter với desktop.
  - Khung 3D là WebView: `webview_flutter` (Android/iOS/macOS) và `webview_windows` (Windows).
  - Không làm agent-session; app gửi lệnh qua BE giống web.

## 4. Việc tiếp theo: DesktopApp (Flutter)
- **Kế hoạch đã duyệt:** `/Users/lequang/.claude/plans/elegant-rolling-reddy.md`.
- **Bản thiết kế:** https://claude.ai/artifact/KMrBoiEaTL583g2yoDnS3A, gồm 5 màn desktop và 5 màn mobile. Chưa có phản hồi về bản thiết kế, nên cần chốt trước khi code.
- **Hiện trạng:** chỉ đăng nhập dùng API thật (`lib/features/auth`). Job, robot và QC đang chạy trên mock (`tech_store.dart`, `seed_orders.dart`, `sim/`, `qc_*`, `roster.dart`). Bộ sinh i18n `gen/` cũ không còn trong repo.

| Mốc | Nội dung |
|---|---|
| 2 | `data/tech_api.dart` và `data/robot_api.dart`: port 1-1 từ `FE/src/services/technician.ts` và `robot.ts` (SHA-256 bằng `package:crypto`). Thêm models `domain/job.dart`, `domain/robot.dart` và Riverpod providers (poll giống FE) |
| 3 | `app_shell.dart` thích ứng: rộng ≥1000 dùng rail trái + top bar; hẹp <700 dùng `NavigationBar` dưới. Theme `core/theme/ws_theme.dart` theo token FE `.ws` (nền `#ebe9e4`, thẻ trắng, accent `#d4401b`). Viết `tool/gen_i18n.dart` đọc `FE/src/i18n/*.ts` |
| 4 | Màn Tổng quan và Danh sách job (desktop master-detail) |
| 5 | Chi tiết job (gói job + hash, chuẩn bị, sự kiện/sự cố, viết xong) và Ảnh QC (`file_selector` trên desktop, `image_picker`/camera trên mobile) |
| 6 | Điều khiển robot, 3D WebView, chuông cảnh báo (popover trên desktop, bottom sheet trên mobile) |
| 7 | Xoá mock và màn cũ (`robot_preview_screen.dart`, `quality_check_screen.dart`), cập nhật README/project_summary. Kiểm chứng bằng `flutter analyze`, `flutter test`, `flutter run -d macos` với `tech@netviet.vn` (chỉ gọi API đọc), thử layout mobile |

## 5. Việc còn treo ở FE/BE
- **Giao hàng và thanh toán cuối chưa nối ở FE:** `delivery-quote`, `PUT delivery`, `payments/final`, `receipt`, `shipment`, `/locations`, `pickup/confirm`. Khách hiện bị kẹt ở trạng thái `AWAITING_FINAL_PAYMENT`.
- **Chat:** chỉ lấy `page_size=100`, mà BE sắp tin cũ trước, nên tin thứ 101 trở đi không bao giờ hiện. Ngoài ra `read_at` lưu trên tin nhắn (dùng chung cho mọi người đọc) chứ không theo từng người, vẫn chờ chọn hướng sửa.
- **Thiếu ở FE:** kiểu chữ theo đoạn (`text-styles`, `layout`), địa chỉ hồ sơ hai cấp (`PATCH /me addresses`), Service G (`evaluate`), các màn vận hành robot cho Quản lý.
- **Deploy:** cần thêm origin của Vercel vào `CORS_ORIGINS` của BE thì khung 3D mới nhúng được ở bản production.
- **Robot thật chưa từng chạy:** muốn thử phải có agent online, `real-enable` tại máy trạm và người vận hành xác nhận.
