# Mô tả UI của FE (AI-VHRS)

Tài liệu mô tả toàn bộ giao diện trong `FE/` theo từng role. Không tính các phần chỉ dùng cho prototype (thanh Assistive Touch, nút "Prototype: ...", nút giả lập quét GHN, nút điền sẵn tài khoản demo).

AI-VHRS là web cho dịch vụ **robot Fairino FR3 viết thư pháp / chữ tay bằng mực thật trên giấy thật**. Khách đặt đơn, AI vẽ phác thảo, staff duyệt, technician điều khiển robot và kiểm tra chất lượng, rồi giao qua GHN.

- Stack: React + Vite + TypeScript, router tự viết (`src/router/router.tsx`), dữ liệu mock localStorage (`src/store/store.ts`).
- Ba ngôn ngữ: Anh, Nhật, Việt (nút đổi ngôn ngữ cạnh nút theme). Hai giao diện: sáng và tối.
- Bốn nhóm người dùng: **Guest**, **Customer**, **Staff**, **Technician**.

## 1. Sơ đồ route

| Route | Trang | Ai dùng |
|---|---|---|
| `/` | Landing | Mọi người |
| `/login` | Đăng nhập | Mọi người |
| `/create-order`, `/create-order/draft/:id` | Wizard tạo đơn (mở lại bản nháp) | Customer, Guest |
| `/create-order/draw`, `/create-order/draw/:id` | Canvas vẽ tay toàn màn hình | Customer, Guest |
| `/order/:id/review` | Xem sketch AI, gửi staff, trạng thái duyệt | Customer |
| `/order/:id/deposit` | Trả cọc 30% | Customer |
| `/order/:id/result` | Ảnh thành phẩm, duyệt hoặc xin viết lại | Customer |
| `/order/:id/final-payment` | Địa chỉ giao và thanh toán phần còn lại | Customer |
| `/order/:id/tracking` | Theo dõi giao hàng | Customer |
| `/account`, `/account/preferences`, `/account/orders`, `/account/drafts`, `/account/payment` | Tài khoản | Đã đăng nhập (3 mục cuối chỉ customer) |
| `/staff` | Dashboard staff | Staff |
| `/staff/review`, `/staff/review/:id` | Hàng đợi duyệt đơn | Staff |
| `/staff/assign/:id` | Gán technician và robot | Staff |
| `/staff/shipping`, `/staff/shipping/:id` | Bảng giao hàng và chi tiết | Staff |
| `/tech` | Dashboard technician | Technician |
| `/tech/preview`, `/tech/preview/:id` | Danh sách đơn và mô phỏng robot | Technician |
| `/tech/qc`, `/tech/qc/:id` | Danh sách đơn và kiểm tra chất lượng | Technician |

Các route `/staff/*` và `/tech/*` được bọc `RequireStaff`: sai role bị chuyển về `/login?next=...`. Sau đăng nhập, mỗi role chỉ được quay lại `next` nằm trong khu vực của mình. Vị trí mặc định: customer về `/`, staff về `/staff`, technician về `/tech`.

## 2. Thành phần dùng chung

- **Skip link** "Skip to content" ở đầu mỗi trang.
- **ThemeToggle** (sáng/tối) và **LanguageToggle** (menu 3 ngôn ngữ, hiện mã ngôn ngữ hiện tại, đóng bằng Esc).
- **SiteHeader** (các trang customer): logo `AI-VHRS`, menu *Features, Robot Specs, Penmanship, Order Queue*, nút tìm kiếm, theme, ngôn ngữ, **AccountButton**, nút **Start Writing**. Staff thấy thêm link "Staff dashboard", technician thấy "Technician desk".
- **AccountButton**: chưa đăng nhập là icon người dẫn tới `/login`; đã đăng nhập là avatar (ảnh hoặc chữ cái đầu) dẫn tới `/account`.
- **Page**: khung trang customer có nhãn và độ rộng cố định (720, 1200...).
- **OrderTimeline**: dải chấm các bước (đã xong, đang ở bước này).
- **SpecRows**: bảng hàng "nhãn: giá trị" cho thông số đơn.
- **NoOrder**: trang trống khi không tìm thấy đơn, có nút "Create an order".
- **PaperSheet**: vẽ tờ giấy với chữ/ảnh/nét vẽ, bố cục (Centered, Framed, Letter), có hiệu ứng "đầu bút" khi AI đang vẽ.
- **PaymentMethods**: lưới phương thức (VietQR, VNPay, MoMo, ZaloPay, Card) kèm khối chi tiết:
  - VietQR: khung QR, ngân hàng Vietcombank, số tài khoản, tên, nội dung chuyển khoản (`<mã đơn> COC` hoặc `TT`).
  - Card: số thẻ, hạn MM/YY, CVC.
  - Ví: thông báo sẽ chuyển sang ứng dụng để xác nhận số tiền.
- **ShipmentTimeline**: danh sách các mốc GHN với lời lẽ riêng cho staff và customer.
- **Rail của staff và technician**: thanh icon dọc, đánh dấu mục đang mở, có badge đếm. Cuối rail: "Site" và "Sign out".
  - Staff: Dashboard, Review (badge số đơn Pending), Shipping (badge số đơn cần đóng gói hoặc đặt GHN).
  - Technician: Dashboard, Preview, QC (badge số đơn chờ QC của mình).

## 3. Guest (chưa đăng nhập)

### Landing `/`
Trang giới thiệu cuộn dọc, header riêng (`lp-header`) có cùng nút tìm kiếm, theme, ngôn ngữ, tài khoản và Start Writing.

1. **Hero**: nhãn "Robot-written Vietnamese calligraphy", slogan lớn "make your own style" (không dịch), phụ đề, hai nút *Start Writing* và *Explore Robot Demo*.
2. **Modes** ("Bring your hand. We bring the arm."): 3 thẻ dẫn thẳng vào wizard với đúng chế độ (`#mode=text|upload|draw`):
   - Text + Single-Line Font (kèm chữ mẫu "An khang thịnh vượng"),
   - Upload Handwriting Photo,
   - iPad Live Canvas Drawing.
3. **Showcase**: cuộn để chữ "FR3" lớn mờ đi, ảnh cánh tay robot bay vào, hiện tiêu đề `AI-VHRS·FR3`, đoạn mô tả và lưới thông số (±0.02 mm, 6-DoF, 100% Ink, VNPay / MoMo).
4. **CTA**: dải **marquee** các sản phẩm mẫu (thiệp Tết, thiệp cưới, thiệp cảm ơn, bản in thư pháp, thư tình, phong bì) chạy ngang, dừng khi hover, đứng yên nếu bật giảm chuyển động; dưới là thẻ "Ready to put ink on paper?" kèm nút Start Writing.

### Login `/login`
Thẻ đăng nhập giữa màn hình, header chỉ có logo, theme, ngôn ngữ. Có ô email (kiểm tra định dạng), mật khẩu (bắt buộc nhập), thông báo lỗi dạng `alert`, nút *Sign in*. Nếu đã đăng nhập sẽ có dòng "Signed in as {name} ({role}). Continue".

### Khả năng của guest
Guest vẫn dùng được wizard tạo đơn và canvas vẽ tay. Nút "Save draft and exit" sẽ đưa sang login rồi về `/account/drafts`.

## 4. Customer

Vòng đời đơn: `Sketching → Pending → Accepted → Queued → Written → (Rewriting) → Shipped → Delivered`, hoặc `Rejected`. Mỗi trạng thái có chip màu riêng.

### 4.1 Create order `/create-order`
Wizard 4 bước, thanh bước phía trên (bước chưa mở thì khóa), cột chính bên trái và cột tóm tắt bên phải.

- **Bước 1 "Order type"**: 4 thẻ có hình tờ giấy đúng tỉ lệ: Greeting card (A6), Handwritten letter (A5), Addressed envelope (DL, nằm ngang), Wedding invitation. Mỗi thẻ ghi kích thước và giá "from".
- **Bước 2 "Content"**: 3 chế độ nhập:
  - *Type text*: ô soạn thảo (đếm "n / 120 chars included", +200₫ mỗi ký tự vượt), chọn kiểu chữ một nét Script / Formal / Casual, mỗi kiểu hiện chữ mẫu "Chữ đẹp".
  - *Upload image*: vùng kéo thả hoặc bấm chọn (PNG, JPG, PDF tới 20 MB, +30.000₫), hiện thumbnail, tên file, nút Remove.
  - *Write it yourself*: mở trang canvas toàn màn hình (+15.000₫). Quay lại sẽ thấy khung xem trước bản vẽ, số nét, khổ giấy, nút "Edit on canvas".
- **Bước 3 "Materials"**: chọn **giấy** (Ivory, Cotton rag, Kraft, Giấy dó; có mẫu màu và giá cộng thêm), rồi **bút** (Fountain, Gel, Calligraphy nib, Brush; hình nét minh họa), rồi **mực** (5 màu). Mỗi nhóm bị khóa tới khi chọn xong nhóm trước. Ô **Quantity** có nút − / + và nhập số (1 đến 500), ghi chú giảm 10% từ 10 cái, 20% từ 50 cái.
- **Bước 4 "Review"**: bảng tóm tắt Type / Content / Materials / Quantity, mỗi dòng có link *Edit* nhảy về bước tương ứng. Form giao hàng (họ tên, SĐT, địa chỉ, tự điền từ profile) và chọn thanh toán (VNPay, MoMo, Cash on delivery).
- **Thanh điều hướng dưới**: *← Back*, gợi ý còn thiếu gì ("Write something first", "Choose a pen"...), nút *Continue →*; bước cuối là *Submit & generate sketch →*.
- **Cột phải**: bản xem trước tờ giấy theo loại, màu giấy, màu mực (chữ, ảnh hoặc nét vẽ), khối **Instant estimate** liệt kê từng dòng giá, giảm giá số lượng, Total, Robot time, Delivery by, ghi chú "Price locks at submit". Dưới cùng là nút **Save draft and exit**.
- Tự lưu bản nháp sau mỗi thay đổi.

### 4.2 Draw Studio `/create-order/draw`
Trang tối toàn màn hình với lưới chấm.
- Thanh trên: *Back to order*, tiêu đề "Write it yourself" kèm kích thước mm và số nét, nút *Use this drawing* (tắt khi chưa có nét nào).
- Thanh công cụ: chọn khổ giấy (các chip kèm kích thước mm), hướng Portrait / Landscape, *Undo* (Ctrl/Cmd+Z, tối đa 25 bước), *Clear*.
- Khung giấy được vẽ viền, có thước và nhãn kích thước; chỉ phần trong khung được xuất ra.
- Dock dưới: nút bút hiện kiểu bút và cỡ ngòi; mở popup chọn cỡ ngòi (0.5 / 0.8 / 1.2 / 2 / 3 mm) và kiểu bút: **Pen**, **Monoline**, **Pencil**, **Fountain Pen**. Pen và Fountain nhận lực ấn của bút cảm ứng.

### 4.3 Order Review `/order/:id/review`
Đầu trang: mã đơn, trạng thái, tiêu đề lớn đổi theo giai đoạn, timeline 6 bước (Order placed, AI sketch, Staff review, Deposit, Writing, Delivered). Bên trái là tờ giấy, bên phải là *Order details*.

| Giai đoạn | Nội dung |
|---|---|
| Đang tạo sketch (~3.6 s) | Tờ giấy được "vẽ" dần với đầu bút chạy, thanh tiến độ với các bước *Parsing content → Fitting single-line font → Planning 6-DoF pen trajectory → Rendering sketch on paper*. |
| Chờ khách duyệt | Chọn 1 trong 3 bố cục, ô ghi chú sửa (không bắt buộc), nút **Regenerate** và **Send to staff**. |
| Pending | Hộp vàng "Pending staff review" (thường trả lời trong 2 giờ, 8:00 đến 21:00). |
| Rejected | Hộp đỏ liệt kê lý do và tên staff, nút "Start a new order". |
| Accepted | Hộp xanh ngọc "Accepted by staff", dòng "Deposit due (30%)" và nút **Pay deposit →**. |
| Đã cọc trở đi | Hộp xanh lá "Deposit paid · {status}", nút xem ảnh thành phẩm. |

Bảng chi tiết gồm Format, Content, Paper, Pen, Ink, Quantity, Robot time, Total.

### 4.4 Deposit `/order/:id/deposit`
Hai cột. Trái: "Pay your deposit" (30% giá trị), lưới phương thức thanh toán, nút trả tiền có nhãn đổi theo phương thức ("I've transferred {amount}", "Pay {amount} with MoMo", "Processing…"), ghi chú hoàn cọc đầy đủ cho tới khi robot bắt đầu viết. Phải: xem trước tờ giấy, Order total, Due on delivery, Deposit (30%). Sau khi trả: dấu tick lớn "Deposit received", nút *View order* và *Back to home*.

### 4.5 Result `/order/:id/result`
- Bên trái: **viewer 3D** tờ giấy (kéo để xoay 360°, pinch hoặc cuộn để zoom, double-click để reset), có mặt sau ghi "Written by Fairino FR3", nhãn ảnh "STAFF PHOTO · ORIGINAL/REWRITE #1", điều khiển zoom − / % / + và Reset. Khi đang viết lại có lớp phủ "Rewriting in progress".
- Bên phải: người gửi (Minh · AI-VHRS Studio), ghi chú, các ảnh QC do technician chụp (kèm chú thích), ghi chú QC, bảng thông số.
- Hành động khi `Written`: **Looks perfect, pay & ship** (sang thanh toán cuối) hoặc **Request rewrite** (có chip "1 FREE" hoặc "USED"). Form viết lại: chọn nhiều lý do (Ink smudge, Uneven spacing, Stroke quality, Wrong content, Other), ô ghi chú, *Cancel* / *Use free rewrite*.
- `Rewriting`: hộp cam kèm lý do đã gửi và "Usually ready within 24 hours".
- `Shipped / Delivered`: hộp xanh "Approved · shipping now", nút *Track delivery*, *Back to home*.

### 4.6 Final Payment `/order/:id/final-payment`
- Trái: thẻ **Your order** (hình nhỏ, tóm tắt thông số, nhãn "Written · approved by you", link xem ảnh); thẻ **Delivery address** (họ tên, SĐT, địa chỉ, phường/xã, thành phố chọn từ danh sách, ghi chú giao hàng); thẻ **Payment method**.
- Phải: ô **mã khuyến mãi** (VHRS10 giảm 10% phần còn lại, FREESHIP miễn phí ship), các dòng Order subtotal, VAT 8%, Deposit paid, Shipping (30.000₫, miễn phí nếu đơn từ 500.000₫), Promo, **Total due**, nút thanh toán, cảnh báo còn thiếu gì (địa chỉ, phương thức, thẻ), điều khoản.
- Sau khi trả: "Payment complete", nút *Track delivery*, *View order*.

### 4.7 Tracking `/order/:id/tracking`
- Chưa tới giai đoạn giao: thông báo "Tracking starts after payment".
- Đầu trang: tiêu đề lớn đổi theo giai đoạn (Packing, Waiting for GHN pickup, On the road, Out for delivery, Delivered, hoặc có sự cố), dòng phụ, timeline 5 bước (Packing, Pickup, In transit, Out for delivery, Delivered).
- Trái: checklist đóng gói (khi đang đóng gói) và **Updates** là timeline quét của GHN. Có thông báo khi chưa có lần quét hoặc lỗi làm mới.
- Phải: mã vận đơn GHN có nút **Copy**, bảng Carrier, Expected, Deliver to, Address, Due on delivery, lần quét gần nhất, nút *Open on GHN*, *View order photos*.
- Tự đồng bộ trạng thái từ GHN theo chu kỳ.

### 4.8 Account `/account`
Thanh bên + nội dung, đầu trang có avatar, tên, "Your personal account".
- **Profile**: tên, email, SĐT, địa chỉ giao, bio, ảnh đại diện (Edit / Remove photo, nén ảnh), nút *Update profile* và thông báo đã lưu.
- **Preferences**: chọn Light / Dark, chọn ngôn ngữ.
- **Order history** (customer): danh sách đơn kèm mã, ngày, chip trạng thái, tổng tiền; bấm vào mở đúng trang theo trạng thái (Accepted vào deposit, Written/Rewriting vào result, Shipped/Delivered vào tracking, còn lại vào review).
- **Drafts** (customer): lưới bản nháp (tiêu đề, bước hiện tại, thời gian lưu dạng "x phút trước", ước tính giá, mẫu giấy và mực), nút **Continue**, **Delete** (xác nhận Delete / Keep, tự hủy sau 4 giây), ô "Start a new order". Bên dưới là **carousel "You might also like"**: sản phẩm mẫu, chọn màu giấy, chọn gói 1 hoặc 10 cái, nút **Use this design** tạo bản nháp mới.
- **Payment methods** (customer): chọn phương thức mặc định (hoặc "No preference") và các logo phương thức được hỗ trợ.
- Khách chưa đăng nhập thấy "Sign in to see your account". Staff và technician chỉ có Profile và Preferences. Có nút **Sign out**.

## 5. Staff (`/staff`)

Bố cục chung: rail trái, vùng nội dung có tiêu đề + theme + ngôn ngữ.

### 5.1 Staff Dashboard
- Đầu trang: lời chào theo giờ, ngày, nhãn trạng thái robot "FR3 #01 · Writing/Idle".
- **Orders**: tổng giá trị "In pipeline", nút *Open review*, các nhóm gập mở được (Needs review, Waiting for the deposit, In production, Finished, Rejected). Mỗi dòng có tên, mã, khách, chip trạng thái (xanh khi đã gán technician, vàng khi cần technician) và tổng tiền; bấm vào mở review hoặc assign.
- 4 **KPI**: Needs review, Waiting deposit, In production, Rejected.
- Thẻ **Robot FR3 #01**: biểu đồ donut (Writing / Idle / Calibrating, giờ), job hiện tại kèm thanh tiến độ và phút còn lại, thanh vật tư (mực, khay giấy, độ mòn ngòi), số tờ viết hôm nay.
- Thẻ **AI usage**: tổng số request, đường spark 7 ngày, thanh theo dịch vụ (Handwriting OCR, Stroke vectorization, Trajectory planning, Quality evaluation).
- Thẻ **Quality**: điểm trung bình trên 100, tỉ lệ pass (ngưỡng 80), ghi chú dựa trên số đơn đã đánh giá.
- Dữ liệu robot và AI là **mô phỏng** (có nhãn "Simulated telemetry").

### 5.2 Staff Console `/staff/review`
Header riêng với logo, nhãn STUDIO, trạng thái robot, theme, ngôn ngữ, tên staff.
- **Cột trái, hàng đợi**: 3 tab Pending / Accepted / Rejected (kèm số lượng). Mỗi mục có mã, nhãn chế độ nhập (TEXT / IMAGE / DRAWING), tiêu đề, tên khách, trạng thái (Input review, AI sketch, Assigned · tên, Needs technician).
- **Cột phải, chi tiết** gồm tiêu đề, 3 bước tiến độ *Input review → AI sketch and evaluation → Accepted*, và dải chip thông số (Format, Paper, Pen, Ink, Qty, Total):
  1. **Input review**: tùy chế độ, hiển thị văn bản khách gõ kèm dải giấy xem trước, hoặc ảnh khách upload / ảnh canvas (bấm để zoom 200%). Bảng **Input recognition** (loại input, ngôn ngữ, số ký tự, dấu, ký tự không hỗ trợ, font; với ảnh: tên file, độ phân giải, độ nét, độ tin cậy OCR; với nét vẽ: số nét, dữ liệu lực ấn, số mẫu). Với ảnh hoặc nét vẽ có ô **sửa văn bản nhận diện**. Nút **Approve input, generate sketch** hoặc **Reject** (chọn nhiều lý do theo loại input, rồi *Reject and notify*).
  2. **AI sketch and evaluation**: tờ giấy được vẽ dần cùng bước "Vectorizing, Fitting font, Planning trajectory, Scoring"; bên phải là **System evaluation**: điểm tổng và nhãn "Ready to write" hoặc "Review recommended", 6 thanh kiểm tra (Legibility, Diacritic placement, Stroke continuity, Workspace fit, Ink load per piece, Layout balance), số nét, số lần nhấc bút, phút mỗi tờ. Nút **Accept order, request deposit**, *Regenerate*, *Back to input*.
  3. **Kết quả**: khối "Accepted, needs a technician" / "Assigned to {name} on {robot}" kèm nút gán hoặc đổi technician, hoặc khối "Rejected" kèm lý do.
- **Modal "Order accepted"** sau khi chấp nhận: tóm tắt đơn, điểm AI, nút *Choose technician* hoặc *Later*.

### 5.3 Assign Technician `/staff/assign/:id`
- Cột trái: phiếu "ACCEPTED ORDER" (input, format, bút, mực, giấy, số tờ, thời gian viết, điểm AI, tiền cọc) và ghi chú robot chỉ bắt đầu khi khách trả cọc.
- Chính giữa: "STEP 2 OF 2 · ASSIGN", **danh sách technician** (T-01 Hà Trần, T-02 Phúc Lê, T-03 Anh Vũ, T-04 Thảo Đinh): ca làm, kỹ năng bút, số robot, số robot rảnh, số đơn đang xếp hàng, chấm trạng thái từng robot; nhãn "Recommended" (ít việc nhất mà có robot rảnh) hoặc "Assigned to this order".
- **Robots của technician đã chọn**: từng robot với mã `FR3-xx`, trạng thái (Idle, Writing, Calibrating, Offline), thanh mực; chỉ chọn được robot Idle.
- Khối xác nhận với nút **Assign technician / Reassign order / Already assigned**, link *Decide later*. Sau khi lưu có khối thành công với *Back to dashboard* và *Review next order*.
- Đơn chưa Accepted hoặc không tồn tại sẽ hiện thông báo tương ứng.

### 5.4 Shipping Board `/staff/shipping`
- Đầu trang: "Shipping" kèm nhãn "GHN live" hoặc "GHN simulated".
- 4 KPI: To pack or book, With GHN, Out for delivery, Needs attention.
- Các nhóm: **Needs attention** (chỉ hiện khi có), **To pack and book**, **With GHN**, **Delivered**. Mỗi dòng có tên, mã, người nhận, mã GHN, thành phố, chip giai đoạn. Nhóm trống có hướng dẫn riêng.

### 5.5 Shipping Detail `/staff/shipping/:id`
- Đầu: nút quay lại, tiêu đề, mã đơn, người nhận, SĐT, chip giai đoạn.
- **Packing**: 3 checkbox (bọc giấy và lót bìa, đóng hộp dán kín, in và dán nhãn), khóa sau khi đã đặt GHN.
- **GHN courier**: người nhận, địa chỉ, ghi chú cho shipper, COD, và khi đã đặt: phí, thời điểm đặt, dự kiến giao, mã vận đơn. Ô **cân nặng (g)**, nút **Book GHN courier** (tắt tới khi đóng gói xong, hiện lỗi nếu đặt thất bại), link *Open on GHN*.
- **Activity**: timeline các lần quét, nút *Refresh* (khi dùng GHN thật) kèm thời điểm đồng bộ và lỗi; khi có sự cố hiện nhắc liên hệ khách.

## 6. Technician (`/tech`)

Technician chỉ thấy đơn được gán cho mình (`techId`). Đơn được chia theo **phase**: `qc` (robot viết xong), `live` (đang viết), `ready` (đã cọc), `wait` (chờ cọc), `done`.

### 6.1 Tech Dashboard
- Lời chào, ngày, ca làm; nhãn "N robots · WRITING/READY".
- **My orders**: tổng "Queue time" (phút), các nhóm gập: *Photo and QC, Writing now, Ready to preview, Waiting for deposit, Finished*; mỗi dòng dẫn tới `/tech/qc/:id` hoặc `/tech/preview/:id`, hiện robot và số phút.
- 4 KPI: Needs QC, Writing now, Ready to preview, Waiting deposit.
- **My robots**: donut theo trạng thái, danh sách robot (mã, trạng thái, thanh mực, đơn đang chạy hoặc đang chờ).
- **Queue time**: thanh phút theo từng đơn mở; **Workload**: số đơn đang xếp hàng, số robot rảnh, kỹ năng bút.
- Chưa có đơn: thông báo "Nothing assigned yet".

### 6.2 Danh sách đơn `/tech/preview` và `/tech/qc`
Lưới thẻ đơn. Preview hiện các phase live, ready, wait; QC hiện qc, live. Mỗi thẻ: mã, chip phase, tiêu đề, khách, chế độ nhập, bảng giấy / bút / mực (kèm mẫu màu) / số tờ / thời gian viết / robot (và trạng thái robot), ghi chú phase, nút hành động (Open QC, Follow live, Open simulator, Preview only; thẻ đầu tiên ghi "..., next up"). Rỗng thì có hướng dẫn.

### 6.3 Robot Preview `/tech/preview/:id`
Chỉ vào được nếu đơn được gán cho mình (không thì hiện "Not your order" hoặc "Order not found").
- **Viewport mô phỏng** (canvas): bàn, tờ giấy, mực đã viết, cánh tay FR3 và hình nhìn ngang trục Z; nhãn "ISAAC SIM · PREVIEW" hoặc "LIVE · {robot}", "Piece 1 of N", ghi chú không kết nối Isaac Sim.
- **Thanh điều khiển** (preview): Play / Pause / Replay, Reset, thanh kéo thời gian, đồng hồ, tốc độ phát 1x / 10x / 30x / 60x. Khi chạy thật thay bằng thanh tiến độ trực tiếp và "N s left".
- **Telemetry**: Progress, Words, Strokes, Pen (Down / Lifted), Tip X, Y, Reach (In range / Clamped); **Joint angles** J1 đến J6.
- **Cột phải**: *Order options* (format, input, giấy, bút, mực, font, layout, số tờ và văn bản); *Tuning* với 3 thanh trượt (Pen speed 20 đến 120 mm/s, Contact force 0.5 đến 3 N, Pen lift 2 đến 20 mm) và ước lượng thời gian; ba checkbox hiển thị (Planned path, Reach envelope, Joint labels).
- **Preflight**: 5 checkbox (giấy đã nạp, bút đã lắp, mực, hiệu chuẩn độ cao bút, vùng làm việc trống), danh sách **cổng điều kiện** (đã xem hết preview, đã tick preflight, khách đã trả cọc, robot online). Nút **Start real robot** mở hộp xác nhận (robot, số tờ, bút, mực, thời gian, tốc độ) với *Start writing* / *Not yet*.
- Khi đang chạy: khối "Robot is writing"; khi xong: "Writing finished" kèm nút **Go to photo and QC**.

### 6.4 Quality Check `/tech/qc/:id`
Chỉ mở khi robot đã chạy xong; nếu chưa, hiện "The robot is still writing" kèm link mở simulator.
- Thanh 2 tab: **QC checklist** (n/total) và **Photos** (chỉ mở khi tick hết).
- **Checklist** gồm các nhóm: *Paper and layout* (giấy đúng loại, không nhăn rách; bố cục đúng bản xem trước; mực không thấm sang mặt sau), *The writing* (chữ khớp đơn, đủ dấu và dấu câu, nét liền, mực đều, không lem), *Pieces and packing* (đủ số tờ, mực đã khô, đóng phẳng kèm tờ lót). Có thanh tiến độ chia đoạn và đếm theo nhóm. Tick hết thì tự chuyển sang tab Photos.
- Khối **"Something is wrong, reschedule this order"**: chọn lý do (Missing strokes, Wrong paper, Text mismatch, Pen skipped, Ink smudge, Other), ghi chú lịch, nút **Reschedule**; đơn quay lại hàng đợi robot.
- Cột phải **Compare against**: văn bản cần đối chiếu, input, giấy, mực, số tờ, robot.
- **Photos**: 3 ô ảnh: *Whole sheet* (bắt buộc), *Close-up* (bắt buộc), *Packed* (tùy chọn); mỗi ô có gợi ý, nút chụp hoặc tải ảnh (dùng camera sau nếu có), Retake, Remove, nhãn Added / Required / Optional. Ghi chú cho khách, dòng báo còn thiếu ảnh nào, nút **Send to customer**.
- Hộp xác nhận "Send to {name}?" nêu số ảnh và việc không thu hồi được từ màn hình này. Sau khi gửi: "Sent to {name}" với *Back to dashboard* và *Next order to check*; nếu reschedule thì "Back in the robot queue".

## 7. Quy ước giao diện chung

- Chuỗi hiển thị luôn có đủ en, ja, vi (`src/i18n/`); tên danh mục (giấy, bút, mực, lý do...) lưu tiếng Anh và dịch lúc hiển thị.
- Giá tiền định dạng VND; ngày giờ theo locale hiện tại.
- Mọi biểu đồ (donut, spark) là SVG tự vẽ, có nhãn cho trình đọc màn hình; modal có focus và Esc; nhiều vùng có `role`/`aria-label`.
- Dữ liệu robot, AI, GHN ở bản này là mô phỏng, nhãn "Simulated" luôn hiển thị nơi liên quan.
