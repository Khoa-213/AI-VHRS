# Report 3 – Software Requirement Specification (SRS) – AI-VHRS

> Bản chép lại từ PDF `REPORT (4).pdf` (Capstone Project Report 3, 09/2026). Chỉ chép phần chữ; sơ đồ (context diagram,
> use case diagram, screens flow, ERD, hình 8–9) là ảnh nên **không** có ở đây. Xem `README.md` cùng thư mục để biết thứ tự ưu tiên
> khi tài liệu mâu thuẫn với nhau hoặc với code. Mã FR/UC/BR/NFR/MSG trong code BE trích từ file này.
> Lưu ý: bản này dừng ở FR-51 và BR-24. Các mã **FR-52** (chính sách riêng tư), **BR-25**, **FR-53..58**, **UC-53..59** nằm ở bản
> "theo phiếu mới" mà repo không có; xem `04_feature_entity_list_v2.md` để biết tên chức năng.

Ghi chú bản gốc (Record of Changes, 22/09/2026): "Khởi tạo Report 3 cho AI-VHRS theo phạm vi đã chốt (3 actor, 3 hình thức nhập liệu)" –
dòng này **lỗi thời**: nội dung bên dưới là mô hình **5 actor**.

---

## 1. Product Overview

AI-VHRS là hệ thống vận hành của một xưởng dịch vụ viết tay bằng robot ("Xưởng Nét Việt"). Khách hàng đặt đơn trên website theo 3 loại:
Sao chép – Phục hồi (upload ảnh bản gốc), Sáng tạo theo nét chữ đã học, và Viết theo mẫu/Trang trí; chọn giấy, bút, màu mực; nhận phác
thảo và báo giá; đặt cọc; theo dõi tiến độ; nghiệm thu qua ảnh sản phẩm thật; thanh toán phần còn lại và phí giao hàng. Tại xưởng,
Staff xử lý đơn, Manager quản lý robot, vật tư, giá và lập lịch sản xuất, Technical Staff dùng ứng dụng Flutter Desktop để tải job,
chuẩn bị và chạy tay robot Fairino FR3 có kiểm soát lực bút bằng thiết bị IoT, chụp ảnh sản phẩm và cập nhật trạng thái sản xuất.
Admin quản trị tài khoản, tích hợp và tham số hệ thống.

Thực thể bên ngoài trong context diagram: Customer, Staff, Technical Staff, Manager, Admin, Payment Gateway, Carrier (Delivery API),
FR3 Robot and IoT Force Module (và Email System trong use case overview).

## 2. User Requirements

### 2.1 Actors

| # | Actor | Kênh | Mô tả |
|---|---|---|---|
| 1 | Customer | Web | Khách cá nhân/doanh nghiệp. Tạo đơn: chọn loại đơn (3 loại), tải ảnh hoặc nhập nội dung, chọn giấy → bút → màu mực, số lượng, xem giá ước tính, gửi đơn; duyệt phác thảo và báo giá; đặt cọc theo % tối thiểu; theo dõi 2 trạng thái đơn; nghiệm thu qua ảnh sản phẩm thật; chọn giao hàng hoặc nhận tại xưởng, thanh toán phần còn lại + phí ship; xác nhận đã nhận; hủy đơn theo chính sách. |
| 2 | Staff | Web | Nhân viên phụ trách đơn. Tiếp nhận hoặc từ chối đơn (tài liệu quá cũ, hư hỏng, thiếu thông tin), yêu cầu bổ sung; phác thảo (chạy AI và chỉnh sửa) và đề xuất cách làm; lập báo giá dạng bảng/file; trao đổi với khách; xác nhận thanh toán; tạo vận đơn/giao hàng; cập nhật trạng thái đơn và ETA. |
| 3 | Technical Staff | Flutter Desktop App (có thể có vai trò web) | Kỹ thuật viên tại xưởng. Xem job được giao, tải file job về máy trạm, chuẩn bị robot (lắp khung, kẹp giấy, lắp bút, hiệu chuẩn), mô phỏng, chạy viết, giám sát lực và dừng khẩn cấp, báo sự cố, chụp ảnh sản phẩm thật và tải lên, cập nhật trạng thái sản xuất. |
| 4 | Manager | Web | Quản lý xưởng. Quản lý danh sách robot và loại robot, lập lịch sản xuất (gán job cho robot và kỹ thuật viên), quản lý vật tư (giấy, bút, mực) và bảng tương thích giấy–bút, quản lý mẫu chữ, cấu hình bảng giá và % cọc tối thiểu, duyệt điều chỉnh giá vượt ngưỡng, phân công Staff, xem dashboard sản xuất và báo cáo. |
| 5 | Admin | Web | Quản trị hệ thống, cấp trên Manager. Quản lý tài khoản và vai trò, cấu hình tích hợp (cổng thanh toán, hãng vận chuyển, email), tham số hệ thống, xem audit log và dashboard toàn hệ thống. |

### 2.2 Use Cases (2.2.2 Descriptions)

| ID | Use case | Actor | Mô tả |
|---|---|---|---|
| **Tất cả** | | | |
| UC-01 | Login | Tất cả | Đăng nhập web (4 vai trò) hoặc Flutter App (Technical Staff). |
| UC-02 | Logout | Tất cả | Kết thúc phiên làm việc. |
| UC-03 | Reset Password | Tất cả | Đặt lại mật khẩu qua email. |
| UC-04 | Manage Profile | Tất cả | Xem, sửa thông tin cá nhân, địa chỉ,... |
| **Customer** | | | |
| UC-05 | Register | Customer | Tạo tài khoản khách hàng bằng email và mật khẩu. |
| UC-06 | Browse Services & Templates | Customer | Xem các loại dịch vụ, thư viện mẫu, bảng giá tham khảo, sản phẩm mẫu. |
| UC-07 | Create Order | Customer | Tạo đơn mới, chọn 1 trong 3 loại đơn. |
| UC-08 | Upload Original | Customer | Loại Sao chép – Phục hồi: tải ảnh bản gốc, xoay/crop, xem kết quả kiểm tra chất lượng ảnh. |
| UC-09 | Learned-style Content | Customer | Loại Sáng tạo: tải bộ mẫu chữ hoặc chọn bộ nét đã lưu, nhập nội dung mới. |
| UC-10 | Template Writing | Customer | Loại Viết theo mẫu: chọn mẫu typography/thư pháp/font, nhập nội dung, thêm hình vẽ canvas nếu cần. |
| UC-11 | Select Materials | Customer | Chọn loại giấy và khổ → bút (lọc theo giấy) → màu mực, số lượng; hoặc chọn "để xưởng đề xuất vật tư". |
| UC-12 | Instant Estimate | Customer | Xem giá ước tính tức thời (chưa gồm phí giao hàng). |
| UC-13 | Submit Order | Customer | Gửi đơn cho xưởng kèm ghi chú (include UC-12). |
| UC-14 | Provide Info | Customer | Bổ sung ảnh/thông tin khi Staff yêu cầu. |
| UC-15 | Review Sketch & Quote | Customer | Xem phác thảo và báo giá, đồng ý hoặc yêu cầu chỉnh. |
| UC-16 | Pay Deposit | Customer | Chọn % cọc (≥ mức tối thiểu) và thanh toán qua cổng. |
| UC-17 | Track Order | Customer | Theo dõi trạng thái đơn, trạng thái sản xuất, ETA. |
| UC-18 | Accept Product | Customer | Nghiệm thu qua ảnh sản phẩm thật hoặc yêu cầu viết lại. |
| UC-19 | Delivery & Final Pay | Customer | Chọn giao hàng (xem phí ship qua API) hoặc nhận tại xưởng; thanh toán phần còn lại + phí ship. |
| UC-20 | Confirm Receipt | Customer | Xác nhận đã nhận hàng, đánh giá. |
| UC-21 | Cancel Order | Customer | Hủy đơn theo chính sách hoàn tiền. |
| UC-22 | Payment History | Customer | Xem lịch sử giao dịch, hóa đơn. |
| **Staff** | | | |
| UC-23 | View Incoming Orders | Staff | Xem danh sách đơn mới/đơn được phân công, lọc theo loại, trạng thái. |
| UC-24 | Review Order | Staff | Tiếp nhận, từ chối (kèm lý do) hoặc yêu cầu bổ sung. |
| UC-25 | Prepare Sketch | Staff | Chạy AI tạo phác thảo, chỉnh sửa nét, đề xuất cách làm và vật tư. |
| UC-26 | Create Quotation | Staff | Lập báo giá dạng bảng từ Pricing Engine, xuất file, gửi khách. |
| UC-27 | Message Customer | Staff | Trao đổi với khách trong đơn. |
| UC-28 | Confirm Payment | Staff | Kiểm tra, xác nhận các khoản thanh toán, xử lý hoàn tiền. |
| UC-29 | Arrange Delivery | Staff | Lấy phí ship qua API, tạo vận đơn, theo dõi hoặc hẹn nhận tại xưởng. |
| UC-30 | Update ETA | Staff | Cập nhật/dời thời gian giao dự kiến kèm lý do. |
| **Technical Staff (Flutter App)** | | | |
| UC-31 | View Assigned Jobs | Technical Staff | Xem các job được Manager gán theo robot và ca. |
| UC-32 | Download Job | Technical Staff | Tải gói job (lộ trình, thông số bút/giấy, file mẫu) về máy trạm. |
| UC-33 | Prepare & Calibrate Robot | Technical Staff | Lắp khung, kẹp giấy, lắp bút vào giá kẹp, hiệu chuẩn mặt giấy và lực. |
| UC-34 | Simulate Job | Technical Staff | Mô phỏng lộ trình trên máy trạm trước khi chạy thật. |
| UC-35 | Execute Writing | Technical Staff | Ra lệnh robot viết theo job. |
| UC-36 | Monitor & E-Stop | Technical Staff | Giám sát tiến độ, lực bút theo thời gian thực; tạm dừng, dừng khẩn cấp. |
| UC-37 | Report Incident | Technical Staff | Báo sự cố robot/vật tư, trả job về chờ xếp lịch lại. |
| UC-38 | Upload Product Photo & QC | Technical Staff | Chụp ảnh sản phẩm thật, kiểm tra chất lượng, tải ảnh lên. |
| UC-39 | Update Production Status | Technical Staff | Cập nhật trạng thái sản xuất của đơn. |
| **Manager** | | | |
| UC-40 | Manage Robots | Manager | Quản lý danh sách robot, loại robot, trạng thái (sẵn sàng/bảo trì/hỏng). |
| UC-41 | Schedule Production | Manager | Gán job cho robot và kỹ thuật viên theo lịch; hệ thống gợi ý, Manager quyết định; xếp lại khi robot hỏng. |
| UC-42 | Manage Materials & Compatibility | Manager | Quản lý giấy (loại, độ dày, khổ), bút, màu mực, tồn kho và bảng tương thích giấy–bút. |
| UC-43 | Manage Templates & Styles | Manager | Quản lý mẫu typography/thư pháp/font và bộ nét chữ đã học. |
| UC-44 | Configure Pricing | Manager | Cấu hình bảng giá, hệ số độ phức tạp, phí setup, chiết khấu số lượng, % cọc tối thiểu; duyệt điều chỉnh giá vượt ngưỡng. |
| UC-45 | Production Dashboard | Manager | Xem hàng đợi, lịch robot, công suất, đơn trễ ETA. |
| UC-46 | View Reports | Manager | Báo cáo doanh thu, sản lượng, tỷ lệ viết lại, hiệu suất robot. |
| UC-47 | Assign Staff | Manager | Phân công Staff phụ trách đơn. |
| **Admin** | | | |
| UC-48 | Manage Accounts & Roles | Admin | Tạo, khóa tài khoản nội bộ, gán vai trò. |
| UC-49 | Configure Integrations | Admin | Cấu hình khóa API cổng thanh toán, hãng vận chuyển, email. |
| UC-50 | System Parameters | Admin | Tham số hệ thống: thời hạn báo giá, giới hạn file, chính sách hủy. |
| UC-51 | View Audit Log | Admin | Tra cứu nhật ký thao tác. |
| UC-52 | System Dashboard | Admin | Tình trạng hệ thống, tích hợp, người dùng. |

## 3. Functional Requirements

### 3.1 System Functional Overview

#### 3.1.2 Screen Descriptions (tóm tắt theo kênh)

**Website – Customer:** 1 Home & Services · 2 Template Library (xem thử với nội dung tùy ý) · 3 Login/Register/Reset Password · 4 Create Order – Order Type ·
5 Upload Original (OT-1: tải ảnh/pdf, xoay, crop, cảnh báo chất lượng) · 6 Learned-style Input (OT-2) · 7 Template Writing & Canvas (OT-3) ·
8 Material Selection & Estimate · 9 Order Summary & Submit (tóm tắt, ghi chú, điều khoản) · 10 My Orders (2 cột trạng thái + ETA) ·
11 Order Detail (dòng thời gian 2 trạng thái, ETA và lịch sử dời, phác thảo, báo giá, tin nhắn, ảnh sản phẩm, nút nghiệm thu/viết lại/hủy) ·
12 Payment (Deposit/Final: chọn % cọc hoặc thanh toán phần còn lại + phí ship) · 13 Delivery Options (địa chỉ, dịch vụ, phí từ API, hoặc nhận tại xưởng) ·
14 Payment History · 15 Profile.

**Website – Staff:** 16 Order Queue · 17 Order Review (Accept/Reject/Need info) · 18 Sketch Editor · 19 Quotation Builder (điều chỉnh ±15%, xuất PDF, gửi) ·
20 Payments & Refunds (đối soát, hoàn tiền) · 21 Delivery Management (phí ship, tạo vận đơn, in nhãn, theo dõi; lịch nhận tại xưởng) · 22 Messages & ETA (dời ETA kèm lý do).

**Website – Manager:** 23 Production Dashboard · 24 Robot Management · 25 Production Scheduler (Gantt theo robot; gợi ý; kéo thả) · 26 Materials & Compatibility ·
27 Templates & Styles · 28 Pricing Configuration (đơn giá, hệ số, phí setup, chiết khấu, p_min; duyệt điều chỉnh giá) · 29 Reports · 30 Staff Assignment.

**Website – Admin:** 31 Account & Role Management · 32 Integration Settings (khóa API VNPay/Momo, GHN/GHTK, email; bật/tắt, kiểm tra kết nối) ·
33 System Parameters (hạn báo giá, thời gian tự nghiệm thu, giới hạn file, chính sách hủy, **bảng phí ship dự phòng**) · 34 Audit Log & System Dashboard.

**Flutter Desktop App – Technical Staff:** 35 Login & Station Setup · 36 Job List · 37 Job Detail & Download · 38 Preparation & Calibration (checklist, zero lực, dò mặt giấy) ·
39 Simulation · 40 Execution Monitor (tiến độ theo nét, biểu đồ lực F_ref/F, Tạm dừng/Tiếp tục/E-Stop) · 41 Incident Report · 42 Product Photo & QC.

#### 3.1.3 Screen Authorization (X = thao tác, Xem = chỉ xem)

| Màn hình / chức năng | Customer | Staff | Technical | Manager | Admin |
|---|---|---|---|---|---|
| Login/Register, Reset Password, Manage Profile, Home & Services, Template Library | X | X | X | X | X |
| My Orders, Create Order, Upload Original, Learned-style Input, Template Writing & Canvas, Material Selection & Estimate, Order Summary & Submit | X | | | | |
| Preview Sketch (pop-up) | X | X | | | |
| Order Detail (Track Status / View Result) | X | X | Xem | X | Xem |
| Payment (Deposit/Final), Delivery Options, Payment History | X | | | | |
| Order Queue, Order Review (Accept/Reject), Quotation Builder, Messages & ETA Update, Payments & Refunds, Delivery Management | | X | | X | |
| Sketch Editor | | X | | | |
| Production Dashboard | | Xem | Xem | X | Xem |
| Robot Management | | | Xem | X | Xem |
| Production Scheduler | | Xem | Xem | X | |
| Materials & Compatibility, Templates & Styles | | Xem | | X | |
| Pricing Configuration, Staff Assignment | | | | X | |
| Reports | | | | X | X |
| Account & Role Mgmt, Integration Settings, System Settings, Audit Log, System Dashboard | | | | | X |
| Station Setup, Job List & History, Job Detail & Download, Preparation & Calibration, Simulation, Execution Monitor & E-Stop, Incident Report, Product Photo & QC | | | X | | |
| Query Own Data | X | | | | |
| Query Managed Data (đơn/job được phân công) | | X | X | | |
| Query All Data (toàn xưởng: Manager; toàn hệ thống: Admin) | | | | X | X |

Customer chỉ thấy đơn của mình; Staff chỉ thao tác trên đơn được phân công; Technical Staff chỉ thao tác trên job được gán cho mình (BR-02, BR-19).
> Bảng này cho Manager cả "Order Review", "Quotation Builder", "Messages", "Payments & Refunds", "Delivery Management" (cột X). **Dự án đã
> chọn khác** (Manager chỉ đọc, ghi là Staff only; Admin không xem đơn) – xem `README.md` mục "Quyết định đã override".

#### 3.1.4 Non-Screen Functions

| # | Nhóm | Hàm hệ thống | Mô tả |
|---|---|---|---|
| 1 | Pricing | Pricing Engine | Tính giá ước tính và báo giá theo công thức mục 3.3; lưu snapshot. |
| 2 | AI | Image Quality Check | Đánh giá độ nét, độ sáng, độ tương phản ảnh upload; cảnh báo cho khách và Staff. |
| 3 | AI | Trajectory Reconstruction | Phục dựng nét và thứ tự nét từ ảnh (OT-1). |
| 4 | AI | Text-to-Stroke | Sinh nét từ mẫu/font single-line, ghép dấu tiếng Việt (OT-3). |
| 5 | AI | Style Learning (R&D) | Học bộ nét từ mẫu chữ một người và sinh nội dung mới (OT-2). |
| 6 | AI | FR3 Motion Planner & Job Packager | Hồ sơ vận tốc, biến đổi giấy → robot, kiểm tra khả thi, đóng gói job + hash. |
| 7 | Sản xuất | Schedule Suggester | Gợi ý robot và khung giờ theo thời gian ước tính, loại robot, lịch hiện có. |
| 8 | Sản xuất | ETA Calculator | Tính ETA theo BR-15; tính lại khi lập lịch, sự cố, viết lại. |
| 9 | Sản xuất | Robot Agent (máy trạm) | Tiến trình Python cạnh Flutter App: kết nối FR3 qua SDK, chạy lộ trình, vòng lực, an toàn, telemetry. |
| 10 | IoT | Force Module Firmware (ESP32) | Đọc loadcell ≥ 500 Hz, lọc, gửi lực về Robot Agent qua USB serial. |
| 11 | Đơn hàng | State Guard | Kiểm tra mọi chuyển trạng thái theo bảng 2.5 và ràng buộc đồng bộ BR-17. |
| 12 | Thanh toán | Payment Webhook Handler | Xác thực chữ ký, idempotency theo mã giao dịch, polling dự phòng. |
| 13 | Giao hàng | Carrier Adapter | Giao diện chung tính phí, tạo vận đơn, nhận webhook cho GHN/GHTK. |
| 14 | Hệ thống | Notification Service | Email và thông báo trong ứng dụng khi đổi trạng thái, báo giá, dời ETA. |
| 15 | Hệ thống | Scheduled Jobs | Hủy báo giá hết hạn, nhắc nghiệm thu, tự nghiệm thu, xóa ảnh sau 90 ngày. |

#### 3.1.5 Entities (24 trong Report 3; bản 2 thêm 5 → 29, xem `04_...`)

Role, Account, Order, OrderInput, Template, HandwritingStyle, Sketch, Quotation, Payment, Shipment, Message, StatusHistory, PaperType, PenType, InkColor,
PaperPenCompat, Robot, ProductionJob, JobEvent, ProductPhoto, PricingConfig*, Calibration*, Incident*, AuditLog*. (`*` = đánh dấu trong ERD của báo cáo.)
Mô tả từng entity: xem `04_feature_entity_list_v2.md` (bảng entity có cột chức năng). Cột/kiểu dữ liệu thật nằm ở `migrations/sql/AI-VHRS_database_postgresql.sql`.

### 3.2 Nhóm 1 – Website đặt hàng và quản trị

- **FR-01 Tài khoản và xác thực (UC-01..04)**: đăng ký khách bằng email; đăng nhập web và Flutter App; quên mật khẩu qua email. Mật khẩu băm; **khóa tạm sau 5 lần sai**; Technical Staff đăng nhập được cả web (xem) và App.
- **FR-02 Hồ sơ và địa chỉ (UC-05)**: sửa thông tin, lưu nhiều địa chỉ nhận hàng. Địa chỉ chuẩn hóa tỉnh/quận/phường theo mã của hãng vận chuyển để tính phí ship.
- **FR-03 Phân quyền 5 vai trò**: kiểm tra quyền theo ma trận 3.1.3; BR-01, BR-02; API trả 403 khi sai quyền.
- **FR-04 Trang dịch vụ và thư viện mẫu (UC-06)**: hiển thị 3 loại dịch vụ, mẫu chữ, sản phẩm mẫu, giá tham khảo; xem thử mẫu với nội dung khách gõ (render ảnh, không cần đăng nhập).
- **FR-05 Tạo đơn và chọn loại đơn (UC-07)**: tạo Order DRAFT với 1 loại đơn; BR-03; loại đơn có thể tạm ngừng (LI-10).
- **FR-06 Upload bản gốc (UC-08)**: tải ảnh/pdf, xoay, crop, kiểm tra chất lượng tự động; BR-04; cảnh báo nhưng vẫn cho gửi, Staff quyết định.
- **FR-07 Nội dung theo nét chữ đã học (UC-09)**: tải ≥ 1 trang mẫu chữ của cùng một người (khuyến nghị có đủ chữ cái) hoặc chọn bộ nét đã lưu; nhập nội dung mới; khách xác nhận có quyền sử dụng nét chữ (BR-23).
- **FR-08 Viết theo mẫu và canvas (UC-10)**: chọn mẫu, nhập nội dung, cỡ chữ, căn lề, bố cục; vẽ hình trang trí trên canvas (ghi tọa độ, thứ tự nét, áp lực nếu có bút cảm ứng qua Pointer Events).
- **FR-09 Chọn vật tư có ràng buộc (UC-11)**: giấy + khổ → bút lọc theo tương thích → màu mực; hoặc để xưởng đề xuất; BR-05, BR-06, BR-07.
- **FR-10 Giá ước tính tức thời (UC-12)**: gọi Pricing Engine với N đếm từ nội dung (OT-2, OT-3) hoặc ước lượng từ ảnh (OT-1), độ phức tạp mặc định theo loại đơn; hiển thị khoảng giá và ghi chú "giá chưa gồm phí giao hàng, báo giá chính thức sau phác thảo" (BR-08, BR-12).
- **FR-11 Gửi đơn (UC-13)**: DRAFT → SUBMITTED, thông báo Staff; kiểm tra đủ trường, điều khoản.
- **FR-12 Hàng đợi đơn của Staff (UC-23, UC-47)**: danh sách đơn mới/được phân công; Manager phân công hoặc Staff tự nhận; một đơn có đúng 1 Staff phụ trách sau khi ACCEPTED.
- **FR-13 Tiếp nhận, từ chối, yêu cầu bổ sung (UC-24, UC-14)**: chuyển ACCEPTED / REJECTED / NEED_INFO; lý do bắt buộc khi từ chối, chọn từ danh mục (quá cũ, hư hỏng, thiếu nội dung, nội dung cấm, khác).
- **FR-14 Phác thảo (UC-25)**: gọi module AI theo loại đơn; editor chỉnh nét; lưu phiên bản. Mỗi phiên bản lưu độ phức tạp đề xuất và thời gian viết ước tính dùng cho giá và lập lịch.
- **FR-15 Báo giá (UC-26, UC-15)**: tạo Quotation dạng bảng + PDF, gửi khách; khách đồng ý/yêu cầu chỉnh/hủy; BR-08, BR-09, BR-22; ETA hiển thị trong báo giá.
- **FR-16 Tin nhắn trong đơn (UC-27)**: luồng tin gắn với đơn, có đính kèm ảnh; thông báo cho bên kia.
- **FR-17 Đặt cọc (UC-16)**: khách đồng ý báo giá → chọn % ≥ p_min, thanh toán qua cổng; BR-10; thành công → CONFIRMED + PENDING_SCHEDULE.
- **FR-18 Thanh toán phần còn lại và phí ship (UC-19)**: đơn AWAITING_FINAL_PAYMENT; **một lần thanh toán gồm (G − D) + F_ship**; BR-11; **ghi 2 dòng Payment (final, shipping)**.
- **FR-19 Hủy đơn và hoàn tiền (UC-21, UC-28)**: khách bấm Hủy hoặc hệ thống hủy; tính số tiền hoàn theo BR-14/BR-16, gọi API hoàn tiền của cổng; Staff xác nhận hoàn tiền; lưu Payment(type=refund).
- **FR-20 Lịch sử thanh toán (UC-22, UC-28)**: danh sách giao dịch, trạng thái, hóa đơn; Staff đối soát với cổng.
- **FR-21 Tính phí giao hàng qua API (UC-19)**: khách chọn Giao hàng → gọi API hãng với địa chỉ, khối lượng, kích thước gói. Kích thước gói suy ra từ khổ giấy và số bản (**hộp phẳng A5/A4, ống cứng cho poster**); **phí dự phòng khi API lỗi**.
- **FR-22 Tạo vận đơn và theo dõi (UC-29)**: đơn READY_TO_DELIVER → tạo vận đơn, in nhãn; webhook cập nhật DELIVERING, COMPLETED; ánh xạ trạng thái hãng về trạng thái hệ thống; lưu mã vận đơn cho khách tra cứu.
- **FR-23 Nhận tại xưởng (UC-19, UC-29)**: phí ship = 0; hẹn khung giờ; Staff xác nhận đã giao → COMPLETED; khách nhận bằng mã đơn + số điện thoại.
- **FR-24 Máy trạng thái đơn hàng**: chỉ cho phép chuyển tiếp theo bảng 2.5.1; ghi StatusHistory; từ chối chuyển không hợp lệ (409).
- **FR-25 Máy trạng thái sản xuất và đồng bộ (UC-39)**: chuyển theo bảng 2.5.2 và ràng buộc 2.5.3; các cặp chuyển đồng thời (nghiệm thu, tải ảnh) thực hiện trong 1 giao dịch DB.
- **FR-26 ETA và dời ETA (UC-30)**: tính ETA (BR-15) khi báo giá, cọc, lập lịch, sự cố, viết lại; Staff dời ETA kèm lý do, khách được thông báo; hiển thị ETA hiện tại và lịch sử dời; **dời lũy kế > 7 ngày → mở quyền hủy hoàn 100% (BR-16)**.
- **FR-27 Thông báo**: email + thông báo trong ứng dụng khi đổi trạng thái, báo giá, dời ETA, tin nhắn; nội dung theo mục 5.3.
- **FR-28 Nghiệm thu và viết lại (UC-18, UC-20)**: đơn AWAITING_ACCEPTANCE; khách nghiệm thu hoặc yêu cầu viết lại; xác nhận đã nhận hàng; BR-13; **tự nghiệm thu sau thời gian tham số (mặc định 7 ngày)**.
- **FR-51 Quản trị hệ thống (UC-48..52)**: tài khoản, vai trò, tích hợp, tham số, audit log, dashboard hệ thống; mọi thao tác Admin ghi AuditLog.

### 3.3 Nhóm 2 – Pricing Engine

**FR-29 Công thức giá (UC-12, UC-26)** – hàm nội bộ, thuần (không phụ thuộc UI), có unit test cho mọi nhánh:

```
N      = số ký tự không tính khoảng trắng  (hình vẽ canvas: N = tổng độ dài nét / 40 mm)
Viết   = max(W_min, N × u_type) × K_cx            công viết cho 1 bản
   u_type : đơn giá / ký tự theo loại đơn (OT-1, OT-2, OT-3)
   K_cx   : hệ số độ phức tạp 1,0 (đơn giản) | 1,3 (trung bình) | 1,6 (phức tạp)
Giá_1  = P_paper(loại, khổ) + P_pen + P_ink + Viết       giá 1 bản
G      = S_type + Q × Giá_1 × (1 − d(Q))                 tổng đơn (chưa gồm ship)
   S_type : phí setup theo loại đơn (phác thảo, chuẩn bị máy)
   d(Q)   : 0% (Q<10) | 5% (Q≥10) | 10% (Q≥50) | 15% (Q≥100)
D      ≥ p_min × G                                       tiền cọc, p_min mặc định 50%
Đợt 2  = (G − D) + F_ship        F_ship từ API hãng vận chuyển, = 0 nếu nhận tại xưởng
```

K_cx được đề xuất tự động từ phác thảo (thời gian viết ước tính, tổng độ dài nét, số lần nhấc bút) và Staff xác nhận: **đơn giản** – chữ thường cỡ vừa, bố cục đơn;
**trung bình** – chữ nhỏ, nhiều dấu, bản gốc cần chỉnh nhiều; **phức tạp** – thư pháp, bút máy/bút lông, hình trang trí.

Ví dụ minh họa (giá giả định): chép 1 lá thư, 320 ký tự, giấy mỹ thuật A4 15.000đ, bút máy 10.000đ, mực 0đ, u = 300đ/ký tự, W_min = 50.000đ, K_cx = 1,3, S = 100.000đ, Q = 2:

| Khoản | Cách tính | Thành tiền |
|---|---|---|
| Công viết / bản | max(50.000; 320×300 = 96.000) × 1,3 | 124.800đ |
| Giá 1 bản | 15.000 + 10.000 + 0 + 124.800 | 149.800đ |
| 2 bản | 2 × 149.800 × (1 − 0%) | 299.600đ |
| Tổng G | 100.000 + 299.600 | 399.600đ |
| Cọc tối thiểu (50%) | 0,5 × 399.600 | 199.800đ |
| Đợt 2 | (399.600 − 199.800) + phí ship API (ví dụ 30.000) | 229.800đ |

Hai cách định vật tư khi báo giá: (1) khách tự chọn trong danh mục → giá tính ngay; (2) khách chọn "để xưởng đề xuất" → Staff chọn vật tư phù hợp với vật tư đang có, có thể đưa 2–3 phương án với giá tương ứng để khách chọn.

- **FR-30 Cấu hình bảng giá (UC-44)**: Manager sửa đơn giá vật tư, u_type, W_min, K_cx, S_type, bậc chiết khấu, p_min; mỗi lần lưu tạo phiên bản PricingConfig mới; đơn đã báo giá giữ snapshot cũ.
- **FR-31 Điều chỉnh và duyệt giá (UC-26, UC-44)**: Staff điều chỉnh tổng giá; trong ±15% ghi lý do; vượt thì chờ Manager duyệt; BR-09; lưu AuditLog.
- **FR-32 Snapshot và file báo giá (UC-26)**: lưu toàn bộ tham số và dòng chi tiết; xuất PDF **có logo xưởng**; BR-08; hiệu lực 7 ngày; ghi rõ "Giá chưa bao gồm phí giao hàng".

### 3.4 Nhóm 3 – AI phục dựng và lộ trình robot

- **FR-33 Kiểm tra và tiền xử lý ảnh (UC-08, UC-25)**: đo độ nét (Laplacian variance), độ sáng, tương phản; khử nghiêng, nhị phân hóa thích nghi, khử nhiễu, tách nền giấy cũ/ố vàng; kết quả chất lượng hiển thị cho khách và Staff.
- **FR-34 Phục dựng nét từ ảnh (OT-1) (UC-25)**: skeletonization, vector hóa, tách nét tại giao điểm, suy luận thứ tự và chiều nét, xử lý riêng dấu thanh/dấu phụ tiếng Việt; ước lượng độ rộng nét làm lực tham chiếu. Đầu ra: danh sách nét (x, y, pen) + chỉ số độ giống (**IoU nét ≥ 80% – NFR-02**).
- **FR-35 Sinh nét từ mẫu/font (OT-3) (UC-25)**: chuẩn hóa Unicode NFC, tra glyph single-line, ghép dấu tiếng Việt theo điểm neo, dàn trang theo khổ giấy, biến thể tự nhiên có seed. Pipeline S0–S5 bên dưới.
- **FR-36 Học nét chữ và sinh nội dung mới (OT-2, R&D) (UC-09, UC-25)**: tách ký tự từ mẫu, xây bộ glyph của người viết (HandwritingStyle), bổ sung ký tự thiếu bằng mô hình sinh; sau đó dùng pipeline FR-35. Hướng nghiên cứu: few-shot handwriting generation, mô hình ánh xạ đồng thời XY và lực. Chất lượng không đạt → LI-10.
- **FR-37 Lập lộ trình cho FR3 (UC-32, UC-34)**: sau khi đơn CONFIRMED và có hiệu chuẩn; hồ sơ vận tốc theo độ cong, biến đổi tọa độ giấy → gốc robot từ hiệu chuẩn, kiểm tra tầm với/IK/dị điểm, sinh lệnh (S6–S10).
- **FR-38 Đóng gói job (UC-32)**: Manager lập lịch xong → gói job gồm lộ trình theo tọa độ giấy, PenProfile, thông số giấy/bút, ảnh phác thảo, **hash SHA-256 của phác thảo đã duyệt**; Robot Agent từ chối chạy nếu hash không khớp.

Pipeline chuyển văn bản/nét thành lộ trình tay FR3 (Hình 8):

| Bước | Nội dung | Chi tiết chính |
|---|---|---|
| S0 | Chuẩn hóa Unicode | NFC; kiểm tra tập ký tự hỗ trợ (89 chữ thường + 89 hoa tiếng Việt, số, dấu câu); báo vị trí ký tự lỗi. |
| S1 | Glyph + ghép dấu | Tách NFD: chữ gốc + dấu phụ (trăng, mũ, móc) + dấu thanh; gắn vào neo top/bottom/horn; sắc/huyền/hỏi lệch phải mũ, ngã trên mũ; dấu nặng dưới chân chữ. |
| S2 | Biến thể tự nhiên | Tỉ lệ, nghiêng, rung nét, trôi baseline ngẫu nhiên nhỏ theo seed (preview và robot giống nhau). |
| S3 | Dàn trang | Quy đổi mm theo cỡ chữ; ngắt dòng theo âm tiết; căn lề theo mẫu; báo tràn khổ. |
| S4 | Thứ tự nét | Thứ tự đọc; dấu thanh viết sau mỗi từ; nối nét gần nhau < 0,3 mm; ảnh/canvas giữ thứ tự sẵn có. |
| S5 | Hình học | Làm phẳng Bézier (sai số 0,02 mm), giữ góc > 60°, smoothing spline, lấy mẫu lại Δs = 0,2 mm. |
| S6 | Hồ sơ vận tốc | v ≤ min(v_max_pen, √(a_lat/κ)); quét xuôi/ngược theo gia tốc tiếp tuyến; v đầu/cuối nét 5 mm/s. |
| S7 | Giấy → robot | Từ 3 điểm dò chạm P0, P1, P2: x̂, ŷ (Gram–Schmidt), ẑ = x̂ × ŷ; p_B = R·p_P + t; cộng bản đồ độ cao z_map. |
| S8 | Khả thi | Tầm với ≤ 0,9 × 622 mm; IK mỗi 5 mm cùng nhánh nghiệm; cách giới hạn khớp ≥ 5°; tránh dị điểm cổ tay; vận tốc khớp ≤ 30%. |
| S9 | Sinh lệnh | Chế độ vị trí: spline/MoveL; chế độ lực: stream điểm Cartesian chu kỳ ~8 ms, z hiệu chỉnh bởi vòng lực. Tên hàm SDK xác minh ở spike. |
| S10 | Gói job | JSON lộ trình + hash + thời gian ước tính (dùng cho lập lịch và K_cx). |

### 3.5 Nhóm 4 – IoT, sản xuất, báo cáo

- **FR-39 Quản lý robot và loại robot (UC-40)**: CRUD robot, loại robot, trạng thái AVAILABLE/BUSY/MAINTENANCE/BROKEN; BR-18; robot mô phỏng đánh dấu để demo lập lịch nhiều robot (LI-03).
- **FR-40 Lập lịch sản xuất (UC-41)**: đơn PENDING_SCHEDULE → gợi ý robot + khung giờ; Manager xác nhận/kéo thả; xếp lại khi FAILED/REWRITE_REQUIRED. **Thời lượng job = thời gian viết ước tính × Q + chuẩn bị (mặc định 15 phút) + chụp ảnh (5 phút); ưu tiên ETA gần nhất.**
- **FR-41 Vật tư và tương thích (UC-42)**: giấy, bút, mực, tồn kho, ma trận tương thích; BR-05, BR-06; **trừ tồn kho khi job WRITTEN**.
- **FR-42 Mẫu chữ và bộ nét (UC-43)**: thêm mẫu (font single-line JSON, ảnh xem trước), duyệt bộ nét đã học; mẫu có trạng thái active/inactive.
- **FR-43 Flutter App: danh sách và tải job (UC-31, UC-32)**: hiển thị job được gán, tải gói job, kiểm tra hash; App giữ bản cục bộ để chạy khi mạng chập chờn, đồng bộ trạng thái khi có mạng.
- **FR-44 Chuẩn bị và hiệu chuẩn (UC-33)**: job PREPARING; checklist lắp khung/giấy/bút; zero lực; dò mặt giấy 3 điểm (+ lưới); BR-19; lưu Calibration.
- **FR-45 Mô phỏng (UC-34)**: vẽ lại lộ trình trên khổ giấy theo thời gian, cảnh báo khả thi; **không cho chạy nếu còn lỗi khả thi**.
- **FR-46 Chạy viết qua Robot Agent (UC-35)**: App gửi lệnh cho Robot Agent (localhost); Agent điều khiển FR3 qua SDK TCP/IP, gửi tiến độ và telemetry; Agent là tiến trình Python độc lập, giao tiếp WebSocket cục bộ.
- **FR-47 Kiểm soát lực bút (IoT) (UC-33, UC-35)**: module lực đo lực tì; Robot Agent điều chỉnh độ cao z để giữ lực trong dải của bút (mục 3.6).
- **FR-48 Giám sát, E-Stop, sự cố (UC-36, UC-37)**: tạm dừng/tiếp tục, E-Stop, tự PAUSED khi bất thường, báo sự cố; NFR-03; **sự cố → FAILED → PENDING_SCHEDULE**.
- **FR-49 Ảnh sản phẩm, QC, trạng thái (UC-38, UC-39)**: job WRITTEN → chụp/tải ≥ 2 ảnh, chồng ảnh với phác thảo, QC, cập nhật PHOTO_UPLOADED; BR-21; đồng bộ Order → AWAITING_ACCEPTANCE.
- **FR-50 Báo cáo và dashboard (UC-45, UC-46, UC-52)**: doanh thu theo kỳ, sản lượng theo loại đơn, tỷ lệ từ chối/viết lại, thời gian chạy và sự cố theo robot, đơn trễ ETA; xuất Excel/PDF.

### 3.6 Thiết bị IoT kiểm soát lực bút

Cấu tạo: giá kẹp bút in 3D gắn mặt bích FR3 (thân bút trượt trong ống dẫn hướng, lò xo nén hành trình 5–10 mm); loadcell 1 trục + HX711 (~0,01 N);
ESP32 đọc loadcell ≥ 500 Hz, lọc thông thấp, gửi lực về Robot Agent qua USB serial (Wi-Fi phụ); Robot Agent hiệu chỉnh trục z theo vòng điều khiển.

Cơ chế (Hình 9: XY theo vị trí, Z theo lực):
1. **Zero lực**: bút trên không, lấy trung bình 1 s làm offset.
2. **Hạ bút có phát hiện chạm**: hạ theo pháp tuyến giấy 5 mm/s; chạm khi F > 0,15 N trong 3 mẫu liên tiếp.
3. **Bám lực**: z_cmd = z_giấy + F_ref/k_s + Δz; Δz từ bộ điều khiển admittance/PI theo e = F_ref − F_đo, giới hạn ±2 mm; băng thông thấp ~3 Hz.
4. **Biến thiên áp lực**: F_ref giảm ở đầu/cuối nét; OT-1 lấy theo độ rộng nét trong ảnh; canvas lấy theo áp lực bút cảm ứng.
5. **An toàn**: F > F_hard → nhấc bút, dừng ≤ 100 ms; mất nét (F < 0,3·F_min > 60 ms) → thử phục hồi 1 lần rồi PAUSED; mất dữ liệu cảm biến → PAUSED.

| Loại bút | F_nominal | Dải [F_min, F_max] | F_hard | v_max |
|---|---|---|---|---|
| Bút bi 0,7 mm | 1,0 N | 0,6 – 1,6 N | 4,0 N | 40 mm/s |
| Bút gel 0,5 mm | 0,6 N | 0,3 – 1,0 N | 3,0 N | 30 mm/s |
| Bút kim 0,3 mm | 0,4 N | 0,2 – 0,8 N | 2,0 N | 25 mm/s |
| Bút máy | 0,3 N | 0,15 – 0,6 N | 2,0 N | 20 mm/s |
| Bút lông | 0,8 N | 0,2 – 2,0 N | 3,5 N | 15 mm/s |

Giá trị khởi điểm; giá trị chính thức xác định bằng thí nghiệm (ma trận bút × giấy × tốc độ × lực, scan 600 dpi đo độ đều nét).

## 4. Non-Functional Requirements

### 4.1 External Interfaces
- UI: Website React (Chrome/Edge mới nhất, responsive cho Customer); Flutter Desktop (Windows) cho Technical Staff.
- Software: REST/JSON giữa web và Backend; HTTPS + WebSocket giữa Flutter App và Backend; WebSocket cục bộ giữa App và Robot Agent.
- Hardware: Robot Agent ↔ FR3 qua SDK Fairino (TCP/IP); ESP32 ↔ Robot Agent qua USB serial; camera USB tại trạm.
- Third-party: VNPay/Momo (thanh toán, hoàn tiền, webhook), GHN/GHTK (phí ship, vận đơn, webhook), SMTP email.

### 4.2 Quality Attributes

| ID | Thuộc tính | Yêu cầu |
|---|---|---|
| NFR-01 | Performance | Giá ước tính ≤ 1 s; phác thảo OT-3 1 trang A4 ≤ 5 s; phục dựng ảnh A5 ≤ 15 s; gói job ≤ 10 s. |
| NFR-02 | Accuracy (AI) | IoU nét phục dựng so với ảnh gốc ≥ 80% trên bộ ảnh kiểm thử. |
| NFR-03 | Safety | Robot dừng ≤ 1 s sau E-Stop; nhấc bút ≤ 100 ms khi quá lực. |
| NFR-04 | Precision | Sai lệch vị trí nét trên giấy ≤ 0,5 mm so với phác thảo (chồng ảnh scan). |
| NFR-05 | Force quality | Lực trong dải [F_min, F_max] ≥ 95% thời gian bút chạm giấy; RMS sai số lực ≤ 0,2 N (bút bi). |
| NFR-06 | Reliability | ≥ 90% job demo hoàn tất không lỗi hệ thống; webhook xử lý idempotent. |
| NFR-07 | Usability | Khách mới tạo và gửi đơn ≤ 5 phút không cần hướng dẫn; 2 trạng thái hiển thị bằng tiếng Việt dễ hiểu. |
| NFR-08 | Security | Phân quyền 5 vai trò; JWT; mật khẩu băm; HTTPS; khách chỉ thấy đơn của mình. |
| NFR-09 | Payment security | Không lưu thông tin thẻ; xác thực chữ ký webhook; mọi giao dịch qua cổng. |
| NFR-10 | Maintainability | Tách lớp Website / Backend / Pricing / AI / Robot Agent; thay robot chỉ cần adapter mới cho Robot Agent; thêm hãng vận chuyển chỉ cần Carrier Adapter mới. |
| NFR-11 | Auditability | Ghi StatusHistory và AuditLog cho trạng thái, giá, lịch, thao tác quản trị. |
| NFR-12 | Privacy | Ảnh và bộ nét của khách chỉ dùng cho đơn, xóa sau 90 ngày trừ khi khách đồng ý lưu (BR-23). |

## 5. Requirement Appendix

### 5.1 Business Rules

| ID | Rule |
|---|---|
| BR-01 | Mỗi tài khoản thuộc đúng 1 vai trò. Customer tự đăng ký; tài khoản nội bộ (Staff, Technical Staff, Manager) do Admin tạo; tài khoản Admin do hệ thống khởi tạo. |
| BR-02 | Customer chỉ xem và thao tác trên đơn của chính mình. |
| BR-03 | Mỗi đơn thuộc đúng 1 loại đơn (OT-1, OT-2 hoặc OT-3); không trộn loại trong một đơn. |
| BR-04 | Ảnh upload: jpg/png/pdf, ≤ 20 MB, tối đa 10 trang/ảnh mỗi đơn; cảnh báo khi ảnh mờ hoặc thiếu sáng. Staff được từ chối đơn có tài liệu quá cũ, hư hỏng, thiếu nội dung, bắt buộc ghi lý do. |
| BR-05 | Thứ tự chọn vật tư: giấy (loại + khổ) → bút → màu mực. Bút lọc theo bảng tương thích giấy–bút; màu mực chỉ gồm màu có của bút đã chọn. |
| BR-06 | Ví dụ tương thích mặc định: giấy ≤ 80 gsm không dùng bút lông/bút dạ đậm; giấy bóng/couché không dùng bút máy; thiệp ≥ 250 gsm chỉ dùng bút gel, bút bi, bút kim. Manager cấu hình được bảng này. |
| BR-07 | Mỗi đơn dùng 1 loại giấy, 1 loại bút, 1 màu mực; số lượng bản ≥ 1; khổ tối đa A4. |
| BR-08 | Giá ước tính chỉ để tham khảo. Báo giá chính thức do Staff lập, hiệu lực 7 ngày, lưu snapshot bảng giá tại thời điểm lập. |
| BR-09 | Staff được điều chỉnh tổng giá trong ±15% so với giá Pricing Engine tính, bắt buộc ghi lý do; vượt ngưỡng cần Manager duyệt. |
| BR-10 | Khách chọn mức cọc D ≥ p_min × G (p_min mặc định 50%, Manager cấu hình). Đơn chỉ vào sản xuất khi cọc thành công. |
| BR-11 | Phần còn lại (G − D) và phí giao hàng phải được thanh toán **trước khi giao hoặc trước khi nhận tại xưởng**. Không hỗ trợ COD. |
| BR-12 | Phí giao hàng tách riêng khỏi giá sản phẩm, lấy từ API hãng vận chuyển theo địa chỉ và kích thước gói; mọi báo giá ghi rõ "Giá chưa bao gồm phí giao hàng". Nhận tại xưởng: phí ship = 0. |
| BR-13 | Customer nghiệm thu qua ảnh sản phẩm thật (≥ 2 ảnh). **Mỗi đơn được viết lại miễn phí tối đa 1 lần nếu lỗi do xưởng hoặc sai so với phác thảo đã duyệt; lần sau tính phí theo báo giá mới.** |
| BR-14 | **Hủy đơn: trước khi đơn được xếp lịch (Production = SCHEDULED) hoàn 100% cọc; sau khi đã xếp lịch nhưng chưa viết hoàn 100% cọc trừ phí setup; khi đã bắt đầu viết không được hủy, trừ trường hợp BR-16.** |
| BR-15 | ETA (thời gian giao dự kiến tối đa) = ngày cọc thành công + thời gian chờ sản xuất theo lịch robot + thời gian giao hàng ước tính của hãng. ETA hiển thị cho khách từ lúc báo giá. |
| BR-16 | ETA được phép dời (robot hỏng, thiếu vật tư, viết lại) nhưng phải có lý do và thông báo cho khách. **Nếu tổng thời gian dời > 7 ngày, khách được hủy đơn và hoàn 100% số đã thanh toán.** |
| BR-17 | Đồng bộ 2 trạng thái: sản xuất chỉ bắt đầu khi đơn ở CONFIRMED; đơn chỉ chuyển AWAITING_ACCEPTANCE khi sản xuất ở PHOTO_UPLOADED; đơn chỉ được giao khi sản xuất ở FINISHED và đã thanh toán đủ. |
| BR-18 | Mỗi robot chạy tối đa 1 job tại một thời điểm; chỉ robot AVAILABLE và có loại phù hợp với vật tư của đơn mới được xếp lịch. |
| BR-19 | Technical Staff chỉ thao tác trên job được gán cho mình; bắt buộc hiệu chuẩn mặt giấy và lực mỗi lần thay giấy/bút trước khi chạy. |
| BR-20 | Lực tì bút phải nằm trong dải [F_min, F_max] của loại bút; vượt F_hard thì robot nhấc bút và tạm dừng ngay. |
| BR-21 | Trước khi chuyển PHOTO_UPLOADED, Technical Staff phải tải ≥ 2 ảnh sản phẩm (toàn cảnh và cận nét) và đánh dấu QC đạt. |
| BR-22 | Staff chỉ được gửi báo giá sau khi đã tiếp nhận đơn và có phác thảo được lưu. |
| BR-23 | Không nhận viết chữ ký, giấy tờ pháp lý, văn bản có dấu hiệu giả mạo. Ảnh của khách chỉ dùng cho đơn hàng và bị xóa sau 90 ngày kể từ khi hoàn tất, trừ khi khách đồng ý lưu bộ nét. |
| BR-24 | Mọi thanh toán đi qua cổng thanh toán; mọi thay đổi trạng thái, giá, lịch sản xuất được ghi StatusHistory/AuditLog (ai, khi nào, lý do). |
| BR-25 | *(không có trong PDF này; code/SQL tham chiếu: chính sách riêng tư – khách phải chấp nhận trước khi xem phác thảo/báo giá, trạng thái AWAITING_PRIVACY. Nguyên văn chưa có.)* |

### 5.2 Common Requirements
Ngôn ngữ giao diện: tiếng Việt. Định dạng ngày dd/MM/yyyy; múi giờ Asia/Ho_Chi_Minh (UTC+7). Tiền tệ VNĐ, làm tròn đến 100đ. Đơn vị: mm (khổ giấy, sai lệch nét), N (lực), gsm (độ dày giấy).

Tham số hệ thống mặc định (Admin/Manager cấu hình): p_min = 50%; hiệu lực báo giá 7 ngày; ngưỡng điều chỉnh giá ±15%; **tự nghiệm thu sau 7 ngày; nhắc nghiệm thu sau 3 ngày**; dời ETA lũy kế > 7 ngày cho phép hủy hoàn 100%; lưu ảnh 90 ngày; khổ tối đa A4.

### 5.3 Application Messages List

| # | Code | Loại | Ngữ cảnh | Nội dung |
|---|---|---|---|---|
| 1 | MSG01 | Inline | Thiếu trường bắt buộc | Vui lòng nhập đầy đủ thông tin bắt buộc. |
| 2 | MSG02 | Toast | Gửi đơn thành công | Đơn của bạn đã được gửi. Xưởng sẽ phản hồi sớm. |
| 3 | MSG03 | Inline | Loại đơn tạm ngừng | Loại dịch vụ này đang tạm ngừng nhận đơn. |
| 4 | MSG04 | Inline | Ảnh chất lượng thấp | Ảnh có thể quá mờ hoặc thiếu sáng. Kết quả phục dựng có thể không như mong muốn. |
| 5 | MSG05 | Inline | Bút không hợp với giấy mới | Bút đã chọn không dùng được với loại giấy này. Vui lòng chọn lại bút. |
| 6 | MSG06 | Toast | Thanh toán thất bại | Thanh toán chưa thành công. Vui lòng thử lại. |
| 7 | MSG07 | Email + in-app | Đơn bị từ chối | Rất tiếc, xưởng chưa thể nhận đơn {mã}: {lý do}. |
| 8 | MSG08 | Email + in-app | Báo giá hết hạn | Báo giá cho đơn {mã} đã hết hạn và đơn được hủy. |
| 9 | MSG09 | Toast | AI lỗi/timeout | Không tạo được phác thảo. Vui lòng thử lại. |
| 10 | MSG10 | Email + in-app | Có báo giá | Đơn {mã} đã có phác thảo và báo giá {G} (chưa gồm phí giao hàng). |
| 11 | MSG11 | Email + in-app | Dời ETA | Thời gian giao dự kiến của đơn {mã} được dời sang {ngày}. Lý do: {lý do}. |
| 12 | MSG12 | Email + in-app | Sản phẩm hoàn thành | Sản phẩm của đơn {mã} đã hoàn thành. Vui lòng xem ảnh và nghiệm thu. |
| 13 | MSG13 | App alert | Quá lực | Lực bút vượt ngưỡng. Robot đã nhấc bút và tạm dừng. |
| 14 | MSG14 | App alert | Hash job sai | Gói job không khớp phác thảo đã duyệt. Không thể chạy. |
| 15 | MSG15 | Email + in-app | Đang giao | Đơn {mã} đang được giao. Mã vận đơn: {mã vận đơn}. |

### 5.4 Bảng trạng thái 2.5.1 / 2.5.2 / 2.5.3
PDF này **không có** các bảng trạng thái 2.5.x (chỉ tham chiếu). Nguồn thực tế dùng trong code: trigger `fn_order_state_guard` (`migrations/versions/0002_fixes.py`) và các enum `order_status`, `production_status`, `job_status` trong baseline SQL.
