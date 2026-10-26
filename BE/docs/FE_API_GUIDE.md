# AI-VHRS – Hướng dẫn kết nối API cho Frontend

> Dành cho: đội FE (web + Flutter) cần biết **gọi API nào, theo thứ tự nào, nhận gì về** để nối giao diện.
> Cập nhật lần cuối: **2026-10-22, tới Phase 4f** (thanh toán VNPay/MoMo/payOS, chọn dịch vụ vận chuyển, vận đơn, chat; xem `../PROJECT_STATUS.md` để biết dự án đang tới đâu).
> Nguồn sự thật tuyệt đối là Swagger (`/docs`): file này giải thích **luồng** và **quy ước**, Swagger cho **schema chi tiết**.

## 0. DANH SÁCH VIỆC FE CẦN LÀM (BE đã xong, FE chưa làm; cập nhật 2026-10-22)

Mỗi dòng trỏ tới mục có chi tiết. Đánh dấu khi xong.

**Thanh toán (mục 5.3b, 5.3c, 7d)**
- [ ] **Thêm `vercel.json`** với rewrite SPA `{"rewrites":[{"source":"/(.*)","destination":"/index.html"}]}`: thiếu thì `/payment/result` và mọi đường dẫn sâu bị 404 trên Vercel.
- [ ] **Trang `/payment/result`** (cổng đưa khách về đây kèm `?order_id=<id>`): poll `GET /orders/{id}` tới ~60 giây, gọi `POST /payments/{id}/refresh` một lần nếu còn `PENDING` (bỏ qua lỗi 502 của VNPay), rồi đưa khách về đơn. Không tin tham số của cổng.
- [ ] **`pages/order/Deposit.tsx`:** thêm lựa chọn **PAYOS** (đọc `GET /payments/gateways`, chỉ hiện cổng `enabled`); khi `PaymentOut.pay_url` có giá trị thì `window.location.assign(pay_url)` và không chạy luồng mock; nhãn "MOCK" chỉ hiện khi `mode === "MOCK"`; thêm `pay_url`, `pay_url_expires_at`, `qr_code`, `bank`, `needs_refund` vào kiểu `Payment` trong `services/orders.ts`.
- [ ] **payOS:** hiện hạn của mã (`pay_url_expires_at`) và cho tạo mã mới khi hết hạn; thông báo "đã chuyển sai số tiền" khi `needs_refund`. Khi test, trang `pay.payos.vn/web/<id>` từng không mở được trên trình duyệt của chủ dự án (nghi sao chép sai đường dẫn): hãy thử luồng redirect thật và báo lại BE nếu vẫn lỗi. Tuỳ chọn: tự vẽ QR từ `qr_code`.
- [ ] **Màn thanh toán cuối** (`POST /orders/{id}/payments/final`, mục 7d).

**Giao hàng (mục 7d, 7e)**
- [ ] Thanh công cụ soạn chữ cho đơn viết theo mẫu: cỡ chữ, nghiêng, gạch chân, gạch ngang, giãn dòng + xem trước (`GET /catalog/text-styles`, `POST /catalog/templates/{id}/preview`, mục 5.1b). Không có chữ đậm.
- [ ] Form địa chỉ **tỉnh/thành → phường/xã** (hai cấp, `GET /locations/...`, mục 7d-2; bỏ ô quận/huyện) cho hồ sơ và đơn hàng.
- [ ] Màn **chọn hãng + dịch vụ vận chuyển** (`POST /orders/{id}/delivery-quote`, rồi `PUT /orders/{id}/delivery` với `carrier`, `service_code`), xử lý `FEE_CHANGED`. Chỉ còn hãng GHN.
- [ ] Màn **xem vận đơn** của khách (`GET /orders/{id}/shipment`) và màn Staff tạo vận đơn / nhãn PDF (`/workshop/orders/{id}/shipment`).

**Chat (mục 5.4)**
- [ ] **Gửi thẻ đơn qua API** (`POST /orders/{id}/messages {kind:"ORDER_CARD"}`) thay cho state tạm trong `store/chatDock.ts`; hiển thị tin `ORDER_CARD` (từ `order_card`) cho **cả khách và Staff/Manager**.
- [ ] `services/chat.ts` dùng **`GET /me/conversations`** (khách) và **`GET /workshop/conversations`** (Staff/Manager) thay cho gọi `/messages` từng đơn; badge nút chat dùng **`GET /me/conversations/unread-count`** (hoặc `/workshop/...`).
- [ ] **Bỏ việc khoá ô nhập khi đơn `COMPLETED`** (BE vẫn cho nhắn; chỉ `REJECTED`/`CANCELLED` là đã đóng).
- [ ] **Staff: ngừng ẩn các đơn chưa ai nhận** trong danh sách chat (BE trả cả đơn mình phụ trách lẫn đơn `SUBMITTED` chưa ai nhận). Khi khách nhắn đơn chưa ai nhận, FE khách có thể hiện "Đơn chưa có nhân viên nhận, xưởng sẽ trả lời sớm" (Manager trả lời được, Staff chưa nhắn được).

**Robot, hiệu chuẩn, mẫu chữ mới (mục 7b, 7.1; chi tiết `docs/ROBOT_INTEGRATION.md`)**
- [ ] **Màn hiệu chuẩn của Technical Staff** gửi thêm khối `frame_transform = {schema:"vhrs-motion/1", motion:{…}, workspace:{…}}` (các trường ở mục 7b); hiển thị `UNCONFIGURED` khi thiếu số đo.
- [ ] Sau `POST .../simulation`, **đọc kết quả của server** (`passed` có thể bị server đổi thành `false`) và hiện danh sách lỗi `SERVER …`; `GET /technician/jobs/{id}` có `can_start`.
- [ ] **App Technical Staff điều khiển robot qua BE** (mục 7g, KHÔNG gọi máy trạm trực tiếp): gửi lệnh bằng `POST /technician/robot-commands`, hỏi kết quả bằng `GET /technician/robot-commands/{id}`; luôn hiện nhãn chế độ MOCK / SIM / REAL và trạng thái kết nối agent (`GET /technician/robots/{id}/live` → `agent_online`).
- [ ] **Danh sách mẫu chữ:** có thêm 4 mẫu `kind = "TYPOGRAPHY"` (Playpen Sans, Pangolin, Patrick Hand, Mali Light, `font_uri` dạng `outline:fonts/...`); `GET /catalog/templates/{id}/preview?text=` trả PNG (tối đa 80 ký tự với mẫu này, lần đầu có thể chậm ~3 giây). Hiển thị cảnh báo "thứ tự nét do hệ thống dựng lại" nếu cần.

**Bản sao số 3D của robot (mục 7g)**
- [ ] **Xem 3D = nhúng trang do BE phục vụ** (cách chắc chắn nhất, không cần viết three.js): gọi `POST /technician/robots/{id}/view-ticket` → mở `<BE>` + `viewer_path` trong WebView (mobile) hoặc `<iframe>` (web). Trang chỉ-đọc, tự cập nhật 4 lần/giây, tự hiện cảnh báo đỏ "NHẤN NÚT E-STOP". Vé sống 60 phút: hết hạn thì xin vé mới và nạp lại. Chi tiết và phương án tự vẽ ở mục 7g.3. Nút Tạm dừng/Tiếp tục/DỪNG của FE nằm **ngoài** khung 3D và gọi `POST /technician/robot-commands`.
- [ ] **Ảnh phác thảo cho khách** (mục 5.2, 6): `GET /orders/{id}/quotation` → `sketch.image_urls[]` (JPG) là ảnh khách xem để quyết định đặt cọc; Staff dùng `image_urls[]` + `trajectory_url` (file chạy của robot) ở `GET /workshop/orders/{id}/sketches/{v}`.
- [ ] **Đánh giá chất lượng bản viết** (mục 7c.2): sau khi tải ảnh QC, nút "Đánh giá" gọi `POST /technician/jobs/{id}/photos/{photo_id}/evaluate`; hiện `verdict`, số đo mm và `overlay_url`; luôn kèm dòng `advisory` (chỉ tham khảo).

**Vận hành robot: cảnh báo, tình trạng, tuân thủ quy trình (mục 7f)**
- [ ] **Màn Technical Staff:** poll `GET /technician/robot-status` (2 giây) hiển thị `headline_vi`, `level` 1–4, `open_alerts[]` (`title_vi` + `action_vi`), nút "Đã thấy" (`POST /technician/alerts/{id}/ack`) và "Đóng" (`.../resolve`, mức 4 bị chặn). **Mức 4 = banner đỏ nhấp nháy + còi + chữ "BẤM NÚT E-STOP NGAY"**; không bao giờ ẩn banner đỏ khi chưa có Manager đóng.
- [ ] **Màn Manager:** `GET /manager/robot-status`, `GET /manager/robots/{id}/health`, `GET /manager/alerts`, `GET /manager/jobs/{id}/compliance` (từng bước đạt/không + ngoại lệ), `GET /manager/runs`, `GET/PATCH /manager/alert-catalog`.
- [ ] Cảnh báo mức 4 cũng được **gửi email** (BE làm); FE không cần gửi.

**Chưa có ở BE (đừng chờ):** đẩy tức thời (SSE/WebSocket), thông báo in-app và email, huỷ sau cọc và hoàn tiền (xem mục 10).

## 1. Kết nối nhanh

| Mục | Giá trị |
|---|---|
| Base URL | `<host>/api/v1` (local: `http://localhost:8000/api/v1`) |
| Swagger UI | `<host>/docs` (bấm **Authorize**, nhập email vào `username`) |
| Health check | `GET /api/v1/health` |
| Content-Type | `application/json` (trừ upload file: PUT thẳng lên link ký sẵn) |
| Xác thực | Header `Authorization: Bearer <access_token>` |
| Thời gian | ISO-8601 có múi giờ (UTC hoặc `+07:00`). FE tự hiển thị giờ VN |
| Tiền | VND, số nguyên. **Decimal trả về dạng chuỗi** (`"399600"`, `"50.00"`): dùng `Number()`/`BigInt`, đừng cộng chuỗi |
| Enum | Chuỗi IN HOA, ví dụ `AWAITING_DEPOSIT` |

Chạy local: `cd BE && source .venv/bin/activate && python -m uvicorn app.main:app --reload --port 8000`.
Tài khoản demo (mật khẩu chung do nhóm giữ): `customer@example.com`, `staff@netviet.vn`, `manager@netviet.vn`, `tech@netviet.vn`, `admin@netviet.vn`.

### Quy ước chung

**Lỗi luôn cùng một dạng** (hiển thị `message` cho người dùng, xử lý logic theo `code`):
```json
{"error": {"code": "INVALID_DEPOSIT", "message": "Tiền cọc phải từ 50% đến 100% ...", "details": {"min_deposit_pct": "50.00"}}}
```
Lỗi nhập liệu (422 `VALIDATION_ERROR`) có `details = [{"field": "quantity", "message": "..."}]`: gắn lỗi vào đúng ô nhập.

**Phân trang**: `?page=1&page_size=20` → `{items, total, page, page_size}`.

**Mã HTTP**: `401` chưa đăng nhập/hết phiên · `403` sai vai trò · `404` không tồn tại **hoặc không phải của bạn** (cố ý, để không lộ dữ liệu người khác) · `409` sai trạng thái/xung đột · `422` dữ liệu sai · `429` gọi quá nhanh (đọc header `Retry-After`) · `503` dịch vụ phụ chưa cấu hình.

**Phân biệt 403 và 404**: gọi sai vai trò → 403. Gọi đúng vai trò nhưng đơn của người khác → 404.

## 2. Vai trò và phạm vi

| Vai trò | Làm được gì | Không làm được |
|---|---|---|
| `CUSTOMER` | Tạo/sửa/gửi/huỷ đơn của mình, duyệt báo giá, đặt cọc, chat, **xem ảnh sản phẩm, nghiệm thu hoặc yêu cầu viết lại** | Xem đơn người khác, bất kỳ API `/workshop`, `/manager` |
| `STAFF` | Hàng đợi, nhận/tiếp nhận/từ chối đơn, phác thảo AI, lập & gửi báo giá, chat với khách | Đơn của Staff khác, `/manager/*`, đổi bảng giá, tự duyệt giá vượt ngưỡng |
| `MANAGER` | **Xem** mọi đơn đã gửi, xem phác thảo/báo giá/chat; **phân công Staff**, **duyệt/từ chối giá vượt ngưỡng**, vật tư/tồn kho/mẫu chữ/duyệt bộ nét/robot, **bảng giá + ngưỡng %**, lập lịch sản xuất | **Không** tiếp nhận/từ chối đơn, tạo phác thảo, lập/chỉnh/gửi báo giá (tách nhiệm vụ: người duyệt không tự làm). **Được** nhắn tin với khách để xử lý khiếu nại |
| `TECHNICAL_STAFF` | Chỉ **job được giao cho mình**: xem job, tải gói job + hash, chuẩn bị, hiệu chuẩn, ghi kết quả mô phỏng, bắt đầu/kết thúc viết, báo sự kiện an toàn, báo sự cố, **tải ảnh sản phẩm + QC rồi nộp ảnh** (`/technician/*`) | Job của người khác (trả `404`), đơn/khách/giá, `/manager/*`. **Không** điều khiển robot |
| `ADMIN` | Tài khoản, vai trò, nhật ký hệ thống (`/admin/*`) | **Không** xem/sửa đơn, giá, sản xuất (BR-02) |

Bản nháp (`DRAFT`) chỉ chủ đơn thấy; xưởng không thấy cho tới khi khách bấm gửi.

### Bảng quyền theo nhóm endpoint (BE kiểm tra từng request)

| Nhóm | Customer | Staff | Manager | Technical | Admin |
|---|:-:|:-:|:-:|:-:|:-:|
| Công khai: `/health`, `/catalog/papers|pens|templates`, `/privacy-policy`, đăng ký/đăng nhập/làm mới/quên mật khẩu | ✔ | ✔ | ✔ | ✔ | ✔ |
| Mọi vai trò đã đăng nhập: `/me*`, `/auth/logout` | ✔ | ✔ | ✔ | ✔ | ✔ |
| `/orders/*` (đơn của mình), `/pricing/estimate`, `/catalog/my-styles`, thanh toán cọc, `/payments/{id}/mock-checkout` | ✔ | ✘ | ✘ | ✘ | ✘ |
| Chat `/orders/{id}/messages` (đọc, gửi, ảnh, đánh dấu đã đọc) | ✔ | ✔ | ✔ (xử lý khiếu nại) | ✘ | ✘ |
| `/workshop/*` **đọc** (GET: hàng đợi, chi tiết, phác thảo, báo giá, PDF, payments, jobs, **product-photos**) | ✘ | ✔ | ✔ | ✘ | ✘ |
| `/workshop/*` **ghi** (claim, accept, reject, request-info, phác thảo, báo giá, điều chỉnh, gửi, huỷ báo giá) | ✘ | ✔ | ✘ | ✘ | ✘ |
| `/manager/*` (phân công, duyệt giá, vật tư, mẫu chữ, robot, bảng giá, lịch sản xuất, **sự cố, nhật ký job**) | ✘ | ✘ | ✔ | ✘ | ✘ |
| `/technician/*` (job của tôi, gói job, hiệu chuẩn, mô phỏng, viết, sự kiện, sự cố, ảnh sản phẩm + QC) | ✘ | ✘ | ✘ | ✔ (chỉ job được giao) | ✘ |
| `/admin/*` (tài khoản, nhật ký hệ thống) | ✘ | ✘ | ✘ | ✘ | ✔ |
| `POST /webhooks/payments/{gateway}` | không dùng token: xác thực bằng chữ ký HMAC | | | | |

**Cách hoạt động:** đăng nhập → nhận `access_token` (JWT) → gắn `Authorization: Bearer <token>` vào MỌI request. BE giải token, **đọc lại tài khoản và phiên từ DB mỗi lần** (khoá tài khoản, đăng xuất, đổi vai trò có hiệu lực ngay) và lấy **vai trò từ DB, không từ nội dung token**. Thiếu/sai/hết hạn token → `401`; đúng token nhưng sai vai trò → `403 FORBIDDEN`. Bảng trên được test tự động cho **từng route** (`tests/test_permission_matrix.py`); thêm endpoint mà quên khai báo quyền sẽ làm test đỏ.

## 3. Xác thực

```
POST /auth/register     {email, password(≥8, đủ mạnh), full_name, phone?}  → AccountOut
POST /auth/login        {email, password}  → {access_token, refresh_token, token_type, account{id,role,...}}
POST /auth/google       {id_token}         → cùng dạng như /auth/login (chỉ khách hàng, xem 3.1)
POST /auth/refresh      {refresh_token}    → cặp token mới
POST /auth/logout       (Bearer)           → thu hồi phiên hiện tại
GET  /me                → AccountOut        PATCH /me {full_name?, phone?, addresses?}
POST /me/change-password, POST /auth/password-reset/request|confirm
```
### 3.1 Đăng nhập bằng Google (khách hàng)
1. FE dùng **Google Identity Services** (web) hoặc Google Sign-In SDK (Flutter) với **Web Client ID** của dự án, nhận `credential` (= Google **ID token**).
2. `POST /auth/google {"id_token": "<credential>"}` → trả `{access_token, refresh_token, account}` y như đăng nhập thường; từ đó dùng Bearer như mọi API.
3. Lần đầu: BE tự tạo tài khoản `CUSTOMER` theo email Google (họ tên lấy từ Google). Đã có tài khoản cùng email: đăng nhập vào tài khoản đó (khớp theo email, không phân biệt hoa/thường). Khách có thể đặt mật khẩu sau bằng "Quên mật khẩu".
4. Lỗi: `401 GOOGLE_TOKEN_INVALID` (token sai/hết hạn/không phải của app này), `401 GOOGLE_EMAIL_NOT_VERIFIED`, `403 GOOGLE_NOT_ALLOWED` (email thuộc Staff/Manager/Admin/Technical: dùng email + mật khẩu), `403 ACCOUNT_DISABLED`, `503 GOOGLE_NOT_CONFIGURED` (BE chưa có env `GOOGLE_CLIENT`), `503 GOOGLE_UNAVAILABLE`.
5. FE **không** gửi email/họ tên tự khai: chỉ gửi `id_token`; BE xác minh với Google.

- Access token sống **30 phút**, refresh token **7 ngày**. Lưu refresh token an toàn (Flutter: secure storage; web: ưu tiên bộ nhớ/`httpOnly` nếu có BFF).
- Khi nhận `401` với `code` = `TOKEN_EXPIRED` hoặc `NOT_AUTHENTICATED` → gọi `/auth/refresh` **một lần**, thử lại request; refresh cũng lỗi → về màn đăng nhập.
- Sai mật khẩu 5 lần → `423 ACCOUNT_TEMP_LOCKED` (khoá tạm 15 phút).
- Vai trò lấy từ `account.role` sau login: dùng để chọn menu, **nhưng quyền thật luôn do BE kiểm tra**.

## 4. Vòng đời đơn hàng (state machine)

`order_status` (trạng thái nghiệp vụ) và `production_status` (trạng thái sản xuất) là **hai trường riêng** trong mọi object đơn.

```mermaid
stateDiagram-v2
  [*] --> DRAFT: tạo đơn
  DRAFT --> SUBMITTED: customer submit
  SUBMITTED --> ACCEPTED: staff accept
  SUBMITTED --> NEED_INFO: staff request-info
  SUBMITTED --> REJECTED: staff reject
  NEED_INFO --> SUBMITTED: customer provide-info
  SUBMITTED --> CANCELLED: customer cancel
  NEED_INFO --> CANCELLED: customer cancel
  ACCEPTED --> AWAITING_PRIVACY: staff send quotation (khách chưa đồng ý chính sách)
  ACCEPTED --> QUOTED: staff send quotation (đã đồng ý trước đó)
  AWAITING_PRIVACY --> QUOTED: customer accept privacy
  AWAITING_PRIVACY --> CANCELLED: customer decline privacy / báo giá hết hạn
  QUOTED --> ACCEPTED: customer request-changes
  QUOTED --> AWAITING_DEPOSIT: customer approve quotation
  QUOTED --> CANCELLED: customer cancel / hết hạn 7 ngày
  AWAITING_DEPOSIT --> CONFIRMED: webhook cọc SUCCESS
  AWAITING_DEPOSIT --> CANCELLED: customer cancel
  CONFIRMED --> AWAITING_ACCEPTANCE: technician nộp ảnh (≥ 2 ảnh QC đạt)
  AWAITING_ACCEPTANCE --> AWAITING_FINAL_PAYMENT: customer accept / tự nghiệm thu sau 7 ngày
  AWAITING_ACCEPTANCE --> CONFIRMED: customer rewrite (1 lần miễn phí), production = REWRITE_REQUIRED
  AWAITING_FINAL_PAYMENT --> READY_TO_DELIVER: webhook thanh toán cuối thành công (hoặc không còn gì phải trả)
  READY_TO_DELIVER --> COMPLETED: Staff bàn giao tại xưởng (nhận tại xưởng)
  READY_TO_DELIVER --> DELIVERING: hãng vận chuyển báo đã lấy hàng (callback của hãng, sau khi Staff tạo vận đơn)
  DELIVERING --> COMPLETED: hãng báo DELIVERED (giao thất bại / hoàn về: đơn GIỮ ở DELIVERING)
```

`production_status`: `NOT_STARTED → PENDING_SCHEDULE (sau khi cọc xong) → SCHEDULED (Manager xếp lịch) → PREPARING → WRITING ⇄ PAUSED → WRITTEN → PHOTO_UPLOADED → FINISHED`; nhánh lỗi `FAILED`, `REWRITE_REQUIRED` quay lại `PENDING_SCHEDULE`. Hai bước đầu do Phase 3 làm; từ `PREPARING` trở đi là Phase 4.

### Bảng "trạng thái → màn hình khách thấy → nút được phép"

| `order_status` | Khách thấy | Hành động gọi |
|---|---|---|
| `DRAFT` | Đơn đang soạn | sửa vật tư, nhập nội dung, `submit`, xoá nháp |
| `SUBMITTED` | Chờ xưởng tiếp nhận | `cancel`, chat |
| `NEED_INFO` | Xưởng cần bổ sung (`info_request_note`) | sửa đơn, `provide-info`, `cancel` |
| `REJECTED` | Bị từ chối (`reject_reason`, `reject_note`) | chỉ xem |
| `ACCEPTED` | Xưởng đang làm phác thảo/báo giá | chat |
| `AWAITING_PRIVACY` | **Phải** đọc & đồng ý chính sách riêng tư mới xem được báo giá | `GET /privacy-policy`, `POST /orders/{id}/privacy` |
| `QUOTED` | Xem phác thảo + báo giá (hiệu lực `valid_until`) | `approve`, `request-changes`, `cancel` |
| `AWAITING_DEPOSIT` | Chờ cọc (`deposit_amount`) | `payments/deposit`, mock-checkout, `cancel` |
| `CONFIRMED` | Đã cọc, xưởng sắp xếp sản xuất (`production_status` cho biết bước; `REWRITE_REQUIRED` = đang viết lại) | chat |
| `AWAITING_ACCEPTANCE` | Sản phẩm đã viết xong, có ảnh thật để nghiệm thu (`awaiting_acceptance_at`) | `GET /orders/{id}/product-photos`, `accept`, `rewrite` (xem mục 7c). **Không huỷ được ở bước này** |
| `AWAITING_FINAL_PAYMENT` | Đã nghiệm thu (`accepted_product_at`); chờ thanh toán phần còn lại | `GET delivery-quote`, `PUT delivery`, `POST payments/final`, mock-checkout (mục 7d) |
| `READY_TO_DELIVER` | Đã thanh toán đủ; chờ nhận tại xưởng (`pickup_slot_*`) hoặc chờ hãng vận chuyển lấy hàng (`shipping_carrier`, `shipping_service_code`, `shipping_eta`) | chỉ xem. Nhận tại xưởng: Staff bàn giao → `COMPLETED`. Giao hàng: Staff tạo vận đơn, khách theo dõi bằng `GET /orders/{id}/shipment` (mục 7e) |
| `DELIVERING` | Hãng đã nhận hàng, đang giao; hiện mã vận đơn và `tracking_url` | `GET /orders/{id}/shipment`; giao thất bại thì đơn vẫn ở đây và Staff tạo vận đơn mới |
| `COMPLETED` | Đã nhận hàng (`completed_at`) | `POST /orders/{id}/receipt` (ghi `received_confirmed_at`), đánh giá (Phase 5) |
| `CANCELLED` | Đã huỷ (`cancel_reason`) | chỉ xem |

> **Chưa có thông báo đẩy** (Phase 4). FE hiện phải **poll** `GET /orders/{id}` (ví dụ mỗi 15–30 giây ở màn chi tiết đơn) hoặc làm mới khi người dùng mở màn hình.

## 5. Luồng Customer (từ ý tưởng tới đã cọc)

### 5.1 Chuẩn bị đơn
1. **Danh mục** (không cần đăng nhập): `GET /catalog/papers`, `GET /catalog/pens?paper_id=` (chỉ bút tương thích với giấy), `GET /catalog/pens/{id}/inks`, `GET /catalog/templates`, `GET /catalog/templates/{id}/preview?text=...` (ảnh PNG xem thử). Bộ nét đã lưu: `GET /catalog/my-styles`.
2. **Giá ước tính**: `POST /pricing/estimate {order_type, quantity, paper_type_id?, pen_type_id?, ink_color_id?, text? | order_id?}` → `{chars_min, chars_max, price_min, price_max, min_deposit_pct, basis, note}`. Hiển thị **khoảng giá**; không bao giờ bắt khách tự nhập số ký tự (hệ thống tự đếm).
3. **Tạo đơn**: `POST /orders {order_type, quantity}` → đơn `DRAFT`. Loại đơn đang mở cho khách do hệ thống cấu hình: hiện **chỉ `OT1_COPY_RESTORE` và `OT3_TEMPLATE`** (OT-2 bị khoá, lỗi `409 ORDER_TYPE_SUSPENDED`).
4. **Chọn vật tư theo thứ tự giấy → bút → mực.** Sau khi khách chọn giấy, gọi **`GET /catalog/suggest-materials?paper_type_id=`** (công khai) → `{paper, pens:[{id,name,category,surcharge,..., inks:[{id,name,hex_code,unit_price}]}]}`: chỉ gồm các bút **tương thích** với giấy đó, mỗi bút kèm màu mực còn bán; hiển thị để khách chọn (không cần gọi thêm `/catalog/pens` và `/pens/{id}/inks`). Khách không thể chọn bút/mực không phù hợp (BE từ chối `422 PEN_INCOMPATIBLE`), nên không cần cảnh báo chất lượng.
   **"Để xưởng chọn"** (`workshop_suggest_materials:true`): khách **giữ nguyên** những gì đã chọn (có thể chỉ chọn giấy, hoặc giấy + bút) và để trống phần còn lại; Staff chỉ điền phần thiếu (bút, mực… vẫn theo luật tương thích) và đề xuất 1–3 phương án, khách chọn một khi duyệt báo giá. Chọn đủ cả ba thì không còn gì để xưởng đề xuất.
   `PATCH /orders/{id} {paper_type_id, pen_type_id, ink_color_id | workshop_suggest_materials:true, quantity, customer_note}`; bút/mực sai tương thích → `422 PEN_INCOMPATIBLE / INK_REQUIRES_PEN`. Mọi thay đổi khi còn nháp được **tự lưu** (có `last_saved_at`); danh sách nháp: `GET /orders?status=DRAFT`.
5. **Nội dung theo loại đơn**:

| Loại đơn | Gọi |
|---|---|
| `OT3_TEMPLATE` (viết theo mẫu) | `PUT /orders/{id}/inputs/text {text_content, template_id, font_size_mm? (4–100 mm), alignment?, layout?}` (`layout` = cỡ chữ/kiểu chữ theo đoạn, mục 5.1b); vẽ tay: `PUT /orders/{id}/inputs/canvas {canvas_data:{strokes:[{points:[{x,y,p}]}]}}` (x,y theo **mm**) |
| `OT1_COPY_RESTORE` (sao chép) | **Upload ảnh 3 bước** (bên dưới) |

**5.1b Cỡ chữ và kiểu chữ theo đoạn (đơn viết theo mẫu, FR-08).** Ngoài `font_size_mm` chung, khách có thể đổi **cỡ chữ**, **nghiêng**, **gạch chân** (đơn/đôi), **gạch ngang** cho từng đoạn và chỉnh **giãn dòng**. **Không có chữ đậm.** Kiểu chữ **không đổi giá** (báo giá vẫn theo số ký tự × độ phức tạp, và độ phức tạp được tính như khi chưa có kiểu chữ).
- `GET /catalog/text-styles` (không cần đăng nhập) → giới hạn để dựng thanh công cụ: `min_font_size_mm: 4`, `max_font_size_mm: 100`, `default_font_size_mm: 8`, `line_spacing {min 0.8, max 2.5, default 1}`, `styles`, `underline: ["single","double"]`, `max_spans: 200`.
- `layout` gửi kèm `PUT /orders/{id}/inputs/text`:
```json
{"version": 1, "line_spacing": 1.2,
 "spans": [{"start": 0, "end": 12, "size_mm": 14, "italic": true, "underline": "single"},
           {"start": 20, "end": 27, "strike": true}]}
```
  `start`/`end` là vị trí ký tự **theo code point** trong nội dung **đã chuẩn hoá NFC**, khoảng `[start, end)` (khác chỉ số UTF-16 của JavaScript: dùng `Array.from(text.normalize('NFC'))` để đếm). Đoạn không nêu thuộc tính nào thì giữ cỡ chung và chữ thường; các đoạn không được chồng nhau, tối đa 200. Cỡ chữ của đoạn: 4–100 mm. **PUT thay thế toàn bộ**: không gửi `layout` nghĩa là xoá định dạng; sửa nội dung phải gửi lại `layout` cho khớp vị trí. Sai → `422 INVALID_LAYOUT` (`details` nói đoạn nào). Cỡ chữ chung dưới 4 mm → `422 VALIDATION_ERROR`.
- Xem trước: `POST /catalog/templates/{id}/preview {text (≤200), font_size_mm?, alignment?, layout?}` → ảnh PNG trang đầu (A5), không cần đăng nhập, 60 lần/phút/IP; mẫu `TYPOGRAPHY` tối đa 80 ký tự. `GET .../preview?text=` cũ vẫn dùng được (không có kiểu chữ).
- `InputOut.layout` trả đúng dạng đã lưu (đoạn theo thứ tự, bỏ giá trị mặc định); layout không đổi gì thì lưu `null`. Lúc Staff sinh phác thảo, nghiêng/gạch chân/cỡ chữ được vẽ thành nét thật (gạch chân là một nét thẳng dưới mỗi dòng của đoạn); layout hỏng → `422 INVALID_LAYOUT`.
- Cỡ tối thiểu 4 mm là giả định tạm (chưa thử với bút thật); độ nghiêng cố định khoảng 12°.

**Upload ảnh/PDF – 3 bước** (jpg/png/pdf, ≤ 20 MB, ≤ 10 tệp):
```
1) POST /orders/{id}/inputs/upload-url {kind:"ORIGINAL_IMAGE", mime_type:"image/jpeg", size_bytes}
      → {input_id, upload_url, method:"PUT", expires_in}
2) PUT <upload_url>   body = file thô, header Content-Type = mime_type      (gọi thẳng Supabase Storage, KHÔNG qua BE, KHÔNG kèm Bearer)
3) POST /orders/{id}/inputs/{input_id}/confirm → InputOut {quality_result, is_quality_warning, ...}
```
Sau `confirm`, BE kiểm tra chất lượng + ước lượng số ký tự; nếu `is_quality_warning` hãy gợi ý chụp lại nhưng vẫn cho đi tiếp. Xoay/cắt: `PATCH .../inputs/{input_id} {rotation_deg, crop_box}`. Mở lại nháp cần ảnh: `GET .../inputs/{input_id}/file` (link hết hạn sau 10 phút, đừng cache lâu).

6. **Gửi đơn**: `POST /orders/{id}/submit {terms_accepted:true}` → `SUBMITTED`. Thiếu nội dung/vật tư → `422 ORDER_INCOMPLETE` (kèm `details` cho biết thiếu gì).

### 5.2 Nhận phác thảo & báo giá
- `NEED_INFO` → khách sửa rồi `POST /orders/{id}/provide-info {terms_accepted:true}`.
- Khi xưởng gửi báo giá, đơn sang `AWAITING_PRIVACY` (hoặc `QUOTED` nếu khách đã đồng ý bản chính sách hiện hành):
  1. `GET /privacy-policy` (public) → `{version, title, body}`; hiển thị toàn văn.
  2. `POST /orders/{id}/privacy {accept:true}` → `QUOTED`. `{accept:false}` → đơn **bị huỷ**; hãy hỏi xác nhận trước khi gọi.
  3. Trước bước này `GET /orders/{id}/quotation` trả `403 PRIVACY_REQUIRED`.
- `GET /orders/{id}/quotation` → `{status, line_items[], options[], final_total, min_deposit_pct, eta, valid_until, pdf_url, sketch{image_urls[], preview_urls[], estimated_writing_sec, ...}}`. **`sketch.image_urls[]` là ảnh JPG phác thảo (mực, độ dày nét và loại giấy đúng như đơn) để khách xem rồi quyết định đặt cọc**, mỗi trang một ảnh, đặt trong thẻ báo giá / `ORDER_CARD`; `preview_urls` giữ để tương thích (bằng `image_urls` khi có). Ảnh là hình dung **kế hoạch** nét viết, không phải ảnh chụp kết quả. `pdf_url` và các link ảnh là **link hết hạn sau 10 phút**: lấy lại khi cần.
  - Báo giá **1 phương án**: `options` có 1 phần tử. Khách chọn "để xưởng gợi ý" có thể có **2–3 phương án vật tư**: bắt khách chọn 1.
  - `valid_until` quá hạn: lần gọi kế tiếp thấy `status:"EXPIRED"` và đơn `CANCELLED` (đếm ngược 7 ngày trong UI).
- Không đồng ý: `POST /orders/{id}/quotation/request-changes {note}` → đơn về `ACCEPTED`, xưởng lập lại; hoặc `POST /orders/{id}/cancel {reason}`.

### 5.3 Duyệt báo giá và đặt cọc
```
POST /orders/{id}/quotation/approve {option?: 1..3, deposit_pct?: số}      → OrderOut (order_status = AWAITING_DEPOSIT)
      - deposit_pct: từ min_deposit_pct (trong quotation) tới 100; bỏ trống = mức tối thiểu
      - đơn nhiều phương án bắt buộc có `option`
      - OrderOut mới có total_amount, deposit_pct, deposit_amount
POST /orders/{id}/payments/deposit {gateway:"VNPAY"|"MOMO"}                → PaymentOut {id, amount, status:"PENDING", mode:"MOCK", checkout_path, gateway_txn_id}
POST /payments/{payment_id}/mock-checkout {result:"SUCCESS"|"FAILED"}      → {result, status, order_status}
GET  /orders/{id}/payments                                                 → lịch sử giao dịch
```
- **Hai chế độ (xem mục 5.3b):** mặc định thanh toán là **MOCK**; khi máy chủ bật cổng thật thì `mode` là `SANDBOX` (môi trường thử của VNPay/MoMo) hoặc `LIVE` (tiền thật) và giao dịch trả `pay_url`. Phần dưới mô tả MOCK.
- **Thanh toán MOCK** (`mode:"MOCK"`): không có tiền thật. FE nên hiện nhãn "Thanh toán mô phỏng" khi `mode == "MOCK"` và nút "Thanh toán thành công / thất bại" gọi `mock-checkout`.
- Cổng thật sau này sẽ trả URL chuyển hướng; `checkout_path` là chỗ FE đọc để mở trang thanh toán. Kết quả luôn tới BE qua **webhook** (FE không báo kết quả thanh toán cho BE); sau khi thanh toán xong, FE chỉ cần poll `GET /orders/{id}` tới khi `order_status = CONFIRMED`.
- Thất bại (`status:"FAILED"`): đơn vẫn `AWAITING_DEPOSIT`, gọi lại `payments/deposit` để thử lần mới. Gọi lại cùng cổng khi còn giao dịch `PENDING` sẽ **dùng lại** giao dịch đó.
- Cọc xong: `order_status = CONFIRMED`, `production_status = PENDING_SCHEDULE`. Từ đây khách **không tự huỷ online được** (`409 ORDER_CANCEL_UNSUPPORTED`: chính sách hoàn tiền ở Phase 4): hiển thị "Liên hệ xưởng".

### 5.3b Thanh toán thật qua VNPay / MoMo (Phase 4c-2a)

`PAYMENT_MODE` của máy chủ quyết định: `mock` (mặc định), `sandbox` (cổng thử, tiền thử), `live` (tiền thật). FE đọc cổng nào dùng được và chế độ hiện tại:

```
GET  /payments/gateways                          → [{gateway: "VNPAY"|"MOMO", mode: "MOCK"|"SANDBOX"|"LIVE", enabled: bool}]   (khách; chỉ hiện cổng enabled)
POST /orders/{id}/payments/deposit {gateway}     → PaymentOut        (cọc)
POST /orders/{id}/payments/final   {gateway, expected_total?}        (thanh toán cuối, mục 7d)
POST /payments/{id}/refresh                      → {result, status, order_status}   hỏi cổng khi IPN trễ/mất
```
- **MOCK**: `PaymentOut.checkout_path` có giá trị, nút "thanh toán thử" gọi `mock-checkout` (như trên). `pay_url` là `null`.
- **SANDBOX / LIVE**: `PaymentOut.pay_url` là địa chỉ trang thanh toán của cổng, `pay_url_expires_at` là hạn (mặc định 15 phút); `checkout_path` là `null`. **FE chuyển trình duyệt của khách tới `pay_url`** (`window.location = pay_url`). `mock-checkout` bị từ chối (`409 NOT_A_MOCK_PAYMENT`).
- Sau khi trả tiền, cổng đưa khách về **trang kết quả của web app** (`PAYMENT_RETURN_URL`, hiện là `https://ai-vhrs.vercel.app/payment/result`; BE gắn thêm `?order_id=`) kèm tham số của cổng. **Đừng tin các tham số đó**: trang kết quả chỉ để hiển thị. Kết quả thật tới BE qua IPN của cổng. Trang kết quả nên: gọi `GET /orders/{id}` mỗi 2–3 giây tới khi `order_status` đổi (`CONFIRMED` sau cọc; `READY_TO_DELIVER` sau thanh toán cuối) tối đa ~30 giây; nếu giao dịch vẫn `PENDING`, gọi **`POST /payments/{id}/refresh`** một lần (BE hỏi thẳng cổng). `result`: `PROCESSED` (vừa cập nhật), `ALREADY_PROCESSED`, `IGNORED` + `status:"PENDING"` (cổng chưa có kết quả cuối).
- **Việc FE phải làm để thanh toán thật chạy (chưa làm, ghi cho team FE):**
  1. **Trang kết quả `/payment/result`** (hiện FE chưa có; chỉ có `/orders/:id/review` và `/orders/:id/deposit`). BE tự gắn `?order_id=<id đơn>` vào địa chỉ này, cổng thêm tham số của họ (VNPay `vnp_*`, MoMo `orderId`, `resultCode`...). Trang đọc `order_id` rồi làm theo đoạn trên (poll `GET /orders/{id}`, tối đa ~30 giây; còn `PENDING` thì `POST /payments/{id}/refresh` một lần với `id` lấy từ `GET /orders/{id}/payments`); xong thì chuyển khách về `/orders/{id}/review` (hoặc trang đơn). Không dùng tham số của cổng để quyết định đã trả tiền.
  2. **`Deposit.tsx`**: hiện chỉ chạy luồng mock (`startDeposit` rồi `mock-checkout`). Khi `PaymentOut.pay_url` khác `null` thì `window.location.assign(pay_url)` và không gọi `mock-checkout`; thêm `pay_url`, `pay_url_expires_at` vào kiểu `Payment` trong `services/orders.ts`; nhãn "MOCK" chỉ hiện khi `mode === "MOCK"`.
  3. **Rewrite cho SPA trên Vercel** (hiện chưa có `vercel.json`): `{"rewrites":[{"source":"/(.*)","destination":"/index.html"}]}`. Thiếu thì cổng đưa khách về `/payment/result` sẽ bị 404.
  4. Màn **thanh toán cuối**, **chọn hãng + dịch vụ vận chuyển** (`POST /orders/{id}/delivery-quote`) và **xem vận đơn** (mục 7d, 7e) cũng chưa có trên FE.
- **`refresh` với VNPay hiện có thể trả `502 GATEWAY_UNAVAILABLE`** (máy chủ BE chưa gọi được API truy vấn của VNPay từ nước ngoài; đã thấy ở sandbox). Đó không phải lỗi thanh toán: kết quả thật vẫn tới BE qua IPN. FE chỉ cần **bỏ qua lỗi này và tiếp tục poll `GET /orders/{id}`** (tới ~60 giây), đừng báo thanh toán thất bại.
- Giao dịch `FAILED` (khách huỷ/hết hạn trên cổng): đơn vẫn chờ, gọi lại endpoint thanh toán để tạo giao dịch mới. Gọi lại khi liên kết cũ còn hạn sẽ **dùng lại** giao dịch đó; hết hạn hoặc đổi cổng thì giao dịch cũ bị huỷ và tạo cái mới.
- `needs_refund: true` trên một giao dịch nghĩa là tiền đã về một giao dịch đã bị huỷ (khách trả muộn sau khi đổi ý): BE giữ bản ghi để hoàn tiền (Phase 4d); hãy hiện "Liên hệ xưởng".
- Lỗi riêng: `503 GATEWAY_NOT_CONFIGURED` (cổng chưa cấu hình trên máy chủ), `502 GATEWAY_UNAVAILABLE` / `502 GATEWAY_REJECTED` (cổng lỗi hoặc từ chối tạo giao dịch; không tạo giao dịch nào), `403 MOCK_WEBHOOK_DISABLED` (webhook mô phỏng bị tắt khi dùng cổng thật), `409 NOT_A_REAL_PAYMENT` (refresh giao dịch mô phỏng).
- FE **không** gọi các IPN: `GET /webhooks/payments/vnpay/ipn` và `POST /webhooks/payments/momo/ipn` là của cổng (xem mục 9).

### 5.3c Chuyển khoản VietQR qua payOS (Phase 4c-2d) — cổng thứ ba, `gateway = "PAYOS"`

Khách quét mã VietQR bằng app ngân hàng; tiền về **thẳng tài khoản ngân hàng của chủ xưởng**; payOS báo cho BE bằng webhook. **Không có môi trường test: mọi giao dịch PAYOS là chuyển khoản thật** (`mode = "LIVE"`), và cổng này bật ngay khi máy chủ có đủ khoá, bất kể `PAYMENT_MODE` (chế độ đó chỉ áp dụng cho VNPay/MoMo).

```
GET  /payments/gateways                       → thêm {"gateway":"PAYOS","mode":"LIVE","enabled":true|false}
POST /orders/{id}/payments/deposit   {"gateway":"PAYOS"}        → PaymentOut (cọc)
POST /orders/{id}/payments/final     {"gateway":"PAYOS", ...}   → thanh toán cuối (FINAL + SHIPPING trong MỘT mã QR, mục 7d)
GET  /orders/{id}/payments                    → trạng thái hiện tại (poll)
```

`PaymentOut` của PAYOS (khi còn `PENDING`) có thêm:
- `pay_url`: trang thanh toán của payOS (có QR và thông tin chuyển khoản). **Cách đơn giản nhất (đã chọn): `window.location.assign(pay_url)`.** payOS đưa khách về `PAYMENT_RETURN_URL?order_id=<id>` khi xong (thêm tham số `cancelled=1` nếu khách bấm huỷ trên trang payOS).
- `qr_code`: chuỗi VietQR (EMV), để FE **tự vẽ mã QR** sau này nếu muốn (thư viện QR bất kỳ, nội dung chính là chuỗi này). Số tiền và nội dung chuyển khoản đã nằm trong mã.
- `bank`: `{bin, account_number, account_name, amount, content}`: hiển thị cạnh mã QR để khách đối chiếu hoặc chuyển tay. **`amount` là số tiền phải chuyển (với thanh toán cuối là tổng FINAL + SHIPPING), `content` là nội dung chuyển khoản: phải đúng cả hai.**
- `pay_url_expires_at`: hạn của mã (mặc định 15 phút); hết hạn thì gọi lại endpoint để tạo mã mới.

Luồng giống mục 5.3b: sau khi khách chuyển khoản, **FE poll `GET /orders/{id}`** mỗi 2–3 giây (tới ~60 giây; ngân hàng có thể trễ vài chục giây) tới khi `order_status` đổi (`CONFIRMED` sau cọc, `READY_TO_DELIVER` sau thanh toán cuối). Kết quả thật chỉ tới BE qua webhook của payOS; trang kết quả chỉ để hiển thị. Gọi lại `POST /orders/{id}/payments/deposit` khi mã cũ còn hạn sẽ trả lại **đúng mã đó**; đổi cổng hoặc mã hết hạn thì mã cũ bị đóng (cả bên payOS).

Các tình huống cần UI xử lý:
- **Khách chuyển sai số tiền hoặc sửa nội dung:** tuỳ app ngân hàng có cho sửa hay không (BE không kiểm soát được). Chuyển **sai nội dung**: payOS không ghép được vào đơn, đơn không đổi, khách phải liên hệ xưởng hoặc tạo mã mới. Chuyển **sai số tiền** (thiếu hoặc thừa): đơn **không** được xác nhận, giao dịch giữ `PENDING` và có `needs_refund: true` (hiện "Liên hệ xưởng để được hoàn/bù tiền"); khách vẫn có thể chuyển đúng số tiền qua cùng mã trước khi hết hạn.
- **Hoàn tiền không tự động** (payOS không có API hoàn tiền cho chuyển khoản): Staff chuyển khoản ngược rồi xử lý theo quy trình hoàn tiền (Phase 4d).
- **Mã hết hạn / khách huỷ:** payOS chỉ báo webhook khi **đã nhận tiền**, nên `FAILED` không tự tới; FE hiện "Mã đã hết hạn" theo `pay_url_expires_at` rồi cho tạo mã mới. `POST /payments/{id}/refresh` hỏi thẳng payOS (trạng thái `EXPIRED`/`CANCELLED` → giao dịch `FAILED`; `PAID` → xác nhận), dùng khi nghi webhook trễ.
- Lỗi riêng: `503 GATEWAY_NOT_CONFIGURED` (máy chủ chưa có khoá payOS, `enabled:false` trong `/payments/gateways`: ẩn lựa chọn này), `502 GATEWAY_UNAVAILABLE` / `502 GATEWAY_REJECTED` (payOS lỗi hoặc từ chối tạo mã; không tạo giao dịch).
- FE **không** gọi webhook `POST /webhooks/payments/payos` (của payOS, mục 9).

### 5.4 Chat trong đơn
```
GET  /orders/{id}/messages?page=&page_size=     → {items[{id,mine,kind,order_card,body,attachments[{url,mime}],read_at,created_at}], total, unread}
POST /orders/{id}/messages {body?, attachments?:[{path}]}        → 201 MessageOut (tin chữ / ảnh)
POST /orders/{id}/messages {kind:"ORDER_CARD"}                   → 201 thẻ mới | 200 thẻ cũ (chỉ khách; xem dưới)
POST /orders/{id}/messages/read                  (đánh dấu đã đọc tin của bên kia)
POST /orders/{id}/messages/upload-url {mime_type:"image/jpeg"|"image/png", size_bytes ≤ 5MB} → {path, upload_url, method, expires_in}
```
Gửi ảnh: xin `upload-url` → `PUT` file → `POST messages` với `attachments:[{path}]`. Chat chỉ dùng được sau khi đơn đã gửi (`409 ORDER_NOT_SUBMITTED` nếu chưa) và còn mở (`409 ORDER_CLOSED` khi đơn bị **từ chối hoặc huỷ**); Staff phải nhận đơn trước khi nhắn (`409 ORDER_NOT_CLAIMED`). Tối đa 2000 ký tự và 5 ảnh mỗi tin.

**Đơn `COMPLETED` vẫn nhắn được** (BE giữ nguyên: chỉ `REJECTED` và `CANCELLED` là đã đóng) để khách còn khiếu nại sau khi nhận hàng. **FE không được khoá ô nhập khi đơn `COMPLETED`**; chỉ khoá khi `order_status` là `REJECTED`/`CANCELLED` (hoặc khi gọi gửi bị `409 ORDER_CLOSED`).

**Thẻ đơn hàng (`kind = "ORDER_CARD"`)** — thay cho state tạm ở `store/chatDock.ts`:
- Chỉ **khách** gửi được và luôn là thẻ của **chính đơn này** (`403 CARD_CUSTOMER_ONLY` nếu Staff/Manager gửi; `422 INVALID_CARD` nếu kèm `body` hoặc `attachments`). Không cần `body`.
- **Chống spam:** nếu đơn đã có thẻ trong **10 phút** gần nhất, BE trả lại **thẻ cũ** với HTTP **200** (không tạo tin mới, không báo lại cho xưởng); gửi mới thì **201**. FE cứ gọi, đừng cần tự chống trùng. Bấm đúp chỉ ra một thẻ.
- Mỗi tin trong danh sách có `kind` (`"TEXT"` hoặc `"ORDER_CARD"`). Với thẻ: `body = null`, `attachments = []`, và `order_card = {code, order_type, order_status, quantity, total_amount}` đọc từ **trạng thái hiện tại của đơn** (không phải bản sao lúc gửi), nên thẻ luôn khớp với đơn; `total_amount` là `null` tới khi báo giá được duyệt. **Cả hai phía thấy thẻ** (Staff/Manager đọc cùng `GET /orders/{id}/messages`).
- Với tin `TEXT`, `order_card` là `null`.

**Danh sách cuộc chat (một truy vấn, thay cho việc gọi `/messages` từng đơn):**
```
GET /me/conversations?page=&page_size=                   (khách)           → {items[], total, page, page_size}
GET /workshop/conversations?page=&page_size=             (Staff, Manager)  → như trên
GET /me/conversations/unread-count                       (khách)           → {unread: n}
GET /workshop/conversations/unread-count                 (Staff, Manager)  → {unread: n}
```
- Mỗi dòng: `{order_id, code, order_type, order_status, customer_name, last_message:{body, kind, has_attachment, created_at, mine}, unread}`. Chỉ có **đơn đã có ít nhất một tin nhắn**, sắp theo tin mới nhất trước; `page_size` mặc định 20, tối đa 100. `customer_name` chỉ có ở phía xưởng (`null` với khách). `last_message.body` là `null` khi tin cuối là thẻ hoặc chỉ có ảnh (dùng `kind` / `has_attachment` để hiện "[Thẻ đơn hàng]" / "[Hình ảnh]").
- Phạm vi: khách thấy đơn của mình (đã gửi); **Staff thấy đơn mình phụ trách và các đơn chưa ai nhận (`SUBMITTED`)**; Manager thấy mọi đơn đã gửi. Vì vậy **FE Staff không nên ẩn các đơn chưa ai nhận** nữa.
- `unread-count` chỉ là một con số (một truy vấn đếm, có chỉ mục): gọi thoải mái cho badge nút chat (15–60 giây/lần). `unread` đếm tin của **bên kia** chưa `read_at`; `POST /orders/{id}/messages/read` đánh dấu đã đọc. Lưu ý: `read_at` gắn vào tin nhắn, không theo từng người đọc, nên khi Staff và Manager cùng xem một đơn thì một người đọc là cả hai thấy đã đọc.

**Khách nhắn khi đơn chưa có Staff nhận:** tin vẫn được lưu; BE báo cho **mọi Manager đang hoạt động** (mã thông báo `MESSAGE_UNCLAIMED`; thông báo in-app/email ở Phase 4e, hiện mới ghi log). Staff đọc được nhưng **chưa nhắn được** cho tới khi nhận đơn (`409 ORDER_NOT_CLAIMED`); Manager trả lời được. FE khách có thể hiện dòng "Đơn chưa có nhân viên nhận, xưởng sẽ trả lời sớm".

**Chưa có:** thông báo tức thời (SSE/WebSocket): FE vẫn poll `unread-count` và `GET /orders/{id}/messages`.

## 6. Luồng Staff (`/workshop/*`; Manager chỉ đọc ở nhóm này)

Staff thấy **đơn được giao cho mình + "pool" đơn `SUBMITTED` chưa ai nhận** (chỉ đọc cho tới khi nhận). Manager **chỉ đọc** mọi đơn (trừ nháp); mọi thao tác ghi trong `/workshop/*` là của Staff. Đơn mới trong pool: Staff tự `claim`, hoặc Manager `PUT /manager/orders/{id}/assignment` giao cho một Staff.

```
GET  /workshop/orders?status=&order_type=&unassigned=&q=&eta_before=&page=   hàng đợi
GET  /workshop/orders/{id}                      chi tiết: inputs (ảnh có link 10 phút), cảnh báo chất lượng
POST /workshop/orders/{id}/claim                Staff tự nhận (nguyên tử: 1 người thắng, người kia 404/409)
POST /workshop/orders/{id}/accept | reject {reason: TOO_OLD|DAMAGED|MISSING_CONTENT|PROHIBITED_CONTENT|OTHER, note?} | request-info {note}
        (chỉ STAFF; Manager gọi các lệnh ghi này nhận 403)
PUT  /manager/orders/{id}/assignment {staff_id}      Manager phân công / đổi Staff
```
**Phác thảo (AI thật)** – chỉ khi đơn `ACCEPTED`:
```
POST /workshop/orders/{id}/sketches/generate {paper_size?, approach_note?, seed?}   OT-1: phục dựng nét từ ảnh; OT-3: sinh nét từ font một nét
POST /workshop/orders/{id}/sketches {trajectory, approach_note?, suggested_complexity?}   tải quỹ đạo vẽ tay (OT-2 / chỉnh sửa)
GET  /workshop/orders/{id}/sketches[/{version}]   danh sách / chi tiết (quỹ đạo + preview_urls từng trang)
PATCH .../sketches/{version} {approach_note, suggested_complexity}      POST .../sketches/{version}/finalize   (chốt đúng 1 bản)
```
`SketchOut` có `image_urls[]` (**JPG cho khách**, mỗi trang một ảnh), `preview_urls[]` (PNG kỹ thuật có chấm xanh đầu nét, chỉ để Staff xem), **`trajectory_url`** (link ký 10 phút tới file quỹ đạo JSON mà robot chạy; Staff xem/tải cùng ảnh) và `similarity_score` (độ giống bản gốc, OT-1), `suggested_complexity`, `estimated_writing_sec`, `warnings[]`. Lỗi AI thường gặp: `NO_STROKES_FOUND`, `IMAGE_TOO_NOISY`, `UNSUPPORTED_CHARS` (kèm danh sách ký tự), `TEXT_TOO_LONG`, `AI_TYPE_UNSUPPORTED` (OT-2 không có AI).

**Báo giá** (cần phác thảo đã chốt – BR-22):
```
POST /workshop/orders/{id}/quotations {complexity?, char_count?, options?:[{paper_type_id,pen_type_id,ink_color_id}] (≤3), eta?}
PUT  /workshop/quotations/{qid}/adjustment {adjusted_total, reason}     Staff điều chỉnh trong ngưỡng; vượt ngưỡng → chờ Manager
DELETE /workshop/quotations/{qid}/adjustment
POST /workshop/quotations/{qid}/send   (tạo PDF, hiệu lực 7 ngày)      POST .../cancel      GET .../pdf
GET  /manager/quotations/pending-approval      POST /manager/quotations/{qid}/approve-adjustment | reject-adjustment {reason}
```
- **Ngưỡng điều chỉnh** (mặc định ±15%) và tỷ lệ cọc tối thiểu do Manager cấu hình ở bảng giá (xem 7.2). Ngưỡng so **giá Staff nhập** với **giá hệ thống tính** của chính báo giá đó (không so với giá ước tính lúc khách đặt đơn). Giá không chỉnh thì gửi thẳng, không cần duyệt. Manager **không** tự chỉnh giá: giá vượt ngưỡng do Staff đặt, Manager duyệt/từ chối. `adjustment_status`: `NONE | WITHIN_THRESHOLD | PENDING_MANAGER | APPROVED | REJECTED`. Khi `PENDING_MANAGER` không gửi được (`409 APPROVAL_PENDING`).
- **Vật tư khi khách chọn "để xưởng chọn"**: `GET /workshop/orders/{id}/material-suggestions` → `{fixed (phần khách đã chọn), combos[{paper,pen,ink ids + tên}], total}` liệt kê các tổ hợp còn đề xuất được. Tạo báo giá `options:[{paper_type_id?,pen_type_id?,ink_color_id?}]` chỉ cần ghi **phần còn thiếu**; đổi thứ khách đã chọn → `422 MATERIAL_LOCKED_BY_CUSTOMER` (`details.field`), thiếu/không tương thích → `422 INVALID_MATERIALS`.
- Giá nhập tay là **tổng đơn**, bội số 100 đồng; báo giá nhiều phương án **không** điều chỉnh được (`422`).
- Lý do điều chỉnh của Staff **không** hiện cho khách.
- Đọc thêm tiền/lịch của một đơn: `GET /workshop/orders/{id}/payments`, `GET /workshop/orders/{id}/jobs` (chỉ đọc).
- Chat dùng chung endpoint với khách (`/orders/{id}/messages`); Manager cũng nhắn được cho khách để xử lý khiếu nại.

## 7. Luồng Manager (`/manager/*`)

## 7f. Vận hành robot: lần chạy, cảnh báo, tình trạng (migration 0008)

Robot Agent (máy trạm) gọi các route `/technician/*` bằng token của Technical Staff. Agent chỉ **gọi tên** cảnh báo; **mức, câu chữ và việc cần làm do bảng `alert_catalog` quyết định** (agent không thể báo thấp hơn thực tế).
Bốn mức: 1 xanh · 2 vàng (chú ý) · 3 cam (**robot đã tự dừng an toàn**: kiểm tra rồi tiếp tục/bỏ qua nét dở) · 4 đỏ (**bấm nút E-Stop vật lý ngay**, `estop_advised = true`, gửi email cho Technical Staff của job và mọi Manager đang hoạt động).

| Việc | Endpoint |
|---|---|
| Mở lần chạy | `POST /technician/jobs/{id}/runs {run_id, mode: MOCK\|SIM\|REAL, dry_run, authorized, plan_digest?, total_strokes, agent_version?, robot_info?, refused_reason?}` → 201. Chạy thử cần job `PREPARING`; chạy viết cần `WRITING`/`PAUSED`; **REAL cần `authorized:true`** (người vận hành đã xác nhận; BE ghi `authorized_by/at`; DB có CHECK). Một robot chỉ có **một** lần chạy đang mở (`409 ROBOT_BUSY`). `refused_reason` = lần chạy bị từ chối ở bước kiểm tra, lưu đã đóng với kết quả `REFUSED` |
| Đóng lần chạy | `PATCH /technician/runs/{run_id} {result: DONE\|STOPPED\|FAULT\|UNKNOWN\|DRY_RUN_DONE\|REFUSED, completed_strokes, total_strokes?, summary?}`; gọi lại cùng kết quả là idempotent, kết quả khác → `409 RUN_ALREADY_CLOSED` |
| Báo cảnh báo | `POST /technician/alerts {robot_id, code, job_id?, run_id?, details?}` (mã trong danh mục, sai mã → `422 UNKNOWN_ALERT`). Cảnh báo cùng (robot, mã, job) đang mở chỉ tăng `occurrences` |
| Xem cảnh báo | `GET /technician/alerts?open=true&min_level=&robot_id=&job_id=` (robot tôi phụ trách); Manager: `GET /manager/alerts` |
| Đã thấy / đóng | `POST /technician/alerts/{id}/ack`, `POST /technician/alerts/{id}/resolve {note}` (mức 1–3). **Mức 4 chỉ Manager đóng được** (`403 RED_ALERT_NEEDS_MANAGER`): `POST /manager/alerts/{id}/resolve {note}` |
| Heartbeat | `PUT /technician/robots/{id}/heartbeat {mode, controller_version?, firmware_version?, sdk_version?, agent_version?}` mỗi 1–5 giây; quá `offline_after_seconds` (15) coi là mất kết nối. Khi robot đang có lần chạy mở mà agent im lặng, BE tự báo `AGENT_OFFLINE` + `RUN_OUTCOME_UNKNOWN` (kiểm tra "lười" khi có người gọi các route status/alerts) |
| Tình trạng bằng lời thường | `GET /technician/robot-status` · `GET /manager/robot-status` → `[{robot_id, robot_code, state: OFFLINE\|IDLE\|PREPARING\|WRITING\|PAUSED_SAFE\|DANGER, headline_vi, level, mode, connection_state, last_seen_at, controller_version, sdk_version, agent_version, job_id, job_status, open_run, open_alerts[], calibration_age_minutes}]` |
| Sức khoẻ robot (Manager) | `GET /manager/robots/{id}/health?days=30` → số lần chạy theo kết quả/chế độ, giờ chạy, số lần dừng an toàn, cảnh báo theo mức, `in_band_pct_avg`, sự cố mở, cảnh báo đỏ chưa đóng |
| Lần chạy (Manager) | `GET /manager/runs?robot_id=&job_id=` |
| Có đúng quy trình không | `GET /manager/jobs/{id}/compliance` → `steps[{key, label_vi, status: PASS\|FAIL\|PENDING\|NOT_APPLICABLE, at, detail}]`, `exceptions[]`, `followed_process`. Các bước: gói khớp hash, hiệu chuẩn, máy chủ tự kiểm lại, mô phỏng, chạy thử pen-up, người vận hành xác nhận, viết xong, **có lần chạy robot thật hoàn tất** (job ghi nhận viết xong mà chỉ có MOCK/SIM bị đánh FAIL), ảnh QC |
| Danh mục cảnh báo | `GET /manager/alert-catalog`; `PATCH /manager/alert-catalog/{code} {title_vi?, action_vi?, notify_roles?, send_email?, threshold?, is_active?}` (mức không đổi được; cảnh báo đỏ không tắt được, không tắt email, không bỏ Technical Staff khỏi người nhận: `422 RED_ALERT_PROTECTED`). Cảnh báo đã phát giữ nguyên câu chữ lúc phát |

Mã cảnh báo: mức 4 `STOP_NOT_EFFECTIVE`, `LINK_LOST_MOVING`, `TRACKING_ERROR`, `CONTROLLER_SAFETY_FAULT`, `OVER_FORCE_STILL`; mức 3 `OVER_FORCE`, `SENSOR_LOST`, `STROKE_LOST`, `RUN_OUTCOME_UNKNOWN`, `STROKE_INTERRUPTED`; mức 2 `PREFLIGHT_REFUSED`, `CALIBRATION_OLD`, `FORCE_NEAR_LIMIT`, `DROPPED_FRAMES`, `AGENT_OFFLINE`; mức 1 `PAPER_CHANGE`.
Lỗi riêng: `404 ROBOT_NOT_FOUND`, `404 RUN_NOT_FOUND`, `404 ALERT_NOT_FOUND`, `409 RUN_EXISTS`, `409 ROBOT_BUSY`, `409 RUN_ALREADY_CLOSED`, `422 AUTHORIZATION_REQUIRED`, `422 UNKNOWN_ALERT`, `422 RESULT_INVALID`, `403 RED_ALERT_NEEDS_MANAGER`.
Phần mềm không bấm được E-Stop: câu chữ mức 4 luôn nói rõ điều đó. Email cần cấu hình SMTP (`SMTP_HOST`, ...); chưa cấu hình thì chỉ ghi log.

## 7g. Điều khiển robot qua BE (kiến trúc A, migration 0010, 0011)

**Mọi thứ liên quan robot là API của BE đã deploy.** Máy trạm chạy Robot Agent **gọi RA** BE (không mở cổng vào xưởng); app Technical Staff chỉ nói chuyện với BE. Lệnh là bản ghi bền trong DB, agent kéo về khoảng 1 lần/giây (4 lần/giây khi đang chạy). Không lệnh nào được gửi lại sau khi hết hạn.

```
App kỹ thuật viên ──POST robot-commands──▶ BE (Render) ◀──POST /agent/sync (agent gọi ra)── Máy trạm ── FR3 + gripper
        ▲  GET live / view-ticket (3D)  ◀── khung hình sống: khớp, bút, lực, cảnh báo ──────────┘
```

### 7g.1 Lệnh (Technical Staff; Manager chỉ PAUSE/RESUME/STOP)
`POST /technician/robot-commands {kind, job_id?, robot_id?, params, idempotency_key?}` → 201 `CommandOut {id, kind, status, result, error_code, expires_at, ...}`. Theo dõi `GET /technician/robot-commands/{id}` mỗi 0,5–1 giây tới khi `status` là `DONE` hoặc `FAILED`. Trạng thái: `PENDING` (chưa được agent lấy) → `DELIVERED` (agent đã nhận, đang làm) → `DONE` / `FAILED`; `PENDING` quá hạn (20 giây cho PAUSE/RESUME/STOP, 60 giây cho lệnh khác) → `EXPIRED` (**không chạy trễ**). `GET /technician/jobs/{id}/robot-commands` liệt kê lịch sử.

| `kind` | `params` | Điều kiện job | `result` khi `DONE` |
|---|---|---|---|
| `LOAD` | (không) | job đang hoạt động | tóm tắt job, `validation`, `plan_digest`, **`authorization_token`** (mã người vận hành xác nhận khi chạy THẬT), `scene` (cho 3D) |
| `PREFLIGHT` | `mode` | đang hoạt động | `{ok, moves, plan_digest}` hoặc `{ok:false, code, message}`; robot không di chuyển |
| `DRY_RUN` | `mode`, `speed?` | job `PREPARING` | `{started:true}`; chạy thử pen-up (bút không chạm giấy); xem kết quả qua `live` |
| `RUN` | `mode`, `authorization?`, `resume_from?`, `confirm_unknown?`, `speed?` | job `WRITING`/`PAUSED` (**bấm `POST /technician/jobs/{id}/start` trước**) | `{started:true}`; theo dõi bằng `live` |
| `PAUSE` / `RESUME` / `STOP` | (không) | có lần chạy | `{ok}`; `STOP` chỉ dừng phần mềm, **không thay nút E-Stop** |
| `PAPER_CHANGED` | (không) | đang đợi thay giấy | `{ok}` |
| `ALIGN_START` | `mode`, `authorization` (REAL) | job đang hoạt động | đưa đầu bút (người vận hành đã đặt gần điểm bắt đầu bằng tay) tới **điểm bắt đầu cố định của job** (trên tờ giấy, cách góc trái-trên 20 mm, ở độ cao nhấc bút + 2 mm) với **đúng góc viết**; một lệnh MoveL chậm, từ chối khi xa hơn 150 mm hoặc lệch góc quá 15°, hoặc đầu bút thấp hơn độ cao nhấc bút. `{moved, distance_mm, angle_deg, target_mm}`. Dùng khi `RUN` báo `START_ORIENTATION_MISMATCH`. Chạy REAL cần `real-enable` + mã `AUTHORIZE-…` như `DRY_RUN`; `STOP`/`PAUSE` dừng nó tại chỗ |
| `IDENTIFY` | `mode` | (không cần job; gửi `robot_id`) | nối **chỉ-đọc** lấy mẫu/phiên bản/tư thế robot rồi ngắt; không enable, không chuyển động |

`mode` là `MOCK` / `SIM` / `REAL`. `FAILED` kèm `error_code` của agent: `REAL_NOT_ENABLED_ON_SITE`, `MODE_DISABLED`, `AGENT_BUSY`, `JOB_NOT_LOADED`, `VALIDATION_FAILED`, `DRY_RUN_REQUIRED`, `PARTIAL_JOB_EXISTS`, `NO_RUN_ACTIVE`, ... (hiện `error_message` cho người dùng).
Lỗi tạo lệnh: `409 ROBOT_IN_USE` (robot đang do kỹ thuật viên khác điều khiển), `409 AGENT_OFFLINE` (máy trạm chưa kết nối: **không** xếp hàng; hiện "robot không liên lạc được, nếu nguy hiểm hãy nhấn E-Stop vật lý"), `409 JOB_STATE_CONFLICT` (sai trạng thái job), `409 JOB_NOT_ACTIVE`, `409 IDEMPOTENCY_KEY_REUSED`, `422 MODE_REQUIRED`, `422 AUTHORIZATION_REQUIRED` (RUN chạy REAL cần `authorization: "AUTHORIZE-<job>-<mã>"` lấy từ kết quả `LOAD`), `422 JOB_REQUIRED`, `404` khi không có job trên robot đó (BR-19), `403` khi Manager gửi lệnh khác PAUSE/RESUME/STOP.
Gửi `idempotency_key` (UUID mới cho mỗi lần bấm) để bấm đúp / mạng chập chờn không tạo hai lệnh.
**Chạy robot THẬT** vẫn cần ba điều độc lập mà lệnh từ xa không thay được: (1) `real` nằm trong `modes` của agent ở máy trạm; (2) **người ở máy trạm** chạy `cli real-enable --job N --minutes M` (gõ YES; file hết hạn, đúng job đó); (3) mã `AUTHORIZE-…` gắn kế hoạch + đã chạy thử pen-up. Quy trình đầy đủ: `docs/ROBOT_REAL_TEST_RUNBOOK.md`.

**Trình tự một job (app kỹ thuật viên):** `package` → `prepare` → `calibration` → `simulation` → `LOAD` → `PREFLIGHT` → `DRY_RUN` → (người vận hành xác nhận tại máy trạm khi chạy THẬT) → `POST /jobs/{id}/start` → `RUN` → theo dõi `live` → tới khi `status.busy=false` → `POST /jobs/{id}/finish` → ảnh QC.

### 7g.2 Trạng thái sống
`GET /technician/robots/{robot_id}/live?after=<last_seq>` (Manager: `/manager/robots/{id}/live`) → `{agent_online, age_s, mode, status{busy, current, last, state, level, ...}, last_seq, frames[]}`. Gọi **4–5 lần/giây** khi đang xem; truyền `after = last_seq` lần trước để chỉ nhận khung mới. Mỗi khung: `state, mode, tcp (mm), joints_deg (độ, j1..j6), move_kind, stroke, total_strokes, progress_pct, force_n, touching, level, alerts[], message`. `agent_online=false` (im lặng > 15 giây) → banner "mất kết nối máy trạm". `GET /technician/robots/{id}/scene` → tờ giấy, khung toạ độ, nét của job đã `LOAD`. Cảnh báo đỏ/cam/vàng vẫn lấy từ `robot-status` và `alerts` (mục 7f) và có thêm mã **`BACKEND_LINK_LOST` (mức 3, cam)**.

**Mất liên lạc agent ↔ BE khi đang viết (đã chốt):** sau ~6 giây không gọi được BE, agent viết nốt nét đang viết, nhấc bút, **tạm dừng** và hiện cảnh báo cam tại máy trạm; khi nối lại, nó báo `BACKEND_LINK_LOST` lên BE và **không tự tiếp tục**: kỹ thuật viên gửi `RESUME` hoặc `STOP`. Agent không thể dừng robot nó không liên lạc được: **nút E-Stop vật lý là an toàn thật**.

### 7g.3 Xem 3D (cách chọn và vì sao)
**Chọn: nhúng trang 3D do BE phục vụ** (FE không viết three.js). Lý do: một nguồn code duy nhất cho cả mobile (WebView) và web (iframe), mô hình robot và logic đặt tờ giấy/khớp đã được kiểm tra, cập nhật không cần phát hành lại app.
1. `POST /technician/robots/{robot_id}/view-ticket` (Manager: `/manager/robots/{id}/view-ticket`) → `{ticket, expires_in:3600, viewer_path, live_path, scene_path}`.
2. Mở `<BE_URL>` + `viewer_path` (ví dụ `https://<be>/viewer/robot.html?ticket=...`) trong WebView/iframe. Chiều cao tối thiểu 300 px; chạm-kéo để xoay, véo để thu phóng.
3. Hết vé (401 `INVALID_VIEW_TICKET`): xin vé mới và nạp lại. **Vé chỉ đọc**: không gửi được lệnh. Điều khiển luôn qua `robot-commands` bằng token của người dùng.
4. Web FE: thêm origin của FE vào `CORS_ORIGINS` của BE (BE dùng danh sách này cho `frame-ancestors`); nếu không iframe bị chặn.
Phương án tự vẽ (không khuyến nghị): three.js r160 + `urdf-loader` 0.12.1; URDF `GET /api/v1/robot-model/fairino3_v6.urdf` (công khai, cache 1 ngày), mesh `GET /api/v1/robot-model/meshes/fairino3_v6/{name}.STL`, `loader.packages = {fairino_description: "<BE>/api/v1/robot-model"}`; dữ liệu từ `viewer/{ticket}/live` và `viewer/{ticket}/scene` (không cần token); `joints_deg` theo độ, tên khớp `j1`..`j6`; hệ trục Z hướng lên, đơn vị mét (tcp/scene theo mm). Ghi chú trung thực: đây là **dữ liệu thật từ agent hiển thị lại**, không phải camera và không mô phỏng vật lý; mô hình giả định gốc URDF trùng gốc controller (chưa kiểm chứng trên robot thật).

### 7g.4 Khoá agent: đăng nhập là có (app desktop) và khoá của Manager (migration 0010, 0012)
**Đường chính (app desktop của technical staff): khoá theo phiên đăng nhập, không ai phải cấp tay.**
1. App đăng nhập bằng tài khoản technical staff (`/auth/login`), chọn robot mình đang giữ job (`GET /technician/robot-status` → `robot_id`).
2. `POST /technician/robots/{robot_id}/agent-session {instance_id}` → `201 {key, key_prefix, expires_at, renew_after_s}`. `instance_id` là UUID (hoặc chuỗi 8–64 ký tự `A-Za-z0-9_.-`) **sinh một lần mỗi lần mở app** và giữ nguyên cho mọi lần gia hạn. Chỉ technical staff **đang giữ job đang hoạt động trên robot đó** mới lấy được (không có thì `404`); Manager `403`.
3. App đưa `key` cho agent chạy trong app (chỉ trong bộ nhớ, **không ghi ra file**). Khoá sống ~4 giờ (`expires_at`).
4. **Gia hạn êm:** sau `renew_after_s` (~3 giờ) gọi lại đúng endpoint với **cùng `instance_id`**; khoá mới cấp ngay, khoá cũ còn dùng được thêm ~2 phút rồi hết hạn. Không có khoảng trống nên không sinh "mất liên lạc". Nếu gia hạn lỗi, giữ khoá cũ và thử lại sau 30 giây.
5. Đóng app: `DELETE /technician/robots/{robot_id}/agent-session?instance_id=...` → `204` (`409 RUN_OPEN` nếu robot còn lần chạy chưa kết thúc: dừng trước). App sập thì khoá tự hết hạn.

**Mỗi robot chỉ có một app điều khiển, không ai bị đẩy ra giữa chừng:** lấy khoá lần đầu (instance mới) bị `409 ROBOT_IN_USE` khi robot đang có agent online (kể cả cùng một người mở cửa sổ/máy thứ hai, hoặc agent dùng khoá của Manager), đang có lần chạy mở, hoặc có khoá vừa cấp chưa kịp kết nối (60 giây). Hiện lời báo "Robot đang do người khác điều khiển" và đừng thử lại liên tục. Khoá của app đã bỏ đi (offline, quá 60 giây, không có lần chạy mở) bị thay thế bởi lần đăng nhập mới. Khi một agent theo phiên đang online, kỹ thuật viên khác gửi lệnh nhận `409 ROBOT_IN_USE` (Manager vẫn PAUSE/RESUME/STOP).
Khoá phiên chỉ mở `/agent/*` và `/technician/*` **với tư cách đúng tài khoản đó** (cần còn job hoạt động trên robot); không tạo được lệnh, không xin được khoá khác.

**Đường phụ (máy trạm cố định, không cần ai đăng nhập): khoá của Manager.** `POST /manager/robots/{id}/agent-key` → `{key}` **chỉ hiện một lần** (BE chỉ lưu SHA-256); cấp lại thu hồi khoá Manager cũ (không đụng khoá phiên). `GET /manager/robots/{id}/agent` cho biết đã có khoá Manager chưa, agent `online`, `session_keys[]` đang hiệu lực và `controlled_by_account_id`. `DELETE /manager/robots/{id}/agent-key` thu hồi **mọi** khoá của robot (cắt ngay). Đặt khoá vào biến môi trường `VHRS_AGENT_KEY`, không commit.

### 7g.5 Agent API trong LAN (tuỳ chọn, để gỡ lỗi)
Agent vẫn có thể phục vụ trang điều khiển riêng trong LAN (`cli serve`, `lan_server:true`; đăng nhập bằng tài khoản hệ thống; `GET /api/agent`, `POST /api/login`, `/api/jobs/{id}/load|preflight|dry-run|run`, `/api/pause|resume|stop`, `WS /ws`...). Đây là đường phụ cho kỹ thuật viên đứng tại máy trạm; **FE không dựa vào nó**.

### 7.1 Vật tư, mẫu chữ, robot
| Việc | Endpoint |
|---|---|
| Giấy | `GET/POST /manager/papers`, `PATCH /manager/papers/{id}`, `POST /manager/papers/{id}/stock {mode:"ADD"\|"SET", quantity, reason}` |
| Bút (hồ sơ lực) | `GET/POST /manager/pens`, `PATCH .../{id}`, `POST .../{id}/stock` |
| Mực | `GET /manager/inks?pen_id=`, `POST /manager/pens/{id}/inks`, `PATCH /manager/inks/{id}`, `POST .../stock` |
| Tương thích giấy–bút | `GET /manager/compatibility`, `PUT /manager/compatibility/{paper_id}/{pen_id} {is_compatible, note?}` (thiếu dòng = **không** tương thích) |
| Mẫu chữ | `GET/POST /manager/templates`, `PATCH .../{id}` (bật/tắt qua `is_active`). `font_uri` dạng `hershey:<tên>` (font một nét) hoặc `outline:fonts/<tên>/<file>.ttf` (font có sẵn trong Storage, thêm bằng `scripts/add_outline_font.py`, không qua API) |
| Bộ nét chờ duyệt | `GET /manager/styles?status=`, `POST .../{id}/approve`, `POST .../{id}/reject {reason}` |
| Robot | `GET/POST /manager/robots`, `PATCH .../{id}`; đặt `MAINTENANCE`/`BROKEN` trả `affected_job_ids` (job cần xếp lại). Không đặt tay `BUSY` |

Không có xoá cứng: dùng `is_active:false` (khách không còn thấy nhưng đơn cũ vẫn tham chiếu được). Mọi thay đổi tồn kho cần `reason` và được ghi nhật ký.

### 7.2 Bảng giá có phiên bản (FR-30)
```
GET  /manager/pricing-config                  phiên bản đang áp dụng
GET  /manager/pricing-config/versions         mọi phiên bản (mới nhất trước)
POST /manager/pricing-config {…chỉ các trường muốn đổi…, note?}   → tạo phiên bản N+1 và áp dụng ngay
```
Trường: `u_ot1/2/3` (đ/ký tự), `w_min`, `s_ot1/2/3` (phí setup), `k_simple/medium/complex`, `discount_tiers[{min_qty,pct}]`, `p_min_pct` (cọc tối thiểu %), `adjust_threshold_pct` (ngưỡng điều chỉnh giá %), `canvas_mm_per_char`. Tiền là bội số 100. Báo giá đã lập **giữ nguyên** giá cũ; chỉ báo giá mới theo phiên bản mới. Lỗi `422 INVALID_PRICING` có `details[{field,message}]`; `422 NO_CHANGES` nếu không đổi gì.

### 7.3 Lập lịch sản xuất (đơn đã cọc)
```
GET  /manager/schedule/queue                       đơn PENDING_SCHEDULE / FAILED / REWRITE_REQUIRED (+ duration_min ước tính)
GET  /manager/orders/{id}/schedule-suggestion      ≤5 gợi ý {robot, technician, slot_start, slot_end, finish_by, eta_risk} + stock_warnings
POST /manager/orders/{id}/schedule {robot_id, technician_id, slot_start, note?}   → JobOut (201)
POST /manager/jobs/{id}/reschedule {robot_id?, technician_id?, slot_start?, reason}   (chỉ khi job còn SCHEDULED)
POST /manager/jobs/{id}/unschedule {reason}
GET  /manager/jobs?status=&robot_id=&technician_id=&from=&to=      (cũng dùng làm lịch/calendar)       GET /manager/jobs/{id}
GET  /manager/technicians                          kỹ thuật viên + số job đang giữ
```
- Thời lượng job = thời gian viết × số lượng + 15' chuẩn bị + 5' chụp ảnh. Giờ làm việc mặc định T2–T7, 08:00–17:00 (UTC+7); job dài tự nối sang ngày làm việc kế.
- `slot_start` **bắt buộc có múi giờ** (ví dụ `2026-10-20T09:00:00+07:00`) và nằm trong giờ làm việc.
- Lỗi cần xử lý trên UI: `409 SLOT_CONFLICT` (`details.resource` = `robot`|`technician`), `409 ROBOT_UNAVAILABLE`, `422 ROBOT_NOT_SUITABLE` (robot không hỗ trợ loại bút), `422 OUTSIDE_WORKING_HOURS`, `422 SLOT_IN_PAST`, `409 JOB_ALREADY_STARTED`.
- Đây chỉ là **lịch**; không điều khiển robot.
- Xem diễn biến sau khi xếp lịch (Phase 4a, chỉ đọc): `GET /manager/jobs/{id}/events` (nhật ký: tải gói, hiệu chuẩn, mô phỏng, tiến độ, dừng khẩn cấp, sự cố), `GET /manager/incidents?resolved=&robot_id=` và `POST /manager/incidents/{id}/resolve {note}`. `JobOut` có thêm `progress_pct`, `downloaded_at`, `started_at`, `finished_at`, `simulation_passed`. Đơn có sự cố quay lại `schedule/queue` với `production_status=FAILED`; đổi trạng thái robot về `AVAILABLE` (API robot) rồi xếp lại như bình thường.

## 7b. Luồng Technical Staff (`/technician/*`) – Phase 4a

Chỉ vai trò `TECHNICAL_STAFF`, chỉ job được giao cho chính mình (job khác → `404 JOB_NOT_FOUND`). **Hiện BE chưa kết nối robot** (sẽ làm khi chủ dự án yêu cầu); BE chỉ ghi nhận và canh trạng thái. Kết quả mô phỏng, tiến độ, lực, dừng khẩn cấp do client báo lên các endpoint dưới đây (web app, máy trạm hoặc nhập tay). Khi nối robot thật, hợp đồng các endpoint này giữ nguyên. Mỗi bước đổi trạng thái job đồng thời đổi `production_status` của đơn (BR-17).

```
SCHEDULED ──prepare──▶ PREPARING ──start──▶ WRITING ◀──RESUME──┐
                          │                    │ │ └─PAUSE/ESTOP/OVER_FORCE/STROKE_LOST/SENSOR_LOST─▶ PAUSED
                          │                    │ └──finish──▶ WRITTEN   (trừ tồn kho)
        PREPARING/WRITING/PAUSED ──báo sự cố──▶ FAILED ──▶ đơn về hàng đợi xếp lại của Manager
```
| Việc | Endpoint |
|---|---|
| Job được giao | `GET /technician/jobs?status=&from=&to=&page=` · `GET /technician/jobs/{id}` (chi tiết + hiệu chuẩn hiện hành + sự cố + `can_start`) |
| Tải gói job (UC-32) | `GET /technician/jobs/{id}/package` → `trajectory_url` (liên kết có chữ ký, hết hạn sau `trajectory_url_expires_in` giây), `package_hash` (SHA-256), `pages`, `paper`, `pen` (hồ sơ lực BR-20: `f_min_n/f_target_n/f_max_n/f_hard_n`, `v_max_mm_s`), `ink_*`, `preview_url`. **Máy trạm phải tính SHA-256 của file tải về và so với `package_hash` trước khi chạy** (khác → MSG14 "Gói job không khớp phác thảo đã duyệt") |
| Chuẩn bị | `POST /technician/jobs/{id}/prepare` (cần đã tải gói; robot phải `AVAILABLE`/`BUSY`) |
| Hiệu chuẩn (FR-44) | `POST /technician/jobs/{id}/calibration {checklist{frame_mounted,paper_clamped,pen_installed,force_zeroed: true}, force_zero_offset, probe_points[{x,y,z}…≥3, P0 P1 P2 không thẳng hàng], frame_transform?, height_map?, force_curve?}` → 201. Bản mới thay bản cũ và **xoá kết quả mô phỏng** (phải mô phỏng lại) |
| Kết quả mô phỏng (FR-45) | `POST /technician/jobs/{id}/simulation {passed, errors[], report?}`; cần đã hiệu chuẩn; `passed:true` mà còn `errors` → 422 |
| Bắt đầu viết (UC-35) | `POST /technician/jobs/{id}/start` – cần: đã tải gói, hiệu chuẩn hiện hành, mô phỏng **đạt**, hash khớp |
| Sự kiện từ máy trạm (UC-36) | `POST /technician/jobs/{id}/events {event_type, stroke_index?, progress_pct?, force_summary?, payload?}` với `PROGRESS` (cần `progress_pct`, không bao giờ giảm), `PAUSE`, `RESUME`, `ESTOP`/`OVER_FORCE`/`STROKE_LOST`/`SENSOR_LOST` (tự chuyển `PAUSED`), `FORCE_SUMMARY {f_mean,f_max,rms_err_pct,in_band_pct,samples}`. Các loại do BE tự ghi (`DOWNLOADED`, `CALIBRATED`, `SIMULATED`, `START`, `WRITTEN`, `INCIDENT`, `HASH_MISMATCH`) → `422 EVENT_NOT_ALLOWED`. `GET .../events` xem nhật ký |
| Viết xong (UC-39) | `POST /technician/jobs/{id}/finish` → `WRITTEN`; trừ tồn kho (giấy = số lượng × số trang, bút 1, mực 1); tồn không đủ thì về 0 và ghi `shortfall` trong sự kiện `WRITTEN`, **không chặn** |
| Báo sự cố (UC-37) | `POST /technician/jobs/{id}/incidents {type: ROBOT\|MATERIAL\|FORCE_MODULE\|OTHER, description, robot_status_after?: MAINTENANCE\|BROKEN}` → 201; job → `FAILED`, đơn → `FAILED` (về hàng đợi Manager). Chỉ khi job đã `PREPARING`/`WRITING`/`PAUSED` |

Lỗi riêng: `404 JOB_NOT_FOUND`, `409 JOB_STATE_CONFLICT` (sai bước; `details.allowed`), `409 JOB_NOT_ACTIVE` (job đã xong/hỏng/huỷ), `409 ORDER_NOT_ACTIVE` (đơn không còn `CONFIRMED`, ví dụ bị huỷ), `409 JOB_NOT_DOWNLOADED`, `409 CALIBRATION_REQUIRED`, `409 SIMULATION_REQUIRED`/`SIMULATION_FAILED`, `409 JOB_HASH_MISMATCH` (MSG14), `409 FILE_MISSING`, `409 ROBOT_UNAVAILABLE`, `422 CHECKLIST_INCOMPLETE`, `422 INVALID_PROBE_POINTS`, `422 SIMULATION_INCONSISTENT`, `422 INVALID_FORCE_SUMMARY`, `422 PROGRESS_REQUIRED`, `422 EVENT_NOT_ALLOWED`, `503 STORAGE_NOT_CONFIGURED`.
Ảnh sản phẩm + QC (UC-38) ở mục 7c; sự cố chưa có ảnh đính kèm.

**Kiểm chứng phía server (thêm 2026-10-23, không đổi route).** Nếu `frame_transform` của hiệu chuẩn có `schema:"vhrs-motion/1"`, `POST .../simulation` tự dựng lại kế hoạch từ phác thảo đã duyệt và kiểm tra;
lời khai `passed:true` bị đổi thành `false` khi server tìm thấy lỗi (lỗi vào `simulation_report.errors` với tiền tố `SERVER`; `simulation_report.server_validation` có `checks`, `errors`, `stats`).
Khối gồm: `motion {a_lat_mm_s2, a_tan_mm_s2, travel_speed_mm_s, approach_speed_mm_s, pen_up_clearance_mm, spring_k_n_per_mm, max_spring_travel_mm}` (mọi số **do nhóm đo**, thiếu → `UNCONFIGURED`; `f_target_n`, `v_max_mm_s` luôn lấy từ hồ sơ bút trong DB)
và `workspace {box_min_mm[x,y,z], box_max_mm[x,y,z], max_reach_mm?, edge_margin_mm?}` (hộp bắt buộc). Với `MOTION_VALIDATION_REQUIRED=true` (trạm có robot thật) hiệu chuẩn thiếu khối này → mô phỏng không đạt (`MOTION_BLOCK_MISSING`).
Kiểm tra IK / giới hạn khớp **không** làm ở server (`checks.joint_reachability_ik = NOT_CHECKED`): do Robot Agent hỏi controller trước khi chạy.
Robot Agent gửi thêm vào sự kiện đầu của lần chạy `PROGRESS.payload.agent_run {run_id, mode, robot{model, controller_version, sdk_version, ip}, digest, total_strokes, estimated_seconds}`; dừng bằng phần mềm ghi `payload.source = "agent_software_stop"`.

## 7c. Ảnh sản phẩm, QC và nghiệm thu – Phase 4b

Sau khi `finish` (job `WRITTEN`), kỹ thuật viên chụp ảnh sản phẩm thật, đánh dấu QC rồi nộp; khách xem ảnh và nghiệm thu hoặc yêu cầu viết lại.

```
job WRITTEN ──nộp ≥2 ảnh QC đạt──▶ job PHOTO_UPLOADED + đơn AWAITING_ACCEPTANCE ──accept / quá 7 ngày──▶ job DONE, production FINISHED, đơn AWAITING_FINAL_PAYMENT
     │                                               └──rewrite (khách, 1 lần miễn phí)──▶ job REWRITE_REQUIRED, đơn CONFIRMED + production REWRITE_REQUIRED ─▶ Manager xếp lại (`POST /manager/orders/{id}/schedule`) ─▶ job mới `is_rewrite`
     └──qc-fail (kỹ thuật viên)──▶ job REWRITE_REQUIRED (đơn vẫn CONFIRMED; KHÔNG tính lượt viết lại miễn phí của khách)
```

**Kỹ thuật viên** (`/technician/jobs/{id}/…`, chỉ khi job `WRITTEN`):

| Việc | Endpoint |
|---|---|
| Xin liên kết tải ảnh | `POST …/photos/upload-url {mime_type: image/jpeg\|image/png, size_bytes}` → 201 `{photo_key, upload_url, method: "PUT", expires_in}`. Client `PUT` file thẳng vào `upload_url` |
| Đăng ký ảnh đã tải | `POST …/photos {photo_key, kind: OVERALL\|CLOSE_UP\|OTHER, qc_result?: PASS\|FAIL, qc_note?}` → 201 `{id, kind, qc_result, qc_note, url, url_expires_in}`. BE đọc lại file, kiểm tra loại thật (jpg/png), ≤ `max_upload_mb`, cạnh dài ≥ **1280 px**; sai thì xoá file và trả lỗi, không để lại bản ghi. Gọi lại cùng `photo_key` an toàn |
| Đánh dấu QC | `PATCH …/photos/{photo_id} {qc_result, qc_note}` (**FAIL bắt buộc có ghi chú**) |
| Xoá ảnh | `DELETE …/photos/{photo_id}` → 204 (xoá mềm; ảnh đã xoá không tính vào BR-21 và không đăng ký lại được) |
| Danh sách ảnh | `GET …/photos` (kèm liên kết xem có chữ ký) |
| Nộp ảnh | `POST …/photos/submit` – cần ≥ 2 ảnh, **có cả OVERALL và CLOSE_UP**, mọi ảnh còn lại QC = PASS (BR-21). Thành công: job `PHOTO_UPLOADED`, đơn `AWAITING_ACCEPTANCE`, khách được báo (MSG12) |
| Sản phẩm không đạt | `POST …/qc-fail {note}` → job `REWRITE_REQUIRED`, đơn vào hàng đợi xếp lịch của Manager |

Tối đa 10 ảnh/job. Lỗi: `409 PHOTO_REQUIREMENTS_NOT_MET` (`details`: `photos`, `missing_kinds`, `failed`, `unchecked`), `409 UPLOAD_NOT_FOUND`, `409 PHOTO_REMOVED`, `409 JOB_STATE_CONFLICT` (job không ở `WRITTEN`), `409 ORDER_NOT_ACTIVE`, `422 INVALID_PHOTO`, `422 PHOTO_TOO_SMALL`, `422 FILE_TOO_LARGE`, `422 TOO_MANY_PHOTOS`, `422 QC_NOTE_REQUIRED`, `422 INVALID_PHOTO_KEY`.

**Khách hàng** (chỉ đơn của mình):

| Việc | Endpoint |
|---|---|
| Xem ảnh thật | `GET /orders/{id}/product-photos` → `{order_status, photos[{id, kind, url, url_expires_in}] (chỉ ảnh QC đạt của lần viết gần nhất), sketch_preview_url (đối chiếu phác thảo), acceptance_due_at, can_accept, can_request_rewrite, free_rewrite_used}`. Dùng từ `AWAITING_ACCEPTANCE`; trước đó `409 PHOTOS_NOT_AVAILABLE` |
| Nghiệm thu | `POST /orders/{id}/accept` → đơn `AWAITING_FINAL_PAYMENT` (`production_status = FINISHED`, `accepted_product_at`) |
| Viết lại | `POST /orders/{id}/rewrite {reason_code: WORKSHOP_ERROR\|DIFFERS_FROM_SKETCH, note (≥5 ký tự)}` → đơn `CONFIRMED`, `production_status = REWRITE_REQUIRED`, `free_rewrite_used = true`. **Chỉ 1 lần miễn phí**; lần 2 trả `409 REWRITE_LIMIT_REACHED` ("liên hệ xưởng"). UI nên ẩn nút khi `can_request_rewrite = false` |

**Tự nghiệm thu:** nếu khách không trả lời trong `auto_accept_days` (mặc định 7 ngày) kể từ `awaiting_acceptance_at` thì đơn được nghiệm thu tự động (hiển thị hạn ở `acceptance_due_at`). BE kiểm tra khi khách đọc hoặc thao tác trên đơn (`GET /orders/{id}/product-photos`, `accept`, `rewrite`); thao tác muộn trả `409 ACCEPTANCE_CLOSED` và đơn đã được nghiệm thu. Chưa có tiến trình chạy nền chủ động và chưa có nhắc nghiệm thu sau 3 ngày (Phase 5 / 4e).
`OrderOut` có thêm `awaiting_acceptance_at`, `accepted_product_at`, `free_rewrite_used`.

**Xưởng:** `GET /workshop/orders/{id}/product-photos` (Staff của đơn, Manager) – mọi ảnh còn hiện của mọi job kèm QC (`job_status`, `qc_result`, `qc_note`). Ảnh chồng với phác thảo (`overlay_url`) **chưa được BE tạo**: client tự chồng `sketch_preview_url` lên ảnh.

### 7c.2 Đánh giá chất lượng bản viết (Service G, migration 0011)
`POST /technician/jobs/{id}/photos/{photo_id}/evaluate {page?}` → 201 `{id, verdict: PASS|NEEDS_REVIEW|FAIL, metrics{coverage_pct, extra_ink_pct, chamfer_mm, hd95_mm, hausdorff_mm, alignment{dx_mm,dy_mm,rot_deg}, thresholds{..., source}}, overlay_url, advisory}`. BE tìm tờ giấy trong ảnh, nắn phẳng, tìm nét mực (mọi màu mực), căn chỉnh nhỏ rồi đo so với phác thảo đã duyệt (mm). `overlay_url`: xanh dương = nét đo được, xanh lá = nét có đủ, đỏ = nét kế hoạch bị thiếu. `GET /technician/jobs/{id}/quality` và `GET /manager/jobs/{id}/quality` liệt kê các lần đánh giá.
- **Ảnh không đo được thì báo chứ không đoán:** `422 PAPER_NOT_FOUND` (không thấy đủ tờ giấy: chụp thấy 4 góc, nền tương phản, đủ sáng), `422 NO_INK`, `422 NO_MATCH` (sai tờ/sai đơn), `422 PHOTO_UNREADABLE`, `422 PAGE_OUT_OF_RANGE`.
- **Chỉ tham khảo:** số mm giả định tờ giấy phẳng và **chưa hiệu chuẩn bằng thước**; ngưỡng đạt/không đạt là mặc định chưa kiểm chứng (`thresholds.source = DEFAULT_UNCALIBRATED`). Kết luận QC vẫn là của kỹ thuật viên (`qc_result` của ảnh không bị đổi). FE hiện dòng `advisory` cạnh kết quả.

## 7d. Thanh toán cuối và nhận hàng – Phase 4c-1

Sau khi nghiệm thu, đơn ở `AWAITING_FINAL_PAYMENT`. Khách **chọn cách nhận**, rồi **thanh toán một lần** `(G − D) + phí ship` (G = tổng, D = tiền cọc). Cổng thanh toán theo `PAYMENT_MODE` (mục 5.3b). Khách **chọn hãng và dịch vụ vận chuyển** như trên các sàn thương mại điện tử (Phase 4c-2b); sau khi thanh toán xong, Staff tạo vận đơn và hãng đưa đơn tới `DELIVERING` rồi `COMPLETED` (mục 7e). Nhận tại xưởng vẫn chạy như trước.

```
AWAITING_FINAL_PAYMENT ──chọn cách nhận──▶ ──POST payments/final──▶ (webhook SUCCESS) ──▶ READY_TO_DELIVER ──Staff bàn giao (mã đơn + SĐT)──▶ COMPLETED
                                                  └─ cọc 100% + nhận tại xưởng: không có gì phải trả → READY_TO_DELIVER ngay (payment_required = false)
```

| Việc | Endpoint |
|---|---|
| Xem phí và dịch vụ cho một **địa chỉ chưa lưu** (FR-21) | `POST /orders/{id}/delivery-quote {address: {...}}` → `services[]` mỗi mục `{carrier: "GHN", service_code, service_name, fee, total_due (= G−D + phí), eta, is_fallback_fee, mode}`. Không đổi dữ liệu. **Dùng ngay khi khách nhập xong địa chỉ** để hiện danh sách cho khách chọn |
| Xem phí của đơn | `GET /orders/{id}/delivery-quote` → như trên cho địa chỉ **đã lưu** (chưa lưu: chỉ phí dự phòng) + `{paper_size, package_type, balance, is_fallback_fee, options: {DELIVERY, PICKUP}, chosen, chosen_service}`. Gói: A6/A5 → `FLAT_BOX_A5`, A4 → `FLAT_BOX_A4`. GHN thật (`SANDBOX`/`LIVE`) trả **một** dịch vụ cho gói nhẹ (`service_code: "2"`, "Giao hàng nhẹ"), phí + ngày giao dự kiến lấy từ GHN; `MOCK` trả hai dịch vụ `STANDARD`/`EXPRESS` để demo. Khi API GHN đang tắt/lỗi chỉ có **một** dịch vụ `STANDARD` tính theo bảng phí dự phòng (`is_fallback_fee: true`, `mode: "FALLBACK"`, `eta: null`). Địa chỉ GHN không nhận → `422 INVALID_ADDRESS` (khách sửa địa chỉ), không rơi về phí dự phòng |
| Chọn giao hàng + dịch vụ | `PUT /orders/{id}/delivery {method: "DELIVERY", address: {receiver, phone, street, province_code, ward_code, label?}, carrier: "GHN", service_code}` → `OrderOut` có `shipping_carrier`, `shipping_service_code`, `shipping_eta`. `carrier` và `service_code` **đi cùng nhau** và phải là một trong các dịch vụ vừa báo (`422 SERVICE_NOT_AVAILABLE` nếu không); **bỏ trống cả hai** = BE chọn dịch vụ rẻ nhất. **Địa chỉ theo mô hình hai cấp (tỉnh/thành → phường/xã, không còn quận/huyện)**: `province_code` và `ward_code` lấy từ `GET /locations/...` (mục 7d-2); BE kiểm tra ward thuộc đúng tỉnh và **tự điền** `province_name`, `ward_name` theo danh mục (tên FE gửi lên bị bỏ qua). `district_code`/`district_name` cũ vẫn được nhận nhưng **bị bỏ qua và không lưu**. Hãng duy nhất là **GHN** (GHTK đã gỡ: gửi `carrier: "GHTK"` → `422 VALIDATION_ERROR`) |
| Chọn nhận tại xưởng (FR-23) | `PUT /orders/{id}/delivery {method: "PICKUP", pickup_slot_start, pickup_slot_end (có múi giờ, trong giờ làm việc của xưởng, dài 15–240 phút, trong 30 ngày tới), contact_phone, receiver?}`. SĐT này dùng để đối chiếu khi bàn giao |
| Thanh toán cuối (FR-18) | `POST /orders/{id}/payments/final {gateway: VNPAY\|MOMO, expected_total?}` → 201 `{payment_required, total_due, order_status, payments[]}`. Giao hàng: 2 dòng `FINAL` (G−D) + `SHIPPING` (phí ship); nhận tại xưởng: chỉ `FINAL`. Cọc 100% thì không có dòng `FINAL`. **Hai dòng thuộc một giao dịch cổng**: mock-checkout bằng id của một trong hai dòng đều thanh toán cả hai |
| Mock thanh toán | `POST /payments/{payment_id}/mock-checkout {result: SUCCESS\|FAILED}` (như đặt cọc) → đơn `READY_TO_DELIVER` |
| Bàn giao tại xưởng | **Staff** `POST /workshop/orders/{id}/pickup/confirm {phone}` → đơn `COMPLETED` (`completed_at`). Chỉ Staff của đơn; sai số điện thoại → `422 PICKUP_PHONE_MISMATCH` |
| Xác nhận đã nhận (UC-20) | `POST /orders/{id}/receipt` → chỉ ghi `received_confirmed_at` (cho `DELIVERING` hoặc `COMPLETED`), gọi lại → `409 RECEIPT_ALREADY_CONFIRMED` |

- **`expected_total`** (nên gửi): số tiền khách đã thấy (`total_due` của dịch vụ đã chọn). Phí hãng thay đổi từ lúc đó thì trả `409 FEE_CHANGED` (`details.expected_total`, `details.current_total`) và **không** mở giao dịch nào: hiện số mới cho khách xác nhận lại. Dịch vụ đã chọn không còn khả dụng → `409 SERVICE_NOT_AVAILABLE` (cho khách chọn lại).
- Đổi cách nhận sau khi đã bắt đầu thanh toán: các giao dịch cuối đang chờ bị **huỷ** (webhook muộn của chúng được bỏ qua, `IGNORED`); gọi lại `payments/final` để tạo giao dịch mới theo số tiền mới. Sau khi đã thanh toán thì không đổi được (`409 FINAL_ALREADY_PAID`).
- `GET /orders/{id}/payments` liệt kê cả `FINAL` và `SHIPPING`. `OrderOut` có thêm `delivery_method`, `delivery_address` (nhận tại xưởng: chỉ `{receiver, phone}`), `pickup_slot_start/end`, `received_confirmed_at`, `completed_at`.
- Lỗi riêng: `409 FINAL_PAYMENT_NOT_EXPECTED`, `409 FINAL_ALREADY_PAID`, `409 DELIVERY_NOT_CHOSEN`, `409 DELIVERY_NOT_READY` (đơn chưa có loại giấy), `409 ORDER_NOT_DELIVERED`, `409 RECEIPT_ALREADY_CONFIRMED`, `409 PICKUP_NOT_EXPECTED`, `422 INVALID_ADDRESS` (thiếu trường: `details.missing`; mã tỉnh/phường không có trong danh mục hoặc phường không thuộc tỉnh; hoặc GHN không nhận địa chỉ/số điện thoại), `422 INVALID_SLOT`, `422 SLOT_IN_PAST`, `422 SLOT_TOO_FAR`, `422 OUTSIDE_WORKING_HOURS`, `422 INVALID_CONTACT`, `422 PICKUP_PHONE_MISMATCH`, `503 SHIPPING_FEE_UNAVAILABLE` (chưa cấu hình phí cho loại gói), `409 FEE_CHANGED`, `409`/`422 SERVICE_NOT_AVAILABLE`, `503 LOCATIONS_UNAVAILABLE` (chưa tải được danh mục địa chỉ từ GHN và chưa có bản lưu).

### 7d-2. Danh mục địa chỉ (tỉnh/thành, phường/xã) – dùng cho form địa chỉ

Từ 01/07/2025 Việt Nam chỉ còn **hai cấp** (tỉnh/thành → phường/xã). BE lấy danh mục từ **GHN** (cùng nguồn đã tính phí và tạo vận đơn, nên mã không bao giờ lệch) và giữ cache 24 giờ; **FE không giữ token GHN và không gọi GHN**. Cần đăng nhập (mọi vai trò). Giới hạn 120 lần/phút/IP; trình duyệt được giữ kết quả 1 giờ (`Cache-Control: private, max-age=3600`).

| Việc | Endpoint |
|---|---|
| Danh sách tỉnh/thành (khoảng 34) | `GET /locations/provinces` → `[{code, name}]`, sắp theo tên |
| Phường/xã của một tỉnh | `GET /locations/provinces/{province_code}/wards` → `[{code, name}]` (tỉnh lớn nhất ~170 phường). Tỉnh lạ → `404 PROVINCE_NOT_FOUND` |

- Form địa chỉ: chọn tỉnh → tải phường/xã của tỉnh đó → ô đường/số nhà (`street`). Gửi `province_code` + `ward_code` (chuỗi) cùng `receiver`, `phone`, `street` khi `PUT /orders/{id}/delivery`, `POST .../delivery-quote` và `PATCH /me` (địa chỉ hồ sơ).
- `PATCH /me` kiểm tra địa chỉ như khi đặt hàng: mã sai → `422 INVALID_ADDRESS`; địa chỉ đã lưu **bằng mã cũ (có quận/huyện) không còn dùng được**, khách cần chọn lại.
- `503 LOCATIONS_UNAVAILABLE`: GHN không trả lời và BE chưa có bản lưu (hiếm). Cho khách thử lại.
- `MOCK` (mặc định): chỉ có 4 tỉnh (Hà Nội, Hồ Chí Minh, Đà Nẵng, Cà Mau) với vài phường mỗi tỉnh, mã thật của GHN staging. Khi máy chủ bật GHN (`CARRIER_MODE=sandbox|live`) danh sách đầy đủ.

## 7e. Vận đơn và giao hàng – Phase 4c-2c

Khách đã chọn hãng + dịch vụ và đã thanh toán đủ (`READY_TO_DELIVER`). **Staff tạo vận đơn đúng hãng + dịch vụ khách đã chọn**; hãng báo hành trình qua callback; đơn đi theo:

```
READY_TO_DELIVER ──Staff tạo vận đơn (CREATED)──▶ hãng lấy hàng (PICKED_UP/DELIVERING) ──▶ đơn DELIVERING ──hãng báo DELIVERED──▶ đơn COMPLETED
                                                       └─ FAILED / RETURNED: vận đơn đổi trạng thái, ĐƠN GIỮ DELIVERING; Staff tạo lại vận đơn mới
```
| Ai | Việc | Endpoint |
|---|---|---|
| Khách | Theo dõi vận đơn (FR-22), mới nhất trước | `GET /orders/{id}/shipment` → `[{id, carrier, service_code, waybill_code, status, fee (khách đã trả), eta, picked_up_at, delivered_at, mode, tracking_url}]`. `tracking_url` là trang tra cứu của GHN (`null` với vận đơn mô phỏng). Chưa có vận đơn → `[]` |
| Staff | Xem vận đơn + link nhãn (MOCK: PDF lưu sẵn, hết hạn sau 10 phút; GHN thật: **trang in A5 của GHN**, link mới mỗi lần xem, chỉ có khi vận đơn còn sống) | `GET /workshop/orders/{id}/shipment` (Staff, Manager đọc) → thêm `package_type, weight_g, is_fallback_fee, carrier_status_raw, to_address, label_link, created_by` |
| Staff | Tạo vận đơn (UC-29) | `POST /workshop/orders/{id}/shipment {note?}` → 201. Đơn phải `READY_TO_DELIVER` (hoặc `DELIVERING` khi vận đơn trước đã `FAILED`/`RETURNED`/`CANCELLED`), hình thức giao hàng, đã có dịch vụ khách chọn, chưa có vận đơn đang sống |
| Staff | Huỷ vận đơn hãng chưa lấy hàng | `POST /workshop/shipments/{id}/cancel {reason}` (chỉ `CREATED`) → `CANCELLED`; sau đó tạo lại. GHN từ chối huỷ (hãng đã lấy hàng) → `409 CARRIER_CANCEL_REFUSED`, vận đơn **giữ nguyên** `CREATED` |
| Staff | **Demo** hãng báo trạng thái (chỉ vận đơn MOCK) | `POST /workshop/shipments/{id}/mock-event {status: PICKED_UP\|DELIVERING\|DELIVERED\|FAILED\|RETURNED, reason?}` → phát lại đúng callback có chữ ký |
| Hãng | Callback (FE không gọi) | `POST /webhooks/shipments/GHN` (mục 9) |

- Vận đơn: `CREATED → PICKED_UP → DELIVERING → DELIVERED`; `FAILED` (có thể giao lại), `RETURNED`, `CANCELLED`. Callback **trùng hoặc cũ hơn** trạng thái hiện tại bị bỏ qua (`ALREADY_PROCESSED`). Chỉ vận đơn **mới nhất** của đơn điều khiển trạng thái đơn.
- **Giao thất bại / hoàn về: đơn vẫn `DELIVERING`.** UI Staff nên hiện "Giao thất bại" và nút "Tạo vận đơn mới" (hoặc liên hệ khách chuyển sang nhận tại xưởng).
- Sau `COMPLETED` khách bấm "Đã nhận hàng" (`POST /orders/{id}/receipt`, chỉ ghi `received_confirmed_at`).
- Lỗi riêng: `409 SHIPMENT_NOT_EXPECTED`, `409 SHIPPING_SERVICE_NOT_CHOSEN`, `409 SHIPMENT_ALREADY_EXISTS` (`details.shipment_id`), `409 SHIPMENT_NOT_CANCELLABLE`, `409 CARRIER_CANCEL_REFUSED`, `409 NOT_A_MOCK_SHIPMENT`, `404 SHIPMENT_NOT_FOUND`, `502 CARRIER_REJECTED` / `502 CARRIER_UNAVAILABLE` (hãng từ chối/lỗi: chưa tạo vận đơn), `503 CARRIER_NOT_CONFIGURED`.
- Hãng mặc định là **MOCK** (`mode:"MOCK"`, mã vận đơn dạng `MOCK-GHN-...`, nhãn PDF có chữ MÔ PHỎNG). Khi máy chủ bật hãng thật, `mode` là `SANDBOX`/`LIVE` và hợp đồng API giữ nguyên.

## 8. Mã lỗi hay gặp và cách xử lý trên UI

| `code` | HTTP | Ý nghĩa | UI nên |
|---|---|---|---|
| `VALIDATION_ERROR` | 422 | Dữ liệu sai | gắn lỗi theo `details[].field` |
| `NOT_AUTHENTICATED`, `TOKEN_EXPIRED`, `TOKEN_INVALID` | 401 | Phiên hết | refresh 1 lần rồi về đăng nhập |
| `FORBIDDEN` | 403 | Sai vai trò | ẩn tính năng, báo "không có quyền" |
| `ORDER_NOT_FOUND` (và `*_NOT_FOUND`) | 404 | Không có / không phải của bạn | quay danh sách |
| `STATE_CONFLICT` | 409 | Chuyển trạng thái không hợp lệ (đơn đã đổi) | tải lại đơn, báo "đơn đã được cập nhật" |
| `ORDER_TYPE_SUSPENDED` | 409 | Loại đơn đang tạm đóng | ẩn lựa chọn đó |
| `PRIVACY_REQUIRED` | 403 | Chưa đồng ý chính sách | chuyển tới màn chính sách |
| `QUOTATION_NOT_OPEN`, `QUOTATION_EXPIRED` | 409 | Báo giá không còn hiệu lực | tải lại đơn |
| `INVALID_DEPOSIT` | 422 | % cọc ngoài khoảng | hiện `details.min_deposit_pct` |
| `OPTION_REQUIRED`, `INVALID_OPTION` | 422 | Chưa chọn phương án | bắt chọn |
| `DEPOSIT_NOT_EXPECTED`, `DEPOSIT_ALREADY_PAID` | 409 | Sai thời điểm đặt cọc | tải lại đơn |
| `ORDER_CANCEL_UNSUPPORTED` | 409 | Không huỷ online được (kể cả khi cọc vừa được xác nhận đúng lúc khách bấm huỷ: hãy tải lại đơn, nó đang `CONFIRMED`) | "Liên hệ xưởng" |
| `UNSUPPORTED_CHARS`, `TEXT_TOO_LONG`, `FONT_TOO_LARGE`, `CANVAS_OUT_OF_PAPER` | 422 | Nội dung không sinh được nét | nêu lỗi, cho sửa |
| `SLOT_CONFLICT`, `ROBOT_UNAVAILABLE`, `ROBOT_NOT_SUITABLE` | 409/422 | Lịch sản xuất | đổi robot/giờ |
| `JOB_STATE_CONFLICT`, `JOB_NOT_ACTIVE`, `ORDER_NOT_ACTIVE` | 409 | Job/đơn không ở bước đó (xem mục 7b) | tải lại job, vô hiệu nút |
| `JOB_HASH_MISMATCH` | 409 | Gói job không khớp phác thảo đã duyệt (MSG14) | chặn chạy, báo Manager |
| `GATEWAY_NOT_CONFIGURED`, `GATEWAY_UNAVAILABLE`, `GATEWAY_REJECTED` | 503/502 | Cổng thanh toán chưa cấu hình / lỗi / từ chối | ẩn cổng hoặc báo thử lại; không có giao dịch nào được tạo |
| `FEE_CHANGED` | 409 | Số tiền phải trả đã đổi so với lúc khách xem | hiện `details.current_total` để khách xác nhận lại |
| `SERVICE_NOT_AVAILABLE` | 422/409 | Dịch vụ vận chuyển đã chọn không còn khả dụng | tải lại danh sách dịch vụ, cho chọn lại |
| `SHIPMENT_*`, `CARRIER_*` | 409/502/503 | Vận đơn / hãng vận chuyển (mục 7e) | hiện `message` |
| `PHOTO_REQUIREMENTS_NOT_MET` | 409 | Chưa đủ ≥ 2 ảnh toàn cảnh + cận cảnh QC đạt (BR-21) | hiện `details` (thiếu loại nào, bao nhiêu ảnh FAIL / chưa QC) |
| `INVALID_PHOTO`, `PHOTO_TOO_SMALL`, `TOO_MANY_PHOTOS`, `QC_NOTE_REQUIRED`, `UPLOAD_NOT_FOUND`, `PHOTO_REMOVED` | 422/409 | Ảnh sản phẩm không hợp lệ (mục 7c) | nêu lỗi, cho chụp/tải lại |
| `PHOTOS_NOT_AVAILABLE`, `ORDER_NOT_AWAITING_ACCEPTANCE`, `ACCEPTANCE_CLOSED` | 409 | Đơn chưa/không còn ở bước nghiệm thu | tải lại đơn |
| `FINAL_PAYMENT_NOT_EXPECTED`, `FINAL_ALREADY_PAID`, `DELIVERY_NOT_CHOSEN`, `DELIVERY_NOT_READY` | 409 | Sai bước thanh toán cuối / chưa chọn cách nhận (mục 7d) | tải lại đơn, đưa khách về bước phù hợp |
| `INVALID_ADDRESS`, `INVALID_SLOT`, `SLOT_IN_PAST`, `SLOT_TOO_FAR`, `OUTSIDE_WORKING_HOURS`, `INVALID_CONTACT` | 422 | Địa chỉ / khung giờ nhận hàng không hợp lệ | gắn lỗi vào form, `details.missing` cho biết trường thiếu |
| `PICKUP_NOT_EXPECTED`, `PICKUP_PHONE_MISMATCH`, `ORDER_NOT_DELIVERED`, `RECEIPT_ALREADY_CONFIRMED` | 409/422 | Bàn giao / xác nhận nhận hàng sai bước hoặc sai SĐT | nêu lỗi |
| `REWRITE_LIMIT_REACHED` | 409 | Đã dùng lượt viết lại miễn phí (BR-13) | "Liên hệ xưởng" |
| `INVALID_REWRITE_REASON`, `REWRITE_NOTE_REQUIRED` | 422 | Lý do viết lại thiếu/sai | bắt chọn lý do và mô tả |
| `STOCK_NEGATIVE`, `NO_CHANGES`, `INVALID_PRICING`, `CODE_TAKEN` | 409/422 | Quản trị danh mục | hiện `message` |
| `RATE_LIMITED` | 429 | Gọi quá nhanh | chờ `Retry-After` giây |
| `STORAGE_NOT_CONFIGURED`, `STORAGE_UNAVAILABLE` | 503 | Chưa/không có kho file | báo lỗi tạm thời |

Danh sách đầy đủ nằm trong Swagger (mục `responses` của từng endpoint) và lệnh liệt kê trong `../PROJECT_STATUS.md` (mục 5).

## 9. Webhook và IPN (tham khảo, FE không gọi)

Tất cả do **bên ngoài** gọi vào BE; FE chỉ cần poll `GET /orders/{id}` (và `POST /payments/{id}/refresh` khi cần).

| Endpoint | Ai gọi | Xác thực | Ghi chú |
|---|---|---|---|
| `POST /webhooks/payments/{VNPAY\|MOMO}` | cổng **MOCK** | HMAC-SHA256 ở `X-Signature` | Tắt (`403 MOCK_WEBHOOK_DISABLED`) khi `PAYMENT_MODE` ≠ `mock` |
| `GET /webhooks/payments/vnpay/ipn` | VNPay | `vnp_SecureHash` HMAC-SHA512 | Luôn HTTP 200 + `{RspCode, Message}`: `00` ok, `02` đã xác nhận, `01` không thấy giao dịch, `04` sai số tiền, `97` sai chữ ký, `99` lỗi |
| `POST /webhooks/payments/momo/ipn` | MoMo | `signature` HMAC-SHA256 | `204` khi đã xử lý (kể cả trùng); `401` sai chữ ký; `422` sai số tiền/dữ liệu |
| `POST /webhooks/shipments/GHN` | GHN | MOCK: `X-Signature`; GHN: `?key=<mã bí mật>` hoặc header `X-Webhook-Secret` | Idempotent; callback cũ/trùng → `ALREADY_PROCESSED`; trạng thái lạ/loại sự kiện khác → `IGNORED`. GHTK không còn hỗ trợ (`422 CARRIER_NOT_SUPPORTED`) |

Tất cả idempotent theo mã giao dịch / mã vận đơn. Với cổng thật, địa chỉ IPN/callback phải là `https` công khai (`PUBLIC_BASE_URL`), và phải được đăng ký với từng bên (xem `DEPLOY.md`).

- **payOS:** `POST /webhooks/payments/payos` (JSON có `signature` HMAC-SHA256 bằng Checksum Key, trả 200 cho mọi webhook hợp lệ, kể cả trùng lặp hoặc giao dịch lạ). Đăng ký địa chỉ một lần bằng `scripts/register_payos_webhook.py`.

## 10. Chưa có / sẽ có (đừng chờ ở Phase này)

- Technical Staff: **đã có** xem job, gói job, hiệu chuẩn, mô phỏng, viết, sự kiện, sự cố (mục 7b), ảnh sản phẩm + QC và nộp ảnh (mục 7c). Ảnh chồng phác thảo do client tự làm.
- Chat: **đã có** thẻ đơn hàng, danh sách cuộc chat, badge chưa đọc (mục 5.4); **chưa có** đẩy tức thời (SSE/WebSocket).
- Khách: **đã có** xem ảnh, nghiệm thu, viết lại 1 lần, tự nghiệm thu sau 7 ngày (mục 7c). Thanh toán cuối + nhận tại xưởng **đã có** (mục 7d). Chọn dịch vụ vận chuyển, vận đơn và giao hàng qua hãng **đã có** (mục 7e). **Chưa có**: huỷ sau cọc + hoàn tiền (kể cả khoản `needs_refund`), dời ETA, **thông báo (in-app + email)** (Phase 4d/4e).
- Cổng thanh toán thật (VNPay, MoMo) đã có code nhưng **chưa được thử với môi trường thật của họ**. **GHN** (hãng duy nhất) đã được thử trên staging ngày 2026-10-26: báo giá (`preview`), tạo/huỷ vận đơn, link nhãn, danh mục địa chỉ; **chưa** thử callback thật. Mặc định vẫn là MOCK cho tới khi cấu hình (xem `DEPLOY.md`).
- Admin: tích hợp, tham số hệ thống, dashboard, OTP SMS, showcase, review (Phase 5).
- OT-2 (nét đã học) khoá với khách; AI không sinh phác thảo cho OT-2.
- Độ chính xác dựng nét OT-1 trên chữ viết tay thật **chưa được kiểm chứng**: giao diện nên cho Staff xem/sửa phác thảo trước khi gửi.

## 11. Ví dụ nhanh (fetch)

```js
const api = async (path, {method = "GET", body, token} = {}) => {
  const r = await fetch(`${BASE}/api/v1${path}`, {
    method, headers: {"Content-Type": "application/json", ...(token && {Authorization: `Bearer ${token}`})},
    body: body && JSON.stringify(body)});
  const data = r.status === 204 ? null : await r.json();
  if (!r.ok) throw Object.assign(new Error(data.error.message), data.error, {status: r.status});
  return data;
};
// khách duyệt báo giá rồi đặt cọc mô phỏng
await api(`/orders/${id}/quotation/approve`, {method: "POST", token, body: {deposit_pct: 50}});
const pay = await api(`/orders/${id}/payments/deposit`, {method: "POST", token, body: {gateway: "VNPAY"}});
await api(`/payments/${pay.id}/mock-checkout`, {method: "POST", token, body: {result: "SUCCESS"}});
```
